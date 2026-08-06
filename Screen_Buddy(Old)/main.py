"""
Screen Buddy — v3.0
A privacy-friendly macOS desktop companion with:
  • Surface climbing  — floor, ceiling, left wall, right wall
  • Edge snapping     — drag near any screen edge to grab it
  • Hugging Face AI   — context-aware break reminders via free Inference API
  • App + URL tracking— osascript reads frontmost app and active browser tab
  • Session timing    — tracks how long you've been in each app
  • Async AI calls    — never freezes the UI
  • Sprite rotation   — pet visually rotates to match its surface
"""

import sys, os, math, random, time, threading, subprocess
from datetime import datetime
from collections import defaultdict

import requests                                     # pip install requests

# Optional: pyobjc gives us direct access to NSStatusWindowLevel (menu-bar
# layer — highest level below the screen saver).  Falls back gracefully to
# the numeric constant (25) if pyobjc isn't installed.
# pip install pyobjc-framework-Cocoa
try:
    from AppKit import NSApp, NSStatusWindowLevel   # type: ignore
    _HAS_APPKIT = True
except ImportError:
    _HAS_APPKIT = False
    NSStatusWindowLevel = 25   # same numeric value on all modern macOS
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMenu, QWidget, QVBoxLayout,
    QSystemTrayIcon, QGraphicsOpacityEffect,
)
from PyQt6.QtGui  import (
    QPixmap, QCursor, QColor, QPainter, QIcon,
    QTransform,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QPropertyAnimation,
    QEasingCurve, QPointF, pyqtSignal, QObject,
)

# ── Config ─────────────────────────────────────────────────────────────────────

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))

# ★ Put your Hugging Face token here (free at hf.co → Settings → Tokens)
HF_TOKEN = ""

# Model — fast, free, good at short instructions. Swap freely.
HF_MODEL  = "mistralai/Mistral-7B-Instruct-v0.3"
HF_URL    = f"https://api-inference.huggingface.co/models/{HF_MODEL}"

# How often to ask the AI for a break assessment (minutes)
AI_CHECK_INTERVAL_MIN = 12

# Snap distance — how close to an edge (px) before the pet grabs it
EDGE_SNAP_PX = 48

# Physics
WALK_SPEED      = 2.5
GRAVITY         = 0.65
BOUNCE_DAMPING  = 0.46
WALL_DAMPING    = 0.55
MIN_BOUNCE_VEL  = 1.8
FLOOR_MARGIN    = 4
VEL_SAMPLE_MS   = 80

# Surfaces the pet can cling to
SURFACE_FLOOR   = "floor"
SURFACE_CEILING = "ceiling"
SURFACE_LEFT    = "left"
SURFACE_RIGHT   = "right"
SURFACE_FALLING = "falling"   # not clinging to anything

TIPS_BY_TIME = {
    "morning":   ["Good morning! Plan your top 3 tasks. 📋",
                  "Hydrate before caffeine! 💧",
                  "Stand up and stretch before diving in. 🌅"],
    "afternoon": ["Drink some water! 💧",
                  "Remember to save your work! 💾",
                  "Eyes tired? Try the 20-20-20 rule. 👀",
                  "Eat something if you haven't. 🍎"],
    "evening":   ["Almost done! Document what you finished. 📝",
                  "Wrap up — your brain needs rest. 🌙",
                  "Commit your code before closing. 💻"],
}
IDLE_THOUGHTS = ["...", "( ᵕ—ᵕ)", "(˘ω˘)", "zz?", "♪", "(・_・)"]

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_time_period():
    h = datetime.now().hour
    return "morning" if h < 12 else ("afternoon" if h < 18 else "evening")

def load_custom_tips():
    path = os.path.join(ASSET_DIR, "tips.txt")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]

def get_safe_screen(pos):
    s = QApplication.screenAt(pos)
    return s or QApplication.primaryScreen()

def ms():
    return time.monotonic() * 1000.0

# ── macOS Activity Tracker ─────────────────────────────────────────────────────

class ActivityTracker:
    """
    Polls the frontmost app every 10 s using osascript (no extra permissions
    beyond Accessibility for browser URL reading).

    browser_url() requires:  System Preferences → Privacy → Accessibility
    → grant Terminal (or your app) access.   Falls back gracefully if denied.
    """

    BROWSER_SCRIPTS = {
        "Google Chrome": 'tell app "Google Chrome" to get URL of active tab of front window',
        "Brave Browser": 'tell app "Brave Browser" to get URL of active tab of front window',
        "Safari":        'tell app "Safari" to get URL of current tab of front window',
        "Firefox":       'tell app "Firefox" to get URL of active tab of front window',
        "Arc":           'tell app "Arc" to get URL of active tab of front window',
        "Microsoft Edge":'tell app "Microsoft Edge" to get URL of active tab of front window',
    }

    def __init__(self):
        self._lock         = threading.Lock()
        self._current_app  = "Unknown"
        self._current_url  = ""
        # app_name → cumulative seconds today
        self._app_time: dict[str, float] = defaultdict(float)
        self._last_switch  = time.monotonic()
        self._last_reset   = datetime.now().date()

        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def _run_script(self, script: str) -> str:
        try:
            r = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=3
            )
            return r.stdout.strip()
        except Exception:
            return ""

    def _get_frontmost_app(self) -> str:
        return self._run_script(
            'tell application "System Events" to get name of first process '
            'whose frontmost is true'
        ) or "Unknown"

    def _get_browser_url(self, app: str) -> str:
        script = self.BROWSER_SCRIPTS.get(app)
        if not script:
            return ""
        return self._run_script(script)

    def _poll_loop(self):
        while True:
            # Reset daily totals at midnight
            today = datetime.now().date()
            with self._lock:
                if today != self._last_reset:
                    self._app_time.clear()
                    self._last_reset = today

            app = self._get_frontmost_app()
            url = self._get_browser_url(app)
            now = time.monotonic()

            with self._lock:
                elapsed = now - self._last_switch
                self._app_time[self._current_app] += elapsed
                self._last_switch = now
                self._current_app = app
                self._current_url = url

            time.sleep(10)

    def snapshot(self) -> dict:
        """Return a JSON-serialisable summary for the AI prompt."""
        with self._lock:
            # Flush current session into totals
            now = time.monotonic()
            elapsed = now - self._last_switch
            totals  = dict(self._app_time)
            totals[self._current_app] = totals.get(self._current_app, 0) + elapsed

            top = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:6]
            return {
                "current_app":     self._current_app,
                "current_url":     self._current_url,
                "time_of_day":     get_time_period(),
                "top_apps_minutes": [
                    {"app": a, "minutes": round(s / 60, 1)}
                    for a, s in top if a not in ("", "Unknown", "loginwindow")
                ],
            }


# ── Hugging Face AI Worker ─────────────────────────────────────────────────────

class AIWorker(QObject):
    """
    Sends usage context to HF inference API in a background thread.
    Emits result_ready(str) on the Qt thread when done.
    """
    result_ready = pyqtSignal(str)

    def __init__(self, tracker: ActivityTracker):
        super().__init__()
        self._tracker = tracker
        self._busy    = False

    def request_assessment(self):
        if self._busy:
            return
        self._busy = True
        snapshot = self._tracker.snapshot()
        t = threading.Thread(target=self._call_hf, args=(snapshot,), daemon=True)
        t.start()

    def _call_hf(self, snapshot: dict):
        try:
            result = self._build_and_call(snapshot)
        except Exception as e:
            result = f"(AI unavailable: {e})"
        self._busy = False
        self.result_ready.emit(result)

    def _build_and_call(self, snapshot: dict) -> str:
        # Summarise usage for the prompt
        app_lines = "\n".join(
            f"  • {e['app']}: {e['minutes']} min"
            for e in snapshot["top_apps_minutes"]
        ) or "  • No data yet"

        url_line = f"\nCurrent URL: {snapshot['current_url']}" if snapshot["current_url"] else ""

        prompt = (
            f"[INST] You are a friendly, concise productivity buddy living on someone's desktop. "
            f"They are using their computer right now. Here is their activity summary:\n\n"
            f"Current app: {snapshot['current_app']}{url_line}\n"
            f"Time of day: {snapshot['time_of_day']}\n"
            f"Today's app usage:\n{app_lines}\n\n"
            f"In 1-2 short sentences (max 120 chars total), give them one piece of advice. "
            f"If they've been in one app a long time, suggest a break or switch. "
            f"Be warm and slightly playful. No bullet points. No preamble. [/INST]"
        )

        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 80,
                "temperature": 0.7,
                "return_full_text": False,
                "stop": ["[INST]", "</s>"],
            },
            "options": {"wait_for_model": True},
        }

        resp = requests.post(HF_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list) and data:
            text = data[0].get("generated_text", "").strip()
        elif isinstance(data, dict):
            text = data.get("generated_text", "").strip()
        else:
            text = str(data)

        # Strip any prompt echo if the model included it
        if "[/INST]" in text:
            text = text.split("[/INST]")[-1].strip()

        return text[:200] if text else "Take a short break! 🌿"


# ── Thought Bubble ─────────────────────────────────────────────────────────────

class QuietBubble(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(260)
        self.label.setStyleSheet("""
            QLabel {
                background-color: #FFFDF7;
                color: #2d2d2d;
                border: 1.5px solid #c8c0b0;
                border-radius: 14px;
                padding: 7px 14px;
                font-family: 'SF Pro Rounded', 'Helvetica Neue', sans-serif;
                font-size: 12px;
                font-weight: 500;
            }
        """)
        self._layout.addWidget(self.label)

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(0.0)

        self._fin  = self._anim(0.0, 1.0, 220)
        self._fout = self._anim(1.0, 0.0, 500)
        self._fout.finished.connect(self.hide)

        self._htimer = QTimer(self, singleShot=True)
        self._htimer.timeout.connect(self._fade_out)

    def _anim(self, s, e, ms_dur):
        a = QPropertyAnimation(self._fx, b"opacity", self)
        a.setStartValue(s); a.setEndValue(e)
        a.setDuration(ms_dur)
        a.setEasingCurve(QEasingCurve.Type.InOutQuad)
        return a

    def showEvent(self, ev):
        super().showEvent(ev)
        wh = self.windowHandle()
        if wh:
            wh.setProperty("NSWindowLevel", NSStatusWindowLevel)
        if _HAS_APPKIT:
            for win in NSApp().windows():
                win.setLevel_(NSStatusWindowLevel)

    def show_thought(self, text: str, duration: int = 4000):
        self._htimer.stop(); self._fout.stop()
        self.label.setText(text)
        self.adjustSize()
        self._fx.setOpacity(0.0)
        self.show(); self._fin.start()
        self._htimer.start(duration)

    def _fade_out(self):
        self._fin.stop(); self._fout.start()

    def dismiss(self):
        self._htimer.stop(); self._fade_out()


# ── Screen Buddy ───────────────────────────────────────────────────────────────

class ScreenBuddy(QLabel):
    """
    States:   idle | walk_left | walk_right | sleeping | falling | climbing
    Surfaces: floor | ceiling | left | right | falling

    Surface logic:
      • Pet always "falls" toward its surface (gravity direction depends on surface)
      • Dragging near an edge within EDGE_SNAP_PX snaps and grabs that edge
      • Pet can walk along whichever surface it's clinging to
      • Sprite is rotated to match orientation
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Assets
        self.asset_paths = {
            "idle":       os.path.join(ASSET_DIR, "idle.png"),
            "walk_left":  os.path.join(ASSET_DIR, "walk_left.png"),
            "walk_right": os.path.join(ASSET_DIR, "walk_right.png"),
            "sleeping":   os.path.join(ASSET_DIR, "sleeping.png"),
            "falling":    os.path.join(ASSET_DIR, "falling.png"),
            "climbing":   os.path.join(ASSET_DIR, "climbing.png"),  # optional
        }
        self._ensure_assets()
        self._raw_px = {k: QPixmap(v) for k, v in self.asset_paths.items()}

        # Tips
        self._all_tips = load_custom_tips()
        for tips in TIPS_BY_TIME.values():
            self._all_tips.extend(tips)

        # State
        self.current_state  = "idle"
        self.surface        = SURFACE_FLOOR   # where we're clinging
        self.target_pos     = QPointF(400, 400)

        # Physics
        self.vel_x: float   = 0.0
        self.vel_y: float   = 0.0
        self.is_falling     = False

        # Drag tracking
        self._drag_offset   = None
        self._drag_samples: list[tuple[QPoint, float]] = []

        # Misc ticks
        self._breath_tick   = 0
        self._walk_step     = 0
        self._idle_ticks    = 0

        # Activity + AI
        self._tracker = ActivityTracker()
        self._ai      = AIWorker(self._tracker)
        self._ai.result_ready.connect(self._on_ai_result)

        # Bubble
        self.bubble = QuietBubble()

        # Tray
        self._tray = self._build_tray()

        # Place on floor centre
        self._apply_state("idle")
        geo = QApplication.primaryScreen().geometry()
        self.move(geo.center().x() - self.width()//2,
                  geo.bottom() - self.height() - FLOOR_MARGIN)

        # Timers
        self._phys_timer = QTimer(self)
        self._phys_timer.timeout.connect(self._tick)
        self._phys_timer.start(16)

        self._behav_timer = QTimer(self)
        self._behav_timer.timeout.connect(self._decide_behavior)
        self._behav_timer.start(7000)

        self._thought_timer = QTimer(self)
        self._thought_timer.timeout.connect(self._idle_thought)
        self._thought_timer.start(22000 + random.randint(0, 10000))

        self._ai_timer = QTimer(self)
        self._ai_timer.timeout.connect(self._ai.request_assessment)
        self._ai_timer.start(AI_CHECK_INTERVAL_MIN * 60 * 1000)

        self._tip_timer = QTimer(self)
        self._tip_timer.timeout.connect(self._show_tip)
        self._tip_timer.start(self._rand_tip_interval())

    # ── Asset generation ──────────────────────────────────────────────────────

    def _ensure_assets(self):
        colors = {
            "idle":      QColor("#a8dadc"),
            "walk_left": QColor("#457b9d"),
            "walk_right":QColor("#1d3557"),
            "sleeping":  QColor("#f1faee"),
            "falling":   QColor("#e63946"),
            "climbing":  QColor("#2a9d8f"),
        }
        for state, path in self.asset_paths.items():
            if not os.path.exists(path):
                pix = QPixmap(80, 80)
                pix.fill(Qt.GlobalColor.transparent)
                p = QPainter(pix)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setBrush(colors[state])
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(8, 8, 64, 64, 16, 16)
                p.end()
                pix.save(path)

    # ── Sprite helpers ────────────────────────────────────────────────────────

    def _rotated_pixmap(self, key: str, surface: str) -> QPixmap:
        """Return the pixmap rotated to match the cling surface."""
        base = self._raw_px.get(key, self._raw_px["idle"])
        angle = {
            SURFACE_FLOOR:   0,
            SURFACE_CEILING: 180,
            SURFACE_LEFT:    90,
            SURFACE_RIGHT:  -90,
            SURFACE_FALLING:  0,
        }.get(surface, 0)
        if angle == 0:
            return base
        return base.transformed(QTransform().rotate(angle),
                                Qt.TransformationMode.SmoothTransformation)

    def _apply_state(self, state: str, surface: str | None = None):
        if surface is not None:
            self.surface = surface
        if state not in self._raw_px:
            state = "idle"
        self.current_state = state
        pix = self._rotated_pixmap(state, self.surface)
        self.setPixmap(pix)
        self.resize(pix.size())
        self.setMask(pix.mask())
        self._update_bubble_pos()

    def _update_bubble_pos(self):
        """Place bubble on the 'open' side of whatever surface we're on."""
        bw = self.bubble.width()
        if self.surface == SURFACE_FLOOR or self.surface == SURFACE_FALLING:
            bx = self.x() + self.width()//2 - bw//2
            by = self.y() - self.bubble.height() - 6
        elif self.surface == SURFACE_CEILING:
            bx = self.x() + self.width()//2 - bw//2
            by = self.y() + self.height() + 6
        elif self.surface == SURFACE_LEFT:
            bx = self.x() + self.width() + 6
            by = self.y() + self.height()//2 - self.bubble.height()//2
        else:  # RIGHT
            bx = self.x() - bw - 6
            by = self.y() + self.height()//2 - self.bubble.height()//2
        self.bubble.move(bx, by)

    # ── Surface helpers ───────────────────────────────────────────────────────

    def _screen_edges(self):
        geo = get_safe_screen(self.pos()).geometry()
        return {
            "floor":   geo.bottom() - self.height() - FLOOR_MARGIN,
            "ceiling": geo.top(),
            "left":    geo.left(),
            "right":   geo.right() - self.width(),
            "geo":     geo,
        }

    def _detect_snap(self, pos: QPoint) -> str | None:
        """
        If pos is within EDGE_SNAP_PX of a screen edge, return which surface
        to snap to, else None.
        """
        e = self._screen_edges()
        geo = e["geo"]
        x, y = pos.x(), pos.y()
        dist_floor   = abs(y - e["floor"])
        dist_ceiling = abs(y - e["ceiling"])
        dist_left    = abs(x - e["left"])
        dist_right   = abs(x - e["right"])

        nearest = min(
            (dist_floor,   SURFACE_FLOOR),
            (dist_ceiling, SURFACE_CEILING),
            (dist_left,    SURFACE_LEFT),
            (dist_right,   SURFACE_RIGHT),
        )
        if nearest[0] <= EDGE_SNAP_PX:
            return nearest[1]
        return None

    def _clamp_to_surface(self, surface: str) -> QPoint:
        e = self._screen_edges()
        geo = e["geo"]
        cx = max(geo.left(), min(self.x(), e["right"]))
        cy = max(geo.top(),  min(self.y(), e["floor"]))
        if surface == SURFACE_FLOOR:
            cy = e["floor"]
        elif surface == SURFACE_CEILING:
            cy = e["ceiling"]
        elif surface == SURFACE_LEFT:
            cx = e["left"]
        elif surface == SURFACE_RIGHT:
            cx = e["right"]
        return QPoint(cx, cy)

    # ── AI callback ───────────────────────────────────────────────────────────

    def _on_ai_result(self, text: str):
        if text:
            self.bubble.show_thought(f"🤖 {text}", 7000)

    # ── Behavior decisions ────────────────────────────────────────────────────

    def _decide_behavior(self):
        if self.is_falling:
            return
        if self.current_state == "sleeping":
            if random.random() < 0.12:
                self._apply_state("idle")
                self.bubble.show_thought("( ˘ω˘ ) !")
            return

        geo = get_safe_screen(self.pos()).geometry()
        roll = random.random()

        if roll < 0.08:
            # Curiosity toward cursor
            cp = QCursor.pos()
            if geo.contains(cp):
                self.target_pos = QPointF(cp.x() - self.width()//2,
                                          cp.y() - self.height()//2)
                d = "walk_left" if self.target_pos.x() < self.x() else "walk_right"
                self._apply_state(d)
            return

        if roll < 0.50:
            self._apply_state("idle")
        elif roll < 0.78:
            # Wander along current surface
            self._wander_on_surface(geo)
        else:
            self._apply_state("sleeping")
            self.bubble.show_thought("(˘ω˘)zzz", 6000)

    def _wander_on_surface(self, geo):
        """Pick a random walk target that stays on the current surface."""
        e = self._screen_edges()
        if self.surface in (SURFACE_FLOOR, SURFACE_CEILING):
            tx = random.randint(e["left"], e["right"])
            ty = e["floor"] if self.surface == SURFACE_FLOOR else e["ceiling"]
        elif self.surface == SURFACE_LEFT:
            tx = e["left"]
            ty = random.randint(geo.top(), e["floor"])
        else:  # RIGHT
            tx = e["right"]
            ty = random.randint(geo.top(), e["floor"])

        self.target_pos = QPointF(tx, ty)
        if self.surface in (SURFACE_FLOOR, SURFACE_CEILING):
            d = "walk_left" if tx < self.x() else "walk_right"
        else:
            d = "climbing"
        self._apply_state(d)

    def _idle_thought(self):
        self._thought_timer.start(18000 + random.randint(0, 14000))
        if self.current_state not in ("idle", "sleeping"):
            return
        self.bubble.show_thought(random.choice(IDLE_THOUGHTS), 2500)

    def _show_tip(self):
        pool = TIPS_BY_TIME.get(get_time_period(), []) + load_custom_tips()
        if not pool:
            pool = self._all_tips
        self.bubble.show_thought(random.choice(pool), 5000)
        self._tip_timer.start(self._rand_tip_interval())

    @staticmethod
    def _rand_tip_interval():
        return (9 + random.randint(0, 6)) * 60 * 1000

    # ── Physics tick ──────────────────────────────────────────────────────────

    def _tick(self):
        self._idle_ticks += 1
        if self.is_falling:
            self._tick_falling()
        elif self.current_state in ("walk_left", "walk_right", "climbing"):
            self._tick_walking()
        elif self.current_state == "idle":
            self._tick_idle_breath()
        self._update_bubble_pos()

    def _tick_falling(self):
        e = self._screen_edges()
        geo = e["geo"]

        # Apply gravity downward (always, even when tossed from ceiling/walls)
        self.vel_y += GRAVITY

        nx = self.x() + self.vel_x
        ny = self.y() + self.vel_y

        # Wall collisions
        if nx <= e["left"]:
            nx = e["left"];  self.vel_x =  abs(self.vel_x) * WALL_DAMPING
        elif nx >= e["right"]:
            nx = e["right"]; self.vel_x = -abs(self.vel_x) * WALL_DAMPING

        # Ceiling collision
        if ny <= e["ceiling"]:
            ny = e["ceiling"]; self.vel_y = abs(self.vel_y) * BOUNCE_DAMPING

        # Floor collision
        if ny >= e["floor"]:
            ny = e["floor"]
            self.vel_y = -self.vel_y * BOUNCE_DAMPING
            self.vel_x *= 0.82
            if abs(self.vel_y) < MIN_BOUNCE_VEL:
                self.vel_y = self.vel_x = 0.0
                self.is_falling = False
                self.surface = SURFACE_FLOOR
                self._apply_state("idle", SURFACE_FLOOR)

        self.move(int(nx), int(ny))

    def _tick_walking(self):
        dx = self.target_pos.x() - self.x()
        dy = self.target_pos.y() - self.y()
        dist = math.hypot(dx, dy)
        if dist <= WALK_SPEED:
            self.move(int(self.target_pos.x()), int(self.target_pos.y()))
            self._apply_state("idle")
            return
        scale = WALK_SPEED / dist
        self.move(int(self.x() + dx * scale), int(self.y() + dy * scale))

    def _tick_idle_breath(self):
        self._breath_tick += 1
        if self._breath_tick % 90 == 0:
            nudge = 1 if (self._breath_tick // 90) % 2 == 0 else -1
            # Nudge perpendicular to surface
            if self.surface in (SURFACE_FLOOR, SURFACE_CEILING):
                self.move(self.x(), self.y() + nudge)
            else:
                self.move(self.x() + nudge, self.y())

    # ── Input handling ────────────────────────────────────────────────────────

    def showEvent(self, ev):
        super().showEvent(ev)
        self._raise()
        if not hasattr(self, "_reraise"):
            self._reraise = QTimer(self)
            self._reraise.timeout.connect(self._raise)
            # 500 ms — aggressive enough to recover from focus steals instantly,
            # cheap enough (single setLevel_ call) to not affect CPU.
            self._reraise.start(500)

    def _raise(self):
        """
        Triple-layer window elevation — combines all three known-good methods:
          1. Qt property (works without pyobjc)
          2. pyobjc NSApp().windows() direct AppKit call (most reliable)
          3. WindowStaysOnTopHint is already set in __init__ flags (layer 3)
        Result: pet sits at NSStatusWindowLevel — same tier as the menu bar.
        """
        # Layer 1: Qt bridge property
        wh = self.windowHandle()
        if wh:
            wh.setProperty("NSWindowLevel", NSStatusWindowLevel)
        # Layer 2: direct AppKit call when pyobjc is available
        if _HAS_APPKIT:
            for win in NSApp().windows():
                win.setLevel_(NSStatusWindowLevel)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.is_falling = False
            self.vel_x = self.vel_y = 0.0
            self._drag_offset  = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_samples = [(ev.globalPosition().toPoint(), ms())]
            self._apply_state("idle")
            self.bubble.dismiss()
        elif ev.button() == Qt.MouseButton.RightButton:
            self._open_menu()

    def mouseMoveEvent(self, ev):
        if self._drag_offset and ev.buttons() & Qt.MouseButton.LeftButton:
            new_pos = ev.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            now = ms()
            self._drag_samples.append((ev.globalPosition().toPoint(), now))
            self._drag_samples = [(p,t) for p,t in self._drag_samples if now-t <= VEL_SAMPLE_MS]
            self._update_bubble_pos()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_offset = None
        pos = self.pos()

        # Check for edge snap first
        snapped = self._detect_snap(pos)
        if snapped:
            clamped = self._clamp_to_surface(snapped)
            self.move(clamped)
            self.vel_x = self.vel_y = 0.0
            self.is_falling = False
            self.surface = snapped
            anim_state = "climbing" if snapped in (SURFACE_LEFT, SURFACE_RIGHT) else "idle"
            self._apply_state(anim_state, snapped)
            self.bubble.show_thought(
                {"floor": "( ᵕ—ᵕ) landed!",
                 "ceiling": "I'm on the ceiling! 🙃",
                 "left":  "Clinging to the wall! 🧗",
                 "right": "Clinging to the wall! 🧗"}.get(snapped, ""), 2000
            )
            return

        # Otherwise toss
        self._toss()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._show_tip()

    def _toss(self):
        if len(self._drag_samples) < 2:
            self.vel_x = 0.0; self.vel_y = 2.0
        else:
            p0, t0 = self._drag_samples[0]
            p1, t1 = self._drag_samples[-1]
            dt = max((t1 - t0) / 1000.0, 0.001)
            self.vel_x = max(-28.0, min(28.0, (p1.x()-p0.x())/dt * 0.016))
            self.vel_y = max(-22.0, min(22.0, (p1.y()-p0.y())/dt * 0.016))
            self.vel_y = max(self.vel_y, -15.0)

        self.surface    = SURFACE_FALLING
        self.is_falling = True
        self._apply_state("falling", SURFACE_FALLING)

    # ── Tray & menu ───────────────────────────────────────────────────────────

    def _build_tray(self):
        icon_pix = self._raw_px["idle"].scaled(
            22, 22, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        tray = QSystemTrayIcon(QIcon(icon_pix), self)
        menu = QMenu()
        menu.addAction("💡 Show Tip",         self._show_tip)
        menu.addAction("🤖 Ask AI Now",        self._ai.request_assessment)
        menu.addAction("📊 Show Usage Snapshot", self._show_snapshot)
        menu.addSeparator()
        menu.addAction("💤 Force Nap",         lambda: self._apply_state("sleeping"))
        menu.addAction("☀️ Wake Up",            lambda: self._apply_state("idle"))
        menu.addAction("🐾 Bring to Center",   self._bring_to_center)
        menu.addSeparator()
        menu.addAction("❌ Quit",              self._quit)
        tray.setContextMenu(menu)
        tray.setToolTip("Screen Buddy")
        tray.activated.connect(
            lambda r: self._show_tip()
            if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        tray.show()
        return tray

    def _show_snapshot(self):
        snap = self._tracker.snapshot()
        lines = [f"📱 {snap['current_app']}"]
        if snap["current_url"]:
            url = snap["current_url"]
            url = url[:50] + "…" if len(url) > 50 else url
            lines.append(f"🌐 {url}")
        for e in snap["top_apps_minutes"][:4]:
            lines.append(f"• {e['app']}: {e['minutes']}m")
        self.bubble.show_thought("\n".join(lines), 8000)

    def _bring_to_center(self):
        geo = get_safe_screen(self.pos()).geometry()
        self.move(geo.center().x() - self.width()//2,
                  geo.bottom() - self.height() - FLOOR_MARGIN)
        self.vel_x = self.vel_y = 0.0
        self.is_falling = False
        self.surface = SURFACE_FLOOR
        self._apply_state("idle", SURFACE_FLOOR)

    def _open_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#fffdf7; border:1px solid #c8c0b0;
                    border-radius:8px; padding:4px; font-size:13px; }
            QMenu::item { padding:6px 18px; border-radius:4px; }
            QMenu::item:selected { background:#e8f4f8; }
        """)
        acts = {
            "💡 Show Tip":           self._show_tip,
            "🤖 Ask AI Now":          self._ai.request_assessment,
            "📊 Usage Snapshot":     self._show_snapshot,
            None: None,
            "💤 Force Nap":          lambda: (self._apply_state("sleeping"),
                                              self.bubble.show_thought("(˘ω˘)zzz",6000)),
            "☀️  Wake Up":           lambda: (self._apply_state("idle"),
                                              self.bubble.show_thought("( •̀ω•́ )✧")),
            "🐾 Bring to Center":   self._bring_to_center,
            "❌ Quit":               self._quit,
        }
        action_map = {}
        for label, fn in acts.items():
            if label is None:
                menu.addSeparator()
            else:
                action_map[menu.addAction(label)] = fn
        sel = menu.exec(QCursor.pos())
        if sel in action_map:
            action_map[sel]()

    def _quit(self):
        self.bubble.close()
        self._tray.hide()
        QApplication.quit()


# ── Entry ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Screen Buddy")
    buddy = ScreenBuddy()
    buddy.show()
    sys.exit(app.exec())