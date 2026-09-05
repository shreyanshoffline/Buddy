"""
Buddy billing backend — the ONLY place Stripe's secret key ever lives.
Desktop app never sees it. Deploy this to Render (or similar).

Routes:
  POST /create-checkout-session   -> desktop app calls this to start a purchase
  GET  /checkout-success           -> Stripe redirects here after payment
  GET  /checkout-cancel            -> Stripe redirects here if user backs out
  POST /webhook                    -> Stripe calls this server-to-server on payment events
  GET  /subscription-status/<uid>  -> desktop app polls this to check tier

Storage: a simple SQLite file (fine for Hack Club scale). Swap for Postgres
later if you outgrow it — nothing else needs to change.
"""
import os
import sqlite3
import time
import secrets
from urllib.parse import urlencode
import stripe
import requests
from flask import Flask, request, jsonify, redirect
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

# price_id -> tier name shown in Buddy
PRICE_TO_TIER = {
    price_id: tier
    for price_id, tier in (
        (os.environ.get("PRICE_ID_PRO_MONTHLY"), "pro"),
        (os.environ.get("PRICE_ID_PRO_YEARLY"), "pro"),
        (os.environ.get("PRICE_ID_MAX_MONTHLY"), "max"),
        (os.environ.get("PRICE_ID_MAX_YEARLY"), "max"),
    )
    if price_id
}

DB_PATH = os.environ.get("BILLING_DB_PATH", "billing.db")
HACKCLUB_CLIENT_ID = os.environ.get("HACKCLUB_CLIENT_ID", "")
HACKCLUB_CLIENT_SECRET = os.environ.get("HACKCLUB_CLIENT_SECRET", "")
HACKCLUB_REDIRECT_URI = os.environ.get(
    "HACKCLUB_REDIRECT_URI", "http://localhost:5000/auth/hackclub/callback"
)
_oauth_states = set()
_oauth_state_users = {}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            buddy_user_id TEXT PRIMARY KEY,
            stripe_customer_id TEXT,
            subscription_tier TEXT DEFAULT 'free',
            updated_at REAL
        )
    """)
    conn.commit()
    conn.close()


init_db()


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/")
def home():
    """Small local page so opening localhost:5000 is useful during setup."""
    sign_in_url = "/auth/hackclub/start"
    client_status = "configured" if HACKCLUB_CLIENT_ID else "not configured"
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Buddy account setup</title>
<style>
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #eef6fc; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ width: min(440px, calc(100% - 40px)); padding: 32px; box-sizing: border-box; background: white; border: 1px solid #d7e2ec; border-radius: 16px; box-shadow: 0 12px 32px rgba(31, 41, 55, .10); }}
h1 {{ margin: 0 0 8px; font-size: 26px; }} p {{ line-height: 1.5; color: #5f6b7a; }}
a.button {{ display: inline-block; margin-top: 12px; padding: 11px 16px; border-radius: 9px; background: #338eda; color: white; text-decoration: none; font-weight: 700; }}
code {{ overflow-wrap: anywhere; }}
</style></head>
<body><main>
<h1>Buddy account setup</h1>
<p>This local server handles Hack Club sign-in for Buddy.</p>
<a class="button" href="{sign_in_url}">Sign in with Hack Club</a>
<p>OAuth client: <strong>{client_status}</strong></p>
<p>Callback URL:<br><code>{HACKCLUB_REDIRECT_URI}</code></p>
</main></body></html>""", 200


@app.route("/auth/hackclub/start")
def hackclub_start():
    """Start Hack Club OAuth using a registered local development callback."""
    if not HACKCLUB_CLIENT_ID:
        return "Set HACKCLUB_CLIENT_ID on the backend first.", 503
    state = secrets.token_urlsafe(32)
    buddy_user_id = request.args.get("buddy_user_id", "")
    _oauth_states.add(state)
    params = urlencode({
        "client_id": HACKCLUB_CLIENT_ID,
        "redirect_uri": HACKCLUB_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email name profile verification_status",
        "state": state,
    })
    _oauth_state_users[state] = buddy_user_id
    return redirect(f"https://auth.hackclub.com/oauth/authorize?{params}")


@app.route("/auth/hackclub/callback")
def hackclub_callback():
    """Receive OAuth's code and show the verified Hack Club account status."""
    error = request.args.get("error")
    if error:
        return f"Hack Club sign-in was cancelled: {error}", 400

    state = request.args.get("state", "")
    if state:
        if state not in _oauth_states:
            return "Invalid or expired Hack Club sign-in request.", 400
        _oauth_states.remove(state)
    buddy_user_id = _oauth_state_users.pop(state, "") if state else ""

    code = request.args.get("code")
    if not code or not HACKCLUB_CLIENT_SECRET:
        return "Set HACKCLUB_CLIENT_SECRET on the backend first.", 503

    token_response = requests.post(
        "https://auth.hackclub.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": HACKCLUB_REDIRECT_URI,
            "client_id": HACKCLUB_CLIENT_ID,
            "client_secret": HACKCLUB_CLIENT_SECRET,
        },
        timeout=10,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        return "Hack Club did not return an access token.", 502

    user_response = requests.get(
        "https://auth.hackclub.com/api/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    user_response.raise_for_status()
    profile = user_response.json()
    verification = profile.get("verification_status") or "unknown"
    is_verified = (
        str(verification).lower() in ("verified", "active", "approved")
        or bool(profile.get("email_verified"))
        or bool(profile.get("ysws_eligible"))
    )
    try:
        from storage import db as local_db
        local_db.init_db()
        local_db.update_profile(
            email=profile.get("email"),
            name=profile.get("name") or profile.get("nickname"),
            auth_provider="hackclub",
            hackclub_verified=is_verified,
            hackclub_verification_status=str(verification),
        )
    except Exception as error:
        # OAuth succeeds even if a separately deployed backend cannot see
        # the desktop app's local database.
        app.logger.warning("Could not update local Buddy profile after OAuth: %s", error)
    return (
        "Hack Club sign-in complete. Verification status: "
        f"{verification}. You can close this tab and return to Buddy."
    ), 200


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    """Desktop app calls this with {buddy_user_id, price_id}. Returns a
    Stripe-hosted checkout URL to open in the user's browser."""
    data = request.get_json(force=True)
    buddy_user_id = data.get("buddy_user_id")
    price_id = data.get("price_id")

    if not isinstance(buddy_user_id, str) or not buddy_user_id or not price_id:
        return jsonify({"error": "buddy_user_id and price_id are required"}), 400
    if price_id not in PRICE_TO_TIER:
        return jsonify({"error": "That billing plan is not available"}), 400

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=request.host_url + "checkout-success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=request.host_url + "checkout-cancel",
        client_reference_id=buddy_user_id,
        metadata={"buddy_user_id": buddy_user_id, "tier": PRICE_TO_TIER[price_id]},
    )
    return jsonify({"checkout_url": session.url})


@app.route("/create-portal-session", methods=["POST"])
def create_portal_session():
    data = request.get_json(silent=True) or {}
    buddy_user_id = data.get("buddy_user_id")
    if not isinstance(buddy_user_id, str) or not buddy_user_id:
        return jsonify({"error": "buddy_user_id is required"}), 400

    conn = _connect()
    row = conn.execute(
        "SELECT stripe_customer_id FROM users WHERE buddy_user_id = ?",
        (buddy_user_id,),
    ).fetchone()
    conn.close()
    if not row or not row["stripe_customer_id"]:
        return jsonify({"error": "No paid subscription exists for this account"}), 404

    session = stripe.billing_portal.Session.create(
        customer=row["stripe_customer_id"],
        return_url=request.host_url.rstrip("/") + "/checkout-success",
    )
    return jsonify({"portal_url": session.url})


@app.route("/checkout-success")
def checkout_success():
    return "Payment complete! You can close this tab and return to Buddy.", 200


@app.route("/checkout-cancel")
def checkout_cancel():
    return "Checkout cancelled. You can close this tab.", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """Stripe calls this directly (not the desktop app) when a payment
    event happens. Signature verification proves it's really Stripe."""
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "invalid signature"}), 400

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        buddy_user_id = obj.get("client_reference_id") or obj.get("metadata", {}).get("buddy_user_id")
        customer_id = obj.get("customer")
        if obj.get("payment_status") != "paid" or not buddy_user_id or not customer_id:
            return jsonify({"received": True}), 200
        # Look up the price actually purchased to know which tier to grant
        line_items = stripe.checkout.Session.list_line_items(obj["id"])
        price_id = line_items.data[0].price.id if line_items.data else None
        tier = PRICE_TO_TIER.get(price_id)
        if tier:
            _upsert_subscription(buddy_user_id, customer_id, tier)

    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        customer_id = obj.get("customer")
        status = obj.get("status")
        if status in ("canceled", "unpaid", "incomplete_expired"):
            _set_tier_by_customer(customer_id, "free")
        elif status in ("active", "trialing"):
            price_id = obj["items"]["data"][0]["price"]["id"] if obj.get("items") else None
            tier = PRICE_TO_TIER.get(price_id)
            if tier:
                _set_tier_by_customer(customer_id, tier)

    return jsonify({"received": True}), 200


@app.route("/subscription-status/<buddy_user_id>")
def subscription_status(buddy_user_id):
    """Desktop app polls this after checkout to learn the current tier."""
    conn = _connect()
    row = conn.execute(
        "SELECT subscription_tier FROM users WHERE buddy_user_id = ?", (buddy_user_id,)
    ).fetchone()
    conn.close()
    tier = row["subscription_tier"] if row else "free"
    return jsonify({"buddy_user_id": buddy_user_id, "subscription_tier": tier})


def _upsert_subscription(buddy_user_id, customer_id, tier):
    conn = _connect()
    conn.execute(
        """
        INSERT INTO users (buddy_user_id, stripe_customer_id, subscription_tier, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(buddy_user_id) DO UPDATE SET
            stripe_customer_id = excluded.stripe_customer_id,
            subscription_tier = excluded.subscription_tier,
            updated_at = excluded.updated_at
        """,
        (buddy_user_id, customer_id, tier, time.time()),
    )
    conn.commit()
    conn.close()


def _set_tier_by_customer(customer_id, tier):
    conn = _connect()
    conn.execute(
        "UPDATE users SET subscription_tier = ?, updated_at = ? WHERE stripe_customer_id = ?",
        (tier, time.time(), customer_id),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))