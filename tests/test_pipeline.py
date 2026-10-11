"""End-to-end test of backup -> verify -> delete against a fake in-memory mailbox."""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mailclean import Job, parse_cutoff  # noqa: E402

UTC = dt.timezone.utc


class FakeProvider:
    name = "fake"

    def __init__(self, messages):
        self.messages = dict(messages)  # id -> received datetime
        self.trashed = []

    def account(self):
        return "dr.guan@example.com"

    def list_before(self, cutoff):
        return [m for m, t in self.messages.items() if t < cutoff and m not in self.trashed]

    def fetch_raw(self, mid):
        raw = f"From: a@example.com\r\nSubject: msg {mid}\r\n\r\nbody {mid}\r\n".encode()
        return raw, self.messages[mid]

    def trash(self, mid):
        self.trashed.append(mid)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cutoff = parse_cutoff("2021-01-01")
        self.provider = FakeProvider({
            "old1": dt.datetime(2019, 5, 1, tzinfo=UTC),
            "old2": dt.datetime(2020, 12, 30, tzinfo=UTC),
            "new1": dt.datetime(2022, 3, 1, tzinfo=UTC),  # e.g. a 2022 reply in a 2020 thread
        })
        self.job = Job(self.provider, self.cutoff, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_run_only_trashes_old_backed_up_messages(self):
        self.job.backup()
        self.job.verify()
        self.job.delete(confirm=True, ask=lambda _: "TRASH 2")
        self.assertEqual(sorted(self.provider.trashed), ["old1", "old2"])
        self.assertEqual(len(list((Path(self.job.dir) / "messages").rglob("*.eml"))), 2)

    def test_delete_refused_without_verify(self):
        self.job.backup()
        with self.assertRaises(SystemExit):
            self.job.delete(confirm=True, ask=lambda _: "TRASH 2")
        self.assertEqual(self.provider.trashed, [])

    def test_dry_run_and_wrong_confirmation_do_nothing(self):
        self.job.backup()
        self.job.verify()
        self.job.delete(confirm=False)
        self.job.delete(confirm=True, ask=lambda _: "yes")
        self.assertEqual(self.provider.trashed, [])

    def test_corrupted_backup_is_not_deleted(self):
        self.job.backup()
        eml = next((Path(self.job.dir) / "messages").rglob("*.eml"))
        eml.write_bytes(b"garbage")
        self.job.verify()
        self.job.delete(confirm=True, ask=lambda _: "TRASH 1")
        self.assertEqual(len(self.provider.trashed), 1)

    def test_backup_resumes_without_duplicates(self):
        self.job.backup(limit=1)
        self.job.backup()
        lines = (Path(self.job.dir) / "manifest.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
