"""Talks to the Buddy billing backend (Flask server on Render/etc).
No Stripe secret key here — that lives only on the backend. This module
just opens Checkout in the browser and polls for the resulting tier.

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
HACKCLUB_AUTHORIZE_URL = "https://auth.hackclub.com/oauth/authorize"
HACKCLUB_CLIENT_ID = os.getenv("HACKCLUB_CLIENT_ID", "7e8a441dc3ac83686a799171c0757d33")

# Price IDs from your Stripe Dashboard — set these once you've created
# the Products/Prices there. Kept here (not secret) so the desktop app
# can tell the backend which plan was clicked.
PRICE_IDS = {
    "pro_monthly": os.getenv("PRICE_ID_PRO_MONTHLY", ""),
    "pro_yearly": os.getenv("PRICE_ID_PRO_YEARLY", ""),
    "max_monthly": os.getenv("PRICE_ID_MAX_MONTHLY", ""),
    "max_yearly": os.getenv("PRICE_ID_MAX_YEARLY", ""),
}


class BillingNotConfigured(Exception):
    pass


def open_hackclub_signin(buddy_user_id):
    """Open Hack Club's authorization URL directly in the browser."""
    webbrowser.open(
        f"{HACKCLUB_AUTHORIZE_URL}?client_id={HACKCLUB_CLIENT_ID}"
        f"&redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fauth%2Fhackclub%2Fcallback"
        f"&response_type=code&scope=openid+email+name+profile+verification_status"
    )
    return True


def poll_hackclub_status(buddy_user_id):
    """Checks whether Hack Club sign-in has completed for this install.
    Returns {signed_in, verified, verification_status, email, name}.
    Never raises — a network hiccup just looks like 'not signed in yet'."""
    backend_url = BACKEND_URL or LOCAL_BACKEND_URL
    try:
        resp = requests.get(f"{backend_url}/auth/hackclub/status/{buddy_user_id}", timeout=8)
        resp.raise_for_status()
        result = resp.json()
        if result.get("signed_in"):
            return result
        latest = requests.get(f"{backend_url}/auth/hackclub/status/latest", timeout=8)
        latest.raise_for_status()
        return latest.json()
    except Exception:
        return {"signed_in": False}


def start_checkout(buddy_user_id, price_key):
    """Opens Stripe Checkout in the user's default browser. Returns True
    if the request succeeded and a browser tab was opened."""
    price_id = PRICE_IDS.get(price_key)
    if not price_id:
        raise BillingNotConfigured(f"No price_id configured for '{price_key}'.")

    # Stripe Payment Links can be used directly while the billing backend is
    # being deployed. Price IDs continue through the secure backend flow.
    if price_id.startswith(("https://", "http://")):
        webbrowser.open(price_id)
        return True

    backend_url = BACKEND_URL or LOCAL_BACKEND_URL

    resp = requests.post(
        f"{backend_url}/create-checkout-session",
        json={"buddy_user_id": buddy_user_id, "price_id": price_id},
        timeout=10,
    )
    resp.raise_for_status()
    checkout_url = resp.json()["checkout_url"]
    webbrowser.open(checkout_url)
    return True


def fetch_subscription_tier(buddy_user_id):
    """Polls the backend for the current tier. Returns 'free' on any
    failure so a network hiccup never crashes the billing page."""
    backend_url = BACKEND_URL or LOCAL_BACKEND_URL
    try:
        resp = requests.get(f"{backend_url}/subscription-status/{buddy_user_id}", timeout=8)
        resp.raise_for_status()
        return resp.json().get("subscription_tier", "free")
    except Exception:
        return "free"


def open_billing_portal(buddy_user_id):
    """Open Stripe's hosted subscription-management page."""
    backend_url = BACKEND_URL or LOCAL_BACKEND_URL
    resp = requests.post(
        f"{backend_url}/create-portal-session",
        json={"buddy_user_id": buddy_user_id},
        timeout=10,
    )
    if resp.status_code == 404:
        raise BillingNotConfigured("No paid subscription is linked to this Buddy installation yet.")
    resp.raise_for_status()
    webbrowser.open(resp.json()["portal_url"])
    return True