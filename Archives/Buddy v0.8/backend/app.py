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
import json
from urllib.parse import urlencode
import stripe
import requests
from flask import Flask, request, jsonify, redirect
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
load_dotenv(os.path.join(_ROOT, ".env"))
load_dotenv(os.path.join(_HERE, ".env"))
load_dotenv()

app = Flask(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

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

DB_PATH = os.environ.get("BILLING_DB_PATH") or os.path.join(_ROOT, "billing.db")
HACKCLUB_CLIENT_ID = os.environ.get("HACKCLUB_CLIENT_ID", "")
HACKCLUB_CLIENT_SECRET = os.environ.get("HACKCLUB_CLIENT_SECRET", "")
DEFAULT_HACKCLUB_REDIRECT_URI = "http://127.0.0.1:5000/auth/hackclub/callback"
HACKCLUB_REDIRECT_URI = (
    os.environ.get("HACKCLUB_REDIRECT_URI") or DEFAULT_HACKCLUB_REDIRECT_URI
).strip().rstrip("/")
_oauth_states = set()
_oauth_state_users = {}
_latest_hackclub_profile = None
# Must be a subset of the scopes checked on your Hack Club developer app.
# Community-allowed: openid profile email name slack_id verification_status
HACKCLUB_SCOPES = (
    os.environ.get("HACKCLUB_SCOPES")
    or "openid email name verification_status"
)


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
            hackclub_verified INTEGER DEFAULT 0,
            hackclub_verification_status TEXT,
            hackclub_email TEXT,
            hackclub_name TEXT,
            hackclub_signed_in_at REAL,
            hackclub_identity_id TEXT,
            hackclub_slack_id TEXT,
            hackclub_ysws_eligible INTEGER DEFAULT 0,
            hackclub_refresh_token TEXT,
            updated_at REAL
        )
    """)
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)")]
    for col, decl in (
        ("hackclub_verified", "INTEGER DEFAULT 0"),
        ("hackclub_verification_status", "TEXT"),
        ("hackclub_email", "TEXT"),
        ("hackclub_name", "TEXT"),
        ("hackclub_signed_in_at", "REAL"),
        ("hackclub_identity_id", "TEXT"),
        ("hackclub_slack_id", "TEXT"),
        ("hackclub_ysws_eligible", "INTEGER DEFAULT 0"),
        ("hackclub_refresh_token", "TEXT"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            buddy_user_id TEXT,
            created_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_latest (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload TEXT,
            updated_at REAL
        )
    """)
    conn.commit()
    conn.close()


init_db()


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "hackclub_client_id_set": bool(HACKCLUB_CLIENT_ID),
        "hackclub_secret_set": bool(HACKCLUB_CLIENT_SECRET),
        "redirect_uri": HACKCLUB_REDIRECT_URI,
    })


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
    """Start Hack Club OAuth using a registered callback + durable state."""
    if not HACKCLUB_CLIENT_ID:
        return _oauth_page("Hack Club is not configured", "Set HACKCLUB_CLIENT_ID in the backend .env.", ok=False), 503
    if not HACKCLUB_CLIENT_SECRET:
        return _oauth_page("Hack Club is not configured", "Set HACKCLUB_CLIENT_SECRET in the backend .env.", ok=False), 503
    state = secrets.token_urlsafe(32)
    buddy_user_id = request.args.get("buddy_user_id", "") or "latest"
    _remember_oauth_state(state, buddy_user_id)
    params = urlencode({
        "client_id": HACKCLUB_CLIENT_ID,
        "redirect_uri": HACKCLUB_REDIRECT_URI,
        "response_type": "code",
        "scope": HACKCLUB_SCOPES,
        "state": state,
    })
    return redirect(f"https://auth.hackclub.com/oauth/authorize?{params}")


def _oauth_page(title, body, ok=True):
    color = "#188038" if ok else "#b3261e"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#eef6fc; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:#1f2937; }}
main {{ width:min(460px, calc(100% - 40px)); padding:32px; background:white; border:1px solid #d7e2ec; border-radius:16px; }}
h1 {{ margin:0 0 8px; color:{color}; font-size:24px; }}
p {{ line-height:1.5; color:#5f6b7a; }}
</style></head><body><main><h1>{title}</h1><p>{body}</p></main></body></html>"""


def _remember_oauth_state(state, buddy_user_id):
    _oauth_states.add(state)
    _oauth_state_users[state] = buddy_user_id
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO oauth_states (state, buddy_user_id, created_at) VALUES (?, ?, ?)",
        (state, buddy_user_id, time.time()),
    )
    conn.commit()
    conn.close()


def _pop_oauth_state(state):
    buddy_user_id = _oauth_state_users.pop(state, "") if state else ""
    if state in _oauth_states:
        _oauth_states.remove(state)
    conn = _connect()
    row = conn.execute("SELECT buddy_user_id FROM oauth_states WHERE state = ?", (state,)).fetchone()
    if row and not buddy_user_id:
        buddy_user_id = row["buddy_user_id"] or ""
    if state:
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()
    conn.close()
    return buddy_user_id


def _exchange_hackclub_code(code):
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": HACKCLUB_REDIRECT_URI,
        "client_id": HACKCLUB_CLIENT_ID,
        "client_secret": HACKCLUB_CLIENT_SECRET,
    }
    last_error = None
    for kwargs in (
        {"json": payload, "headers": {"Accept": "application/json"}},
        {"data": payload, "headers": {"Accept": "application/json"}},
    ):
        try:
            response = requests.post("https://auth.hackclub.com/oauth/token", timeout=15, **kwargs)
            if response.ok:
                data = response.json()
                if data.get("access_token"):
                    return data
            last_error = f"{response.status_code} {response.text[:500]}"
        except requests.RequestException as error:
            last_error = str(error)
    raise RuntimeError(last_error or "token exchange failed")


def _store_latest_profile(profile):
    global _latest_hackclub_profile
    _latest_hackclub_profile = profile
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO oauth_latest (id, payload, updated_at) VALUES (1, ?, ?)",
        (json.dumps(profile), time.time()),
    )
    conn.commit()
    conn.close()


def _load_latest_profile():
    if _latest_hackclub_profile:
        return _latest_hackclub_profile
    conn = _connect()
    row = conn.execute("SELECT payload FROM oauth_latest WHERE id = 1").fetchone()
    conn.close()
    if not row or not row["payload"]:
        return {"signed_in": False}
    try:
        return json.loads(row["payload"])
    except json.JSONDecodeError:
        return {"signed_in": False}


def _save_hackclub_profile(
    buddy_user_id,
    *,
    email,
    name,
    verified,
    verification_status,
    identity_id,
    slack_id,
    ysws_eligible,
    refresh_token=None,
):
    """Upsert OAuth data without replacing an existing billing record."""
    conn = _connect()
    conn.execute(
        """
        INSERT INTO users (
            buddy_user_id, hackclub_verified, hackclub_verification_status,
            hackclub_email, hackclub_name, hackclub_signed_in_at,
            hackclub_identity_id, hackclub_slack_id, hackclub_ysws_eligible,
            hackclub_refresh_token, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(buddy_user_id) DO UPDATE SET
            hackclub_verified = excluded.hackclub_verified,
            hackclub_verification_status = excluded.hackclub_verification_status,
            hackclub_email = excluded.hackclub_email,
            hackclub_name = excluded.hackclub_name,
            hackclub_signed_in_at = excluded.hackclub_signed_in_at,
            hackclub_identity_id = excluded.hackclub_identity_id,
            hackclub_slack_id = excluded.hackclub_slack_id,
            hackclub_ysws_eligible = excluded.hackclub_ysws_eligible,
            hackclub_refresh_token = COALESCE(excluded.hackclub_refresh_token, users.hackclub_refresh_token),
            updated_at = excluded.updated_at
        """,
        (
            buddy_user_id,
            int(verified),
            verification_status,
            email,
            name,
            time.time(),
            identity_id,
            slack_id,
            int(ysws_eligible),
            refresh_token,
            time.time(),
        ),
    )
    conn.commit()
    conn.close()


@app.route("/auth/hackclub/callback")
def hackclub_callback():
    """Receive OAuth's code, persist the profile, and tell Buddy to poll."""
    error = request.args.get("error")
    if error:
        return _oauth_page("Sign-in cancelled", f"Hack Club returned: {error}", ok=False), 400

    state = request.args.get("state", "")
    buddy_user_id = _pop_oauth_state(state) if state else ""
    if state and not buddy_user_id and state not in _oauth_states:
        # State was already consumed or never issued by this backend.
        # Still try to finish if a code is present so a refresh cannot brick sign-in.
        buddy_user_id = "latest"

    code = request.args.get("code")
    if not code:
        return _oauth_page("Missing code", "Hack Club did not send an authorization code.", ok=False), 400
    if not HACKCLUB_CLIENT_SECRET:
        return _oauth_page("Missing secret", "Set HACKCLUB_CLIENT_SECRET on the backend first.", ok=False), 503

    try:
        token_data = _exchange_hackclub_code(code)
    except Exception as error:
        app.logger.exception("Hack Club token exchange failed")
        return _oauth_page("Token exchange failed", f"Check the backend terminal. {error}", ok=False), 502

    access_token = token_data.get("access_token")
    try:
        user_response = requests.get(
            "https://auth.hackclub.com/api/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        user_response.raise_for_status()
    except requests.RequestException as error:
        detail = ""
        if getattr(error, "response", None) is not None:
            detail = error.response.text[:400]
        app.logger.exception("Hack Club profile request failed")
        return _oauth_page("Profile request failed", f"{error} {detail}", ok=False), 502

    profile = user_response.json()
    identity = profile.get("identity") or profile
    first_name = identity.get("first_name") or ""
    last_name = identity.get("last_name") or ""
    name = (f"{first_name} {last_name}").strip() or identity.get("name") or identity.get("nickname")
    email = identity.get("primary_email") or identity.get("email")
    verification = identity.get("verification_status") or "unknown"
    is_verified = str(verification).lower() == "verified"
    ysws_eligible = bool(identity.get("ysws_eligible"))
    saved = {
        "signed_in": True,
        "verified": is_verified,
        "verification_status": str(verification),
        "email": email,
        "name": name,
        "identity_id": identity.get("id"),
        "slack_id": identity.get("slack_id"),
        "ysws_eligible": ysws_eligible,
    }
    _store_latest_profile(saved)

    try:
        import sys
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if root not in sys.path:
            sys.path.insert(0, root)
        from storage import db as local_db
        local_db.init_db()
        local_db.update_profile(
            email=email,
            name=name,
            auth_provider="hackclub",
            hackclub_verified=is_verified,
            hackclub_verification_status=str(verification),
            hackclub_identity_id=identity.get("id"),
            hackclub_slack_id=identity.get("slack_id"),
            hackclub_ysws_eligible=ysws_eligible,
        )
    except Exception as error:
        app.logger.warning("Could not update local Buddy profile after OAuth: %s", error)

    _save_hackclub_profile(
        buddy_user_id or "latest",
        email=email,
        name=name,
        verified=is_verified,
        verification_status=str(verification),
        identity_id=identity.get("id"),
        slack_id=identity.get("slack_id"),
        ysws_eligible=ysws_eligible,
        refresh_token=token_data.get("refresh_token"),
    )

    status_word = "verified" if is_verified else str(verification)
    return _oauth_page(
        "Signed in with Hack Club",
        f"Status: {status_word}. You can close this tab and return to Buddy.",
        ok=True,
    ), 200


@app.route("/auth/hackclub/status/<buddy_user_id>")
def hackclub_status(buddy_user_id):
    """Desktop app polls this after opening the sign-in browser tab."""
    conn = _connect()
    row = conn.execute(
        "SELECT hackclub_verified, hackclub_verification_status, hackclub_email, hackclub_name, "
        "hackclub_signed_in_at, hackclub_identity_id, hackclub_slack_id, hackclub_ysws_eligible "
        "FROM users WHERE buddy_user_id = ?",
        (buddy_user_id,),
    ).fetchone()
    conn.close()
    if row and row["hackclub_signed_in_at"]:
        return jsonify({
            "signed_in": True,
            "verified": bool(row["hackclub_verified"]),
            "verification_status": row["hackclub_verification_status"],
            "email": row["hackclub_email"],
            "name": row["hackclub_name"],
            "identity_id": row["hackclub_identity_id"],
            "slack_id": row["hackclub_slack_id"],
            "ysws_eligible": bool(row["hackclub_ysws_eligible"]),
        })
    return jsonify(_load_latest_profile())


@app.route("/auth/hackclub/status/latest")
def hackclub_latest_status():
    """Return the most recent OAuth result for direct-link sign-in."""
    return jsonify(_load_latest_profile())


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
    if not stripe.api_key:
        return jsonify({"error": "Stripe is not configured on the backend"}), 503

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
    if not stripe.api_key:
        return jsonify({"error": "Stripe is not configured on the backend"}), 503
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

    if not WEBHOOK_SECRET:
        return jsonify({"error": "Stripe webhook is not configured"}), 503
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
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)