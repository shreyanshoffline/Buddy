"""Talks to the Buddy billing / auth backend.

No Stripe secret key here — that lives only on the backend. This module
opens Checkout or Hack Club sign-in in the browser and polls for results.

Set BUDDY_BILLING_URL in your .env once the backend is deployed, e.g.
BUDDY_BILLING_URL=https://buddy-billing.onrender.com
"""
import os
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BUDDY_BILLING_URL", "").rstrip("/")
LOCAL_BACKEND_URL = "http://localhost:5000"

PRICE_IDS = {
    "pro_monthly": os.getenv("PRICE_ID_PRO_MONTHLY", ""),
    "pro_yearly": os.getenv("PRICE_ID_PRO_YEARLY", ""),
    "max_monthly": os.getenv("PRICE_ID_MAX_MONTHLY", ""),
    "max_yearly": os.getenv("PRICE_ID_MAX_YEARLY", ""),
}


class BillingNotConfigured(Exception):
    pass


def backend_url():
    return BACKEND_URL or LOCAL_BACKEND_URL


def backend_is_up():
    try:
        resp = requests.get(f"{backend_url()}/health", timeout=3)
        return resp.ok and resp.json().get("ok") is True
    except Exception:
        return False


def open_hackclub_signin(buddy_user_id=None):
    """Open the backend start URL so state + user id survive the callback."""
    if not backend_is_up():
        raise BillingNotConfigured(
            "The Buddy backend is not running.\n\n"
            "In a second terminal run:\n"
            "  python backend/app.py\n\n"
            "Then make sure http://localhost:5000/health returns {\"ok\": true}.\n"
            "The Hack Club app redirect URI must be exactly:\n"
            "  http://localhost:5000/auth/hackclub/callback"
        )
    uid = buddy_user_id or "latest"
    webbrowser.open(f"{backend_url()}/auth/hackclub/start?buddy_user_id={uid}")
    return True


def poll_hackclub_status(buddy_user_id):
    """Checks whether Hack Club sign-in has completed for this install."""
    try:
        resp = requests.get(f"{backend_url()}/auth/hackclub/status/{buddy_user_id}", timeout=8)
        resp.raise_for_status()
        result = resp.json()
        if result.get("signed_in"):
            return result
        latest = requests.get(f"{backend_url()}/auth/hackclub/status/latest", timeout=8)
        latest.raise_for_status()
        return latest.json()
    except Exception:
        return {"signed_in": False}


def start_checkout(buddy_user_id, price_key):
    """Opens Stripe Checkout in the user's default browser."""
    price_id = PRICE_IDS.get(price_key)
    if not price_id:
        raise BillingNotConfigured(f"No price_id configured for '{price_key}'.")

    if price_id.startswith(("https://", "http://")):
        webbrowser.open(price_id)
        return True

    if not backend_is_up():
        raise BillingNotConfigured("The Buddy backend is not running on localhost:5000.")

    resp = requests.post(
        f"{backend_url()}/create-checkout-session",
        json={"buddy_user_id": buddy_user_id, "price_id": price_id},
        timeout=10,
    )
    resp.raise_for_status()
    webbrowser.open(resp.json()["checkout_url"])
    return True


def fetch_subscription_tier(buddy_user_id):
    """Polls the backend for the current tier. Returns 'free' on failure."""
    try:
        resp = requests.get(f"{backend_url()}/subscription-status/{buddy_user_id}", timeout=8)
        resp.raise_for_status()
        return resp.json().get("subscription_tier", "free")
    except Exception:
        return "free"


def open_billing_portal(buddy_user_id):
    """Open Stripe's hosted subscription-management page."""
    if not backend_is_up():
        raise BillingNotConfigured("The Buddy backend is not running on localhost:5000.")
    resp = requests.post(
        f"{backend_url()}/create-portal-session",
        json={"buddy_user_id": buddy_user_id},
        timeout=10,
    )
    if resp.status_code == 404:
        raise BillingNotConfigured("No paid subscription is linked to this Buddy installation yet.")
    resp.raise_for_status()
    webbrowser.open(resp.json()["portal_url"])
    return True
