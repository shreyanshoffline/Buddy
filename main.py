import json
import time

import tools
from tools_schema import tools_schema
from instruction import Manager_instruction, Action_instruction
from models import run_manager_step, run_action_step


# ============================================================
# GLOBAL CONFIG
# ============================================================

# --- Model selection ---
# Manager: writes plans / simple replies. Cheap model, low reasoning needs.
MANAGER_MODEL = "google/gemini-2.5-flash-lite"
# Worker: actually calls tools. Needs decent instruction-following.
WORKER_MODEL = "google/gemini-2.5-flash-lite"

# --- Token limits per call ---
MANAGER_MAX_TOKENS = 600
WORKER_MAX_TOKENS = 400

# --- Retry / step limits ---
MAX_PLAN_RETRIES = 1   # how many times the Manager gets to re-plan if the Worker rejects a plan
MAX_WORKER_STEPS = 15  # hard cap on tool-call rounds per plan, prevents infinite loops

# --- UI colors (ANSI escape codes) ---
DIM = "\033[90m"
RESET = "\033[0m"
RED = "\033[38;2;236;55;80m"
BLUE = "\033[38;2;39;118;234m"


def print_banner():
    print(f"{RED}Buddy system initialized. - Powered By Hack AI. "
          f"\n{BLUE}'Control + C' to terminate.{RESET}")


# ============================================================
# PHASE 1: MANAGER — decide RESPONSE vs PLAN
# ============================================================

def get_manager_output(message_history):
    """
    Calls the Manager model with the current conversation history.
    Returns the raw text output (still prefixed with 'RESPONSE:' or 'PLAN:').
    """
    print(f"{RED}Buddy is thinking...{RESET}", end="", flush=True)
    start_time = time.time()

    plan_response = run_manager_step(MANAGER_MODEL, message_history, MANAGER_MAX_TOKENS)
    manager_message = plan_response.choices[0].message

    # Guard: if the model returns no text content (e.g. it tried to call a tool
    # instead of replying), don't crash — fall back to an empty string so the
    # caller can handle it as an unexpected response.
    manager_output = (manager_message.content or "").strip()

    elapsed_time = time.time() - start_time
    print(f"\r{RED}Buddy thought for {elapsed_time:.1f} seconds.{RESET}          ")

    return manager_output


def parse_manager_output(manager_output):
    """
    Splits the Manager's output into a route ("response" or "plan") and the
    cleaned text. Falls back to "plan" if the model forgot the prefix.
    """
    if manager_output.startswith("RESPONSE:"):
        return "response", manager_output.replace("RESPONSE:", "").strip()

    if manager_output.startswith("PLAN:"):
        return "plan", manager_output.replace("PLAN:", "").strip()

    # Model ignored formatting instructions — treat raw text as a plan rather
    # than silently dropping it.
    return "plan", manager_output.strip()


# ============================================================
# PHASE 2: WORKER — execute plan via tool calls
# ============================================================

def execute_tool(tool_name, tool_args):
    """
    Runs a single tool by name from tools.py, catching any runtime errors so
    a bad tool call doesn't crash the whole session.
    """
    if not hasattr(tools, tool_name):
        return f"Error: Tool '{tool_name}' not found."

    try:
        func = getattr(tools, tool_name)
        return func(**tool_args)
    except Exception as e:
        return f"Error executing {tool_name}: {str(e)}"


def run_worker(plan_text):
    """
    Feeds the plan to the Worker model and lets it call tools until it either
    calls finish_task, gives up (no tool calls at all), or hits MAX_WORKER_STEPS.

    Returns a dict describing the outcome:
      {"status": "success", "summary": str}
      {"status": "rejected", "complaint": str}   -> worker refused the plan outright
      {"status": "incomplete", "message": str}   -> worker stopped talking without finishing
    """
    action_history = [
        {"role": "system", "content": Action_instruction},
        {"role": "user", "content": f"Execute this plan:\n{plan_text}"}
    ]

    step_count = 0

    while step_count < MAX_WORKER_STEPS:
        step_count += 1

        action_response = run_action_step(WORKER_MODEL, action_history, WORKER_MAX_TOKENS, tools_schema)
        action_msg = action_response.choices[0].message

        # No tool calls at all this round.
        if not getattr(action_msg, "tool_calls", None):
            if step_count == 1:
                # Worker rejected the plan on the very first turn.
                complaint = action_msg.content or "No reason given."
                return {"status": "rejected", "complaint": complaint}
            else:
                # Worker stopped without explicitly calling finish_task.
                message = action_msg.content or "Task ended without a summary."
                return {"status": "incomplete", "message": message}

        action_history.append(action_msg)

        for tool_call in action_msg.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            if tool_name == "finish_task":
                summary = tool_args.get("summary", "Task successfully completed.")
                return {"status": "success", "summary": summary}

            print(f"{DIM} -> Executing system process: {tool_name}{RESET}")
            result = execute_tool(tool_name, tool_args)

            action_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })

    # Hit MAX_WORKER_STEPS without finishing.
    return {"status": "incomplete", "message": "Reached max steps without finishing."}


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    message_history = [{"role": "system", "content": Manager_instruction}]
    print_banner()

    try:
        while True:
            user_input = input("\nUser: ")
            if user_input.lower() in ["quit", "exit"]:
                break

            message_history.append({"role": "user", "content": user_input})

            attempt = 0
            task_success = False
            plan_text = None  # tracked across retries so Phase 3 can log the failed plan

            while attempt <= MAX_PLAN_RETRIES and not task_success:
                attempt += 1

                # ---- PHASE 1: Manager decides response vs plan ----
                manager_output = get_manager_output(message_history)
                route, content = parse_manager_output(manager_output)

                if route == "response":
                    print(f"\nBuddy: {content}")
                    message_history.append({"role": "assistant", "content": content})
                    task_success = True
                    break

                plan_text = content
                print(f"{DIM}[Internal Plan: {plan_text.replace(chr(10), ' | ')}]{RESET}")

                # ---- PHASE 2: Worker executes plan ----
                outcome = run_worker(plan_text)

                if outcome["status"] == "success":
                    print(f"\nBuddy: {outcome['summary']}")
                    message_history.append({"role": "assistant", "content": outcome["summary"]})
                    task_success = True

                elif outcome["status"] == "incomplete":
                    print(f"Buddy: {outcome['message']}")
                    message_history.append({"role": "assistant", "content": outcome["message"]})
                    task_success = True  # treat as done, even though it didn't call finish_task

                else:  # "rejected"
                    # ---- PHASE 3: Self-correction ----
                    complaint = outcome["complaint"]

                    if attempt <= MAX_PLAN_RETRIES:
                        print(f"{BLUE}Buddy is refining the approach...{RESET}")
                        refinement_prompt = (
                            f"The execution agent rejected your plan with this message: '{complaint}'. "
                            "Please create a NEW PLAN that fixes this issue. Rely on direct URLs or App launching."
                        )
                        message_history.append({"role": "assistant", "content": f"PLAN:\n{plan_text}"})
                        message_history.append({"role": "user", "content": refinement_prompt})
                        # loop continues -> Manager is re-called with updated message_history
                    else:
                        print(f"\nBuddy: I'm sorry, I ran into an issue doing that. {complaint}")
                        message_history.append(
                            {"role": "assistant", "content": f"Failed task. Reason: {complaint}"}
                        )
                        task_success = True

    except KeyboardInterrupt:
        print(f"\n\n{RED}Control + C pressed. Buddy powering down. Goodbye!{RESET}")


if __name__ == "__main__":
    main()