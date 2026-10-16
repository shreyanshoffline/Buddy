"""Talks to Buddy's local or deployed backend."""
import os
import webbrowser

import requests
from dotenv import load_dotenv
from tools.paths import app_root

_ROOT = app_root()
load_dotenv(_ROOT / ".env")
load_dotenv()

PREFERRED = "http://127.0.0.1:%s" % os.getenv("BUDDY_BACKEND_PORT", "5000")
BACKEND_URL = os.getenv("BUDDY_BILLING_URL", "").rstrip("/")
SLACK_API_BASE = (os.getenv("SLACK_API_BASE") or "https://api.buddy.dino.icu").rstrip("/")
_discovered = None

PRICE_IDS = {
    "pro_monthly": os.getenv("PRICE_ID_PRO_MONTHLY", ""),
    "pro_yearly": os.getenv("PRICE_ID_PRO_YEARLY", ""),
    "max_monthly": os.getenv("PRICE_ID_MAX_MONTHLY", ""),
    "max_yearly": os.getenv("PRICE_ID_MAX_YEARLY", ""),
}


class BillingNotConfigured(Exception):
    pass


def _alive(url):
    """True only if this is really Buddy's backend. A bare 'any HTTP response' check
    is fooled by macOS AirPlay Receiver, which squats on port 5000 and answers 403."""
    try:
        resp = requests.get(url + "/health", timeout=1.5)
        return resp.ok and bool((resp.json() or {}).get("ok"))
    except Exception:
        return False


def _health(url):
    try:
        return requests.get(url + "/health", timeout=3).json() or {}
    except Exception:
        return {}


def slack_configured():
    """True when a reachable backend has the Slack app credentials set."""
    for base in (SLACK_API_BASE, discover_backend()):
        if base and _alive(base) and _health(base).get("slack_client_id_set") and _health(base).get("slack_secret_set"):
            return True
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
    # main.py normally starts this already. The fallback keeps provider pages
    # usable when billing_client is imported by itself (tests or a CLI).
    try:
        from backend.runtime import start_local_backend
        local = start_local_backend()
        if local:
            return local.url
    except Exception:
        pass
    return discover_backend() or PREFERRED


def backend_url():
    return ensure_backend()


def backend_is_up():
    return discover_backend() is not None


def slack_api_base():
    if SLACK_API_BASE and _alive(SLACK_API_BASE):
        return SLACK_API_BASE
    return ensure_backend()


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


def open_slack_install(buddy_user_id=None):
    url = slack_api_base()
    uid = buddy_user_id or "latest"
    webbrowser.open(f"{url}/slack/install?buddy_user_id={uid}")
    return url


def poll_slack_status(buddy_user_id):
    bases = []
    for candidate in (SLACK_API_BASE, discover_backend(), PREFERRED):
        if candidate and candidate not in bases:
            bases.append(candidate)
    for base in bases:
        try:
            resp = requests.get(f"{base}/slack/status/{buddy_user_id}", timeout=8)
            if resp.ok:
                data = resp.json()
                if data.get("connected"):
                    return data
        except Exception:
            continue
    return {"connected": False}


def slack_disconnect(buddy_user_id):
    base = slack_api_base()
    requests.post(f"{base}/slack/disconnect", json={"buddy_user_id": buddy_user_id}, timeout=8)


def slack_list_channels(buddy_user_id):
    base = slack_api_base()
    resp = requests.get(f"{base}/slack/channels", params={"buddy_user_id": buddy_user_id}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def slack_channel_history(buddy_user_id, channel, limit=20):
    base = slack_api_base()
    resp = requests.get(
        f"{base}/slack/history",
        params={"buddy_user_id": buddy_user_id, "channel": channel, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def slack_post_message(buddy_user_id, channel, text):
    base = slack_api_base()
    resp = requests.post(
        f"{base}/slack/post",
        json={"buddy_user_id": buddy_user_id, "channel": channel, "text": text},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


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
