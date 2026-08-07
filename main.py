import json
import time

import tools
from tools_schema import tools_schema
from instruction import Manager_instruction, Action_instruction
from models import run_manager_step, run_action_step


# ============================================================
# GLOBAL CONFIG
# ============================================================

MANAGER_MODEL = "google/gemini-2.5-flash-lite"
DEFAULT_WORKER_MODEL = "google/gemini-2.5-flash-lite"

WORKER_MODELS = {
    "simple_task": "google/gemini-2.5-flash-lite",
    "moderate_task": "google/gemini-3.5-flash-lite",
    "heavy_task": "~anthropic/claude-haiku-latest"
}

MANAGER_MAX_TOKENS = 600
WORKER_MAX_TOKENS = 500

MAX_PLAN_RETRIES = 1   
MAX_WORKER_STEPS = 15  

DIM = "\033[90m"
RESET = "\033[0m"
RED = "\033[38;2;236;55;80m"
BLUE = "\033[38;2;39;118;234m"


def print_banner():
    print(f"{RED}Buddy v0.0.3 initialized. - Powered By Hack AI."
          f"\n{BLUE}'Control + C' to terminate.{RESET}")


# ============================================================
# PHASE 1: MANAGER — decide RESPONSE vs PLAN
# ============================================================

def get_manager_output(message_history):
    print(f"{RED}Buddy is thinking...{RESET}", end="", flush=True)
    start_time = time.time()

    plan_response = run_manager_step(MANAGER_MODEL, message_history, MANAGER_MAX_TOKENS)
    manager_message = plan_response.choices[0].message
    manager_output = (manager_message.content or "").strip()

    elapsed_time = time.time() - start_time
    print(f"\r{RED}Buddy thought for {elapsed_time:.1f} seconds.{RESET}          ")

    return manager_output


def parse_manager_output(manager_output):
    """
    Returns: (route_type, content, selected_worker_model)
    """
    cleaned_output = manager_output.strip()

    if cleaned_output.startswith("RESPONSE:"):
        return "response", cleaned_output.removeprefix("RESPONSE:").strip(), DEFAULT_WORKER_MODEL

    if cleaned_output.startswith("PLAN:"):
        plan_content = cleaned_output.removeprefix("PLAN:").strip()
        selected_model = DEFAULT_WORKER_MODEL

        # Dynamically route model based on classification tag
        for tag, model in WORKER_MODELS.items():
            if plan_content.startswith(f"[{tag}]"):
                selected_model = model
                break

        return "plan", plan_content, selected_model

    # Fallback if no prefix provided
    return "plan", cleaned_output, DEFAULT_WORKER_MODEL


# ============================================================
# PHASE 2: WORKER — execute plan via tool calls
# ============================================================

def execute_tool(tool_name, tool_args):
    if not hasattr(tools, tool_name):
        return f"Error: Tool '{tool_name}' not found."

    try:
        func = getattr(tools, tool_name)
        return func(**tool_args)
    except Exception as e:
        return f"Error executing {tool_name}: {str(e)}"


def run_worker(plan_text, worker_model):
    """
    Accepts worker_model dynamically selected by Manager.
    """
    action_history = [
        {"role": "system", "content": Action_instruction},
        {"role": "user", "content": f"Execute this plan:\n{plan_text}"}
    ]

    step_count = 0

    while step_count < MAX_WORKER_STEPS:
        step_count += 1

        action_response = run_action_step(worker_model, action_history, WORKER_MAX_TOKENS, tools_schema)
        action_msg = action_response.choices[0].message

        if not getattr(action_msg, "tool_calls", None):
            if step_count == 1:
                complaint = action_msg.content or "No reason given."
                return {"status": "rejected", "complaint": complaint}
            else:
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
            plan_text = None

            while attempt <= MAX_PLAN_RETRIES and not task_success:
                attempt += 1

                # ---- PHASE 1: Manager decides response vs plan ----
                manager_output = get_manager_output(message_history)
                route, content, worker_model = parse_manager_output(manager_output)

                if route == "response":
                    print(f"\nBuddy: {content}")
                    message_history.append({"role": "assistant", "content": content})
                    task_success = True
                    break

                plan_text = content
                print(f"{DIM}[Internal Plan ({worker_model}): {plan_text.replace(chr(10), ' | ')}]{RESET}")

                # ---- PHASE 2: Worker executes plan ----
                outcome = run_worker(plan_text, worker_model)

                if outcome["status"] == "success":
                    print(f"\nBuddy: {outcome['summary']}")
                    message_history.append({"role": "assistant", "content": outcome["summary"]})
                    task_success = True

                elif outcome["status"] == "incomplete":
                    print(f"Buddy: {outcome['message']}")
                    message_history.append({"role": "assistant", "content": outcome["message"]})
                    task_success = True

                else:  # "rejected"
                    # ---- PHASE 3: Self-correction ----
                    complaint = outcome["complaint"]

                    if attempt <= MAX_PLAN_RETRIES:
                        print(f"{BLUE}Buddy is refining the approach...{RESET}")
                        # Removed hardcoded instruction constraint
                        refinement_prompt = (
                            f"The execution agent rejected your plan with this message: '{complaint}'. "
                            "Please create a NEW PLAN that addresses this exact failure."
                        )
                        message_history.append({"role": "assistant", "content": f"PLAN:\n{plan_text}"})
                        message_history.append({"role": "user", "content": refinement_prompt})
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