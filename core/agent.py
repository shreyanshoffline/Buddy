"""Manager -> Worker agent pipeline: talks to the LLM, parses its plan/response
output, dispatches tool calls, and runs the worker loop. Doesn't know about
conversation_id or the database directly (aside from long-term task memory,
which is model-facing context, not conversation storage) — that split lives
in conversations.py.
"""
import json
import time

import tools.tools as tools
import tools.gmail_tools as gmail_tools
from tools.tools_schema import tools_schema
from core.instruction import build_action_instruction
from models import run_manager_step, run_action_step, BuddyCancelled, extract_image_urls, message_text
from storage import db

MANAGER_MODEL = "google/gemini-3.5-flash-lite"
DEFAULT_WORKER_MODEL = "google/gemini-3.5-flash-lite"
 
WORKER_MODELS = {
    "simple_task": "google/gemini-3.5-flash-lite",
    "moderate_task": "google/gemini-3.5-flash-lite",
    "heavy_task": "google/gemini-3.8-flash",
    "vision_task": "google/gemini-3.8-flash",
    "creation_task": "google/gemini-3.1-flash-lite-image"
}
 
MANAGER_MAX_TOKENS = 600
WORKER_MAX_TOKENS = 500
MAX_PLAN_RETRIES = 1
MAX_WORKER_STEPS = 8
OVERALL_TIMEOUT_SECONDS = 150  # 2.5 min hard ceiling on a whole turn, no matter
                                # how many manager/worker steps or retries happen
MEMORY_RETRIEVAL_MIN_OVERLAP = 2
MEMORY_RETRIEVAL_LIMIT = 2

TITLE_MODEL = "google/gemini-2.5-flash-lite"  # cheap and fast, this doesn't need a smart model

def format_attachment_context(chunks):
    if not chunks:
        return None
    parts = [
        "The user has files attached to this chat. Use these excerpts when relevant. "
        "Cite the filename. If the answer is not in the excerpts, say so."
    ]
    for chunk in chunks:
        part = chunk.get("chunk_index", 0) + 1
        parts.append(f"--- {chunk['name']} (part {part}) ---\n{chunk['content']}")
    return "\n\n".join(parts)
 
 
def generate_conversation_title(user_input: str) -> str:
    """One-shot LLM title generation. Falls back to truncation if the call
    fails or returns junk (empty, way too long, etc). Used as the fallback
    inside _ensure_conversation_title when the Manager didn't emit a Title:
    tag itself."""
    title_prompt = [
        {
            "role": "system",
            "content": (
                "Summarize the user's message into a short chat title: "
                "3 to 6 words, no quotation marks, no trailing period. "
                "Reply with ONLY the title, nothing else."
            )
        },
        {"role": "user", "content": user_input}
    ]
    try:
        response = run_manager_step(TITLE_MODEL, title_prompt, 20)
        title = (response.choices[0].message.content or "").strip().strip('"').strip("'")
        if not title or len(title) > 60:
            raise ValueError("bad title")
        return title
    except Exception:
        return db.auto_title_from_first_message(user_input)
 
 
def get_manager_output(message_history, cancel_check=None, model=MANAGER_MODEL):
    plan_response = run_manager_step(model, message_history, MANAGER_MAX_TOKENS, cancel_check=cancel_check)
    manager_message = plan_response.choices[0].message
 
    # Safely extract token usage if the LLM provider returns it
    usage = getattr(plan_response, 'usage', None)
    return message_text(manager_message).strip(), usage
 
 
def parse_manager_output(manager_output):
    cleaned_output = manager_output.strip()
 
    # Force normalize legacy tags for easier parsing
    cleaned_output = cleaned_output.replace("PLAN:", "Plan:").replace("RESPONSE:", "Response:").replace("TITLE:", "Title:")
 
    title = None
    if "Title:" in cleaned_output:
        # Extract Title without disturbing Response/Plan parsing
        title_section = cleaned_output.split("Title:", 1)[1]
        if "Response:" in title_section:
            title = title_section.split("Response:", 1)[0].strip()
            cleaned_output = cleaned_output.replace(f"Title: {title}", "").strip()
        elif "Plan:" in title_section:
            title = title_section.split("Plan:", 1)[0].strip()
            cleaned_output = cleaned_output.replace(f"Title: {title}", "").strip()
        else:
            title = title_section.strip()
            cleaned_output = cleaned_output[:cleaned_output.find("Title:")].strip()
 
    # 1. If a Plan exists anywhere in the output
    if "Plan:" in cleaned_output:
        if "Response:" in cleaned_output:
            if cleaned_output.find("Response:") < cleaned_output.find("Plan:"):
                # Response came first, Plan second
                _, plan_part = cleaned_output.split("Plan:", 1)
            else:
                # Plan came first, Response second
                after_plan = cleaned_output.split("Plan:", 1)[1]
                plan_part = after_plan.split("Response:", 1)[0]
        else:
            plan_part = cleaned_output.split("Plan:", 1)[1]
 
        plan_content = plan_part.strip()
 
        # Determine worker model tag from the cleaned plan content
        selected_model = DEFAULT_WORKER_MODEL
        for tag, model in WORKER_MODELS.items():
            if plan_content.startswith(f"[{tag}]"):
                selected_model = model
                break
 
        return "plan", plan_content, selected_model, title
 
    # 2. If only a Response exists
    if "Response:" in cleaned_output:
        response_part = cleaned_output.split("Response:", 1)[1].strip()
        return "response", response_part, DEFAULT_WORKER_MODEL, title
 
    # 3. Fallback
    return "invalid", cleaned_output, DEFAULT_WORKER_MODEL, title
 
 
def execute_tool(tool_name, tool_args):
    known_tools = [name for name in dir(tools) if not name.startswith("_")]
    known_tools += [name for name in dir(gmail_tools) if not name.startswith("_")]
 
    cleaned = tool_name
    if cleaned not in known_tools:
        for known in known_tools:
            if tool_name.endswith(known):
                cleaned = known
                break
 
    for module in (tools, gmail_tools):
        if hasattr(module, cleaned):
            try:
                func = getattr(module, cleaned)
                return func(**tool_args)
            except Exception as e:
                return f"Error executing {cleaned}: {str(e)}"
    return f"Error: Tool '{tool_name}' not found."
 
 
def run_worker(plan_text, worker_model, on_event=None, cancel_check=None, deadline=None):
    action_history = [
        {"role": "system", "content": build_action_instruction(db.get_profile())},
        {"role": "user", "content": f"Execute this plan:\n{plan_text}"}
    ]
    step_count = 0
 
    # Track stats for the Dev Chamber
    stats = {"tools": [], "tool_log": [], "tokens_in": 0, "tokens_out": 0, "requests": 0}
 
    while step_count < MAX_WORKER_STEPS:
        if cancel_check and cancel_check():
            return {"status": "cancelled", "message": "Cancelled by user.", "step_count": step_count, **stats}
        if deadline and time.time() > deadline:
            return {"status": "timeout", "message": "This is taking longer than expected, so I stopped. Want me to try again?", "step_count": step_count, **stats}
        step_count += 1
        try:
            action_response = run_action_step(worker_model, action_history, WORKER_MAX_TOKENS, tools_schema, cancel_check=cancel_check)
        except BuddyCancelled:
            return {"status": "cancelled", "message": "Cancelled by user.", "step_count": step_count, **stats}
        action_msg = action_response.choices[0].message
 
        # Accumulate usage stats
        stats["requests"] += 1
        if getattr(action_response, 'usage', None):
            stats["tokens_in"] += getattr(action_response.usage, 'prompt_tokens', 0)
            stats["tokens_out"] += getattr(action_response.usage, 'completion_tokens', 0)
 
        generated_images = extract_image_urls(action_msg)
        if not getattr(action_msg, "tool_calls", None):
            if generated_images:
                return {
                    "status": "success",
                    "summary": message_text(action_msg) or "I created that image for you.",
                    "images": generated_images,
                    "step_count": step_count,
                    **stats,
                }
            if step_count == 1:
                return {"status": "rejected", "complaint": action_msg.content or "No reason given.", "step_count": step_count, **stats}
            else:
                return {"status": "incomplete", "message": action_msg.content or "Task ended without a summary.", "step_count": step_count, **stats}
 
        action_history.append(action_msg)
 
        for tool_call in action_msg.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
 
            # Record tool for the UI
            stats["tools"].append(tool_name)
 
            if tool_name == "finish_task" or tool_name.endswith("finish_task"):
                summary = tool_args.get("summary", "Task successfully completed.")
                result = {"status": "success", "summary": summary, "step_count": step_count, **stats}
                if generated_images:
                    result["images"] = generated_images
                return result
 
            if on_event:
                on_event({"type": "tool_call", "name": tool_name, "args": tool_args})
 
            tool_start = time.time()
            result = execute_tool(tool_name, tool_args)
            tool_duration = time.time() - tool_start

            result_str = str(result)
            stats["tool_log"].append({
                "name": tool_name,
                "args": tool_args,
                "result": result_str[:500] + ("…" if len(result_str) > 500 else ""),
                "duration": f"{tool_duration:.2f}s",
            })

            action_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_str
            })
 
    return {"status": "incomplete", "message": "Reached max steps without finishing.", "step_count": step_count, **stats}
 
 
def process_message(user_input, message_history, on_event=None, file_context=None, cancel_check=None, incognito=False, image_attachments=None):
    """Pure model-facing turn: takes a message + history, talks to the
    Manager/Worker pipeline, returns a result dict. Knows nothing about
    conversation_id or the database — that's send_and_save_message's job.
    If incognito=True, never reads or writes long-term memory / db."""
    start_time = time.time()

    metrics = {
        "tokens_in": 0,
        "tokens_out": 0,
        "requests": 0,
        "tools_executed": [],
        "tool_log": [],
        "final_plan": None,
        "generated_images": [],
    }

    user_message = {"role": "user", "content": user_input}
    message_history.append(user_message)

    if file_context:
        message_history.append({"role": "system", "content": file_context})

    image_attachments = [
        item for item in (image_attachments or [])
        if item.get("mime_type", "").startswith("image/") and item.get("data_url")
    ]
    if image_attachments:
        user_message["content"] = [
            {"type": "text", "text": user_input},
            *({"type": "image_url", "image_url": {"url": item["data_url"]}} for item in image_attachments),
        ]

    if not incognito:
        # --- Long-term memory retrieval (POC) ---
        memories = db.find_similar_task_memories(
            user_input, limit=MEMORY_RETRIEVAL_LIMIT, min_overlap=MEMORY_RETRIEVAL_MIN_OVERLAP
        )

        if memories:
            memory_note = "Relevant past experience (for reference, adapt as needed, don't just repeat blindly):\n"
            for mem in memories:
                memory_note += f"- Task: {mem['task_summary']}\n  What worked: {mem['outcome_summary'] or mem['plan_text']}\n"
            message_history.append({"role": "system", "content": memory_note})
        # --- end retrieval ---

    deadline = start_time + OVERALL_TIMEOUT_SECONDS

    attempt = 0
    while attempt <= MAX_PLAN_RETRIES:
        attempt += 1
 
        if cancel_check and cancel_check():
            reply = "Cancelled."
            message_history.append({"role": "assistant", "content": reply})
            return format_response(reply, metrics, start_time)

        if time.time() > deadline:
            reply = "This is taking longer than expected, so I stopped after a couple of minutes. Want me to try again?"
            message_history.append({"role": "assistant", "content": reply})
            return format_response(reply, metrics, start_time)

        if on_event:
            on_event({"type": "thinking"})
 
        try:
            manager_model = "google/gemini-3.8-flash" if image_attachments else MANAGER_MODEL
            manager_output, usage = get_manager_output(message_history, cancel_check=cancel_check, model=manager_model)
        except BuddyCancelled:
            reply = "Cancelled."
            message_history.append({"role": "assistant", "content": reply})
            return format_response(reply, metrics, start_time)
 
        metrics["requests"] += 1
        if usage:
            metrics["tokens_in"] += getattr(usage, 'prompt_tokens', 0)
            metrics["tokens_out"] += getattr(usage, 'completion_tokens', 0)
 
        route, content, worker_model, response_title = parse_manager_output(manager_output)
 
        if route == "invalid":
            if on_event:
                on_event({"type": "malformed_retry"})
            if attempt <= MAX_PLAN_RETRIES:
                continue
 
            reply = "I'm having trouble planning that. Could you rephrase?"
            message_history.append({"role": "assistant", "content": reply})
            return format_response(reply, metrics, start_time)
 
        if route == "response":
            message_history.append({"role": "assistant", "content": content})
            response = format_response(content, metrics, start_time)
            if response_title:
                response["chat_title"] = response_title
            return response
 
        # We have a plan!
        plan_text = content
        metrics["final_plan"] = f"**Plan:**\n{plan_text}"  # Format cleanly for Markdown
 
        if on_event:
            on_event({"type": "plan", "model": worker_model, "plan": plan_text})
 
        outcome = run_worker(plan_text, worker_model, on_event=on_event, cancel_check=cancel_check, deadline=deadline)
 
        # Merge worker metrics
        metrics["requests"] += outcome.get("requests", 0)
        metrics["tokens_in"] += outcome.get("tokens_in", 0)
        metrics["tokens_out"] += outcome.get("tokens_out", 0)
        metrics["tools_executed"].extend(outcome.get("tools", []))
        metrics["tool_log"].extend(outcome.get("tool_log", []))
        metrics["generated_images"] = outcome.get("images", [])
 
        if outcome["status"] == "success":
            reply = outcome["summary"]
            message_history.append({"role": "assistant", "content": reply})

            if not incognito:
                db.save_task_memory(
                    task_summary=user_input,
                    plan_text=plan_text,
                    outcome_summary=reply
                )

            response = format_response(reply, metrics, start_time)
            response["images"] = outcome.get("images", [])
            if response_title:
                response["chat_title"] = response_title
            return response
 
        elif outcome["status"] in ("incomplete", "cancelled", "timeout"):
            reply = outcome["message"]
            message_history.append({"role": "assistant", "content": reply})
            response = format_response(reply, metrics, start_time)
            if response_title:
                response["chat_title"] = response_title
            return response
 
        else:  # rejected
            complaint = outcome["complaint"]
            if attempt <= MAX_PLAN_RETRIES:
                if on_event:
                    on_event({"type": "refining"})
                refinement_prompt = (
                    f"Your previous plan was rejected by the execution agent with this message: "
                    f"'{complaint}'. The original request was: '{user_input}'. "
                    "Write a corrected Plan or Response from scratch — do not repeat the old plan."
                )
                message_history.append({"role": "user", "content": refinement_prompt})
            else:
                reply = f"I'm sorry, I ran into an issue doing that. {complaint}"
                return format_response(reply, metrics, start_time)
 
    reply = "I'm having trouble with that request."
    return format_response(reply, metrics, start_time)
 

def process_message_incognito(user_text, message_history, on_event=None, cancel_check=None, image_attachments=None):
    """Runs the full Manager/Worker pipeline entirely in-memory: no message
    save, no title generation, no long-term memory read/write, no attachment
    storage. `message_history` must be the running list the caller owns —
    this appends to it in place, same contract as process_message."""
    return process_message(user_text, message_history, on_event=on_event, cancel_check=cancel_check, incognito=True, image_attachments=image_attachments)



def format_response(reply_text, metrics, start_time):
    """Packages the data securely for the UI Dev Chamber"""
    latency = time.time() - start_time
    return {
        "reply": reply_text,
        "plan_text": metrics["final_plan"],
        "tools_used": metrics["tools_executed"],
        "tool_log": metrics["tool_log"],
        "stats": {
            "Tokens In": metrics["tokens_in"],
            "Tokens Out": metrics["tokens_out"],
            "Requests": metrics["requests"],
            "Latency": f"{latency:.2f}s"
        }
    }