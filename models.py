from openrouter import OpenRouter
from dotenv import load_dotenv
import os
import time
import base64
import mimetypes
from urllib.parse import urljoin

import requests

load_dotenv()

_client_cache = {"key": None, "client": None}


class ProviderConfigurationError(RuntimeError):
    """A provider is unavailable or missing the configuration it needs."""


class _AttrDict(dict):
    """Dict that also supports the attribute access used by OpenRouter's SDK."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _as_response(value):
    if isinstance(value, dict):
        return _AttrDict({key: _as_response(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_as_response(item) for item in value]
    return value


def provider_mode():
    """Return the active text provider without requiring an app restart in tests.

    ``openrouter`` is deliberately the default so existing installs behave
    exactly as before. ``self_hosted`` speaks to any OpenAI-compatible server,
    including llama.cpp, vLLM, Ollama, or a Buddy server in front of them.
    """
    value = (os.getenv("BUDDY_AI_PROVIDER") or os.getenv("BUDDY_PROVIDER") or "openrouter").strip().lower()
    if value in {"self_hosted", "self-hosted", "selfhosted", "local", "free", "llama.cpp", "llamacpp"}:
        return "self_hosted"
    return "openrouter"


def using_self_hosted_provider():
    return provider_mode() == "self_hosted"


def provider_info():
    """Small, UI/log-safe description of the active provider."""
    if using_self_hosted_provider():
        return {
            "id": "self_hosted",
            "label": "Self-hosted model",
            "url": (os.getenv("BUDDY_SELF_HOSTED_URL") or "").rstrip("/"),
            "model": os.getenv("BUDDY_SELF_HOSTED_MODEL") or "configured server model",
        }
    return {"id": "openrouter", "label": "OpenRouter", "url": os.getenv("SERVER_URL") or "", "model": "per-route"}


class _LocalChat:
    def __init__(self, client):
        self._client = client

    def send(self, *, model=None, messages=None, max_tokens=None, tools=None, timeout_ms=None, modalities=None, **_kwargs):
        if modalities and "image" in modalities:
            raise ProviderConfigurationError(
                "The self-hosted provider is text-only. Set BUDDY_IMAGE_PROVIDER=openrouter for image generation."
            )
        payload = {
            "model": self._client.model(model),
            "messages": messages or [],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
        return self._client.post("/chat/completions", payload, timeout_ms=timeout_ms)


class _LocalEmbeddings:
    def __init__(self, client):
        self._client = client

    def create(self, *, model=None, input=None, timeout_ms=None, **_kwargs):
        if not self._client.embedding_model:
            raise ProviderConfigurationError(
                "No self-hosted embedding model is configured; Buddy will use keyword memory retrieval."
            )
        return self._client.post(
            "/embeddings",
            {"model": self._client.embedding_model, "input": input or []},
            timeout_ms=timeout_ms,
        )


class _OpenAICompatibleClient:
    """Tiny adapter for llama.cpp/vLLM/Ollama-compatible chat endpoints.

    The rest of Buddy only sees the same response shape as the OpenRouter SDK,
    keeping provider selection out of the agent, coding, and UI layers.
    """

    def __init__(self):
        self.base_url = (os.getenv("BUDDY_SELF_HOSTED_URL") or "").strip().rstrip("/")
        self.api_key = (os.getenv("BUDDY_SELF_HOSTED_API_KEY") or "").strip()
        self.embedding_model = (os.getenv("BUDDY_SELF_HOSTED_EMBEDDING_MODEL") or "").strip()
        if not self.base_url:
            raise ProviderConfigurationError(
                "Self-hosted mode is enabled, but BUDDY_SELF_HOSTED_URL is empty."
            )
        self.chat = _LocalChat(self)
        self.embeddings = _LocalEmbeddings(self)

    def model(self, requested):
        return (os.getenv("BUDDY_SELF_HOSTED_MODEL") or requested or "buddy").strip()

    def post(self, path, payload, timeout_ms=None):
        url = self.base_url if self.base_url.endswith(path) else urljoin(self.base_url + "/", path.lstrip("/"))
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        timeout = max(1.0, (timeout_ms or REQUEST_TIMEOUT_MS) / 1000.0)
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            raise RuntimeError("Self-hosted model request failed: %s" % exc) from exc
        if not response.ok:
            detail = response.text[:500].replace("\n", " ")
            raise RuntimeError("Self-hosted model returned HTTP %s: %s" % (response.status_code, detail))
        try:
            return _as_response(response.json())
        except ValueError as exc:
            raise RuntimeError("Self-hosted model returned invalid JSON.") from exc


def _get_client():
    """Return the configured text client, keeping provider details in one place."""
    if using_self_hosted_provider():
        cache_key = (
            "self_hosted",
            os.getenv("BUDDY_SELF_HOSTED_URL", ""),
            os.getenv("BUDDY_SELF_HOSTED_MODEL", ""),
            os.getenv("BUDDY_SELF_HOSTED_API_KEY", ""),
            os.getenv("BUDDY_SELF_HOSTED_EMBEDDING_MODEL", ""),
        )
        if _client_cache["key"] != cache_key:
            _client_cache["client"] = _OpenAICompatibleClient()
            _client_cache["key"] = cache_key
        return _client_cache["client"]

    return _get_openrouter_client()


def _get_openrouter_client():
    """Return OpenRouter's client using the user's key when available."""
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

    cache_key = ("openrouter", api_key, os.getenv("SERVER_URL", ""))
    if _client_cache["key"] != cache_key:
        _client_cache["client"] = OpenRouter(api_key=api_key, server_url=os.getenv("SERVER_URL"))
        _client_cache["key"] = cache_key
    return _client_cache["client"]


MAX_RETRIES = max(1, int(os.getenv("BUDDY_MAX_MODEL_RETRIES", "2")))
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


def validate_api_key(api_key):
    """Cheap live check used by Settings after the user pastes a key."""
    key = (api_key or "").strip()
    if not key:
        return False, "No API key entered."
    try:
        client = OpenRouter(api_key=key, server_url=os.getenv("SERVER_URL"))
        client.chat.send(
            model="google/gemini-2.5-flash-lite",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
            timeout_ms=12_000,
        )
        return True, "Key works."
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "unauthorized" in msg.lower():
            return False, "That key was rejected."
        if "429" in msg or "rate" in msg.lower():
            return True, "Key accepted (rate limited on the test call)."
        return False, msg[:160]


def embed_texts(texts, cancel_check=None):
    """Returns a list of embedding vectors for the given texts.
    NOTE: assumes an OpenAI-compatible embeddings endpoint
    (client.embeddings.create -> response.data[i].embedding).
    If Hack AI's OpenRouter SDK exposes this differently, this is the
    only function that needs to change — nothing else depends on the shape."""
    if not texts:
        return []
    if using_self_hosted_provider() and not os.getenv("BUDDY_SELF_HOSTED_EMBEDDING_MODEL"):
        # Memory retrieval remains available through its existing keyword
        # fallback. Do not make a free text-only deployment depend on a paid
        # embedding API or turn a missing optional service into a crash.
        raise ProviderConfigurationError(
            "No self-hosted embedding model configured; use keyword retrieval."
        )
    embedding_model = (
        os.getenv("BUDDY_SELF_HOSTED_EMBEDDING_MODEL", "")
        if using_self_hosted_provider()
        else EMBED_MODEL
    ) or EMBED_MODEL
    try:
        from storage import db
        cached = db.get_cached_embeddings(texts, model=embedding_model)
    except Exception:
        cached = {}
    missing = [text for text in texts if text not in cached]
    if missing:
        response = _with_retry(
            lambda: _get_client().embeddings.create(model=embedding_model, input=missing, timeout_ms=REQUEST_TIMEOUT_MS),
            cancel_check=cancel_check,
        )
        fresh = [item.embedding for item in response.data]
        try:
            from storage import db
            db.save_cached_embeddings(missing, fresh, model=embedding_model)
        except Exception:
            pass
        cached.update(dict(zip(missing, fresh)))
    return [cached[text] for text in texts]


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


def run_action_step(model, message_history, max_tokens, tools, cancel_check=None, timeout_ms=None):
    return _with_retry(
        lambda: _get_client().chat.send(
            model=model,
            messages=message_history,
            max_tokens=max_tokens,
            tools=tools,
            timeout_ms=timeout_ms or REQUEST_TIMEOUT_MS,
        ),
        cancel_check=cancel_check,
    )


def run_image_generation(model, prompt, source_images=None, cancel_check=None):
    """Generates (or edits, given source_images) an image via a Gemini
    image model on OpenRouter. Returns a list of base64 data-URL strings."""
    content = [{"type": "text", "text": prompt}]
    for url in (source_images or []):
        content.append({"type": "image_url", "image_url": {"url": url}})

    image_provider = (os.getenv("BUDDY_IMAGE_PROVIDER") or "openrouter").strip().lower()
    client = _get_client() if image_provider in {"self_hosted", "self-hosted", "local"} else _get_openrouter_client()
    response = _with_retry(
        lambda: client.chat.send(
            model=model,
            messages=[{"role": "user", "content": content}],
            modalities=["image", "text"],
            timeout_ms=REQUEST_TIMEOUT_MS,
        ),
        cancel_check=cancel_check,
    )
    message = response.choices[0].message
    return extract_image_urls(message)
