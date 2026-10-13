"""More Microsoft 365: Outlook search/read, To Do, Excel (OneDrive workbooks),
OneDrive search/download, Contacts. Shares msgraph_tools' login. Public functions are agent tools."""
import os as _os
import requests as _requests

from tools import msgraph_tools as _m


def outlook_search(query: str, limit: int = 10) -> str:
    """Searches Outlook mail (free text, or from:name / subject:word)."""
    items = _m._get("/me/messages", **{"$search": '"%s"' % query, "$top": limit, "$select": "subject,from,receivedDateTime"}).get("value", [])
    return "\n".join('%s — %s — %s — id:%s' % (i["subject"], i["from"]["emailAddress"]["address"], i["receivedDateTime"][:10], i["id"]) for i in items) or "No matching mail."


def outlook_read(message_id: str, max_chars: int = 5000) -> str:
    """Reads one Outlook email by id (plain text)."""
    r = _requests.get("%s/me/messages/%s" % (_m.GRAPH_BASE, message_id), headers={**_m._headers(), "Prefer": 'outlook.body-content-type="text"'}, timeout=15)
    r.raise_for_status()
    d = r.json()
    return "From: %s\nSubject: %s\n\n%s" % (d["from"]["emailAddress"]["address"], d["subject"], d["body"]["content"][:max_chars])


def todo_list_tasks(limit: int = 20) -> str:
    """Lists open Microsoft To Do tasks from the default list."""
    lists = _m._get("/me/todo/lists").get("value", [])
    if not lists:
        return "No To Do lists."
    items = _m._get("/me/todo/lists/%s/tasks" % lists[0]["id"], **{"$filter": "status ne 'completed'", "$top": limit}).get("value", [])
    return "\n".join("%s — id:%s" % (t["title"], t["id"]) for t in items) or "No open tasks."


def todo_add_task(title: str) -> str:
    """Adds a task to the default Microsoft To Do list."""
    lists = _m._get("/me/todo/lists").get("value", [])
    if not lists:
        return "No To Do list found."
    _m._post("/me/todo/lists/%s/tasks" % lists[0]["id"], {"title": title})
    return "Added to To Do: %s" % title


def onedrive_search(query: str, limit: int = 10) -> str:
    """Searches OneDrive by name/content."""
    items = _m._get("/me/drive/root/search(q='%s')" % query.replace("'", "''"), **{"$top": limit}).get("value", [])
    return "\n".join("%s — %s" % (i["name"], i.get("webUrl", "")) for i in items) or "Nothing found."


def onedrive_download(remote_path: str, save_path: str = "~/Downloads/") -> str:
    """Downloads a OneDrive file by its path from the root, e.g. 'Documents/report.docx'."""
    r = _requests.get("%s/me/drive/root:/%s:/content" % (_m.GRAPH_BASE, remote_path.lstrip("/")), headers={"Authorization": "Bearer " + _m._get_token()}, timeout=60)
    r.raise_for_status()
    dest = _os.path.expanduser(save_path)
    if _os.path.isdir(dest):
        dest = _os.path.join(dest, _os.path.basename(remote_path))
    with open(dest, "wb") as fh:
        fh.write(r.content)
    return "Saved to %s" % dest


def excel_read_range(remote_path: str, range_a1: str = "A1:F20", sheet: str = "Sheet1") -> str:
    """Reads cells from an Excel workbook stored in OneDrive."""
    data = _m._get("/me/drive/root:/%s:/workbook/worksheets/%s/range(address='%s')" % (remote_path.lstrip("/"), sheet, range_a1))
    return "\n".join(" | ".join(str(c) for c in row) for row in data.get("values", [])) or "Empty range."


def excel_write_range(remote_path: str, range_a1: str, rows: list, sheet: str = "Sheet1") -> str:
    """Writes a 2D list of values into an Excel workbook in OneDrive starting at range_a1 (e.g. 'A1:B2')."""
    r = _requests.patch("%s/me/drive/root:/%s:/workbook/worksheets/%s/range(address='%s')" % (_m.GRAPH_BASE, remote_path.lstrip("/"), sheet, range_a1),
                        headers=_m._headers(), json={"values": rows}, timeout=20)
    r.raise_for_status()
    return "Wrote %d row(s) to %s." % (len(rows), range_a1)


def contacts_search_ms(query: str, limit: int = 5) -> str:
    """Finds Outlook contacts by name."""
    items = _m._get("/me/contacts", **{"$search": '"%s"' % query, "$top": limit}).get("value", [])
    return "\n".join("%s — %s" % (c.get("displayName"), ", ".join(e["address"] for e in c.get("emailAddresses", [])) or "no email") for c in items) or "No matching contacts."
