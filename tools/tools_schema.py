# tools_schema.py

tools_schema = [
    # ==================== APP TOOLS ====================
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Launches an application installed on the Mac.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Name of the application (e.g., 'Google Chrome', 'Spotify', 'Slack')."}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Gracefully quits an application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Name of the application to close."}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "force_close_app",
            "description": "Force closes a non-responsive app using pkill (last resort).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Process name to force close."}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_apps",
            "description": "Lists installed applications in /Applications.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_apps_running",
            "description": "Lists all active visible GUI applications currently running.",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    # ==================== WEB TOOLS ====================
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web via DuckDuckGo for live facts, current information, or links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                    "max_results": {"type": "integer", "description": "Number of results to return (default 3)."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Opens a specific URL directly in Google Chrome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL starting with http:// or https://."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_action",
            "description": "Performs tab or window actions in a web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["new_tab", "new_window", "reopen_tab", "reopen_window", "open_history", "undo", "redo"],
                        "description": "Action to perform."
                    },
                    "browser": {"type": "string", "description": "Target browser (default 'Google Chrome')."}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_open_tabs",
            "description": "Lists all currently open tabs in Google Chrome, including their titles and URLs, grouped by window. Use this BEFORE closing tabs or taking any action that depends on knowing what's currently open.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "Browser name (default 'Google Chrome')."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_tab",
            "description": "Closes browser tabs containing a specific website keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "website": {"type": "string", "description": "Keyword/URL segment to match and close."},
                    "browser": {"type": "string", "description": "Browser name (default 'Google Chrome')."}
                },
                "required": ["website"]
            }
        }
    },

    # ==================== CODING & FILES ====================
    {
        "type": "function",
        "function": {
            "name": "run_code",
            "description": "Runs a Python file and returns stdout and stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the Python file."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_local_files",
            "description": "Searches for local files on the Mac using Spotlight index (mdfind).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filename or keyword to search for."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder_in_editor",
            "description": "Opens a folder or file in VS Code (or Finder as fallback).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Directory or file path to open."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Creates an empty file at a given directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string", "description": "Name of the file."},
                    "file_path": {"type": "string", "description": "Directory path."}
                },
                "required": ["file_name", "file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Deletes a specified file from disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string", "description": "Name of the file to delete."},
                    "file_path": {"type": "string", "description": "Directory path containing the file."}
                },
                "required": ["file_name", "file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_package",
            "description": "Installs, updates, or uninstalls a Python package using pip3.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["install", "update", "uninstall"],
                        "description": "Package management operation."
                    },
                    "package_name": {"type": "string", "description": "Name of the PyPI package."}
                },
                "required": ["action", "package_name"]
            }
        }
    },

    # ==================== SYSTEM & SHELL SUPERPOWERS ====================
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Executes a raw bash command in the terminal and returns output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash shell command string to run."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard",
            "description": "Reads and returns text currently stored in the system clipboard.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_clipboard",
            "description": "Writes text directly into the system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text string to copy to clipboard."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Triggers a native macOS desktop banner notification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notification header/title."},
                    "message": {"type": "string", "description": "Main notification body text."}
                },
                "required": ["title", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screen",
            "description": "Takes a screenshot of the display and saves it to a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {"type": "string", "description": "Destination file path (e.g. '~/Desktop/screenshot.png')."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Sets the macOS output volume percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "Volume integer between 0 and 100."}
                },
                "required": ["amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_dark_mode",
            "description": "Enables or disables macOS system Dark Mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "enum": ["on", "off"], "description": "'on' for dark mode, 'off' for light mode."}
                },
                "required": ["state"]
            }
        }
    },

    # ==================== SPOTIFY ====================
    {
        "type": "function",
        "function": {
            "name": "spotify_control",
            "description": "Controls active Spotify playback (play, pause, skip, previous).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "previous"],
                        "description": "Playback command to send to Spotify."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_spotify_playlist",
            "description": "Plays a saved playlist mapping in Spotify (e.g., 'liked songs' or 'fav songs').",
            "parameters": {
                "type": "object",
                "properties": {
                    "playlist_name": {"type": "string", "description": "Name of the playlist."}
                },
                "required": ["playlist_name"]
            }
        }
    },

    # ==================== GMAIL ====================
    {
        "type": "function",
        "function": {
            "name": "get_recent_emails",
            "description": "Gets recent inbox emails (read-only) from the last N days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "How many days back to search (default 7)."},
                    "max_results": {"type": "integer", "description": "Max number of emails to return (default 10)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_unread_emails",
            "description": "Gets unread inbox emails (read-only) from the last N days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "How many days back to search (default 7)."},
                    "max_results": {"type": "integer", "description": "Max number of emails to return (default 10)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft",
            "description": "Creates a new Gmail draft. Does NOT send the email — only saves it as a draft for the user to review and send manually.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject line."},
                    "body": {"type": "string", "description": "Plain text body of the email."}
                },
                "required": ["recipient", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_drafts",
            "description": "Lists existing Gmail drafts with their draft_id, recipient, and subject. Use this BEFORE modify_draft to find the correct draft_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Max number of drafts to return (default 10)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_draft",
            "description": "Modifies an existing Gmail draft by draft_id. Only fields provided are changed; omitting body will clear it, so always pass the full intended body text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string", "description": "ID of the draft to modify, from list_drafts."},
                    "recipient": {"type": "string", "description": "New recipient email address (optional)."},
                    "subject": {"type": "string", "description": "New subject line (optional)."},
                    "body": {"type": "string", "description": "New plain text body (optional, but recommended to always include)."}
                },
                "required": ["draft_id"]
            }
        }
    },
    # ==================== iMESSAGE ====================
    {
        "type": "function",
        "function": {
            "name": "lookup_contact_number",
            "description": "Looks up a phone number for a contact by name using the macOS Contacts app. Use this BEFORE send_imessage whenever the user gives a contact name instead of a phone number or email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Contact name to search for (e.g. 'Muhyee'). Partial matches are supported."}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_imessage",
            "description": "Sends an iMessage to a contact via a fixed, pre-tested AppleScript template. Requires the recipient's phone number or iMessage-enabled email, and the message text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Phone number (e.g. '+16143729805') or iMessage-enabled email of the recipient."},
                    "message": {"type": "string", "description": "The text content to send."}
                },
                "required": ["recipient", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_unread_messages",
            "description": "Reads unread incoming iMessages/SMS directly from the local Messages database (read-only). Includes messages from both individual contacts and group chats, with sender and chat name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max number of unread messages to return (default 20)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_group_chats",
            "description": "Lists group chats (not 1:1 conversations) with their chat_id and display_name if set. Use this BEFORE send_group_message to find the correct chat_id, especially if the group has no custom name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max number of group chats to return (default 20)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_group_message",
            "description": "Sends an iMessage to an existing group chat, identified by its chat_id or display_name from list_group_chats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_name": {"type": "string", "description": "The chat_identifier or display_name of the target group chat."},
                    "message": {"type": "string", "description": "The text content to send."}
                },
                "required": ["chat_name", "message"]
            }
        }
    },
    # ==================== TASK COMPLETION ====================
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Signals that all steps in the plan have been executed successfully.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "A short, direct answer or confirmation for the user. Must NOT contain bullet points of steps taken."}
                },
                "required": ["summary"]
            }
        }
    }
]