from core import process_message, new_message_history

RED = "\033[38;2;236;55;80m"
BLUE = "\033[38;2;39;118;234m"
DIM = "\033[90m"
RESET = "\033[0m"

def handle_event(event):
    if event["type"] == "thinking":
        print(f"{RED}Buddy is thinking...{RESET}", end="", flush=True)
    elif event["type"] == "malformed_retry":
        print(f"\r{RED}Buddy: Manager returned malformed output, retrying...{RESET}")
    elif event["type"] == "plan":
        print(f"\r{DIM}[Internal Plan ({event['model']}): {event['plan'].replace(chr(10), ' | ')}]{RESET}")
    elif event["type"] == "tool_call":
        print(f"{DIM} -> Executing system process: {event['name']}({list(event['args'].values())}){RESET}")
    elif event["type"] == "refining":
        print(f"{BLUE}Buddy is refining the approach...{RESET}")

def main():
    message_history = new_message_history()
    print(f"{RED}Buddy v0.3.2 initialized.{RESET}")
    try:
        while True:
            user_input = input("\nUser: ")
            if user_input.lower() in ["quit", "exit"]:
                break
            reply = process_message(user_input, message_history, on_event=handle_event)
            print(f"\nBuddy: {reply}")
    except KeyboardInterrupt:
        print(f"\n\n{RED}Goodbye!{RESET}")

if __name__ == "__main__":
    main()