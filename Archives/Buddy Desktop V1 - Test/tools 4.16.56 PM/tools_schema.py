# tools_schema.py
# Master schema matching the complete tools.py (macOS Agent Tools)

tools_schema = [
    # ==================== APP TOOLS ====================
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Launches an application installed on the Mac by name.",
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
            "description": "Force closes a non-responsive app using pkill. REQUIRES user confirmation dialog.",
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
            "description": "Lists installed applications in /Applications and /System/Applications.",
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
    {
        "type": "function",
        "function": {
            "name": "get_frontmost_app",
            "description": "Returns the name of the currently frontmost (focused) application.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "activate_app",
            "description": "Brings an already-running app to the foreground (or launches it).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "Name of the application."}
                },
                "required": ["app"]
            }
        }
    },

    # ==================== WEB / BROWSER TOOLS ====================
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web via DuckDuckGo for live facts, current information, or links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                    "max_results": {"type": "integer", "description": "Number of results to return (default 5)."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Opens a specific URL in the given browser (default Google Chrome).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL starting with http:// or https://."},
                    "browser": {"type": "string", "description": "Browser name (default 'Google Chrome')."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_action",
            "description": "Performs common browser actions via keyboard shortcuts (new_tab, new_window, close_tab, next_tab, prev_tab, undo, redo, reopen_tab, open_history).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["new_tab", "new_window", "reopen_tab", "reopen_window", "open_history", "undo", "redo", "close_tab", "next_tab", "prev_tab"],
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
            "description": "Lists all currently open tabs in the browser, including titles and URLs, grouped by window. Use BEFORE closing tabs or acting on current pages.",
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
            "description": "Closes browser tabs whose URL contains the given keyword.",
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
    {
        "type": "function",
        "function": {
            "name": "get_active_tab_info",
            "description": "Returns title and URL of the currently active tab.",
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
            "name": "navigate_active_tab",
            "description": "Navigates the currently active tab to a new URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Target URL."},
                    "browser": {"type": "string", "description": "Browser name (default 'Google Chrome')."}
                },
                "required": ["url"]
            }
        }
    },

    # ==================== FILE SYSTEM TOOLS ====================
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists contents of a directory (names only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default '~')."},
                    "max_entries": {"type": "integer", "description": "Max entries to return (default 100)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_content",
            "description": "Reads text content of a file (truncated if very large).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Full path to the file."},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 50000)."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file_content",
            "description": "Writes text content to a file. Asks for confirmation if the file already exists (unless overwrite=True).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Full path to write."},
                    "content": {"type": "string", "description": "Text content to write."},
                    "overwrite": {"type": "boolean", "description": "If true, skip confirmation when overwriting (default false)."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_to_file",
            "description": "Appends text to the end of a file (creates if missing).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Full path to the file."},
                    "content": {"type": "string", "description": "Text to append."}
                },
                "required": ["path", "content"]
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
            "name": "create_directory",
            "description": "Creates a directory (and parents if needed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copies a file or directory tree to a new location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source path."},
                    "dst": {"type": "string", "description": "Destination path."}
                },
                "required": ["src", "dst"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Moves/renames a file or directory. REQUIRES user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source path."},
                    "dst": {"type": "string", "description": "Destination path."}
                },
                "required": ["src", "dst"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Renames a file or folder (stays in same directory). REQUIRES user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Current full path."},
                    "new_name": {"type": "string", "description": "New name only (not full path)."}
                },
                "required": ["path", "new_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trash_file",
            "description": "Moves a file or folder to the Trash (recoverable). Preferred over permanent delete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Full path to trash."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "PERMANENTLY deletes a file (NOT recoverable). REQUIRES strong user confirmation. Prefer trash_file.",
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
            "name": "empty_trash",
            "description": "Empties the macOS Trash permanently. REQUIRES user confirmation.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_info",
            "description": "Returns size, created, modified, permissions, is_dir etc. for a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Full path."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_local_files",
            "description": "Searches for local files using Spotlight (mdfind).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filename or keyword to search for."},
                    "max_results": {"type": "integer", "description": "Max results (default 10)."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_in_finder",
            "description": "Reveals a file or folder in Finder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Full path to reveal."}
                },
                "required": ["path"]
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

    # ==================== SYSTEM & SHELL ====================
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Executes a raw bash command and returns stdout + stderr. Dangerous-looking commands (rm -rf, sudo, etc.) automatically trigger a confirmation dialog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash shell command string to run."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."}
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
            "description": "Takes a screenshot of the entire display and saves it to a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {"type": "string", "description": "Destination file path (default '~/Desktop/screenshot.png')."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Sets the macOS output volume percentage (0-100).",
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
            "name": "get_volume",
            "description": "Returns the current output volume level (0-100).",
            "parameters": {"type": "object", "properties": {}}
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
    {
        "type": "function",
        "function": {
            "name": "get_dark_mode",
            "description": "Returns whether Dark Mode is currently enabled.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Returns basic system information (macOS version, hardware, Python version, etc.).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_battery_status",
            "description": "Returns battery percentage and charging status (laptops).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_space",
            "description": "Returns human-readable disk usage for the given path (default root).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to check (default '/')."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory_info",
            "description": "Returns memory pressure / usage summary.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "Lists top processes by CPU usage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max processes to show (default 30)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Kills a process by PID or name. REQUIRES user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid_or_name": {"type": "string", "description": "PID (number as string) or process name."}
                },
                "required": ["pid_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lock_screen",
            "description": "Immediately locks the screen (requires password to unlock).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sleep_display",
            "description": "Puts the display to sleep (computer stays awake).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_screensaver",
            "description": "Starts the system screensaver.",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    # ==================== NETWORK ====================
    {
        "type": "function",
        "function": {
            "name": "get_ip_address",
            "description": "Returns local (en0) and public IP address info.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ping_host",
            "description": "Pings a host and returns the result summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Hostname or IP to ping."},
                    "count": {"type": "integer", "description": "Number of pings (default 3)."}
                },
                "required": ["host"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_file",
            "description": "Downloads a file from a URL to the given local path using curl.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to download."},
                    "save_path": {"type": "string", "description": "Local path to save the file."}
                },
                "required": ["url", "save_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_internet",
            "description": "Quick check whether the machine can reach the internet.",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    # ==================== SPOTIFY & APPLE MUSIC ====================
    {
        "type": "function",
        "function": {
            "name": "spotify_control",
            "description": "Controls active Spotify playback (play, pause, next, previous).",
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
    {
        "type": "function",
        "function": {
            "name": "music_control",
            "description": "Controls the Apple Music app (play, pause, next, previous).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "previous"],
                        "description": "Playback command."
                    }
                },
                "required": ["action"]
            }
        }
    },

    # ==================== GMAIL ====================
    {
        "type": "function",
        "function": {
            "name": "get_recent_emails",
            "description": "Gets recent inbox emails (read-only) from the last N days. Requires Gmail OAuth credentials in ~/Buddy/.",
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
            "description": "Looks up a phone number for a contact by name using the macOS Contacts app. Use this BEFORE send_imessage whenever the user gives a contact name instead of a phone number or email. Requires Contacts permission.",
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
            "description": "Sends an iMessage to a contact via AppleScript. Requires the recipient's phone number or iMessage-enabled email, and the message text.",
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
            "description": "Reads unread incoming iMessages/SMS directly from the local Messages database (read-only). Includes messages from both individual contacts and group chats. Requires Full Disk Access permission for the Python process.",
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
            "description": "Lists group chats (not 1:1 conversations) with their chat_id and display_name if set. Use this BEFORE send_group_message to find the correct chat_id.",
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

    # ==================== PRODUCTIVITY ====================
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Creates a new reminder in the Reminders app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the reminder."},
                    "body": {"type": "string", "description": "Optional body/notes."},
                    "list_name": {"type": "string", "description": "Reminders list name (default 'Reminders')."}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "Creates a new note in the Notes app.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Note title."},
                    "body": {"type": "string", "description": "Note body text."}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Creates a basic calendar event. Datetime format: YYYY-MM-DD HH:MM (local time).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start_datetime": {"type": "string", "description": "Start time as 'YYYY-MM-DD HH:MM'."},
                    "end_datetime": {"type": "string", "description": "End time as 'YYYY-MM-DD HH:MM' (optional, defaults to +1 hour)."},
                    "calendar_name": {"type": "string", "description": "Calendar name (default 'Home')."}
                },
                "required": ["title", "start_datetime"]
            }
        }
    },

    # ==================== INPUT SIMULATION ====================
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Types the given text using simulated keyboard (requires Accessibility permission for the process).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type."},
                    "interval": {"type": "number", "description": "Delay between keystrokes in seconds (default 0.02)."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_hotkey",
            "description": "Presses a hotkey combination, e.g. command+c for copy. Common keys: command, option, control, shift, enter, tab, escape, up, down, left, right.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of keys to press together, e.g. ['command', 'c']."
                    }
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": "Clicks the mouse at absolute screen coordinates (or current position if x/y omitted).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Screen X coordinate (optional)."},
                    "y": {"type": "integer", "description": "Screen Y coordinate (optional)."},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button (default left)."},
                    "clicks": {"type": "integer", "description": "Number of clicks (default 1)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_move",
            "description": "Moves the mouse cursor to absolute screen coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Target X."},
                    "y": {"type": "integer", "description": "Target Y."},
                    "duration": {"type": "number", "description": "Animation duration in seconds (default 0.3)."}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mouse_position",
            "description": "Returns current mouse (x, y) coordinates.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_screen_size",
            "description": "Returns screen width and height in pixels.",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    # ==================== SPEECH ====================
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": "Speaks the given text using the macOS 'say' command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to speak."},
                    "voice": {"type": "string", "description": "Optional voice name (use list_voices to see options)."},
                    "rate": {"type": "integer", "description": "Speaking rate (words per minute, optional)."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_voices",
            "description": "Lists available macOS voices for the say command.",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    # ==================== CODING / PACKAGES ====================
    {
        "type": "function",
        "function": {
            "name": "run_code",
            "description": "Runs a Python file and returns stdout and stderr (15s timeout).",
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

    # ==================== TASK COMPLETION ====================
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Signals that all steps in the plan have been executed successfully. The summary must be a short, direct answer for the user (no bullet points of steps taken).",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "A short, direct answer or confirmation for the user."}
                },
                "required": ["summary"]
            }
        }
    }
]