"""
Microsoft ecosystem backend for Buddy (Graph API).
Drop this in as tools/msgraph_tools.py.

Requires: msal requests
    pip install --break-system-packages msal requests

One Azure AD app registration covers Outlook, OneDrive, OneNote, Teams.
See the setup doc for exact steps (app registration, redirect URI, API
permissions, client secret).
"""

import os
import json
import requests
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from msal import PublicClientApplication

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

# A client ID is not a secret, but keeping it in configuration avoids baking
# an environment-specific app registration into the source code.
CLIENT_ID = (os.getenv("BUDDY_MS_CLIENT_ID") or "").strip()
AUTHORITY = "https://login.microsoftonline.com/consumers"  # personal MS accounts; use /organizations for work accounts
SCOPES = ["Mail.Read", "Mail.Send", "Calendars.ReadWrite", "Files.ReadWrite", "Notes.ReadWrite", "Chat.ReadWrite"]
TOKEN_CACHE_PATH = Path(os.path.expanduser("~/.buddy/ms_token_cache.json"))

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_app():
    if not CLIENT_ID:
        raise RuntimeError("Microsoft is not configured. Set BUDDY_MS_CLIENT_ID in .env.")
    from msal import SerializableTokenCache
    cache = SerializableTokenCache()
    if TOKEN_CACHE_PATH.is_file():
        os.chmod(TOKEN_CACHE_PATH, 0o600)
        with TOKEN_CACHE_PATH.open("r", encoding="utf-8") as cache_file:
            cache.deserialize(cache_file.read())
    app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    return app, cache


def _save_cache(cache):
    if cache.has_state_changed:
        TOKEN_CACHE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix="ms_token_cache_",
            suffix=".tmp",
            dir=TOKEN_CACHE_PATH.parent,
            text=True,
        )
        temp_path = Path(temp_name)
        os.chmod(temp_path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as cache_file:
            cache_file.write(cache.serialize())
        os.replace(temp_path, TOKEN_CACHE_PATH)
        os.chmod(TOKEN_CACHE_PATH, 0o600)


def _get_token() -> str:
    app, cache = _get_app()
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Could not start device login: {flow}")
        print(flow["message"])  # surface this to the user / GUI dialog
        result = app.acquire_token_by_device_flow(flow)
    _save_cache(cache)
    if "access_token" not in result:
        raise RuntimeError(f"Microsoft login failed: {result.get('error_description')}")
    return result["access_token"]


def check_microsoft_connection() -> str:
    try:
        _get_token()
        return "OK: Microsoft account connected."
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


def _patch(path, body):
    r = requests.patch(f"{GRAPH_BASE}{path}", headers=_headers(), data=json.dumps(body), timeout=15)
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
    data = _get("/me/calendarView", startDateTime=today, endDateTime=tomorrow,
                **{"$select": "subject,start,end"})
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
    data = _get("/me/drive/recent")
    items = data.get("value", [])[:limit]
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
            headers={"Authorization": f"Bearer {_get_token()}"},
            data=f, timeout=30,
        )
    r.raise_for_status()
    return f'Uploaded {local_path} to OneDrive as {name} — {r.json().get("webUrl")}'


# ---------------------------------------------------------------------------
# OneNote
# ---------------------------------------------------------------------------

def onenote_create_page(notebook_section_id: str, title: str, html_body: str) -> str:
    html = f"<html><head><title>{title}</title></head><body>{html_body}</body></html>"
    r = requests.post(
        f"{GRAPH_BASE}/me/onenote/sections/{notebook_section_id}/pages",
        headers={"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/xhtml+xml"},
        data=html, timeout=15,
    )
    r.raise_for_status()
    return f'Created OneNote page "{title}".'


def onenote_list_sections() -> str:
    data = _get("/me/onenote/sections")
    sections = data.get("value", [])
    return "\n".join(f'{s["displayName"]} — id:{s["id"]}' for s in sections) or "No OneNote sections found."


# ---------------------------------------------------------------------------
# Teams — draft only, never auto-sends
# ---------------------------------------------------------------------------

def teams_draft_message(chat_id: str, text: str) -> str:
    """Posts to a chat immediately — Graph has no true 'draft' state for
    Teams chats, so surface a confirm step in the GUI BEFORE calling this,
    same as the Messages.app pattern but enforced one layer up."""
    payload = {"body": {"content": text}}
    msg = _post(f"/me/chats/{chat_id}/messages", payload)
    return f'Sent to Teams chat {chat_id} — id:{msg.get("id")}'


def teams_list_chats(limit: int = 10) -> str:
    data = _get("/me/chats", **{"$top": limit})
    chats = data.get("value", [])
    return "\n".join(f'{c.get("topic") or "(direct chat)"} — id:{c["id"]}' for c in chats) or "No Teams chats found."