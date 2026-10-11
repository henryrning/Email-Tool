import datetime as dt
import json
import time
from urllib.parse import quote

import msal
import requests

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.ReadWrite", "User.Read"]


class OutlookProvider:
    name = "outlook"

    def __init__(self, config_dir):
        cfg = json.loads((config_dir / "outlook_config.json").read_text())
        self.cache_path = config_dir / "outlook_token_cache.json"
        self.cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            self.cache.deserialize(self.cache_path.read_text())
        self.app = msal.PublicClientApplication(
            cfg["client_id"],
            authority=cfg.get("authority", "https://login.microsoftonline.com/common"),
            token_cache=self.cache,
        )
        self.http = requests.Session()
        self._account = None
        self._received = {}  # id -> received time, filled while listing

    def _token(self):
        accounts = self.app.get_accounts()
        result = self.app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        if not result:
            flow = self.app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise SystemExit(f"Could not start sign-in: {flow}")
            print(flow["message"])  # "go to https://microsoft.com/devicelogin and enter code ..."
            result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise SystemExit(f"Sign-in failed: {result.get('error_description', result)}")
        if self.cache.has_state_changed:
            self.cache_path.write_text(self.cache.serialize())
        return result["access_token"]

    def _call(self, method, url, **kwargs):
        # ImmutableId keeps message ids stable even if the message is moved between folders.
        headers = {"Authorization": f"Bearer {self._token()}", "Prefer": 'IdType="ImmutableId"'}
        for attempt in range(8):
            r = self.http.request(method, url, headers=headers, timeout=120, **kwargs)
            if r.status_code in (429, 503, 504):
                time.sleep(int(r.headers.get("Retry-After", 2 ** attempt)))
                continue
            r.raise_for_status()
            return r
        r.raise_for_status()

    def account(self):
        if self._account is None:
            me = self._call("GET", f"{GRAPH}/me", params={"$select": "mail,userPrincipalName"}).json()
            self._account = me.get("mail") or me["userPrincipalName"]
        return self._account

    def _folder_id(self, well_known):
        return self._call("GET", f"{GRAPH}/me/mailFolders/{well_known}", params={"$select": "id"}).json()["id"]

    def list_before(self, cutoff):
        skip = {self._folder_id("deleteditems"), self._folder_id("junkemail")}
        stamp = cutoff.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"{GRAPH}/me/messages"
        params = {
            "$filter": f"receivedDateTime lt {stamp}",
            "$select": "id,parentFolderId,receivedDateTime",
            "$top": "500",
        }
        while url:
            data = self._call("GET", url, params=params).json()
            params = None  # nextLink already carries the query
            for m in data["value"]:
                if m["parentFolderId"] in skip:
                    continue
                self._received[m["id"]] = m["receivedDateTime"]
                yield m["id"]
            url = data.get("@odata.nextLink")

    def fetch_raw(self, mid):
        url = f"{GRAPH}/me/messages/{quote(mid, safe='')}"
        received = self._received.get(mid)
        if received is None:
            received = self._call("GET", url, params={"$select": "receivedDateTime"}).json()["receivedDateTime"]
        raw = self._call("GET", f"{url}/$value").content
        return raw, dt.datetime.fromisoformat(received.replace("Z", "+00:00"))

    def trash(self, mid):
        self._call("POST", f"{GRAPH}/me/messages/{quote(mid, safe='')}/move",
                   json={"destinationId": "deleteditems"})
