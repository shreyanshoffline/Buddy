from openrouter import OpenRouter
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenRouter(
    api_key=os.getenv("HACK_AI_API_KEY"),
    server_url="https://ai.hackclub.com/proxy/v1",
)


def run_manager_step(model, message_history, max_tokens):
    
    plan_response = client.chat.send(
    model=model,
    messages=message_history,
    max_tokens=max_tokens,
    reasoning={"enabled": False}
    )
    return plan_response
def run_action_step(model, message_history, max_tokens, tools):
    action_response = client.chat.send(
    model=model,
    messages=message_history,
    max_tokens=max_tokens,
    tools=tools
    )
    return action_response
