import json
import time
 
import pyautogui
import tools.mac_tools as tools
import tools.gmail_tools as gmail_tools
from tools.mac_tools_schema import tools_schema
from instruction import Manager_instruction, Action_instruction
from models import run_manager_step, run_action_step
import storage.storage as db
 
# Ensure the database is initialized before any storage calls.
db.init_db()
 
MANAGER_MODEL = "qwen/qwen3.7-flash"
DEFAULT_WORKER_MODEL = "google/gemini-2.5-flash-lite"
 
WORKER_MODELS = {
    "simple_task": "google/gemini-2.5-flash-lite",
    "moderate_task": "google/gemini-3.5-flash-lite",
    "heavy_task": "~anthropic/claude-haiku-latest"
}
 
MANAGER_MAX_TOKENS = 600
WORKER_MAX_TOKENS = 500
MAX_PLAN_RETRIES = 1
MAX_WORKER_STEPS = 8
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
 
 
def get_manager_output(message_history):
    plan_response = run_manager_step(MANAGER_MODEL, message_history, MANAGER_MAX_TOKENS)
    manager_message = plan_response.choices[0].message
 
    # Safely extract token usage if the LLM provider returns it
    usage = getattr(plan_response, 'usage', None)
    return (manager_message.content or "").strip(), usage
 
 
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
 
 
def run_worker(plan_text, worker_model, on_event=None, cancel_check=None):
    action_history = [
        {"role": "system", "content": Action_instruction},
        {"role": "user", "content": f"Execute this plan:\n{plan_text}"}
    ]
    step_count = 0
 
    # Track stats for the Dev Chamber
    stats = {"tools": [], "tokens_in": 0, "tokens_out": 0, "requests": 0}
 
    while step_count < MAX_WORKER_STEPS:
        if cancel_check and cancel_check():
            return {"status": "cancelled", "message": "Cancelled by user.", "step_count": step_count, **stats}
        step_count += 1
        action_response = run_action_step(worker_model, action_history, WORKER_MAX_TOKENS, tools_schema)
        action_msg = action_response.choices[0].message
 
        # Accumulate usage stats
        stats["requests"] += 1
        if getattr(action_response, 'usage', None):
            stats["tokens_in"] += getattr(action_response.usage, 'prompt_tokens', 0)
            stats["tokens_out"] += getattr(action_response.usage, 'completion_tokens', 0)
 
        if not getattr(action_msg, "tool_calls", None):
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
                return {"status": "success", "summary": summary, "step_count": step_count, **stats}
 
            if on_event:
                on_event({"type": "tool_call", "name": tool_name, "args": tool_args})
 
            result = execute_tool(tool_name, tool_args)
 
            action_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })
 
    return {"status": "incomplete", "message": "Reached max steps without finishing.", "step_count": step_count, **stats}
 
 
def process_message(user_input, message_history, on_event=None, file_context=None, cancel_check=None, incognito=False):
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
        "final_plan": None
    }

    message_history.append({"role": "user", "content": user_input})

    if file_context:
        message_history.append({"role": "system", "content": file_context})

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

    attempt = 0
    while attempt <= MAX_PLAN_RETRIES:
        attempt += 1
 
        if cancel_check and cancel_check():
            reply = "Cancelled."
            message_history.append({"role": "assistant", "content": reply})
            return format_response(reply, metrics, start_time)

        if on_event:
            on_event({"type": "thinking"})
 
        manager_output, usage = get_manager_output(message_history)
 
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
 
        outcome = run_worker(plan_text, worker_model, on_event=on_event, cancel_check=cancel_check)
 
        # Merge worker metrics
        metrics["requests"] += outcome.get("requests", 0)
        metrics["tokens_in"] += outcome.get("tokens_in", 0)
        metrics["tokens_out"] += outcome.get("tokens_out", 0)
        metrics["tools_executed"].extend(outcome.get("tools", []))
 
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
            if response_title:
                response["chat_title"] = response_title
            return response
 
        elif outcome["status"] in ("incomplete", "cancelled"):
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
 
 
def _sanitize_history_for_model(history):
    sanitized = []
    for msg in history:
        clean_msg = {k: v for k, v in msg.items() if k != "tool_call_id"}
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list) and all(isinstance(item, dict) for item in tool_calls):
            clean_msg["tool_calls"] = tool_calls
        sanitized.append(clean_msg)
    return sanitized
 
 
def _ensure_conversation_title(conversation_id, user_text, response_title=None):
    current_title = db.get_conversation_title(conversation_id) or ""
    title = response_title
 
    # Only generate an automatic title when the conversation still has a default title.
    if not title and current_title.strip().lower() in ("new chat", "untitled chat", ""):
        title = generate_conversation_title(user_text)  # LLM title, falls back to truncation internally
 
    if title:
        db.touch_conversation(conversation_id, title=title)
    return title
 
def process_message_incognito(user_text, message_history, on_event=None, cancel_check=None):
    """Runs the full Manager/Worker pipeline entirely in-memory: no message
    save, no title generation, no long-term memory read/write, no attachment
    storage. `message_history` must be the running list the caller owns —
    this appends to it in place, same contract as process_message."""
    return process_message(user_text, message_history, on_event=on_event, cancel_check=cancel_check, incognito=True)


def send_and_save_message(conversation_id, user_text, on_event=None, attachments=None, cancel_check=None):
    previous_history = db.load_messages(conversation_id)

    db.save_message(conversation_id, "user", content=user_text)
    user_msg_id = db.latest_user_message_id(conversation_id)

    if attachments:
        db.save_conversation_attachments(conversation_id, user_msg_id, attachments)

    history = new_message_history() + _sanitize_history_for_model(previous_history)

    excerpts = db.find_relevant_chunks(conversation_id, user_text, limit=6)
    file_context = format_attachment_context(excerpts)

    result = process_message(user_text, history, on_event=on_event, file_context=file_context, cancel_check=cancel_check)

    assistant_metadata = None
    if result.get("plan_text") or result.get("tools_used") or result.get("stats"):
        assistant_metadata = {
            "plan_text": result.get("plan_text"),
            "tools_used": result.get("tools_used"),
            "stats": result.get("stats")
        }

    result["message_id"] = db.save_message(
        conversation_id,
        "assistant",
        content=result["reply"],
        metadata=assistant_metadata
    )

    title = _ensure_conversation_title(conversation_id, user_text, result.get("chat_title"))
    if title:
        result["chat_title"] = title
        result["title"] = title

    return result
 
def redo_assistant_response(conversation_id, user_text, on_event=None):
    """Regenerates the assistant response for the same user query and saves it as a new assistant message."""
    previous_history = db.load_messages(conversation_id)
    history = new_message_history() + _sanitize_history_for_model(previous_history)
    result = process_message(user_text, history, on_event=on_event)
 
    assistant_metadata = None
    if result.get("plan_text") or result.get("tools_used") or result.get("stats"):
        assistant_metadata = {
            "plan_text": result.get("plan_text"),
            "tools_used": result.get("tools_used"),
            "stats": result.get("stats")
        }
 
    result["message_id"] = db.save_message(
        conversation_id,
        "assistant",
        content=result["reply"],
        metadata=assistant_metadata
    )
 
    title = _ensure_conversation_title(conversation_id, user_text, result.get("chat_title"))
    if title:
        result["chat_title"] = title
        result["title"] = title
 
    return result
 
 
def get_recent_conversations(limit=5):
    """Fetches real chat history titles and IDs for the sidebar."""
    return db.list_conversations(limit=limit)


def search_conversations(query, limit=50):
    """Searches chat titles AND message content."""
    return db.search_conversations(query, limit=limit)


def set_conversation_private(conversation_id, is_private):
    db.set_conversation_private(conversation_id, is_private)
 
 
def get_conversation_title(conversation_id):
    return db.get_conversation_title(conversation_id)


def get_conversation_is_private(conversation_id):
    return db.get_conversation_is_private(conversation_id)
 
 
def create_conversation():
    return db.create_conversation(title="New chat")
 
 
def delete_conversation(conversation_id):
    db.delete_conversation(conversation_id)
 
 
def get_conversation_history(conversation_id):
    return db.load_messages_with_metadata(conversation_id)


def set_message_feedback(message_id, feedback):
    db.set_message_feedback(message_id, feedback)
 
 
def create_conversation_from_title(user_text):
    title = db.auto_title_from_first_message(user_text)
    return db.create_conversation(title=title)
 
 
def format_response(reply_text, metrics, start_time):
    """Packages the data securely for the UI Dev Chamber"""
    latency = time.time() - start_time
    return {
        "reply": reply_text,
        "plan_text": metrics["final_plan"],
        "tools_used": metrics["tools_executed"],
        "stats": {
            "Tokens In": metrics["tokens_in"],
            "Tokens Out": metrics["tokens_out"],
            "Requests": metrics["requests"],
            "Latency": f"{latency:.2f}s"
        }
    }
 
 
def new_message_history():
    return [{"role": "system", "content": Manager_instruction}]