# mailclean

Backs up every email received before a date, verifies the backup, then moves those emails to Trash.
Works on **Gmail** and **Outlook / Microsoft 365** with the same commands.

Safety rules built in:
- Works **message by message**, so a 2022 reply inside a thread that started in 2020 is kept.
- Nothing is trashed unless its `.eml` copy exists and its checksum matches (`verify` step).
- `delete` is a dry run unless you pass `--confirm` **and** type `TRASH <count>`.
- Messages go to Trash / Deleted Items (recoverable), never permanently deleted.
  The Gmail permission requested cannot permanently delete at all.
- Trash and Spam/Junk folders are skipped.
- Every step can be stopped and re-run; it continues where it left off.

## Install

```bash
python3 -m pip install -r requirements.txt
```

## One-time setup

### Gmail
1. Go to <https://console.cloud.google.com/>, create a project, and enable the **Gmail API**.
2. Open **Google Auth Platform → Audience**, choose External, and add the Gmail address as a **test user**.
3. Open **Clients → Create client → Desktop app**. Download the JSON file and save it as
   `config/gmail_credentials.json`.
4. The first run opens a browser to sign in. After that, the token is saved in `config/gmail_token.json`.

### Outlook / Microsoft 365
**University of Illinois (@illinois.edu) accounts:** no setup needed. `config/outlook_config.json` in this
repository already points to a registered app. Skip to step 5 and sign in with your own account.

Other accounts need their own app registration:
1. Go to <https://entra.microsoft.com/> → **App registrations → New registration**.
   - Personal Outlook.com account: choose "personal Microsoft accounts" (or "any org + personal").
   - Work/university account: choose that organization. **The organization's IT may need to approve
     the app** ("admin consent") before it can read mail.
2. Under **Authentication**, turn on **Allow public client flows**.
3. Under **API permissions**, add Microsoft Graph delegated permissions `Mail.ReadWrite` and `User.Read`.
4. Create `config/outlook_config.json`:
   ```json
   {"client_id": "<Application (client) ID>",
    "authority": "https://login.microsoftonline.com/common"}
   ```
   Use `/consumers` for a personal account, or `/<tenant-id>` for one organization.
5. The first run prints a code to enter at <https://microsoft.com/devicelogin>.

## Use

Try a small test run first (`--limit 20`), open a few `.eml` files to check them, then do the full run.

```bash
python3 mailclean.py backup --provider gmail --before 2021-01-01
python3 mailclean.py verify --provider gmail --before 2021-01-01
python3 mailclean.py delete --provider gmail --before 2021-01-01            # dry run: shows the count
python3 mailclean.py delete --provider gmail --before 2021-01-01 --confirm  # moves to Trash
```

For Outlook, use the same commands with `--provider outlook`.

Backups go to `backups/<provider>-<account>-before-<date>/`:
- `messages/YYYY/MM/*.eml` — full original emails with attachments. They open in Apple Mail, Outlook
  or Thunderbird.
- `manifest.jsonl` — one line per email: date, sender, subject, checksum.
- `verified.json` and `deleted.jsonl` — logs of what was verified and what was trashed.

**Keep a second copy of the `backups/` folder (external drive or cloud) before running `delete`.**

## Quick test on a University of Illinois Outlook account

A safe trial on any @illinois.edu mailbox, on any computer. It backs up 3 emails, then moves only
those 3 to Deleted Items, where they can be restored.

**1. Install** (needs Python 3.9 or newer):

```bash
git clone https://github.com/henryrning/Email-Tool.git
cd Email-Tool
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Windows, use `.venv\Scripts\python` wherever these steps say `.venv/bin/python`.

**2. Pick a cutoff date.** In Outlook on the web, sort the mailbox by date, oldest first, and note the
year of the oldest email. Use January 1 of the following year as the cutoff. The oldest emails are
usually notices nobody needs any more. The commands below use `2024-01-01`. Replace it with your date.

**3. Back up 3 emails and verify the copies.** This reads mail only. Nothing is deleted.

```bash
.venv/bin/python mailclean.py backup --provider outlook --before 2024-01-01 --limit 3
.venv/bin/python mailclean.py verify --provider outlook --before 2024-01-01
```

The first run prints a code. Open <https://login.microsoft.com/device>, enter the code, sign in with
**your own** @illinois.edu account, and accept the "Email-Tool" permission request.
If it says `Found 0`, there is no mail before that date. Move the cutoff one year later.

**4. Check the backup.** Open `backups/outlook-<your address>-before-2024-01-01/`:
- `manifest.jsonl` lists the 3 emails (date, sender, subject). Make sure none of them matter.
- Double-click a file in `messages/` to open it in Mail or Outlook.

**5. Move those 3 emails to Deleted Items.**

```bash
.venv/bin/python mailclean.py delete --provider outlook --before 2024-01-01            # dry run: should say 3
.venv/bin/python mailclean.py delete --provider outlook --before 2024-01-01 --confirm  # type: TRASH 3
```

Only emails with a verified backup can be moved, so only these 3 are affected. Other email before
the cutoff stays where it is.

**6. Restore and clean up.**
- To get the emails back: in Outlook, open **Deleted Items**, right-click each email, and choose
  **Move → Inbox**. Deleted Items may be emptied automatically after about 30 days.
- To remove your sign-in from this computer, delete `config/outlook_token_cache.json`. Also delete
  `backups/` if you don't want to keep the copies.
- To revoke the app's access to your mailbox, go to <https://myapps.microsoft.com>.

## Test

```bash
python3 -m unittest tests/test_pipeline.py
```
