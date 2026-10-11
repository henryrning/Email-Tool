#!/usr/bin/env python3
"""Back up, verify, then trash every email received before a cutoff date.

Works with Gmail (Gmail API) and Outlook / Microsoft 365 (Microsoft Graph).
Nothing is ever deleted unless a verified backup of that exact message exists.

    python mailclean.py backup --provider gmail   --before 2021-01-01
    python mailclean.py verify --provider gmail   --before 2021-01-01
    python mailclean.py delete --provider gmail   --before 2021-01-01            # dry run
    python mailclean.py delete --provider gmail   --before 2021-01-01 --confirm  # moves to Trash
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def get_provider(name, config_dir):
    if name == "gmail":
        from providers.gmail import GmailProvider
        return GmailProvider(config_dir)
    if name == "outlook":
        from providers.outlook import OutlookProvider
        return OutlookProvider(config_dir)
    raise SystemExit(f"Unknown provider: {name}")


def parse_cutoff(text):
    """Midnight at the start of the given date, in this computer's local time zone."""
    d = dt.date.fromisoformat(text)
    return dt.datetime(d.year, d.month, d.day).astimezone()


def read_jsonl(path):
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path, row):
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Job:
    """One mailbox + one cutoff date = one folder of backups and logs."""

    def __init__(self, provider, cutoff, out_dir):
        self.provider = provider
        self.cutoff = cutoff
        account = re.sub(r"[^A-Za-z0-9@._-]", "_", provider.account())
        self.dir = Path(out_dir) / f"{provider.name}-{account}-before-{cutoff.date().isoformat()}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = self.dir / "manifest.jsonl"
        self.verified = self.dir / "verified.json"
        self.deleted = self.dir / "deleted.jsonl"
        self._check_run_info()

    def _check_run_info(self):
        info_path = self.dir / "run.json"
        info = {"provider": self.provider.name, "account": self.provider.account(),
                "cutoff": self.cutoff.isoformat()}
        if info_path.exists():
            old = json.loads(info_path.read_text())
            if old != info:
                raise SystemExit(f"{info_path} was made for a different job: {old}")
        else:
            info_path.write_text(json.dumps(info, indent=2))

    # --- step 1 -----------------------------------------------------------
    def backup(self, limit=None):
        done = {row["id"] for row in read_jsonl(self.manifest)}
        print(f"Listing messages received before {self.cutoff.isoformat()} ...")
        ids = list(self.provider.list_before(self.cutoff))
        todo = [i for i in ids if i not in done]
        print(f"Found {len(ids)} on server; {len(ids) - len(todo)} already backed up; {len(todo)} to go.")
        if limit:
            todo = todo[:limit]

        for n, mid in enumerate(todo, 1):
            raw, received = self.provider.fetch_raw(mid)
            if received >= self.cutoff:
                print(f"  skip {mid}: received {received.isoformat()} is not before cutoff")
                continue
            key = sha256(mid.encode())[:24]
            rel = Path("messages") / f"{received:%Y}" / f"{received:%m}" / f"{key}.eml"
            path = self.dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            headers = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
            append_jsonl(self.manifest, {
                "id": mid,
                "received": received.isoformat(),
                "from": str(headers.get("From", "")),
                "subject": str(headers.get("Subject", "")),
                "path": str(rel),
                "bytes": len(raw),
                "sha256": sha256(raw),
            })
            if n % 100 == 0 or n == len(todo):
                print(f"  backed up {n}/{len(todo)}")
        print(f"Backup folder: {self.dir}")

    # --- step 2 -----------------------------------------------------------
    def verify(self):
        rows = read_jsonl(self.manifest)
        good, bad = [], []
        for row in rows:
            path = self.dir / row["path"]
            if not path.exists():
                bad.append((row["id"], "file missing"))
            elif sha256(path.read_bytes()) != row["sha256"]:
                bad.append((row["id"], "file changed or corrupted"))
            else:
                good.append(row["id"])

        server_ids = set(self.provider.list_before(self.cutoff))
        not_backed_up = server_ids - {row["id"] for row in rows}

        self.verified.write_text(json.dumps({
            "verified_at": dt.datetime.now().astimezone().isoformat(),
            "count": len(good),
            "ids": good,
        }))
        print(f"Verified backups: {len(good)}")
        for mid, why in bad[:20]:
            print(f"  PROBLEM {mid}: {why}")
        if bad:
            print(f"Problems: {len(bad)} (these will NOT be deleted)")
        if not_backed_up:
            print(f"Still on server without a backup: {len(not_backed_up)} -> run `backup` again")
        if not bad and not not_backed_up:
            print("Backup is complete: every message before the cutoff has a verified copy.")

    # --- step 3 -----------------------------------------------------------
    def delete(self, confirm=False, limit=None, ask=input):
        if not self.verified.exists():
            raise SystemExit("Run `verify` first. Nothing is deleted without a verified backup.")
        verified = json.loads(self.verified.read_text())["ids"]
        already = {row["id"] for row in read_jsonl(self.deleted)}
        todo = [i for i in verified if i not in already]
        if limit:
            todo = todo[:limit]

        print(f"Account: {self.provider.account()} ({self.provider.name})")
        print(f"Messages with a verified backup, not yet trashed: {len(todo)}")
        if not confirm:
            print("Dry run. Add --confirm to move them to Trash / Deleted Items.")
            return
        if not todo:
            return
        answer = ask(f"Type TRASH {len(todo)} to move these messages to Trash: ")
        if answer.strip() != f"TRASH {len(todo)}":
            print("Cancelled.")
            return

        failed = 0
        for n, mid in enumerate(todo, 1):
            try:
                self.provider.trash(mid)
            except Exception as e:  # message moved or already gone; keep going
                failed += 1
                print(f"  could not trash {mid}: {e}")
                continue
            append_jsonl(self.deleted, {"id": mid, "at": dt.datetime.now().astimezone().isoformat()})
            if n % 100 == 0 or n == len(todo):
                print(f"  trashed {n}/{len(todo)}")
        print(f"Done. Failed: {failed}. Messages stay recoverable in Trash / Deleted Items "
              f"until it is emptied (Gmail empties it after 30 days).")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["backup", "verify", "delete"])
    p.add_argument("--provider", required=True, choices=["gmail", "outlook"])
    p.add_argument("--before", required=True, help="cutoff date, e.g. 2021-01-01 (local midnight)")
    p.add_argument("--out", default=str(ROOT / "backups"), help="where backups are written")
    p.add_argument("--config", default=str(ROOT / "config"), help="folder with credentials/tokens")
    p.add_argument("--limit", type=int, help="only process this many messages (for a test run)")
    p.add_argument("--confirm", action="store_true", help="actually trash messages (delete step)")
    args = p.parse_args(argv)

    job = Job(get_provider(args.provider, Path(args.config)), parse_cutoff(args.before), args.out)
    if args.step == "backup":
        job.backup(limit=args.limit)
    elif args.step == "verify":
        job.verify()
    else:
        job.delete(confirm=args.confirm, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
