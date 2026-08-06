# Screen Buddy v3 🐾

A privacy-friendly macOS desktop companion that climbs your screen edges,
tracks what you're doing, and asks an AI if you need a break.

---

## Quick start

```bash
pip install PyQt6 requests
python main.py
```

---

## Setup: Hugging Face token (free)

1. Go to **hf.co** → sign up (free) → **Settings → Access Tokens**
2. Create a token with **Inference** permission (Read is enough)
3. Open `main.py` and paste it here:

```python
HF_TOKEN = "hf_your_token_here"
```

That's it. The default model (`Mistral-7B-Instruct`) is free tier and
very fast. Swap `HF_MODEL` for any other chat model on HF if you like.

---

## Setup: Browser URL reading (optional)

To see *which website* you're on (not just the browser app):

**System Preferences → Privacy & Security → Accessibility**
→ add **Terminal** (or your launcher) to the allowed list.

Supports: Chrome, Brave, Safari, Firefox, Arc, Edge.
Falls back gracefully (just shows the app name) if not granted.

---

## Surface climbing

| Action | Result |
|--------|--------|
| Drag pet near **any screen edge** | Pet snaps and grabs that edge |
| Drag near **floor** | Lands on floor (normal) |
| Drag near **ceiling** | Hangs upside down from ceiling 🙃 |
| Drag near **left/right wall** | Clings to wall and crawls 🧗 |
| Toss away from edge | Falls with bounce physics |

The snap zone is **48px** from each edge. You can change `EDGE_SNAP_PX` in the config.

---

## Custom sprites

Drop PNGs next to `main.py` (transparent background, any size):

| File | Pose |
|------|------|
| `idle.png` | Sitting |
| `walk_left.png` | Walking left |
| `walk_right.png` | Walking right |
| `sleeping.png` | Napping |
| `falling.png` | Tossed/airborne |
| `climbing.png` | Wall/ceiling crawl (optional, falls back to idle) |

Sprites are **auto-rotated** based on surface, so your floor sprite becomes
a ceiling sprite (flipped 180°) and a wall sprite (rotated 90°) automatically.

---

## Custom tips

Create `tips.txt` next to `main.py`. One tip per line, `#` = comment.

---

## Controls

| Action | Result |
|--------|--------|
| **Drag** | Move pet |
| **Release near edge** | Snap to that surface |
| **Release away from edge** | Toss with physics |
| **Double-click** | Get an instant tip |
| **Right-click** | Full context menu |
| **Tray icon** | Control menu + AI check + usage snapshot |
| **Tray double-click** | Instant tip |

---

## AI check interval

```python
AI_CHECK_INTERVAL_MIN = 12   # change to whatever you like
```

You can also trigger it instantly: right-click → **Ask AI Now**, or via tray.

---

## Note on browser window ceiling

Sitting *on top of browser window title bars* requires macOS Accessibility
API access to enumerate window positions — doable but requires special
entitlements and makes the app feel intrusive. The snap-to-ceiling feature
gives the same visual effect (pet on ceiling above your browser) without
needing window enumeration permissions.