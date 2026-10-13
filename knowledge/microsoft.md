# Microsoft ecosystem guide — Outlook, Calendar, OneDrive, Excel, OneNote, To Do, Teams, Contacts
One Microsoft login (Plugins > Microsoft) via device code: Buddy shows a code, the user enters it at microsoft.com/devicelogin. Personal and work/school accounts both work if the Azure app is set to multitenant + personal.

## Outlook mail
- Unread: outlook_unread. Search: outlook_search("invoice") or "from:alice". Read one: outlook_read(message_id). Draft: outlook_create_draft(to, subject, body). Drafts only, never send without an explicit yes and the exact text.

## Calendar
- Today: outlook_today. Create: outlook_create_event(title, start_iso, end_iso, timezone). Use the user's real timezone name.

## OneDrive
- Recent: onedrive_recent. Search: onedrive_search(query). Upload: onedrive_upload(local_path, remote_name). Download: onedrive_download("Documents/file.docx", save_path).

## Excel (workbooks stored in OneDrive)
- Read: excel_read_range("Documents/budget.xlsx", "A1:D20", sheet="Sheet1"). Write: excel_write_range(path, "A1:B2", [[1,2],[3,4]]).
- Works on .xlsx in OneDrive only; for a local .xlsx use run_code with openpyxl.

## OneNote
- onenote_list_sections, then onenote_create_page(section_id, title, html_body). Body is simple HTML (<p>, <h1>, <ul>).

## To Do
- todo_list_tasks, todo_add_task(title).

## Teams
- teams_list_chats, teams_send_message(chat_id, text). Messages post immediately (no draft state): show the text, get a yes first.

## Contacts
- contacts_search_ms(name) to find an email before drafting.

## Word / PowerPoint
- No direct Graph editing. Create locally with run_code (python-docx / python-pptx), then onedrive_upload. Or open in the browser guide.

## Troubleshooting
- Device code "expired": use only the code from the most recent attempt, enter it right away.
- "AADSTS" errors about account type: Azure app registration > Authentication > Supported account types must include personal accounts (and organizations for work/school).
- Missing scope after an update: Disconnect and connect again to re-consent.
