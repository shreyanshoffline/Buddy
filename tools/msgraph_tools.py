"""
tools/msgraph_tools.py

If device codes keep "expiring" in seconds, it is almost never actual
expiry (Microsoft gives you ~15 minutes). In order of likelihood:

1. You're looking at a code from an earlier run. Every time this script
   runs, it requests a NEW code — an old one in your scrollback is dead
   the instant a new one is issued. Run it exactly once, and use only
   the code from that run's output, immediately.
2. The Azure app's "Supported account types" got left on "Single
   tenant" instead of "Personal Microsoft accounts only" — check the
   Authentication > Supported accounts tab in the Azure Portal. This
   code uses the /consumers authority, which requires that setting.
3. BUDDY_MS_CLIENT_ID isn't actually set, so every device code is
   being requested against an empty/invalid client. This file now
   fails loudly on that instead of silently trying anyway.
4. System clock drift. Check Date & Time is set to "set automatically."

Requires: pip install --break-system-packages msal requests
"""

import os
import json
import time
import requests
from msal import PublicClientApplication, SerializableTokenCache

CLIENT_ID = os.environ.get("BUDDY_MS_CLIENT_ID", "")
AUTHORITY = "https://login.microsoftonline.com/consumers"  # personal MS accounts
SCOPES = ["Mail.Read", "Mail.Send", "Calendars.ReadWrite", "Files.ReadWrite", "Notes.ReadWrite", "Chat.ReadWrite"]
TOKEN_CACHE_PATH = os.path.expanduser("~/Buddy/ms_token_cache.json")  # next to credentials.json/token.json
CLIENT_ID_PATH = os.path.expanduser("~/Buddy/ms_client_id.txt")
SETUP_HELP = (
    "Microsoft is not configured. Set BUDDY_MS_CLIENT_ID or enter the Azure "
    "Application (client) ID in Plugins > Microsoft."
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def has_client_id() -> bool:
    return bool(_client_id())


def _client_id() -> str:
    if CLIENT_ID.strip():
        return CLIENT_ID.strip()
    try:
        with open(CLIENT_ID_PATH, "r") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_client_id(client_id: str):
    client_id = client_id.strip()
    if not client_id:
        raise ValueError("Microsoft client ID cannot be empty.")
    os.makedirs(os.path.dirname(CLIENT_ID_PATH), exist_ok=True)
    with open(CLIENT_ID_PATH, "w") as f:
        f.write(client_id + "\n")
    try:
        os.chmod(CLIENT_ID_PATH, 0o600)
    except OSError:
        pass


def _get_app():
    client_id = _client_id()
    if not client_id:
        raise RuntimeError(
            "BUDDY_MS_CLIENT_ID is not set. Set it to the Application (client) ID from your "
            "Azure app registration's Overview page before calling anything in this file — "
            "export BUDDY_MS_CLIENT_ID=<uuid>, or hardcode it above CLIENT_ID for local testing."
        )
    cache = SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_PATH):
        cache.deserialize(open(TOKEN_CACHE_PATH, "r").read())
    app = PublicClientApplication(client_id, authority=AUTHORITY, token_cache=cache)
    return app, cache


def _save_cache(cache):
    if cache.has_state_changed:
        os.makedirs(os.path.dirname(TOKEN_CACHE_PATH), exist_ok=True)
        with open(TOKEN_CACHE_PATH, "w") as f:
            f.write(cache.serialize())


def _get_token() -> str:
    app, cache = _get_app()
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(
                f"Microsoft rejected the device-flow request before issuing a code — this is "
                f"usually a bad CLIENT_ID or an app registration set to the wrong account type. "
                f"Raw response: {flow}"
            )
        expires_in = flow.get("expires_in", 900)
        print(f"\n>>> Go to {flow['verification_uri']} and enter code: {flow['user_code']}")
        print(f">>> This code is valid for {expires_in // 60} minutes — do it now, don't reuse an old code.\n")
        started = time.time()
        result = app.acquire_token_by_device_flow(flow)
        elapsed = time.time() - started
        if "access_token" not in result:
            raise RuntimeError(
                f"Microsoft login failed after {elapsed:.0f}s "
                f"({result.get('error')}): {result.get('error_description')}"
            )
    _save_cache(cache)
    return result["access_token"]


def check_microsoft_connection() -> str:
    try:
        _get_token()
        return "OK: connected"
    except Exception as e:
        return f"NOT_CONNECTED: {e}"


def _headers():
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


def _get(path, **params):
    r = requests.get(f"{GRAPH_BASE}{path}", headers=_headers(), params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(path, body):
    r = requests.post(f"{GRAPH_BASE}{path}", headers=_headers(), data=json.dumps(body), timeout=15)
    r.raise_for_status()
    return r.json() if r.text else {}


# ---------------------------------------------------------------------------
# Outlook Mail
# ---------------------------------------------------------------------------

def outlook_unread(limit: int = 10) -> str:
    data = _get("/me/mailFolders/inbox/messages",
                 **{"$filter": "isRead eq false", "$top": limit, "$select": "subject,from"})
    msgs = data.get("value", [])
    if not msgs:
        return "No unread mail in Outlook."
    return "\n".join(f'{m["subject"]} — {m["from"]["emailAddress"]["address"]}' for m in msgs)


def outlook_create_draft(to: str, subject: str, body: str) -> str:
    payload = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": to}}],
    }
    msg = _post("/me/messages", payload)
    return f'Drafted an Outlook email to {to} — id:{msg.get("id")}'


# ---------------------------------------------------------------------------
# Outlook Calendar
# ---------------------------------------------------------------------------

def outlook_today() -> str:
    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%dT00:00:00")
    tomorrow = datetime.utcnow().strftime("%Y-%m-%dT23:59:59")
    data = _get("/me/calendarView", startDateTime=today, endDateTime=tomorrow, **{"$select": "subject,start,end"})
    events = data.get("value", [])
    if not events:
        return "Nothing on the Outlook calendar today."
    return "\n".join(f'{e["subject"]} — {e["start"]["dateTime"]}' for e in events)


def outlook_create_event(title: str, start_iso: str, end_iso: str, timezone: str = "UTC") -> str:
    payload = {
        "subject": title,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
    }
    event = _post("/me/events", payload)
    return f'Created "{title}" on Outlook Calendar — {event.get("webLink")}'


# ---------------------------------------------------------------------------
# OneDrive
# ---------------------------------------------------------------------------

def onedrive_recent(limit: int = 10) -> str:
    items = _get("/me/drive/recent").get("value", [])[:limit]
    if not items:
        return "No recent OneDrive files."
    return "\n".join(f'{i["name"]} — {i.get("webUrl")}' for i in items)


def onedrive_upload(local_path: str, remote_name: str = None) -> str:
    local_path = os.path.expanduser(local_path)
    if not os.path.exists(local_path):
        return f"ERROR: {local_path} does not exist."
    name = remote_name or os.path.basename(local_path)
    with open(local_path, "rb") as f:
        r = requests.put(
            f"{GRAPH_BASE}/me/drive/root:/{name}:/content",
            headers={"Authorization": f"Bearer {_get_token()}"}, data=f, timeout=30,
        )
    r.raise_for_status()
    return f'Uploaded {local_path} to OneDrive as {name} — {r.json().get("webUrl")}'


# ---------------------------------------------------------------------------
# OneNote
# ---------------------------------------------------------------------------

def onenote_list_sections() -> str:
    sections = _get("/me/onenote/sections").get("value", [])
    return "\n".join(f'{s["displayName"]} — id:{s["id"]}' for s in sections) or "No OneNote sections found."


def onenote_create_page(section_id: str, title: str, html_body: str) -> str:
    html = f"<html><head><title>{title}</title></head><body>{html_body}</body></html>"
    r = requests.post(
        f"{GRAPH_BASE}/me/onenote/sections/{section_id}/pages",
        headers={"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/xhtml+xml"},
        data=html, timeout=15,
    )
    r.raise_for_status()
    return f'Created OneNote page "{title}".'


# ---------------------------------------------------------------------------
# Teams — no real "draft" state in Graph; enforce a confirm step in the GUI
# before calling this, same as Messages.app.
# ---------------------------------------------------------------------------

def teams_list_chats(limit: int = 10) -> str:
    chats = _get("/me/chats", **{"$top": limit}).get("value", [])
    return "\n".join(f'{c.get("topic") or "(direct chat)"} — id:{c["id"]}' for c in chats) or "No Teams chats found."


def teams_send_message(chat_id: str, text: str) -> str:
    msg = _post(f"/me/chats/{chat_id}/messages", {"body": {"content": text}})
    return f'Sent to Teams chat {chat_id} — id:{msg.get("id")}'
