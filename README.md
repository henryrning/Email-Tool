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

## Test

```bash
python3 -m unittest tests/test_pipeline.py
```
