"""Coding mode: a long-running build/fix/upgrade loop (Copilot + Claude Code style).

Why separate from the normal Manager -> Worker pipeline: that pipeline is tuned for quick
Mac actions (8 steps, 500 tokens per step, 150 s, any tool error aborts). Writing a game or
upgrading a codebase needs dozens of steps, whole files per call, real execution feedback,
and failures that are *information* (a failing test is a result, not a crash).

The loop is model-agnostic: pass `step_fn` (messages, max_tokens, schema, timeout_ms) -> response.
"""
import json
import re
import time

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


CODING_PROMPT = """You are Buddy in CODING MODE: a senior engineer who builds and upgrades software on __USER__'s Mac by yourself, end to end. You write real files, run them, read the real output, and fix problems until it works. You are persistent, careful, and honest.

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


def _result_text(r):
    s = str(r)
    return s if len(s) <= RESULT_CHAR_LIMIT else s[:RESULT_CHAR_LIMIT] + "\n…[output truncated]"


def _trim_history(history):
    tool_idx = [i for i, m in enumerate(history) if isinstance(m, dict) and m.get("role") == "tool"]
    for i in tool_idx[:-KEEP_FULL_RESULTS]:
        c = history[i]["content"]
        if len(c) > 300:
            history[i]["content"] = c[:300] + " …[older output trimmed]"


def _memory_note(message_history):
    for m in reversed(message_history or []):
        if isinstance(m, dict) and m.get("role") == "system" and str(m.get("content", "")).startswith("Memory layers"):
            return m["content"]
    return ""


def _recent_turns(message_history, user_input="", n=6):
    turns = [m for m in (message_history or [])
             if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
    if turns and turns[-1]["role"] == "user" and turns[-1]["content"] == user_input:
        turns = turns[:-1]  # the current request is added separately
    return [{"role": m["role"], "content": m["content"][:1500]} for m in turns[-n:]]


def _is_blocked(result):
    low = str(result).strip().lower()
    return low.startswith(("buddy's", "this plugin is turned off", "this is an apple-only"))


def run_coding_agent(user_input, message_history, step_fn, execute, schema, user_name="the user",
                     on_event=None, cancel_check=None, max_steps=CODING_MAX_STEPS,
                     timeout_seconds=CODING_TIMEOUT_SECONDS):
    tools = [t for t in schema if t.get("function", {}).get("name") in CODING_TOOL_NAMES]
    system = CODING_PROMPT.replace("__USER__", user_name or "the user")
    note = _memory_note(message_history)
    if note:
        system += "\n" + note
    history = [{"role": "system", "content": system}, *_recent_turns(message_history, user_input),
               {"role": "user", "content": user_input}]
    stats = {"tools": [], "tool_log": [], "tokens_in": 0, "tokens_out": 0, "requests": 0}
    deadline = time.time() + timeout_seconds
    seen = {}

    def done(status, **kw):
        return {"status": status, "step_count": step, **stats, **kw}

    step = 0
    while step < max_steps:
        step += 1
        if cancel_check and cancel_check():
            return done("cancelled", message="Stopped. Everything written so far is saved in the project folder.")
        if time.time() > deadline:
            return done("timeout", message="I hit my time limit on this build. The work so far is saved; say 'continue' and I'll pick it up.")
        _trim_history(history)
        try:
            resp = step_fn(history, CODING_MAX_TOKENS, tools, CODING_REQUEST_TIMEOUT_MS)
        except Exception as exc:  # BuddyCancelled and network errors surface here
            if exc.__class__.__name__ == "BuddyCancelled":
                return done("cancelled", message="Stopped. Everything written so far is saved in the project folder.")
            return done("failed", message="I lost the connection to the model: %s. Say 'continue' to resume." % exc)
        stats["requests"] += 1
        usage = getattr(resp, "usage", None)
        if usage:
            stats["tokens_in"] += getattr(usage, "prompt_tokens", 0) or 0
            stats["tokens_out"] += getattr(usage, "completion_tokens", 0) or 0
        choice = resp.choices[0]
        msg = choice.message
        calls = getattr(msg, "tool_calls", None)
        if not calls:
            text = (getattr(msg, "content", "") or "").strip()
            if getattr(choice, "finish_reason", "") == "length" and step < max_steps:
                history.append({"role": "user", "content": "Your reply was cut off. Continue with smaller steps."})
                continue
            return done("success" if step > 1 else "incomplete", summary=text or "Done.", message=text or "Done.")
        history.append(msg)
        for call in calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                history.append({"role": "tool", "tool_call_id": call.id,
                                "content": "Error: your tool call was cut off (too long). Split the work into smaller files/edits and retry."})
                continue
            stats["tools"].append(name)
            if name.endswith("finish_task"):
                return done("success", summary=str(args.get("summary", "Done.")).strip())
            if on_event:
                on_event({"type": "tool_call", "name": name, "args": {k: (str(v)[:80]) for k, v in args.items()}})
            t0 = time.time()
            try:
                result = execute(name, args)
            except Exception as exc:  # a tool crash is feedback for the model, not the end
                result = "Error running %s: %s" % (name, exc)
            if on_event:
                on_event({"type": "tool_done", "name": name, "duration": time.time() - t0,
                          "ok": not str(result).lower().startswith(("error", "exit code 1", "old_text not found"))})
            text = _result_text(result)
            stats["tool_log"].append({"name": name, "args": {k: str(v)[:120] for k, v in args.items()},
                                      "result": text[:300], "duration": "%.2fs" % (time.time() - t0)})
            if _is_blocked(result):
                return done("failed", message="I can't continue: %s" % text)
            key = (name, json.dumps(args, sort_keys=True)[:400], text[:200])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= 3:
                text += "\n[Buddy: you have repeated this exact call 3 times with the same result. Change your approach.]"
            history.append({"role": "tool", "tool_call_id": call.id, "content": text})
    last = stats["tool_log"][-1]["result"] if stats["tool_log"] else ""
    return done("incomplete", message=("I reached my step limit before finishing. Everything so far is saved in the project folder. "
                                       "Last result: %s\nSay 'continue' and I'll keep going." % last))
