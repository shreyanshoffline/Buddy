from openrouter import OpenRouter
from dotenv import load_dotenv
import os
import time

load_dotenv()
client = OpenRouter(
    api_key=os.getenv("API_KEY"),
    server_url=os.getenv("SERVER_URL"),
)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds; doubles each attempt


def _with_retry(fn):
    """Call fn(), retrying on rate-limit (429) or transient errors."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            is_rate_limit = "429" in msg or "rate limit" in msg or "too many" in msg
            is_transient = "500" in msg or "502" in msg or "503" in msg or "timeout" in msg
            if (is_rate_limit or is_transient) and attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                time.sleep(delay)
                continue
            raise
    raise last_exc


def run_manager_step(model, message_history, max_tokens):
    return _with_retry(lambda: client.chat.send(
        model=model,
        messages=message_history,
        max_tokens=max_tokens,
        reasoning={"enabled": False}
    ))


def run_action_step(model, message_history, max_tokens, tools):
    return _with_retry(lambda: client.chat.send(
        model=model,
        messages=message_history,
        max_tokens=max_tokens,
        tools=tools
    ))