"""Thinking levels for Buddy.

Low / Medium / High / Extra / MAX. Medium is the default.

These use the same model IDs already in core/agent.py. A level only changes
how hard a turn works (model, tokens, worker steps, timeout). Image
generation still uses the image model.
"""
from storage import db
from core.model_config import load_model_config, worker_model_for_effort

LEVELS = ("low", "medium", "high", "extra", "max")
LEVEL_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "extra": "Extra",
    "max": "MAX",
}

# Real IDs from the current agent — do not invent new model names here.
FLASH_LITE_25 = "google/gemini-2.5-flash-lite"
FLASH_LITE_35 = "google/gemini-3.5-flash-lite"
FLASH_38 = "google/gemini-3.8-flash"

CONFIG = {
    "low": {
        "manager": FLASH_LITE_25,
        "worker": FLASH_LITE_25,
        "deep": FLASH_LITE_25,
        "max_tokens": 350,
        "max_steps": 4,
        "timeout": 60,
    },
    "medium": {
        "manager": FLASH_LITE_35,
        "worker": FLASH_LITE_35,
        "deep": FLASH_LITE_35,
        "max_tokens": 500,
        "max_steps": 8,
        "timeout": 150,
    },
    "high": {
        "manager": FLASH_LITE_35,
        "worker": FLASH_38,
        "deep": FLASH_LITE_35,
        "max_tokens": 700,
        "max_steps": 10,
        "timeout": 180,
    },
    "extra": {
        "manager": FLASH_38,
        "worker": FLASH_38,
        "deep": FLASH_38,
        "max_tokens": 900,
        "max_steps": 12,
        "timeout": 210,
    },
    "max": {
        "manager": FLASH_38,
        "worker": FLASH_38,
        "deep": FLASH_38,
        "max_tokens": 1200,
        "max_steps": 16,
        "timeout": 240,
    },
}


def _normalize(value):
    key = (value or "medium").strip().lower()
    return key if key in LEVELS else "medium"


def stored_thinking_level():
    profile = db.get_profile() or {}
    return _normalize(profile.get("thinking_level"))


def is_manual():
    profile = db.get_profile() or {}
    return bool(profile.get("thinking_level_manual"))


def credits_are_low():
    profile = db.get_profile() or {}
    if profile.get("credits_low"):
        return True
    try:
        remaining = profile.get("credits_remaining")
        if remaining is None:
            return False
        return float(remaining) <= 0.05
    except (TypeError, ValueError):
        return False


def should_auto_low():
    if is_manual():
        return False
    profile = db.get_profile() or {}
    tier = (profile.get("subscription_tier") or "free").strip().lower()
    if tier not in ("free", "", "none"):
        return False
    return credits_are_low()


def effective_thinking_level():
    if should_auto_low():
        return "low"
    return stored_thinking_level()


def set_thinking_level(level, manual=True):
    db.update_profile(
        thinking_level=_normalize(level),
        thinking_level_manual=1 if manual else 0,
    )


def thinking_config():
    level = effective_thinking_level()
    config = dict(CONFIG[level])
    model_config = load_model_config()
    config["manager"] = model_config["manager"]
    config["worker"] = worker_model_for_effort(level)
    config["deep"] = model_config["chat"]
    return config


def listening_model():
    profile = db.get_profile() or {}
    value = (profile.get("listening_model") or "gemini").strip().lower()
    return value if value in ("gemini", "whisper") else "gemini"


def speaking_model():
    profile = db.get_profile() or {}
    value = (profile.get("speaking_model") or "system").strip().lower()
    return value if value in ("system", "inworld") else "system"


def set_listening_model(value):
    db.update_profile(listening_model="whisper" if value == "whisper" else "gemini")


def set_speaking_model(value):
    db.update_profile(speaking_model="inworld" if value == "inworld" else "system")
