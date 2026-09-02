"""Dynamic theme engine. Reads the user's saved accent color + dark/light
mode preference (Settings > Appearance) and computes every color/typography
token the rest of the GUI uses. Everything below is derived from ONE hero
accent color per theme, so hovers, pressed states, and backgrounds all stay
visually consistent no matter which theme is active.

Changing the theme in Settings takes effect on next launch — this module
computes its constants once, at import time, from whatever was saved.
"""
import core

# ---------------------------------------------------------------------------
# Hack Club official palette. Red is the hero; the rest are supporting
# accents — any one of them can be the user's chosen "hero" for their own
# theme. "Muted" is included as a calm, neutral option for anyone who wants
# minimal color.
# ---------------------------------------------------------------------------
ACCENTS = {
    "red":    "#ec3750",
    "orange": "#ff8c37",
    "yellow": "#f1c40f",
    "green":  "#33d6a6",
    "cyan":   "#5bc0de",
    "blue":   "#338eda",
    "purple": "#a633d6",
    "muted":  "#8492a6",
}
ACCENT_LABELS = {
    "red": "Hack Club Red", "orange": "Orange", "yellow": "Yellow",
    "green": "Green", "cyan": "Cyan", "blue": "Blue",
    "purple": "Purple", "muted": "Muted",
}
# Ordered for the Settings swatch row.
THEME_OPTIONS = [(k, ACCENT_LABELS[k], v) for k, v in ACCENTS.items()]
DEFAULT_ACCENT = "blue"


# ---------------------------------------------------------------------------
# Color math — small, dependency-free helpers for deriving hover/pressed/
# soft-tint variants from a single hero color, and for picking accessible
# text color on top of it.
# ---------------------------------------------------------------------------
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _blend(hex_color, target_rgb, ratio):
    r1, g1, b1 = _hex_to_rgb(hex_color)
    r2, g2, b2 = target_rgb
    return _rgb_to_hex((
        r1 + (r2 - r1) * ratio,
        g1 + (g2 - g1) * ratio,
        b1 + (b2 - b1) * ratio,
    ))


def _tint(hex_color, ratio):
    """Blend toward white — soft, light backgrounds."""
    return _blend(hex_color, (255, 255, 255), ratio)


def _shade(hex_color, ratio):
    """Blend toward black — darker hover/pressed states."""
    return _blend(hex_color, (0, 0, 0), ratio)


def _luminance(hex_color):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(hex1, hex2):
    l1, l2 = _luminance(hex1), _luminance(hex2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _accessible_text_on(hex_color, dark_candidate="#1f2937"):
    """Picks white or dark text on top of hex_color, whichever gives
    better contrast — so bright accents (yellow, cyan, green...) never end
    up with unreadable white-on-light-yellow text."""
    return "#ffffff" if _contrast(hex_color, "#ffffff") >= _contrast(hex_color, dark_candidate) else dark_candidate


# ---------------------------------------------------------------------------
# Theme builder
# ---------------------------------------------------------------------------
def get_theme(accent_key="blue", dark_mode=False):
    accent = ACCENTS.get(accent_key, ACCENTS[DEFAULT_ACCENT])

    if not dark_mode:
        theme = {
            "accent": accent,
            "accent_hover": _shade(accent, 0.12),
            "accent_pressed": _shade(accent, 0.24),
            "accent_soft": _tint(accent, 0.88),        # icon-button hover bg
            "accent_soft_pressed": _tint(accent, 0.78),  # icon-button pressed bg
            "text_primary": "#1f2937",
            "text_secondary": "#5f6b7a",
            "text_muted": "#8a8a8e",
            "window_bg_top": _tint(accent, 0.975),
            "window_bg_mid": _tint(accent, 0.93),
            "window_bg_bottom": _tint(accent, 0.87),
            "page_bg_top": "#ffffff",
            "page_bg_mid": _tint(accent, 0.965),
            "page_bg_bottom": _tint(accent, 0.93),
            "card_bg_top": "#ffffff",
            "card_bg_mid": _tint(accent, 0.97),
            "card_bg_bottom": _tint(accent, 0.94),
            "section_bg": _tint(accent, 0.955),
            "border_color": "rgba(0, 0, 0, 0.08)",
            "sidebar_bg": "rgba(248, 249, 251, 0.75)",
            "input_bg": "#ffffff",
            "input_border": "rgba(0, 0, 0, 0.08)",
            "chat_bubble_agent": "rgba(255, 255, 255, 0.92)",
            "chat_bubble_agent_text": "#1f2937",
            "danger": "#c0392b",
            "danger_soft": "#fdecea",
            "danger_border": "#f5c6cb",
        }
    else:
        theme = {
            "accent": accent,
            "accent_hover": _tint(accent, 0.15),
            "accent_pressed": _tint(accent, 0.30),
            "accent_soft": _blend(accent, (34, 37, 43), 0.82),
            "accent_soft_pressed": _blend(accent, (34, 37, 43), 0.68),
            "text_primary": "#e8e9ec",
            "text_secondary": "#a0a8b4",
            "text_muted": "#6b7280",
            "window_bg_top": "#22252b",
            "window_bg_mid": "#1c1f24",
            "window_bg_bottom": "#16181c",
            "page_bg_top": "#1e2126",
            "page_bg_mid": "#1a1d21",
            "page_bg_bottom": "#16181c",
            "card_bg_top": "#24272d",
            "card_bg_mid": "#1f2226",
            "card_bg_bottom": "#1a1c20",
            "section_bg": "#2a2d33",
            "border_color": "rgba(255, 255, 255, 0.08)",
            "sidebar_bg": "rgba(28, 30, 35, 0.75)",
            "input_bg": "#26292f",
            "input_border": "rgba(255, 255, 255, 0.09)",
            "chat_bubble_agent": "rgba(255, 255, 255, 0.06)",
            "chat_bubble_agent_text": "#e8e9ec",
            "danger": "#ff6b6b",
            "danger_soft": "rgba(255, 107, 107, 0.12)",
            "danger_border": "rgba(255, 107, 107, 0.35)",
        }

    theme["accent_key"] = accent_key
    theme["dark_mode"] = dark_mode
    theme["chat_bubble_user"] = accent
    theme["chat_bubble_user_text"] = _accessible_text_on(accent, dark_candidate="#1f2937")
    theme["on_accent_text"] = theme["chat_bubble_user_text"]  # text color for anything with accent as its bg
    return theme


# ---------------------------------------------------------------------------
# Read the saved preference and compute every constant the rest of the app
# imports. Everything below this line is what actually gets consumed.
# ---------------------------------------------------------------------------
try:
    _profile = core.get_profile()
    _accent_key = _profile.get("theme_color") or DEFAULT_ACCENT
    if _accent_key not in ACCENTS:
        _accent_key = DEFAULT_ACCENT
    _dark_mode = bool(_profile.get("dark_mode"))
except Exception:
    _accent_key = DEFAULT_ACCENT
    _dark_mode = False

CURRENT_ACCENT = _accent_key
CURRENT_DARK_MODE = _dark_mode
_T = get_theme(_accent_key, _dark_mode)

# --- Typography (same scale regardless of color theme) ---
FONT_FAMILY = ".AppleSystemUIFont"
FONT_FAMILY_FALLBACK = "Helvetica Neue"

WINDOW_TITLE_TEXT = "Buddy v1.0.0"
WINDOW_TITLE_SIZE = 18
WINDOW_TITLE_WEIGHT = 600
GREETING_FONT_SIZE = 24
SUBTITLE_FONT_SIZE = 12
BODY_FONT_SIZE = 14
CAPTION_FONT_SIZE = 11
BUTTON_FONT_SIZE = 13
BUTTON_FONT_WEIGHT = 600
CARD_TEXT_SIZE = 26
CARD_TEXT_WEIGHT = 700
CARD_SUBTITLE_SIZE = 13

# --- Window chrome ---
WINDOW_TITLE_COLOR = _T["text_secondary"]
WINDOW_HEADER_HEIGHT = 42
WINDOW_HEADER_PADDING_TOP = 8
WINDOW_HEADER_PADDING_RIGHT = 14
WINDOW_HEADER_PADDING_BOTTOM = 8
WINDOW_HEADER_PADDING_LEFT = 18
WINDOW_CLOSE_BUTTON_SIZE = 24
WINDOW_CLOSE_BUTTON_COLOR = _T["text_secondary"]
WINDOW_CLOSE_BUTTON_HOVER_BG = _T["accent_soft"]
WINDOW_CLOSE_BUTTON_HOVER_COLOR = _T["text_primary"]
WINDOW_CLOSE_BUTTON_FONT_SIZE = 14

# --- Sidebar ---
SIDEBAR_COLLAPSED_WIDTH = 50
SIDEBAR_EXPANDED_WIDTH = 125
ICON_SIZE = 18
SIDEBAR_ANIM_MS = 170
SIDEBAR_BG = _T["sidebar_bg"]

MAX_REDOS = 3

# --- The single consistent hover/pressed language used EVERYWHERE ---
# Icon-only / neutral buttons (close, attach, sidebar nav, bubble footer
# icons, delete icons...) all hover to the same soft accent tint, and press
# to a slightly stronger version of that same tint. Primary CTA buttons
# (Send, Save, primary actions) use the accent itself with its own
# hover/pressed shades. Two clear, consistent visual languages — not one
# button hovering grey and another hovering blue.
HOVER_BG_COLOR = _T["accent_soft"]
PRESSED_BG_COLOR = _T["accent_soft_pressed"]
ACTIVE_BG_COLOR = _T["accent_soft"]

PRIMARY_COLOR = _T["accent"]
PRIMARY_COLOR_DARK = _T["accent_hover"]
PRIMARY_COLOR_PRESSED = _T["accent_pressed"]
ON_PRIMARY_TEXT = _T["on_accent_text"]

DANGER_COLOR = _T["danger"]
DANGER_SOFT_BG = _T["danger_soft"]
DANGER_BORDER = _T["danger_border"]

TEXT_COLOR_DARK = _T["text_primary"]
TEXT_COLOR_MUTED = _T["text_muted"]
TEXT_COLOR_SUBTITLE = _T["text_secondary"]
BORDER_COLOR = _T["border_color"]
CONTAINER_BG = _T["card_bg_top"]
CARD_BG_TOP = _T["card_bg_top"]
CARD_BG_MID = _T["card_bg_mid"]
CARD_BG_BOTTOM = _T["card_bg_bottom"]
SECTION_CARD_BG = _T["section_bg"]

WINDOW_BG_TOP = _T["window_bg_top"]
WINDOW_BG_MID = _T["window_bg_mid"]
WINDOW_BG_BOTTOM = _T["window_bg_bottom"]
PAGE_BG_TOP = _T["page_bg_top"]
PAGE_BG_MID = _T["page_bg_mid"]
PAGE_BG_BOTTOM = _T["page_bg_bottom"]

CARD_TEXT_COLOR = _T["text_primary"]
CARD_SUBTITLE_COLOR = _T["text_secondary"]

INPUT_BG = _T["input_bg"]
INPUT_BORDER = _T["input_border"]

CHAT_BUBBLE_USER = _T["chat_bubble_user"]
CHAT_BUBBLE_USER_TEXT = _T["chat_bubble_user_text"]
CHAT_BUBBLE_AGENT = _T["chat_bubble_agent"]
CHAT_BUBBLE_AGENT_TEXT = _T["chat_bubble_agent_text"]

GREETING_COLOR = _T["text_primary"]

# --- Window sizing ---
WINDOW_MIN_WIDTH = 340
WINDOW_MIN_HEIGHT = 400
WINDOW_DEFAULT_WIDTH = 420
WINDOW_DEFAULT_HEIGHT = 520

# --- Control sizing ---
SEND_BUTTON_SIZE = 36
SEND_BUTTON_RADIUS = 18
INPUT_CONTAINER_HEIGHT = 50
SIZE_GRIP_SIZE = 48