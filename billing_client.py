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


def start_checkout(buddy_user_id, price_key):
    """Opens Stripe Checkout in the user's default browser. Returns True
    if the request succeeded and a browser tab was opened."""
    if not BACKEND_URL:
        raise BillingNotConfigured("BUDDY_BILLING_URL is not set.")
    price_id = PRICE_IDS.get(price_key)
    if not price_id:
        raise BillingNotConfigured(f"No price_id configured for '{price_key}'.")

    resp = requests.post(
        f"{BACKEND_URL}/create-checkout-session",
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
    if not BACKEND_URL:
        return "free"
    try:
        resp = requests.get(f"{BACKEND_URL}/subscription-status/{buddy_user_id}", timeout=8)
        resp.raise_for_status()
        return resp.json().get("subscription_tier", "free")
    except Exception:
        return "free"


def open_billing_portal(buddy_user_id):
    """Open Stripe's hosted subscription-management page."""
    if not BACKEND_URL:
        raise BillingNotConfigured("BUDDY_BILLING_URL is not set.")
    resp = requests.post(
        f"{BACKEND_URL}/create-portal-session",
        json={"buddy_user_id": buddy_user_id},
        timeout=10,
    )
    if resp.status_code == 404:
        raise BillingNotConfigured("No paid subscription is linked to this Buddy installation yet.")
    resp.raise_for_status()
    webbrowser.open(resp.json()["portal_url"])
    return True