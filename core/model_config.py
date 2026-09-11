"""User-editable model routing for Buddy.

The UI stores model IDs as plain JSON in the local profile. The routing is
deliberately small and explicit: one chat model, one manager, three effort
branches, and two image paths. Unknown/custom model IDs are allowed so users
can use another model available through their configured provider.
"""
import json

from storage import db


DEFAULT_MODEL_CONFIG = {
    "chat": "google/gemini-2.5-flash-lite",
    "manager": "google/gemini-3.5-flash-lite",
    "easy": "google/gemini-2.5-flash-lite",
    "medium": "google/gemini-3.5-flash-lite",
    "hard": "google/gemini-3.8-flash",
    "image_create": "google/gemini-3.1-flash-lite-image",
    "image_edit": "google/gemini-3.1-flash-lite-image",
}

MODEL_FIELDS = (
    "chat",
    "manager",
    "easy",
    "medium",
    "hard",
    "image_create",
    "image_edit",
)

MODEL_FIELD_LABELS = {
    "chat": "Chat model",
    "manager": "Manager model",
    "easy": "Easy tasks",
    "medium": "Medium tasks",
    "hard": "Hard tasks",
    "image_create": "Create images",
    "image_edit": "Edit images",
}

# These are the model IDs Buddy already uses or has already been configured
# to use. The editable combo boxes also accept a custom model ID.
MODEL_OPTIONS = (
    "google/gemini-2.5-flash-lite",
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.5-flash-lite",
    "google/gemini-3.8-flash",
)

MODEL_LABELS = {
    "google/gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    "google/gemini-3.1-flash-lite-image": "Gemini 3.1 Flash Lite Image",
    "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
    "google/gemini-3.8-flash": "Gemini 3.8 Flash",
}


def _read_saved_config():
    raw = (db.get_profile() or {}).get("model_config_json") or ""
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else {}


def load_model_config():
    config = dict(DEFAULT_MODEL_CONFIG)
    saved = _read_saved_config()
    for key in MODEL_FIELDS:
        value = saved.get(key)
        if isinstance(value, str) and value.strip():
            config[key] = value.strip()
    return config


def display_model_name(model_id):
    return MODEL_LABELS.get(model_id, model_id)


def save_model_config(config):
    current = load_model_config()
    for key in MODEL_FIELDS:
        value = (config or {}).get(key)
        if isinstance(value, str) and value.strip():
            current[key] = value.strip()
    db.update_profile(model_config_json=json.dumps(current, sort_keys=True))
    return current


def set_model(field, model_id):
    if field not in MODEL_FIELDS:
        raise ValueError("Unknown model route: %s" % field)
    config = load_model_config()
    config[field] = (model_id or "").strip() or DEFAULT_MODEL_CONFIG[field]
    return save_model_config(config)


def worker_model_for_effort(level):
    """Map the existing effort control to the simple three task branches."""
    key = (level or "medium").strip().lower()
    if key == "low":
        route = "easy"
    elif key in ("high", "extra", "max"):
        route = "hard"
    else:
        route = "medium"
    return load_model_config()[route]


def image_model(source_images=False):
    config = load_model_config()
    return config["image_edit" if source_images else "image_create"]
