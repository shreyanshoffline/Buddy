"""Coding mode: plan -> staged build/fix/upgrade (Copilot + Claude Code style, tiered for cost).

A cheap planner splits the job into steps tagged easy / medium / heavy (core/tiers.py); core/staged.py
runs each step on its tier's model with a tiny brief, so the heavy model is billed only for writing
the substantial code. If planning fails, one heavy step runs the full loop (the original behavior).

Why separate from the normal Manager -> Worker pipeline: that pipeline is tuned for quick
quick desktop actions (8 steps, 500 tokens per step, 150 s, any tool error aborts). Writing a game or
upgrading a codebase needs dozens of steps, whole files per call, real execution feedback,
and failures that are *information* (a failing test is a result, not a crash).

The loop is model-agnostic: pass `step_fn` (messages, max_tokens, schema, timeout_ms) -> response.
"""
import json
import os
import re
import time

from core.staged import run_steps
from core.tiers import CostTracker, TIER_ORDER, normalize_tier, tier_model

CODING_MAX_STEPS = 60
CODING_MAX_TOKENS = 8000
CODING_TIMEOUT_SECONDS = 20 * 60
CODING_REQUEST_TIMEOUT_MS = 120_000
RESULT_CHAR_LIMIT = 8000
KEEP_FULL_RESULTS = 8

CODING_TOOL_NAMES = {
    "code_overview", "code_read", "code_search", "code_new_project", "code_write", "code_edit",
    "code_undo", "code_changes", "code_check", "code_setup_env", "code_run", "code_test", "code_launch",
    "read_guide", "search_guides", "list_guides", "save_lesson",
    "web_search", "web_open", "web_read", "web_click", "web_type", "web_scroll", "web_back",
    "open_url", "open_in_finder", "finish_task",
}

_VERBS = ("build", "make", "create", "write", "code", "develop", "program", "refactor", "upgrade", "fix",
          "debug", "implement", "improve", "optimi", "modernize", "clean up", "add a feature", "add feature",
          "port ", "convert ", "rewrite", "review the code", "update the code", "migrate")
_OBJECTS = ("game", "app", "website", "web page", "webpage", "script", "program", "bot", "tool", "function",
            "class", "api", "code", "codebase", "repo", "project", "python", "javascript", "html", "css",
            "bug", "tests", "unit test", "cli", "module", "library", "extension", "backend", "frontend",
            "pygame", "react", "flask", "arduino", "firmware")
_NOT_CODING = ("email", "message", "text to", "reminder", "calendar", "playlist", "note ")


def looks_like_coding_task(text):
    t = (text or "").lower().strip()
    if t.startswith(("/code", "code mode")):
        return True
    if any(n in t for n in _NOT_CODING) and "code" not in t:
        return False
    has_verb = any(v in t for v in _VERBS)
    has_object = any(re.search(r"\b%s" % re.escape(o.strip()), t) for o in _OBJECTS)
    folder = bool(re.search(r"(~/|/users/|/home/)\S+", t)) and ("code" in t or "project" in t or "repo" in t)
    return (has_verb and has_object) or (folder and has_verb)


CODING_PROMPT = """You are Buddy in CODING MODE: a senior engineer who builds and upgrades software on __USER__'s computer by yourself, end to end. You write real files, run them, read the real output, and fix problems until it works. You are persistent, careful, and honest.

TOOLS: code_new_project, code_overview, code_search, code_read, code_write, code_edit, code_undo, code_changes, code_check, code_setup_env, code_run, code_test, code_launch, read_guide/search_guides, web_search + browser tools for docs, finish_task.

WORKFLOW (follow it every time)
1. Decide the location. New work: code_new_project(name) and use the returned folder. Existing code: use the folder the user named.
2. Existing code: code_overview -> code_search for the relevant symbols -> code_read the exact parts you will change. NEVER edit code you have not read. Learn the project's style and match it.
3. New work: choose the stack. Default: Python 3 (+ pygame for desktop games, run in a project .venv via code_setup_env). Use one self-contained index.html (canvas, no dependencies) when the user wants it in the browser or says web/HTML/JS. Keep GAME/APP LOGIC separate from DRAWING so logic can be tested headless. For games call read_guide("coding", section="games") first.
4. Build in layers, not one giant file: files under ~300 lines, one responsibility each (e.g. config, entities, game logic, rendering, main). Write each file completely with code_write. Never leave TODO stubs or placeholder functions.
5. After every meaningful change: code_check, then run it (code_run / code_test; use headless=true for anything with a window). Read the output. Fix the real cause, then rerun. Repeat until clean.
6. For anything with behavior, write tests or a headless simulation (scripted input for N frames; assert scores change, collisions work, game over is reachable). A program you have not run is not done.
7. Upgrading existing code: smallest correct diff with code_edit; preserve behavior; run existing tests before and after; keep unrelated code untouched; explain notable changes. Only rewrite a whole file if asked. If a change makes things worse, code_undo.
8. Finish: when everything passes, if the user wants to play/use it, code_launch it. Then call finish_task with 2-4 plain sentences: what you built or changed, where it is (full path), how to run it, and anything unverified or left out. Never claim success without a passing run in this session.

RULES
- Stay inside the project folder. No sudo. Never read or write credentials or keys; never hard-code secrets; use environment variables.
- Ask before deleting files, installing system-wide tools, pushing to git, or doing anything irreversible. Otherwise do not ask questions — make sensible decisions, state assumptions in the final summary.
- Output budget: do not paste whole files into chat. Narrate in one short line per step at most.
- If a tool result says you are blocked (permission/plugin off), stop and tell the user exactly what to enable.
- If a call fails: read the message, change approach. If the same thing fails 3 times, step back and try a different design.
- Your tool-call arguments can be cut off if too long. If you see "cut off", split the file into smaller modules.
- Teach-once: when the user states a preference (language, style, folder), call save_lesson.
"""



EASY_TOOLS = {"code_new_project", "code_write", "code_setup_env", "code_run", "code_overview", "code_read",
              "code_launch", "code_check", "open_url", "open_in_finder", "finish_task"}
MEDIUM_TOOLS = EASY_TOOLS | {"code_edit", "code_search", "code_test", "code_undo", "code_changes", "read_guide",
                             "search_guides", "list_guides", "web_search", "save_lesson"}
HEAVY_TOOLS = {"code_write", "code_edit", "code_read", "code_search", "code_overview", "code_check", "code_undo",
               "read_guide", "search_guides", "web_search", "finish_task"}
TOOL_SETS = {"easy": EASY_TOOLS, "medium": MEDIUM_TOOLS, "heavy": HEAVY_TOOLS}

PLANNER_PROMPT = """You are the planning manager for a coding job. Split the task into ordered steps and give each step to the CHEAPEST tier that can do it well. Output ONE JSON object and nothing else.

TIERS
- easy: mechanical actions with no creativity: create the project folder, create empty folders/files, set up the virtual environment and install dependencies, run one command, launch the finished program, open something.
- medium: small writing and glue: short config/README/requirements files, short test files, running tests/checks and fixing simple errors, small edits, renames, reading code to summarize what must change.
- heavy: writing the substantial new code or long prose: real logic modules, a game loop, algorithms, a rewrite of a complicated function. The heavy worker ONLY writes content; it never creates folders, installs, or runs tests.

RULES
- Each step's "instruction" must be fully self-contained: exact file paths relative to the project, the public classes/functions with signatures that other files depend on, and the key behaviours. The heavy worker sees only its instruction plus short notes, not the conversation.
- A heavy step writes at most 3 files. Split big programs into several heavy steps (e.g. game logic, then rendering + main loop).
- Final step: tier medium, "verify": true: run syntax check and tests (headless for games), fix small problems, and finish with how to run it. Add a short tests step before it when the project has behaviour worth testing.
- Small tasks need only 1-3 steps. Upgrading existing code: first a medium step that reads the relevant files and reports exactly what must change, then heavy/medium edit steps, then verify.
- Never put an easy step's work in a heavy step.
- For games or apps, tell the heavy step to read_guide("coding", section="games") first when relevant.

FORMAT
{"project_name": "short_snake_case_name", "steps": [{"tier": "easy|medium|heavy", "title": "short title", "instruction": "...", "verify": false}]}

EXAMPLE for "create flappy bird in python":
{"project_name": "flappy_bird", "steps": [
 {"tier": "easy", "title": "Create project folder", "instruction": "Call code_new_project('flappy_bird') and report the path."},
 {"tier": "easy", "title": "Set up environment", "instruction": "Call code_setup_env(<folder>, 'pygame') to create .venv with pygame."},
 {"tier": "heavy", "title": "Write game logic", "instruction": "Create game.py with no pygame imports: class Game(seed=None) with update(dt, flap: bool), fields bird_y, bird_vy, pipes (list of dicts with x, gap_y), score, state ('playing'|'game_over'), reset(). Gravity, flap impulse, pipe spawning every ~1.6s, gap 150px, scoring when a pipe passes, collision with pipes/ground/ceiling."},
 {"tier": "heavy", "title": "Write rendering and main loop", "instruction": "Create render.py with draw(screen, game, font) and main.py with main(max_frames=None): 60 FPS loop, SPACE flaps, R restarts, ESC quits, hi-score saved to .hiscore."},
 {"tier": "medium", "title": "Write tests", "instruction": "Create tests/test_game.py (unittest) covering gravity, flap, scoring, collisions, game over, plus a 60s random-input soak."},
 {"tier": "medium", "title": "Verify and fix", "verify": true, "instruction": "code_check the project, code_test, run main(max_frames=120) headless with code_run(headless=true), fix small problems, finish with the exact run command."}
]}"""


def _find_folder(text):
    for m in re.finditer(r"(~?/[^\s'\"`,;]+(?:\s[^\s'\"`,;/]+)*)", text or ""):
        cand = os.path.expanduser(m.group(1).rstrip(".,)"))
        while cand and cand != "/" and not os.path.isdir(cand):
            cand = os.path.dirname(cand)
        if cand and cand not in ("/", os.path.expanduser("~")) and os.path.isdir(cand):
            return cand
    return None


def _memory_note(message_history):
    for m in reversed(message_history or []):
        if isinstance(m, dict) and m.get("role") == "system" and str(m.get("content", "")).startswith("Memory layers"):
            return m["content"]
    return ""


def _recent_turns(message_history, user_input="", n=4):
    turns = [m for m in (message_history or [])
             if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
    if turns and turns[-1]["role"] == "user" and turns[-1]["content"] == user_input:
        turns = turns[:-1]
    return [{"role": m["role"], "content": m["content"][:1200]} for m in turns[-n:]]


def parse_plan(text):
    """Planner JSON -> list of step dicts, or None if unusable."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    steps = []
    for raw in (data.get("steps") or [])[:10]:
        if not isinstance(raw, dict) or not raw.get("instruction"):
            continue
        steps.append({"tier": normalize_tier(raw.get("tier")), "title": str(raw.get("title") or "Step")[:80],
                      "instruction": str(raw["instruction"]), "verify": bool(raw.get("verify"))})
    return steps or None


def plan_coding_task(user_input, message_history, plan_fn, execute, model, tracker, deadline_ok=lambda: True):
    folder = _find_folder(user_input)
    context = []
    note = _memory_note(message_history)
    if note:
        context.append(note)
    if folder:
        try:
            context.append("EXISTING FOLDER (overview):\n" + str(execute("code_overview", {"folder": folder}))[:3000])
        except Exception:
            pass
    history = [{"role": "system", "content": PLANNER_PROMPT + ("\n\n" + "\n\n".join(context) if context else "")},
               *_recent_turns(message_history, user_input), {"role": "user", "content": user_input}]
    try:
        resp = plan_fn(model, history, 2500)
    except Exception:
        return None
    u = getattr(resp, "usage", None)
    tracker.add("medium", model, getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
    return parse_plan(getattr(resp.choices[0].message, "content", "") or "")


def _is_blocked(result):
    return str(result).strip().lower().startswith(("buddy's", "this plugin is turned off", "this is an apple-only"))


def run_coding_agent(user_input, message_history, step_fn, execute, schema, plan_fn=None, models=None,
                     user_name="the user", on_event=None, cancel_check=None,
                     timeout_seconds=CODING_TIMEOUT_SECONDS):
    """step_fn(model, history, max_tokens, tools, timeout_ms); plan_fn(model, history, max_tokens)."""
    models = models or {t: tier_model(t) for t in TIER_ORDER}
    tracker = CostTracker(heavy_model=models["heavy"])
    deadline = time.time() + timeout_seconds
    steps = None
    if plan_fn:
        if on_event:
            on_event({"type": "thinking"})
        steps = plan_coding_task(user_input, message_history, plan_fn, execute, models["medium"], tracker)
    full_loop = steps is None
    if full_loop:  # planner unavailable or unusable: one heavy worker with the complete toolset
        steps = [{"tier": "heavy", "title": "Build it", "instruction": user_input, "full": True}]
    if on_event:
        on_event({"type": "plan", "model": models["heavy"] if full_loop else models["medium"],
                  "plan": "\n".join("%d. [%s] %s" % (i + 1, s["tier"], s["title"]) for i, s in enumerate(steps))})
    result = run_steps(steps, goal=user_input, step_fn=step_fn, execute=execute, schema=schema, models=models,
                       tracker=tracker, user_name=user_name, tool_sets=TOOL_SETS, kind="coding",
                       on_event=on_event, cancel_check=cancel_check, deadline=deadline,
                       full_rules=CODING_PROMPT, full_tools=CODING_TOOL_NAMES)
    summary = result["summary"]
    if result["status"] == "success" and result["folder"] and result["folder"] not in summary:
        summary += "\n\nProject folder: %s" % result["folder"]
    result["summary"] = result["message"] = summary
    return result
