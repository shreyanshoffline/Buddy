from openrouter import OpenRouter
from dotenv import load_dotenv
import os
import time
import base64
import mimetypes

load_dotenv()

_client_cache = {"key": None, "client": None}


def _get_client():
    """Returns a client using the user's own API key (set in Settings) if
    they've provided one, otherwise falls back to the app's default key.
    Rebuilds the client only when the key actually changes."""
    api_key = os.getenv("API_KEY")
    try:
        # Lazy import: storage.db imports this module for embeddings, so a
        # top-level import here would be circular. By the time this function
        # actually runs, both modules are fully loaded.
        from storage import db
        profile = db.get_profile()
        custom_key = (profile or {}).get("byo_api_key")
        if custom_key:
            api_key = custom_key
    except Exception:
        pass  # storage not ready yet (e.g. very first import) — use the env default

    if _client_cache["key"] != api_key:
        _client_cache["client"] = OpenRouter(api_key=api_key, server_url=os.getenv("SERVER_URL"))
        _client_cache["key"] = api_key
    return _client_cache["client"]


MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds; doubles each attempt
REQUEST_TIMEOUT_MS = 30_000  # hard ceiling per network call — nothing hangs forever
CANCEL_POLL_INTERVAL = 0.25  # seconds; how often we check cancel_check during backoff sleeps


class BuddyCancelled(Exception):
    """Raised when cancel_check() returns True mid-retry, so callers can
    distinguish 'user cancelled' from a real error."""
    pass


def _sleep_cancellable(seconds, cancel_check):
    """Sleeps in small increments so a cancel is noticed quickly instead of
    waiting out the full backoff delay."""
    elapsed = 0.0
    while elapsed < seconds:
        if cancel_check and cancel_check():
            raise BuddyCancelled()
        chunk = min(CANCEL_POLL_INTERVAL, seconds - elapsed)
        time.sleep(chunk)
        elapsed += chunk


def _with_retry(fn, cancel_check=None):
    """Call fn(), retrying on rate-limit (429) or transient errors.
    Every attempt is bounded by REQUEST_TIMEOUT_MS, so a stuck/silent
    connection can no longer hang forever. If cancel_check() becomes True
    between attempts, raises BuddyCancelled immediately."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        if cancel_check and cancel_check():
            raise BuddyCancelled()
        try:
            return fn()
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            is_rate_limit = "429" in msg or "rate limit" in msg or "too many" in msg
            is_transient = "500" in msg or "502" in msg or "503" in msg or "timeout" in msg
            if (is_rate_limit or is_transient) and attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                _sleep_cancellable(delay, cancel_check)
                continue
            raise
    raise last_exc


EMBED_MODEL = "openai/text-embedding-3-small"


def embed_texts(texts, cancel_check=None):
    """Returns a list of embedding vectors for the given texts.
    NOTE: assumes an OpenAI-compatible embeddings endpoint
    (client.embeddings.create -> response.data[i].embedding).
    If Hack AI's OpenRouter SDK exposes this differently, this is the
    only function that needs to change — nothing else depends on the shape."""
    if not texts:
        return []
    response = _with_retry(
        lambda: _get_client().embeddings.create(model=EMBED_MODEL, input=texts, timeout_ms=REQUEST_TIMEOUT_MS),
        cancel_check=cancel_check,
    )
    return [item.embedding for item in response.data]


def run_manager_step(model, message_history, max_tokens, cancel_check=None):
    return _with_retry(
        lambda: _get_client().chat.send(
            model=model,
            messages=message_history,
            max_tokens=max_tokens,
            reasoning={"enabled": False},
            timeout_ms=REQUEST_TIMEOUT_MS,
        ),
        cancel_check=cancel_check,
    )


def image_data_url(path):
    """Encode a local image as an OpenAI-compatible data URL."""
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_image_urls(message):
    """Collect image URLs from common OpenAI/OpenRouter response shapes."""
    found = []
    candidates = [getattr(message, "images", None), getattr(message, "content", None)]
    for candidate in candidates:
        items = candidate if isinstance(candidate, list) else [candidate]
        for item in items:
            if isinstance(item, str):
                continue
            if not isinstance(item, dict):
                continue
            image_url = item.get("image_url") or item.get("image")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            if isinstance(image_url, str) and image_url not in found:
                found.append(image_url)
    return found


def message_text(message):
    """Normalize text content from string or multimodal response parts."""
    content = getattr(message, "content", "") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
    return str(content)


def run_action_step(model, message_history, max_tokens, tools, cancel_check=None):
    return _with_retry(
        lambda: _get_client().chat.send(
            model=model,
            messages=message_history,
            max_tokens=max_tokens,
            tools=tools,
            timeout_ms=REQUEST_TIMEOUT_MS,
        ),
        cancel_check=cancel_check,
    )


def run_image_generation(model, prompt, source_images=None, cancel_check=None):
    """Generates (or edits, given source_images) an image via a Gemini
    image model on OpenRouter. Returns a list of base64 data-URL strings."""
    content = [{"type": "text", "text": prompt}]
    for url in (source_images or []):
        content.append({"type": "image_url", "image_url": {"url": url}})

    response = _with_retry(
        lambda: _get_client().chat.send(
            model=model,
            messages=[{"role": "user", "content": content}],
            modalities=["image", "text"],
            timeout_ms=REQUEST_TIMEOUT_MS,
        ),
        cancel_check=cancel_check,
    )
    message = response.choices[0].message
    return extract_image_urls(message)