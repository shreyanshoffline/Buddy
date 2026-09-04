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
import stripe
from flask import Flask, request, jsonify, redirect

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