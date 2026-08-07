tools_schema = [
    # --- App Tools ---
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open a Mac application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "The name of the application (e.g., 'Google Chrome', 'Spotify', 'Visual Studio Code')."}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Gracefully quit a Mac application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "The name of the application to close."}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "force_close_app",
            "description": "Force close a Mac application process using pkill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "The process name to force close."}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_apps",
            "description": "List all installed applications on the Mac system.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_apps_running",
            "description": "List all currently running applications on the Mac.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "maximize_app",
            "description": "Maximize an application window to full screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "The name of the running application window to maximize."}
                },
                "required": ["app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "minimize_app",
            "description": "Minimize an application window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "description": "The name of the running application window to minimize."}
                },
                "required": ["app"]
            }
        }
    },

    # --- Web Tools ---

    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the live web using DuckDuckGo to find up-to-date information, news, or facts. Use this when the user asks about current events or topics outside your training data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The specific search query to look up on the web."},
                    "max_results": {"type": "integer","description": "The maximum number of search results to return. Default is 3."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a specific URL in the default or specified web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The exact URL to open."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_new_tab",
            "description": "Open a new tab in the specified web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name (e.g., 'Google Chrome', 'Safari')."}
                },
                "required": ["browser"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_new_window",
            "description": "Open a new window in the specified web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."}
                },
                "required": ["browser"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_tab",
            "description": "Close a tab matching a website name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."},
                    "website": {"type": "string", "description": "The website keyword contained in the tab URL."}  
                },
                "required": ["browser", "website"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_window",
            "description": "Close windows matching a browser and website keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."},
                    "website": {"type": "string", "description": "Website keyword contained in windows."}
                },
                "required": ["browser", "website"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reopen_closed_tab",
            "description": "Reopen the last closed tab in a browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."}
                },
                "required": ["browser"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reopen_closed_window",
            "description": "Reopen the last closed window in a browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."}
                },
                "required": ["browser"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_history",
            "description": "Open browsing history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."}
                },
                "required": ["browser"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "undo_tab_action",
            "description": "Undo the last action in a browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."}
                },
                "required": ["browser"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "redo_tab_action",
            "description": "Redo the last action in a browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "The browser name."}
                },
                "required": ["browser"]
            }
        }
    },

    # --- Coding Tools ---
    {
        "type": "function",
        "function": {
            "name": "run_code",
            "description": "Execute a Python script file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute or relative file path to the Python script."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "test_code",
            "description": "Run unit tests on a file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File path for testing."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "debug_code",
            "description": "Placeholder for debugging.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder_in_editor",
            "description": "Open a folder or file path in VS Code or Finder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to open."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new blank file at a specified path.",
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
            "description": "Delete a file from a specified path.",
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
            "name": "install_package",
            "description": "Install a Python package using pip3.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "Name of the package."},
                    "tool": {"type": "string", "description": "Tool to use (default pip3)."}
                },
                "required": ["package_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_package",
            "description": "Update a Python package.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "Name of the package."},
                    "tool": {"type": "string", "description": "Tool to use."}
                },
                "required": ["package_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_package",
            "description": "Uninstall a Python package.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "Name of the package."},
                    "tool": {"type": "string", "description": "Tool to use."}
                },
                "required": ["package_name"]
            }
        }
    },

    # --- System Tools ---
    {
        "type": "function",
        "function": {
            "name": "capture_screen",
            "description": "Take a screenshot of the Mac screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {"type": "string", "description": "Destination file path for the screenshot."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_screen",
            "description": "Record the Mac screen for a specified duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_seconds": {"type": "integer", "description": "Duration in seconds to record."},
                    "save_path": {"type": "string", "description": "Destination file path."}
                },
                "required": ["duration_seconds"]
            }
        }
    },

    # --- Cursor Tools ---
    {
        "type": "function",
        "function": {
            "name": "move_cursor",
            "description": "Move the mouse cursor to specific coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "end_x": {"type": "integer", "description": "Target X coordinate."},
                    "end_y": {"type": "integer", "description": "Target Y coordinate."},
                    "start_x": {"type": "integer", "description": "Optional starting X coordinate."},
                    "start_y": {"type": "integer", "description": "Optional starting Y coordinate."}
                },
                "required": ["end_x", "end_y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "left_click_cursor",
            "description": "Perform a left mouse click.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "left_double_click_cursor",
            "description": "Perform a left double click.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "left_drag_cursor",
            "description": "Drag the mouse with the left button pressed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer", "description": "Start X."},
                    "start_y": {"type": "integer", "description": "Start Y."},
                    "end_x": {"type": "integer", "description": "End X."},
                    "end_y": {"type": "integer", "description": "End Y."}
                },
                "required": ["start_x", "start_y", "end_x", "end_y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "right_click_cursor",
            "description": "Perform a right mouse click.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "right_double_click_cursor",
            "description": "Perform a right double click.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "right_drag_cursor",
            "description": "Drag the mouse with the right button pressed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer", "description": "Start X."},
                    "start_y": {"type": "integer", "description": "Start Y."},
                    "end_x": {"type": "integer", "description": "End X."},
                    "end_y": {"type": "integer", "description": "End Y."}
                },
                "required": ["start_x", "start_y", "end_x", "end_y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_cursor",
            "description": "Scroll the screen up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "'up' or 'down'."},
                    "amount": {"type": "integer", "description": "Number of scroll clicks."}
                },
                "required": ["direction"]
            }
        }
    },

    # --- Text Tools ---
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text using keyboard simulation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text string to type."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_text",
            "description": "Press backspace to delete text.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_text",
            "description": "Copy selected text (Cmd+C).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cut_text",
            "description": "Cut selected text (Cmd+X).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "paste_text",
            "description": "Paste text from clipboard (Cmd+V).",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    # --- Universal Commands ---
    {
        "type": "function",
        "function": {
            "name": "undo",
            "description": "Perform an undo action (Cmd+Z).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "redo",
            "description": "Perform a redo action (Cmd+Shift+Z).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "select_all",
            "description": "Select all elements or text (Cmd+A).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save",
            "description": "Save current file or context (Cmd+S).",
            "parameters": {"type": "object", "properties": {}}
        }
    },

    # --- System Poweroffs ---
    {
        "type": "function",
        "function": {
            "name": "restart",
            "description": "Restart the Mac system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_confirmation": {"type": "string", "description": "Confirmation flag ('yes' or 'true')."}
                },
                "required": ["user_confirmation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown",
            "description": "Shut down the Mac system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_confirmation": {"type": "string", "description": "Confirmation flag ('yes' or 'true')."}
                },
                "required": ["user_confirmation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screensaver",
            "description": "Start the system screensaver.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sleep",
            "description": "Put display to sleep.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lock_screen",
            "description": "Lock the Mac screen.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_out",
            "description": "Log out current user session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_confirmation": {"type": "string", "description": "Confirmation flag."}
                },
                "required": ["user_confirmation"]
            }
        }
    },

    # --- User Preferences & Spotify ---
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set system output volume percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "Volume level from 0 to 100."}
                },
                "required": ["amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_dark_mode",
            "description": "Enable or disable macOS dark mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "'true' or 'false'."}
                },
                "required": ["state"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_play",
            "description": "Resume or start Spotify track playback.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_pause",
            "description": "Pause Spotify playback.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_next",
            "description": "Skip to the next track on Spotify.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_previous",
            "description": "Return to the previous track on Spotify.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_spotify_playlist",
            "description": "Play a specific saved playlist by name (e.g., 'liked songs' or 'fav songs').",
            "parameters": {
                "type": "object",
                "properties": {
                    "playlist_name": {"type": "string", "description": "Name of the playlist to play."}
                },
                "required": ["playlist_name"]
            }
        }
    },

    # --- Worker Control Helper ---
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Call this tool when all steps in the plan are completed successfully to summarize execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "A concise summary of the completed task."}
                },
                "required": ["summary"]
            }
        }
    }
]