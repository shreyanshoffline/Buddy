"""Compatibility facade for Buddy's Gmail tools.

The implementation lives in tools.tools so OAuth paths and token refresh logic
cannot drift between two Gmail clients.
"""

from .tools import (
    HAS_GMAIL,
    SCOPES,
    TOKEN_PATH,
    CREDS_PATH,
    check_gmail_connection,
    create_draft,
    get_recent_emails,
    get_unread_emails,
    list_drafts,
    modify_draft,
)

__all__ = [
    "HAS_GMAIL",
    "SCOPES",
    "TOKEN_PATH",
    "CREDS_PATH",
    "check_gmail_connection",
    "create_draft",
    "get_recent_emails",
    "get_unread_emails",
    "list_drafts",
    "modify_draft",
]
