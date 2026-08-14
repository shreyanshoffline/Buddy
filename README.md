# Buddy v1.0.0 Pre-Release

Buddy is a Jarvis-style AI desktop assistant for macOS built by **Shreyansh Patra ("Shrey")** using [Hack Club's Hack AI](https://ai.hackclub.com/). Featuring a custom PySide6 desktop interface, system tray persistence, dynamic local storage, and real-time tool calls, Buddy controls apps, browses the web, manages files, and operates system settings directly from your desktop.

---

## 🚀 What's New in v1.0.0

- **PySide6 Desktop GUI:** Replaced the terminal UI with a native, frameless macOS window featuring a sleek, collapsible sidebar (48px collapsed / 200px expanded).
- **macOS System Tray Integration:** Quick access to toggle window visibility, trigger global shortcuts, or exit via a custom tray menu.
- **3-Tier Modular Architecture:** Clean separation of presentation (`gui_main.py`), orchestration logic (`core.py`), and local persistence (`storage.py`).
- **SQLite Local History (`buddy.db`):** Persistent conversation memory, background chat titling, dynamic recent chat sidebar updates, and saved settings.
- **DuckDuckGo Web Search:** Integrated web searching capability to fetch live, real-time facts directly into conversation context.

---

## 🏗️ Architecture

Buddy utilizes a structured 3-tier presentation, orchestration, and persistence setup:

    ┌────────────────────────────────────────────────────────┐
    │                      gui_main.py                       │
    │  (PySide6 Desktop GUI, Tray Hooks & Event Processing)  │
    └───────────────────────────┬────────────────────────────┘
                                │
    ┌───────────────────────────▼────────────────────────────┐
    │                        core.py                         │
    │ (Manager/Worker Logic, Tool Dispatch, DDG Web Search)  │
    └───────────────────────────┬────────────────────────────┘
                                │
    ┌───────────────────────────▼────────────────────────────┐
    │                       storage.py                       │
    │      (SQLite Engine: ~/Library/Application Support)    │
    └────────────────────────────────────────────────────────┘

### Execution Pipeline

    User Prompt (GUI)
           │
           ▼
      core.py ─── Manager (Generates execution plan or direct reply)
           │
           ▼
      Worker Model (Executes plan step-by-step)
           │
      ┌────┴──────────────────────────┐
      │                               │
      ▼                               ▼
    Web Search (DDG)           System Tools (tools.py)
      │                               │
      └────┬──────────────────────────┘
           │
           ▼
    storage.py ─── SQLite DB (Saves prompt, tool calls, and response)
           │
           ▼
    GUI Update ─── Renders message bubbles & refreshes sidebar recents

---

## 📁 File Structure

| File / Component | Layer | Description |
|---|---|---|
| `gui_main.py` | Presentation | PySide6 frameless window, responsive sidebar, chat bubbles, tray icon handling, and theme styling. |
| `core.py` | Business / Brain | Manages prompt evaluation, Manager/Worker reasoning loops, web search execution, and message pipeline orchestration. |
| `storage.py` | Data Persistence | SQLite database operations (`buddy.db`), managing `conversations`, `messages`, and `user_profile` records. |
| `tools.py` | Execution | System control scripts (AppleScript, subprocess, `pyautogui`) for controlling macOS features and applications. |
| `tools_schema.py` | Tool Definitions | JSON-Schema specifications passed to the LLM to define available tools and parameter constraints. |
| `instruction.py` | System Prompts | Contextual guidelines and behavior rules for the Manager and Worker roles. |

---

## ⚡ Setup & Installation

### 1. Requirements
Ensure you have Python 3.10+ installed on macOS.

### 2. Install Dependencies
Run this in your terminal:
    
    pip install PySide6 duckduckgo_search python-dotenv pyautogui pillow

### 3. Environment Configuration
Create a `.env` file in the root directory:

    OPENROUTER_API_KEY=sk-hc-v1-your-key-here

### 4. Run Buddy
Launch the desktop application:

    python3 gui_main.py

---

## 🛠️ What Buddy Can Do

- **Web Search** — Real-time DuckDuckGo searches with parsed title, snippet, and URL synthesis.
- **App Control** — Launch, quit, force-close, minimize, maximize, and monitor installed or running Mac applications.
- **Browser Automation** — Open URLs, open/close tabs, navigate browser history (Chrome-first support).
- **System Actions** — Take screenshots, record screen, adjust master volume, toggle dark mode, lock screen, or trigger power actions (sleep, restart, shutdown).
- **Input Simulation** — Precise cursor positioning, click/drag operations, scrolling, text typing, and keyboard shortcuts.
- **Code & File Ops** — Execute Python scripts, manage project files, open workspace paths in VS Code, and handle terminal package commands.
- **Media / Spotify** — Play/pause tracks, skip songs, and launch specific playlists by name.

---

## 🔒 Safety & Permissions

- **Destructive Actions:** Power options (`restart`, `shutdown`, `log_out`) and critical file deletions require explicit user confirmation.
- **System Permissions:** macOS Accessibility, Screen Recording, and Automation permissions are required for `pyautogui` cursor control and screen features.
- **Local Database:** All conversation history, user preferences, and app state are saved locally inside `~/Library/Application Support/Buddy/buddy.db`.

---

## 💡 Config & Customization

Key operational settings, window dimensions, and model configurations can be tweaked directly in the source files:

- **UI Dimensions (`gui_main.py`):** `SIDEBAR_COLLAPSED_WIDTH = 48`, `SIDEBAR_EXPANDED_WIDTH = 200`.
- **Model Parameters (`core.py` / `main.py`):** `MANAGER_MODEL`, `WORKER_MODEL`, token limits, and `MAX_WORKER_STEPS`.
- **Database Path (`storage.py`):** Automatically initializes inside standard macOS Application Support directory.

---

## 🙌 Credits

Built with ❤️ by **Shreyansh Patra ("Shrey")** using **Hack Club's Hack AI**. Part of a series of maker projects including custom hardware (The Anypad macropad) and Python software tools.