import os
import re
import base64
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose"
]
TOKEN_PATH = os.path.expanduser("~/Buddy/token.json")
CREDS_PATH = os.path.expanduser("~/Buddy/credentials.json")


def _get_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _clean_snippet(text: str) -> str:
    return re.sub(r'[\u200c\u200b\ufeff]+', '', text or "").strip()


def _fetch_messages(query: str, max_results: int) -> list[dict]:
    service = _get_service()
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = results.get("messages", [])

    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": _clean_snippet(full.get("snippet", "")),
        })
    return emails


def get_recent_emails(days_back: int = 7, max_results: int = 10) -> list[dict]:
    """Get recent inbox emails from the last `days_back` days, capped at `max_results`."""
    after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    query = f"in:inbox after:{after_date}"
    return _fetch_messages(query, max_results)


def get_unread_emails(days_back: int = 7, max_results: int = 10) -> list[dict]:
    """Get unread inbox emails from the last `days_back` days, capped at `max_results`."""
    after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    query = f"in:inbox is:unread after:{after_date}"
    return _fetch_messages(query, max_results)


def create_draft(recipient: str, subject: str, body: str) -> dict:
    """Create a new draft email. Does NOT send it."""
    service = _get_service()
    message = MIMEText(body)
    message["to"] = recipient
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return {"draft_id": draft["id"], "recipient": recipient, "subject": subject}


def list_drafts(max_results: int = 10) -> list[dict]:
    """List existing drafts so you can find a draft_id by subject."""
    service = _get_service()
    results = service.users().drafts().list(userId="me", maxResults=max_results).execute()
    drafts = results.get("drafts", [])

    out = []
    for d in drafts:
        full = service.users().drafts().get(userId="me", id=d["id"]).execute()
        headers = {h["name"]: h["value"] for h in full["message"]["payload"]["headers"]}
        out.append({
            "draft_id": d["id"],
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
        })
    return out


def modify_draft(draft_id: str, recipient: str = None, subject: str = None, body: str = None) -> dict:
    """Modify an existing draft by draft_id. Only overwrites fields you pass in."""
    service = _get_service()
    existing = service.users().drafts().get(userId="me", id=draft_id).execute()
    headers = {h["name"]: h["value"] for h in existing["message"]["payload"]["headers"]}

    new_recipient = recipient or headers.get("To", "")
    new_subject = subject or headers.get("Subject", "")
    new_body = body if body is not None else ""  # can't easily re-extract old body reliably

    message = MIMEText(new_body)
    message["to"] = new_recipient
    message["subject"] = new_subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    updated = service.users().drafts().update(
        userId="me", id=draft_id, body={"message": {"raw": raw}}
    ).execute()
    return {"draft_id": updated["id"], "recipient": new_recipient, "subject": new_subject}