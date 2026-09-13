"""
Google ecosystem backend for Buddy, beyond Gmail (which already exists in
tools/tools.py). Drop this in as tools/google_workspace_tools.py.

Requires: google-api-python-client google-auth-httplib2 google-auth-oauthlib
    pip install --break-system-packages google-api-python-client google-auth-httplib2 google-auth-oauthlib

Reuses the SAME credentials.json OAuth client your Gmail setup already
uses (one Google Cloud project, one consent screen) — but the scope list
below is a UNION of Gmail's scopes plus these new ones. Because you're
adding scopes, the existing token.json/pickle must be deleted once so the
user re-consents with the full scope set. See the setup doc for exact
steps to enable each API.
"""

import os
import pickle
import base64
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CREDS_PATH = os.path.expanduser("~/.buddy/google_credentials.json")   # same file Gmail uses
TOKEN_PATH = os.path.expanduser("~/.buddy/google_token.pickle")       # same file Gmail uses

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/photoslibrary.readonly",
]


def _get_credentials():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
    return creds


def check_google_connection() -> str:
    try:
        _get_credentials()
        return "OK: Google account connected."
    except FileNotFoundError:
        return f"NOT_CONNECTED: no credentials.json at {CREDS_PATH}. Run through Plugins > Google > Connect."
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def calendar_today() -> str:
    service = build("calendar", "v3", credentials=_get_credentials())
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    end = (now.replace(hour=23, minute=59, second=59)).isoformat() + "Z"
    events = service.events().list(
        calendarId="primary", timeMin=start, timeMax=end, singleEvents=True, orderBy="startTime"
    ).execute().get("items", [])
    if not events:
        return "Nothing on Google Calendar today."
    lines = []
    for e in events:
        start_time = e["start"].get("dateTime", e["start"].get("date"))
        lines.append(f'{e.get("summary", "(no title)")} — {start_time}')
    return "\n".join(lines)


def calendar_create_event(title: str, start_iso: str, end_iso: str, timezone: str = "UTC") -> str:
    service = build("calendar", "v3", credentials=_get_credentials())
    event = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return f'Created "{title}" — {created.get("htmlLink")}'


def calendar_move_event(event_query: str, hours_delta: float) -> str:
    service = build("calendar", "v3", credentials=_get_credentials())
    events = service.events().list(calendarId="primary", q=event_query, singleEvents=True).execute().get("items", [])
    if not events:
        return f'No event matching "{event_query}".'
    e = events[0]
    delta = timedelta(hours=hours_delta)
    for key in ("start", "end"):
        dt_str = e[key].get("dateTime")
        if dt_str:
            dt = datetime.fromisoformat(dt_str)
            e[key]["dateTime"] = (dt + delta).isoformat()
    service.events().update(calendarId="primary", eventId=e["id"], body=e).execute()
    return f'Moved "{e.get("summary")}" by {hours_delta}h.'


def meet_create_link(title: str, start_iso: str, end_iso: str, timezone: str = "UTC") -> str:
    """Creates a Calendar event with a Google Meet link attached."""
    service = build("calendar", "v3", credentials=_get_credentials())
    event = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
        "conferenceData": {"createRequest": {"requestId": f"buddy-{datetime.utcnow().timestamp()}"}},
    }
    created = service.events().insert(
        calendarId="primary", body=event, conferenceDataVersion=1
    ).execute()
    link = created.get("hangoutLink", "(link pending)")
    return f'Created "{title}" with Meet link: {link}'


# ---------------------------------------------------------------------------
# Drive (drive.file scope — Buddy only sees files it created or the user
# explicitly picked, never the whole Drive)
# ---------------------------------------------------------------------------

def drive_list_recent(limit: int = 10) -> str:
    service = build("drive", "v3", credentials=_get_credentials())
    results = service.files().list(
        pageSize=limit, orderBy="modifiedTime desc", fields="files(id, name, modifiedTime)"
    ).execute()
    files = results.get("files", [])
    if not files:
        return "No files visible yet (drive.file only shows files Buddy created or you picked)."
    return "\n".join(f'{f["name"]} — modified {f["modifiedTime"]} — id:{f["id"]}' for f in files)


def drive_upload_file(local_path: str, name: str = None) -> str:
    from googleapiclient.http import MediaFileUpload
    service = build("drive", "v3", credentials=_get_credentials())
    local_path = os.path.expanduser(local_path)
    if not os.path.exists(local_path):
        return f"ERROR: {local_path} does not exist."
    media = MediaFileUpload(local_path, resumable=True)
    metadata = {"name": name or os.path.basename(local_path)}
    file = service.files().create(body=metadata, media_body=media, fields="id, webViewLink").execute()
    return f'Uploaded {local_path} — {file.get("webViewLink")}'


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------

def docs_create(title: str, body_text: str = "") -> str:
    service = build("docs", "v1", credentials=_get_credentials())
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc.get("documentId")
    if body_text:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": body_text}}]},
        ).execute()
    return f'Created Doc "{title}" — https://docs.google.com/document/d/{doc_id}/edit'


def docs_append_heading(doc_id: str, heading_text: str) -> str:
    service = build("docs", "v1", credentials=_get_credentials())
    doc = service.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1
    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [
            {"insertText": {"location": {"index": end_index}, "text": f"\n{heading_text}\n"}},
            {"updateParagraphStyle": {
                "range": {"startIndex": end_index, "endIndex": end_index + len(heading_text) + 1},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }},
        ]},
    ).execute()
    return f"Appended heading to doc {doc_id}."


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def sheets_create(title: str) -> str:
    service = build("sheets", "v4", credentials=_get_credentials())
    sheet = service.spreadsheets().create(body={"properties": {"title": title}}).execute()
    sid = sheet.get("spreadsheetId")
    return f'Created sheet "{title}" — https://docs.google.com/spreadsheets/d/{sid}/edit'


def sheets_write_range(spreadsheet_id: str, range_a1: str, rows: list) -> str:
    service = build("sheets", "v4", credentials=_get_credentials())
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=range_a1,
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()
    return f"Wrote {len(rows)} rows to {range_a1}."


def sheets_read_range(spreadsheet_id: str, range_a1: str) -> str:
    service = build("sheets", "v4", credentials=_get_credentials())
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_a1).execute()
    values = result.get("values", [])
    return "\n".join(" | ".join(row) for row in values) if values else "(empty range)"


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------

def slides_create_from_bullets(title: str, slides: list) -> str:
    """slides: list of {"heading": str, "bullets": [str, ...]}"""
    service = build("slides", "v1", credentials=_get_credentials())
    deck = service.presentations().create(body={"title": title}).execute()
    pid = deck.get("presentationId")
    requests = []
    for i, s in enumerate(slides):
        slide_id = f"slide_{i}"
        requests.append({"createSlide": {"objectId": slide_id, "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"}}})
    if requests:
        service.presentations().batchUpdate(presentationId=pid, body={"requests": requests}).execute()
    return f'Created deck "{title}" with {len(slides)} slides — https://docs.google.com/presentation/d/{pid}/edit'


# ---------------------------------------------------------------------------
# Translate (Cloud Translation API — separate API key, see setup doc)
# ---------------------------------------------------------------------------

def translate_text(text: str, target_lang: str, api_key: str) -> str:
    import requests
    resp = requests.post(
        "https://translation.googleapis.com/language/translate/v2",
        params={"key": api_key},
        json={"q": text, "target": target_lang, "format": "text"},
        timeout=10,
    )
    if resp.status_code != 200:
        return f"ERROR: translation failed ({resp.status_code}): {resp.text[:200]}"
    return resp.json()["data"]["translations"][0]["translatedText"]


# ---------------------------------------------------------------------------
# Maps — no API key needed for the common case: just open the right URL
# ---------------------------------------------------------------------------

def maps_directions(origin: str, destination: str, mode: str = "driving") -> str:
    import urllib.parse
    import subprocess as sp
    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={urllib.parse.quote(origin)}"
        f"&destination={urllib.parse.quote(destination)}"
        f"&travelmode={mode}"
    )
    sp.run(["open", url])
    return f"Opened directions from {origin} to {destination} ({mode})."


# ---------------------------------------------------------------------------
# Google Photos
# NOTE (honest limitation): Google restricted the Photos Library API in 2025.
# Apps without special extended access can only see photos/albums the app
# itself created, NOT the user's full library. Don't promise "search my whole
# library" without applying for that access — it will silently return almost
# nothing.
# ---------------------------------------------------------------------------

def photos_list_recent(limit: int = 10) -> str:
    service = build("photoslibrary", "v1", credentials=_get_credentials(), static_discovery=False)
    results = service.mediaItems().list(pageSize=limit).execute()
    items = results.get("mediaItems", [])
    if not items:
        return ("No items visible. Remember: without Google's extended Photos access, "
                "Buddy can only see media it created itself, not your full library.")
    return "\n".join(f'{i.get("filename")} — {i.get("productUrl")}' for i in items)