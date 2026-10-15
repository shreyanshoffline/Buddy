"""Staged execution: a big job runs as small steps, each on the cheapest model that can do it.

Why this saves money: a single long-running heavy agent re-sends its whole growing transcript
(every file it wrote, every test log) on every call. Here each step starts from a short brief
(goal + project state + this step's instruction), so cheap tiers do the mechanical work and the
heavy tier is billed only for writing the substantial content.

Model-agnostic: pass step_fn(model, history, max_tokens, tools, timeout_ms) -> response.
"""
import json
import re
import time

from core.call_format import format_call, format_result
from core.tiers import BUDGET, LABELS, normalize_tier

REQUEST_TIMEOUT_MS = 120_000
RESULT_CHAR_LIMIT = 6000
KEEP_FULL_RESULTS = 6
MAX_ESCALATIONS = 2
NOTES_CHAR_LIMIT = 3500

_RULES = {
    "easy": ("You are the EASY worker: do exactly this mechanical step with the fewest tool calls, then call finish_task. "
             "Do not write substantial code or prose, do not explore, do not double-check beyond one quick confirmation."),
    "medium": ("You are the MEDIUM worker: carry out this step, verify by running things, and fix small problems with small edits. "
               "If you cannot fix a problem after 3 honest attempts, call finish_task with a summary starting 'BLOCKED:' that "
               "includes the exact error and file/line, so a stronger worker can take over."),
    "heavy": ("You are the HEAVY worker, used only for the hard creative part. Write the complete, working content this step asks for: "
              "full code files via code_write (each under ~300 lines, no stubs, no TODOs, consistent with the interfaces given) "
              "or the full text. Do NOT create folders, install packages, or run tests (cheaper workers do that). "
              "As soon as the content is written, call finish_task with a 1-3 sentence note of file names and public interfaces."),
}
_GENERAL_HEAVY = ("You are the HEAVY worker, used only for the hard creative part. Produce the complete content this step asks for "
                  "(write it out in full as your reply, or save it with the right tool). Then stop.")

STEP_SYSTEM = """You are Buddy, __USER__'s personal AI, executing ONE step of a larger job. {rules}

OVERALL GOAL: {goal}
{state}
Call finish_task(summary) when the step is done: 1-3 plain sentences saying what you did, plus exact paths/names the next step needs.
Never claim something works unless a tool result in THIS step shows it. If a tool says you are blocked by a permission, stop and say what to enable.
Confirm before anything destructive or irreversible. Never use sudo. Stay inside the project folder."""


def _trim(history):
    idx = [i for i, m in enumerate(history) if isinstance(m, dict) and m.get("role") == "tool"]
    for i in idx[:-KEEP_FULL_RESULTS]:
        c = history[i]["content"]
        if len(c) > 300:
            history[i]["content"] = c[:300] + " …[older output trimmed]"


def _is_blocked(result):
    return str(result).strip().lower().startswith(("buddy's", "this plugin is turned off", "this is an apple-only"))


def _usage(resp):
    u = getattr(resp, "usage", None)
    return (getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0) if u else (0, 0)


def run_step_loop(*, model, tier, system, user, tools, step_fn, execute, tracker, max_steps, max_tokens,
                  deadline, cancel_check=None, on_event=None, step_label="", allow_text=True):
    history = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = {"status": "incomplete", "summary": "", "text": "", "files": [], "folder": None, "last_check": None,
           "tools": [], "tool_log": [], "message": ""}
    seen = {}
    for n in range(1, max_steps + 1):
        if cancel_check and cancel_check():
            out.update(status="cancelled", message="Stopped. Everything written so far is saved.")
            return out
        if time.time() > deadline:
            out.update(status="timeout", message="I hit my time limit. The work so far is saved; say 'continue' to pick it up.")
            return out
        _trim(history)
        try:
            resp = step_fn(model, history, max_tokens, tools, REQUEST_TIMEOUT_MS)
        except Exception as exc:
            if exc.__class__.__name__ == "BuddyCancelled":
                out.update(status="cancelled", message="Stopped. Everything written so far is saved.")
            else:
                out.update(status="failed", message="I lost the connection to the model: %s. Say 'continue' to resume." % exc)
            return out
        t_in, t_out = _usage(resp)
        tracker.add(tier, model, t_in, t_out)
        choice = resp.choices[0]
        msg = choice.message
        calls = getattr(msg, "tool_calls", None)
        if not calls:
            text = (getattr(msg, "content", "") or "").strip()
            if getattr(choice, "finish_reason", "") == "length" and n < max_steps:
                history.append({"role": "user", "content": "Your reply was cut off. Continue in smaller pieces."})
                continue
            if text and allow_text:
                out.update(status="success", summary=text[:1500], text=text)
            else:
                out.update(status="incomplete", message="The worker replied without doing the step.")
            return out
        history.append(msg)
        for call in calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                history.append({"role": "tool", "tool_call_id": call.id,
                                "content": "Error: your tool call was cut off (too long). Split the work into smaller files or edits and retry."})
                continue
            out["tools"].append(name)
            if name.endswith("finish_task"):
                out.update(status="success", summary=str(args.get("summary", "Done.")).strip()[:1500])
                return out
            call_text = format_call(name, args)
            if on_event:
                on_event({"type": "tool_call", "name": name, "args": args, "call": call_text,
                          "tier": tier, "model": model, "step": step_label})
            t0 = time.time()
            try:
                result = execute(name, args)
            except Exception as exc:
                result = "Error running %s: %s" % (name, exc)
            dur = time.time() - t0
            text = str(result)
            ok = not text.lower().startswith(("error", "old_text not found", "edit not applied", "no such file")) \
                and not (name in ("code_run", "code_test") and not text.startswith("exit code 0"))
            if on_event:
                on_event({"type": "tool_done", "name": name, "call": call_text, "duration": dur, "ok": ok,
                          "result": format_result(text), "tier": tier})
            out["tool_log"].append({"name": name, "args": {k: str(v)[:200] for k, v in args.items()},
                                    "result": text[:300], "duration": "%.2fs" % dur})
            if name in ("code_run", "code_test"):
                out["last_check"] = (name, text.startswith("exit code 0"))
            if name in ("code_write", "code_edit") and args.get("path"):
                if args["path"] not in out["files"]:
                    out["files"].append(args["path"])
            if name == "code_new_project":
                m = re.search(r"Created project folder: (.+)", text)
                if m:
                    out["folder"] = m.group(1).strip()
            if _is_blocked(result):
                out.update(status="failed", message="I can't continue: %s" % text)
                return out
            key = (name, json.dumps(args, sort_keys=True)[:400], text[:200])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= 3:
                text += "\n[Buddy: you repeated this exact call 3 times with the same result. Change your approach.]"
            history.append({"role": "tool", "tool_call_id": call.id,
                            "content": text if len(text) <= RESULT_CHAR_LIMIT else text[:RESULT_CHAR_LIMIT] + "\n…[truncated]"})
    out.update(status="incomplete", message="Step ran out of tool calls before finishing.")
    return out


def _state_text(state):
    lines = []
    if state["folder"]:
        lines.append("PROJECT FOLDER: %s" % state["folder"])
    if state["files"]:
        lines.append("FILES WRITTEN SO FAR: " + ", ".join(state["files"][-30:]))
    if state["notes"]:
        notes = "\n".join("- %s" % n for n in state["notes"])
        lines.append("NOTES FROM EARLIER STEPS:\n" + notes[-NOTES_CHAR_LIMIT:])
    return "\n".join(lines) if lines else "(Nothing done yet.)"


def run_steps(steps, *, goal, step_fn, execute, schema, models, tracker, user_name="the user",
              tool_sets=None, kind="coding", on_event=None, cancel_check=None, deadline=None,
              full_rules=None, full_tools=None):
    """Runs steps in order, each on its tier's model with a tiny brief. Returns a result dict."""
    deadline = deadline or (time.time() + 20 * 60)
    state = {"folder": None, "files": [], "notes": []}
    outputs, all_tools, all_log, escalations = [], [], [], 0
    heavy_text = []
    total = len(steps)

    def tools_for(tier):
        names = (tool_sets or {}).get(tier)
        return [t for t in schema if names is None or t.get("function", {}).get("name") in names]

    def run_one(step, label):
        tier = normalize_tier(step.get("tier"))
        model = models[tier]
        rules = _GENERAL_HEAVY if (tier == "heavy" and kind != "coding") else _RULES[tier]
        budget = BUDGET[tier]
        tools = tools_for(tier)
        if step.get("full") and full_rules:  # single long-running step with the whole toolset
            rules = full_rules.replace("__USER__", user_name)
            budget = {"max_steps": 60, "max_tokens": 8000}
            tools = [t for t in schema if t.get("function", {}).get("name") in (full_tools or set())]
        system = STEP_SYSTEM.format(rules=rules, goal=goal, state=_state_text(state)).replace("__USER__", user_name)
        user = "STEP: %s\n\n%s" % (step.get("title", ""), step.get("instruction", ""))
        if on_event:
            on_event({"type": "step_start", "label": label, "tier": tier, "model": model, "title": step.get("title", "")})
        res = run_step_loop(model=model, tier=tier, system=system, user=user, tools=tools, step_fn=step_fn,
                            execute=execute, tracker=tracker, max_steps=budget["max_steps"],
                            max_tokens=budget["max_tokens"], deadline=deadline, cancel_check=cancel_check,
                            on_event=on_event, step_label=label, allow_text=True)
        all_tools.extend(res["tools"])
        all_log.extend(res["tool_log"])
        if on_event:
            on_event({"type": "step_done", "label": label, "tier": tier, "ok": res["status"] == "success"})
        return res

    i = 0
    while i < total:
        step = steps[i]
        tier = normalize_tier(step.get("tier"))
        label = "%d/%d" % (i + 1, total)
        res = run_one(step, label)
        if res["status"] in ("cancelled", "timeout") or (res["status"] == "failed" and _is_blocked(res["message"].replace("I can't continue: ", ""))):
            return _finish(res["status"], res["message"], state, outputs, all_tools, all_log, tracker, steps, heavy_text)
        problem = None
        if res["status"] != "success":
            problem = res["message"] or "The step did not finish."
        elif res["summary"].upper().startswith("BLOCKED"):
            problem = res["summary"]
        elif step.get("verify") and res["last_check"] and not res["last_check"][1]:
            problem = "The last %s still failed." % res["last_check"][0]
        if problem and tier != "heavy" and escalations < MAX_ESCALATIONS and not step.get("_retried"):
            escalations += 1
            fix = {"tier": "heavy", "title": "Fix: %s" % step.get("title", ""),
                   "instruction": ("A cheaper worker could not finish this step. Fix the root cause with the smallest correct edits "
                                   "(read the failing code first with code_read). Do not run tests; just fix and describe.\n"
                                   "PROBLEM REPORT:\n%s\n\nORIGINAL STEP: %s" % (problem[:3000], step.get("instruction", "")))}
            fres = run_one(fix, label + " fix")
            state["files"] += [f for f in fres["files"] if f not in state["files"]]
            if fres["status"] == "success":
                step["_retried"] = True
                continue  # rerun the same step now that the code is fixed
            problem = (problem + "\nHeavy fix attempt: " + (fres["message"] or fres["summary"]))[:1500]
        if problem:
            return _finish("incomplete", "Step %s (%s) didn't finish: %s\nEverything so far is saved. Say 'continue' and I'll retry from there."
                           % (label, step.get("title", ""), problem[:700]), state, outputs, all_tools, all_log, tracker, steps, heavy_text)
        if res["folder"]:
            state["folder"] = res["folder"]
        state["files"] += [f for f in res["files"] if f not in state["files"]]
        if res["summary"]:
            state["notes"].append("%s: %s" % (step.get("title", "")[:60], res["summary"][:600]))
        if tier == "heavy" and res["text"]:
            heavy_text.append(res["text"])
        outputs.append(res)
        i += 1
    last = outputs[-1]["summary"] if outputs else "Done."
    return _finish("success", last, state, outputs, all_tools, all_log, tracker, steps, heavy_text)


def _finish(status, message, state, outputs, tools, log, tracker, steps, heavy_text):
    plan_lines = ["%d. [%s] %s" % (i + 1, LABELS.get(normalize_tier(s.get("tier")), "?"), s.get("title", "")) for i, s in enumerate(steps)]
    return {"status": status, "summary": message, "message": message, "heavy_text": heavy_text,
            "folder": state["folder"], "files": state["files"], "tools": tools, "tool_log": log,
            "requests": tracker.requests, "tokens_in": tracker.tokens_in, "tokens_out": tracker.tokens_out,
            "plan_text": "\n".join(plan_lines), "extra_stats": tracker.stats(), "step_count": len(outputs)}
