# Google Workspace guide — Gmail, Calendar, Drive, Docs, Sheets, Slides, Tasks, Contacts, Meet, Maps
All use one Google login (Plugins > Google). If a tool says "Google isn't connected", tell the user to connect; do not retry.

## Gmail
- Read: get_unread_emails, get_recent_emails. Search: gmail_search("from:boss after:2026/09/01 has:attachment"). Gmail operators: from: to: subject: is:unread has:attachment older_than:7d label:.
- Write: create_draft, modify_draft, list_drafts. NEVER send; drafts only, the user presses Send. Show the draft text back.
- To email someone by name: contacts_search(name) for the address first.

## Calendar
- Today: calendar_today. Next days: calendar_list_range(days_ahead). Create: calendar_create_event(title, start_iso, end_iso, timezone). Move: calendar_move_event(event_query, hours_delta). Delete: calendar_delete_event(id), confirm first.
- Always pass the user's real timezone (e.g. America/New_York), not UTC. Read the event back after creating.
- Meeting link: meet_create_link(title, start_iso, end_iso) creates an event with a Meet URL.
- Finding free time: calendar_list_range then reason over the gaps; propose 2–3 slots.

## Drive
- Find anything: drive_search("budget 2026"). Recent: drive_list_recent. Upload: drive_upload_file(local_path, name). Download/export: drive_download(file_id, save_path) (Docs/Sheets/Slides export as PDF).
- Share links come from webViewLink in results. Sharing permission changes are not exposed: open the file in the browser guide if needed.

## Docs
- Create: docs_create(title, body_text). Read: docs_read(doc_id). Add text: docs_append_text(doc_id, text). Add a heading: docs_append_heading(doc_id, heading_text).
- Doc ids are in the URL: docs.google.com/document/d/<ID>/edit.

## Sheets
- Create: sheets_create(title). Read: sheets_read_range(id, "Sheet1!A1:D20"). Write: sheets_write_range(id, "A1", rows). Add rows to the bottom: sheets_append_rows(id, "Sheet1!A:D", rows).
- rows is a list of lists: [["Name","Qty"],["Apples",3]]. Formulas work: "=SUM(B2:B10)".

## Slides
- slides_create_from_bullets(title, slides) where slides = [{"title": "...", "bullets": ["..."]}]. Keep 3–5 bullets per slide.

## Tasks, Contacts, Maps, Translate, Photos
- Tasks: tasks_list, tasks_add(title, due_date YYYY-MM-DD), tasks_complete(id). Contacts: contacts_search(name).
- Maps: maps_directions(origin, destination, mode). Translate: translate_text (needs an API key from the user; otherwise answer the translation yourself).
- Photos: photos_list_recent only sees app-created data (Google API limit); for the user's real library use the Apple Photos tools or the browser.

## Setup / troubleshooting
- First connect opens a browser consent screen. If tools fail with "insufficient scopes" the saved token is old: Plugins > Google > Disconnect, connect again.
- Missing credentials.json = the OAuth desktop client isn't bundled; see PROJECT_STATUS.md.
