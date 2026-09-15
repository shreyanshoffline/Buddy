"""
tools/google_workspace_tools.py

Uses the SAME credentials.json / token.json that tools.py's Gmail
functions already use — same file, same folder (~/Buddy/), same
Credentials format (JSON, not pickle). No second OAuth client needed.

IMPORTANT ONE-TIME STEP: tools.py's SCOPES list just grew (Calendar,
Drive, Docs, Sheets, Slides, Photos added alongside Gmail's two).
Your existing token.json was issued under the OLD, narrower scope
list, so it won't actually be authorized for the new ones even though
this code will happily load it. Delete token.json ONCE:

    rm ~/Buddy/token.json   (or wherever tools.py actually found it —
                              run tools.gmail_connection_status() to check)

Then call anything in this file (or gmail_connect() again) and it will
re-run the consent screen with the full scope list. After that, every
function below shares that one token with Gmail.
"""

from tools.tools import (
    TOKEN_PATH, CREDS_PATH, SCOPES, HAS_GMAIL,
    Credentials, InstalledAppFlow, Request,
)
from googleapiclient.discovery import build

import os
from datetime import datetime, timedelta


def _get_credentials():
    """Mirrors tools.py's _get_gmail_service() credential logic exactly,
    but returns the raw creds object so any Google API can use it, not
    just Gmail's build("gmail", ...)."""
    if not HAS_GMAIL:
        raise RuntimeError("Google libraries not installed. pip install --break-system-packages "
                            "google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(f"Missing {CREDS_PATH}. Place your OAuth credentials.json there.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def check_google_connection() -> str:
    try:
        _get_credentials()
        return "OK: connected"
    except FileNotFoundError as e:
        return f"NOT_CONNECTED: {e}"
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def calendar_today() -> str:
    service = build("calendar", "v3", credentials=_get_credentials())
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    end = now.replace(hour=23, minute=59, second=59).isoformat() + "Z"
    events = service.events().list(
        calendarId="primary", timeMin=start, timeMax=end, singleEvents=True, orderBy="startTime"
    ).execute().get("items", [])
    if not events:
        return "Nothing on Google Calendar today."
    return "\n".join(
        f'{e.get("summary", "(no title)")} — {e["start"].get("dateTime", e["start"].get("date"))}'
        for e in events
    )


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
            e[key]["dateTime"] = (datetime.fromisoformat(dt_str) + delta).isoformat()
    service.events().update(calendarId="primary", eventId=e["id"], body=e).execute()
    return f'Moved "{e.get("summary")}" by {hours_delta}h.'


def meet_create_link(title: str, start_iso: str, end_iso: str, timezone: str = "UTC") -> str:
    service = build("calendar", "v3", credentials=_get_credentials())
    event = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
        "conferenceData": {"createRequest": {"requestId": f"buddy-{datetime.utcnow().timestamp()}"}},
    }
    created = service.events().insert(calendarId="primary", body=event, conferenceDataVersion=1).execute()
    return f'Created "{title}" with Meet link: {created.get("hangoutLink", "(link pending)")}'


# ---------------------------------------------------------------------------
# Drive (drive.file — only files Buddy created or the user picked)
# ---------------------------------------------------------------------------

def drive_list_recent(limit: int = 10) -> str:
    service = build("drive", "v3", credentials=_get_credentials())
    files = service.files().list(
        pageSize=limit, orderBy="modifiedTime desc", fields="files(id, name, modifiedTime)"
    ).execute().get("files", [])
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
    file = service.files().create(
        body={"name": name or os.path.basename(local_path)}, media_body=media, fields="id, webViewLink"
    ).execute()
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
        spreadsheetId=spreadsheet_id, range=range_a1, valueInputOption="USER_ENTERED", body={"values": rows}
    ).execute()
    return f"Wrote {len(rows)} rows to {range_a1}."


def sheets_read_range(spreadsheet_id: str, range_a1: str) -> str:
    service = build("sheets", "v4", credentials=_get_credentials())
    values = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_a1).execute().get("values", [])
    return "\n".join(" | ".join(row) for row in values) if values else "(empty range)"


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------

def slides_create_from_bullets(title: str, slides: list) -> str:
    service = build("slides", "v1", credentials=_get_credentials())
    deck = service.presentations().create(body={"title": title}).execute()
    pid = deck.get("presentationId")
    requests = [
        {"createSlide": {"objectId": f"slide_{i}", "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"}}}
        for i in range(len(slides))
    ]
    if requests:
        service.presentations().batchUpdate(presentationId=pid, body={"requests": requests}).execute()
    return f'Created deck "{title}" with {len(slides)} slides — https://docs.google.com/presentation/d/{pid}/edit'


# ---------------------------------------------------------------------------
# Translate (separate API key, not OAuth)
# ---------------------------------------------------------------------------

def translate_text(text: str, target_lang: str, api_key: str) -> str:
    import requests
    resp = requests.post(
        "https://translation.googleapis.com/language/translate/v2",
        params={"key": api_key}, json={"q": text, "target": target_lang, "format": "text"}, timeout=10,
    )
    if resp.status_code != 200:
        return f"ERROR: translation failed ({resp.status_code}): {resp.text[:200]}"
    return resp.json()["data"]["translations"][0]["translatedText"]


# ---------------------------------------------------------------------------
# Maps — no API/scope needed, just opens a URL
# ---------------------------------------------------------------------------

def maps_directions(origin: str, destination: str, mode: str = "driving") -> str:
    import urllib.parse
    import subprocess
    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={urllib.parse.quote(origin)}&destination={urllib.parse.quote(destination)}&travelmode={mode}"
    )
    subprocess.run(["open", url])
    return f"Opened directions from {origin} to {destination} ({mode})."


# ---------------------------------------------------------------------------
# Google Photos — capped by Google's 2025 restriction: without extended
# access, only sees photos/albums Buddy itself created.
# ---------------------------------------------------------------------------

def photos_list_recent(limit: int = 10) -> str:
    service = build("photoslibrary", "v1", credentials=_get_credentials(), static_discovery=False)
    items = service.mediaItems().list(pageSize=limit).execute().get("mediaItems", [])
    if not items:
        return ("No items visible. Without Google's extended Photos access, Buddy can only "
                "see media it created itself, not your full library.")
    return "\n".join(f'{i.get("filename")} — {i.get("productUrl")}' for i in items)
