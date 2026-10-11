import base64
import datetime as dt

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.modify can read and move to Trash, but cannot permanently delete.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailProvider:
    name = "gmail"

    def __init__(self, config_dir):
        token_path = config_dir / "gmail_token.json"
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds and not creds.valid:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None  # refresh token expired or revoked: sign in again
            if creds:
                token_path.write_text(creds.to_json())
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config_dir / "gmail_credentials.json"), SCOPES)
            creds = flow.run_local_server(port=0)
            config_dir.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())
        self.svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self._account = None

    def account(self):
        if self._account is None:
            profile = self.svc.users().getProfile(userId="me").execute(num_retries=5)
            self._account = profile["emailAddress"]
        return self._account

    def list_before(self, cutoff):
        # Epoch seconds avoid Gmail's own time-zone interpretation of dates.
        query = f"before:{int(cutoff.timestamp())}"
        token = None
        while True:
            resp = self.svc.users().messages().list(
                userId="me", q=query, maxResults=500, pageToken=token,
            ).execute(num_retries=5)
            for m in resp.get("messages", []):
                yield m["id"]
            token = resp.get("nextPageToken")
            if not token:
                return

    def fetch_raw(self, mid):
        m = self.svc.users().messages().get(userId="me", id=mid, format="raw").execute(num_retries=5)
        received = dt.datetime.fromtimestamp(int(m["internalDate"]) / 1000, dt.timezone.utc)
        return base64.urlsafe_b64decode(m["raw"]), received

    def trash(self, mid):
        self.svc.users().messages().trash(userId="me", id=mid).execute(num_retries=5)

    # --- used by triage.py ------------------------------------------------
    def search_threads(self, query, limit):
        ids, token = [], None
        while len(ids) < limit:
            resp = self.svc.users().threads().list(
                userId="me", q=query, maxResults=min(500, limit - len(ids)), pageToken=token,
            ).execute(num_retries=5)
            ids += [t["id"] for t in resp.get("threads", [])]
            token = resp.get("nextPageToken")
            if not token:
                break
        return ids

    def get_thread(self, thread_id):
        return self.svc.users().threads().get(userId="me", id=thread_id, format="full").execute(num_retries=5)

    def label_id(self, name):
        """Id of the label with this name, creating it if needed."""
        if not hasattr(self, "_labels"):
            resp = self.svc.users().labels().list(userId="me").execute(num_retries=5)
            self._labels = {lab["name"]: lab["id"] for lab in resp.get("labels", [])}
        if name not in self._labels:
            lab = self.svc.users().labels().create(userId="me", body={
                "name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show",
            }).execute(num_retries=5)
            self._labels[name] = lab["id"]
        return self._labels[name]

    def add_labels(self, mid, label_ids):
        self.svc.users().messages().modify(
            userId="me", id=mid, body={"addLabelIds": label_ids},
        ).execute(num_retries=5)
