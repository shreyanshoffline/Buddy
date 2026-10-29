# Buddy v0.9.8 fixes

## What was wrong (from the v0.9.7 screenshots)
| Symptom | Root cause | Fix |
|---|---|---|
| 33k–44k tokens for one-line tasks | Every worker request sent **all 209 tool schemas (~16k tokens)** + the full chat history | `core/budget.py`: relevance-based tool selection (~0.5–1.7k tokens), `find_tools` to load more on demand, tool results trimmed, 20k hard cap per turn |
| Chat history grows forever | Whole history resent to the Manager each turn | `compact_history()`: old messages become one cached, incremental summary; last 6 stay verbatim |
| Notes: `Can't get default folder (-1728)` | `notes_create` used `at default folder` (invalid on iCloud accounts) | Omit `at`; HTML body so the title is right; quotes can't break the script |
| Calendar: "couldn't turn that into a plan" | Manager prompt told it to *plan osascript via run_terminal_command*; terminal plugin is off, so the worker rejected, and the retry produced unlabeled output | Prompt now names the real tools and forbids osascript for native apps; `run_terminal_command` blocks it with a pointer to the right tool; rejection reason is shown instead of a dead end |
| Calendar dates | AppleScript `date "November 14, 2026 …"` breaks on non-US locales; `calendar 1` can be read-only | Dates built from numbers; first **writable** calendar; current date injected into the prompts |
| "Task successfully completed." with no data | Worker called `finish_task` with a generic summary after a read tool | `core/report.py`: read-tool results are formatted and put in the final reply |
| iMessage "text unavailable" (blamed Full Disk Access) | `text` column is NULL on new macOS; old decoder guessed the longest ASCII run | Real `attributedBody` decoder; last 14 days only; no tapbacks; Buddy is told not to blame FDA unless the tool errors |
| Work log wall of text | Everything expanded | Closed by default; one dropdown per plan / tool call |

## Files
New: `core/budget.py`, `core/report.py`, `tests/test_token_budget_fixes.py`
Changed: `core/agent.py`, `core/instruction.py`, `tools/apple_tools.py`, `tools/tools.py`, `gui/widgets/chat_bubble.py`, `tests/test_gui_smoke.py`

## Knobs (`core/budget.py`)
`TURN_TOKEN_CAP=20_000`, `WORKER_TOOL_LIMIT=14`, `RESULT_TOKEN_LIMIT=1_200`, `HISTORY_COMPACT_AT=3_500`, `KEEP_RECENT=6`

## Not covered / follow-ups
- Coding mode (`core/coding_agent.py`) keeps its own tool sets; not narrowed.
- Manager system prompt is still ~5k tokens; turn on prompt caching or trim it next.
- AppleScript was verified by unit tests on the generated script only. Run the macOS checks below once on a real Mac.

## Test on your Mac
1. `make a new note titled Haven Columbus Event`
2. `create a calendar event Haven Columbus Nov 14 7am to 8pm and another Nov 15 9am to 8pm`
3. `read my unread iMessages` (shows real text, grouped by chat)
4. `text my mom on my way` (alias still works)
5. Check the work log is closed and each call opens on click; Tokens In should be ~10k or less.
