"""Talks to the local Buddy backend. Never uses localhost — AirPlay owns that."""
import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")
load_dotenv()

PREFERRED = "http://127.0.0.1:5000"
BACKEND_URL = os.getenv("BUDDY_BILLING_URL", "").rstrip("/")
_discovered = None
_started = False

PRICE_IDS = {
    "pro_monthly": os.getenv("PRICE_ID_PRO_MONTHLY", ""),
    "pro_yearly": os.getenv("PRICE_ID_PRO_YEARLY", ""),
    "max_monthly": os.getenv("PRICE_ID_MAX_MONTHLY", ""),
    "max_yearly": os.getenv("PRICE_ID_MAX_YEARLY", ""),
}


class BillingNotConfigured(Exception):
    pass


def _alive(url):
    for path in ("/health", "/"):
        try:
            resp = requests.get(url + path, timeout=1.5)
            if resp.status_code < 500:
                return True
        except Exception:
            pass
    return False


def discover_backend():
    global _discovered
    urls = [u for u in (BACKEND_URL, _discovered, PREFERRED, "http://127.0.0.1:5057") if u]
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        if _alive(url):
            _discovered = url
            return url
    return None


def ensure_backend():
    url = discover_backend()
    if url:
        return url
    global _started
    app = _ROOT / "backend" / "app.py"
    if app.exists() and not _started:
        _started = True
        subprocess.Popen(
            [sys.executable, str(app)],
            cwd=str(_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(24):
            time.sleep(0.25)
            url = discover_backend()
            if url:
                return url
    return discover_backend() or PREFERRED


def backend_url():
    return ensure_backend()


def backend_is_up():
    return discover_backend() is not None


def open_hackclub_signin(buddy_user_id=None):
    url = ensure_backend()
    uid = buddy_user_id or "latest"
    webbrowser.open(f"{url}/auth/hackclub/start?buddy_user_id={uid}")
    return True


def poll_hackclub_status(buddy_user_id):
    url = discover_backend() or PREFERRED
    try:
        resp = requests.get(f"{url}/auth/hackclub/status/{buddy_user_id}", timeout=8)
        if resp.ok:
            result = resp.json()
            if result.get("signed_in"):
                return result
        latest = requests.get(f"{url}/auth/hackclub/status/latest", timeout=8)
        if latest.ok:
            return latest.json()
    except Exception:
        pass
    return {"signed_in": False}


def start_checkout(buddy_user_id, price_key):
    price_id = PRICE_IDS.get(price_key)
    if not price_id:
        raise BillingNotConfigured(f"No price_id configured for '{price_key}'.")
    if price_id.startswith(("https://", "http://")):
        webbrowser.open(price_id)
        return True
    url = ensure_backend()
    resp = requests.post(
        f"{url}/create-checkout-session",
        json={"buddy_user_id": buddy_user_id, "price_id": price_id},
        timeout=10,
    )
    resp.raise_for_status()
    webbrowser.open(resp.json()["checkout_url"])
    return True


def fetch_subscription_tier(buddy_user_id):
    url = discover_backend()
    if not url:
        return "free"
    try:
        resp = requests.get(f"{url}/subscription-status/{buddy_user_id}", timeout=8)
        resp.raise_for_status()
        return resp.json().get("subscription_tier", "free")
    except Exception:
        return "free"


def open_billing_portal(buddy_user_id):
    url = ensure_backend()
    resp = requests.post(
        f"{url}/create-portal-session",
        json={"buddy_user_id": buddy_user_id},
        timeout=10,
    )
    if resp.status_code == 404:
        raise BillingNotConfigured("No paid subscription is linked yet.")
    resp.raise_for_status()
    webbrowser.open(resp.json()["portal_url"])
    return True