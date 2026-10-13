"""More Google Workspace: Tasks, Contacts, Drive search/download, Docs read/append,
Sheets append, Calendar range/delete, Gmail search. Shares the token used by
google_workspace_tools. Public functions are agent tools."""
import io as _io
import os as _os
from datetime import datetime as _dt, timedelta as _td

from googleapiclient.discovery import build as _build

from tools.google_workspace_tools import _get_credentials


def _svc(name, version):
    return _build(name, version, credentials=_get_credentials(), cache_discovery=False)


# ---- Tasks ----
def tasks_list(limit: int = 20) -> str:
    """Lists open Google Tasks."""
    items = _svc("tasks", "v1").tasks().list(tasklist="@default", maxResults=limit, showCompleted=False).execute().get("items", [])
    if not items:
        return "No open tasks."
    return "\n".join('%s — id:%s%s' % (t["title"], t["id"], (" — due " + t["due"][:10]) if t.get("due") else "") for t in items)


def tasks_add(title: str, due_date: str = "", notes: str = "") -> str:
    """Adds a Google Task. due_date as YYYY-MM-DD (optional)."""
    body = {"title": title, "notes": notes}
    if due_date:
        body["due"] = due_date + "T00:00:00.000Z"
    t = _svc("tasks", "v1").tasks().insert(tasklist="@default", body=body).execute()
    return "Added task: %s" % t["title"]


def tasks_complete(task_id: str) -> str:
    """Marks a Google Task complete."""
    _svc("tasks", "v1").tasks().patch(tasklist="@default", task=task_id, body={"status": "completed"}).execute()
    return "Task completed."


# ---- Contacts ----
def contacts_search(query: str, limit: int = 5) -> str:
    """Finds Google Contacts by name/email (names, emails, phone numbers)."""
    svc = _svc("people", "v1")
    svc.people().searchContacts(query="", readMask="names").execute()  # warm-up required by the API
    res = svc.people().searchContacts(query=query, pageSize=limit, readMask="names,emailAddresses,phoneNumbers").execute()
    out = []
    for r in res.get("results", []):
        p = r["person"]
        name = (p.get("names") or [{}])[0].get("displayName", "(no name)")
        mail = ", ".join(e["value"] for e in p.get("emailAddresses", []))
        tel = ", ".join(n["value"] for n in p.get("phoneNumbers", []))
        out.append("%s — %s — %s" % (name, mail or "no email", tel or "no phone"))
    return "\n".join(out) or "No matching contacts."


# ---- Drive ----
def drive_search(query: str, limit: int = 10) -> str:
    """Searches all of the user's Google Drive by file name or content."""
    q = query.replace("'", "\\'")
    files = _svc("drive", "v3").files().list(
        q="(name contains '%s' or fullText contains '%s') and trashed=false" % (q, q),
        pageSize=limit, fields="files(id,name,mimeType,modifiedTime,webViewLink)").execute().get("files", [])
    return "\n".join("%s — %s — id:%s — %s" % (f["name"], f["mimeType"].split(".")[-1], f["id"], f.get("webViewLink", "")) for f in files) or "Nothing found."


def drive_download(file_id: str, save_path: str = "~/Downloads/") -> str:
    """Downloads a Drive file (Google Docs/Sheets/Slides are exported to PDF)."""
    from googleapiclient.http import MediaIoBaseDownload
    svc = _svc("drive", "v3")
    meta = svc.files().get(fileId=file_id, fields="name,mimeType").execute()
    dest = _os.path.expanduser(save_path)
    if _os.path.isdir(dest):
        dest = _os.path.join(dest, meta["name"])
    if meta["mimeType"].startswith("application/vnd.google-apps."):
        req = svc.files().export_media(fileId=file_id, mimeType="application/pdf")
        dest += ".pdf"
    else:
        req = svc.files().get_media(fileId=file_id)
    buf = _io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    with open(dest, "wb") as fh:
        fh.write(buf.getvalue())
    return "Saved to %s" % dest


# ---- Docs / Sheets ----
def docs_read(doc_id: str, max_chars: int = 6000) -> str:
    """Reads the text of a Google Doc."""
    doc = _svc("docs", "v1").documents().get(documentId=doc_id).execute()
    text = "".join(e.get("textRun", {}).get("content", "") for c in doc["body"]["content"] for e in c.get("paragraph", {}).get("elements", []))
    return "%s\n\n%s" % (doc.get("title"), text[:max_chars])


def docs_append_text(doc_id: str, text: str) -> str:
    """Appends a paragraph of text to the end of a Google Doc."""
    _svc("docs", "v1").documents().batchUpdate(documentId=doc_id, body={"requests": [
        {"insertText": {"endOfSegmentLocation": {}, "text": "\n" + text}}]}).execute()
    return "Appended to the doc."


def sheets_append_rows(spreadsheet_id: str, range_a1: str, rows: list) -> str:
    """Appends rows (list of lists) after the last row of a sheet range like 'Sheet1!A:C'."""
    _svc("sheets", "v4").spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=range_a1, valueInputOption="USER_ENTERED", body={"values": rows}).execute()
    return "Appended %d row(s)." % len(rows)


# ---- Calendar ----
def calendar_list_range(days_ahead: int = 7) -> str:
    """Lists Google Calendar events from now through the next N days."""
    now = _dt.now().astimezone()
    ev = _svc("calendar", "v3").events().list(calendarId="primary", timeMin=now.isoformat(),
        timeMax=(now + _td(days=days_ahead)).isoformat(), singleEvents=True, orderBy="startTime", maxResults=40).execute().get("items", [])
    return "\n".join("%s — %s — id:%s" % (e.get("summary", "(no title)"), e["start"].get("dateTime", e["start"].get("date")), e["id"]) for e in ev) or "Nothing scheduled."


def calendar_delete_event(event_id: str) -> str:
    """Deletes a calendar event by id (confirm with the user first)."""
    _svc("calendar", "v3").events().delete(calendarId="primary", eventId=event_id).execute()
    return "Event deleted."


# ---- Gmail ----
def gmail_search(query: str, limit: int = 10) -> str:
    """Searches Gmail with Gmail syntax (from:, subject:, after:2026/01/01, has:attachment, is:unread)."""
    svc = _svc("gmail", "v1")
    ids = svc.users().messages().list(userId="me", q=query, maxResults=limit).execute().get("messages", [])
    out = []
    for m in ids:
        d = svc.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
        h = {x["name"]: x["value"] for x in d["payload"]["headers"]}
        out.append("%s — %s — %s — id:%s" % (h.get("Subject", "(no subject)"), h.get("From", "?"), h.get("Date", "")[:16], m["id"]))
    return "\n".join(out) or "No matching emails."
