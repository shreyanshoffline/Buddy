"""Linking outside accounts to Buddy — separate from the local-Mac-app
catalog in app_catalog.py. These are real network calls, not stubs:

- GitHub uses OAuth's Device Flow, which is built for exactly this case
  (a desktop app with no safe place to hold a client secret). It only
  needs a client ID, which is *not* secret.
- Notion and Linear don't offer a secretless flow, so instead of faking
  OAuth we ask for a personal access token / API key and verify it works
  with one real, read-only request before saving it.

GITHUB_CLIENT_ID below is a placeholder — same situation as the Stripe
price IDs in BUDDY-DESKTOP-README.md. Register a free OAuth App at
https://github.com/settings/developers (Device Flow enabled, no callback
URL or secret needed) and drop the client ID in here, or read it from an
env var if you'd rather not commit it.
"""
import os
import time

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

GITHUB_CLIENT_ID = os.environ.get("BUDDY_GITHUB_CLIENT_ID", "")  # <-- set this
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_SCOPES = "repo read:user"


class IntegrationError(Exception):
    pass


def _require_requests():
    if not HAS_REQUESTS:
        raise IntegrationError("The 'requests' package isn't installed. Run manage_package('install', 'requests').")


# --- GitHub: OAuth Device Flow ------------------------------------------

def github_start_device_flow():
    """Kicks off the device flow. Returns the code to show the user and
    the info needed to poll for a token."""
    _require_requests()
    if not GITHUB_CLIENT_ID:
        raise IntegrationError(
            "No GitHub client ID configured. Register a free OAuth App at "
            "github.com/settings/developers (enable Device Flow, no secret "
            "needed) and set BUDDY_GITHUB_CLIENT_ID."
        )
    resp = requests.post(
        GITHUB_DEVICE_CODE_URL,
        headers={"Accept": "application/json"},
        data={"client_id": GITHUB_CLIENT_ID, "scope": GITHUB_SCOPES},
        timeout=15,
    )
    data = resp.json()
    if "device_code" not in data:
        raise IntegrationError(data.get("error_description") or "GitHub didn't return a device code.")
    return data  # device_code, user_code, verification_uri, expires_in, interval


def github_poll_for_token(device_code, interval=5, timeout=900, cancel_check=None):
    """Blocking poll — call this from a background thread. Returns the
    access token once the user approves the device code in their browser."""
    _require_requests()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cancel_check and cancel_check():
            raise IntegrationError("Cancelled.")
        resp = requests.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" in data:
            return data["access_token"]
        error = data.get("error")
        if error == "authorization_pending":
            time.sleep(interval)
            continue
        if error == "slow_down":
            interval = data.get("interval", interval + 5)
            time.sleep(interval)
            continue
        raise IntegrationError(data.get("error_description") or error or "GitHub authorization failed.")
    raise IntegrationError("Timed out waiting for GitHub authorization.")


def github_whoami(access_token):
    """One real API call to confirm the token works and get a username to show."""
    _require_requests()
    resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise IntegrationError(f"GitHub rejected that token ({resp.status_code}).")
    data = resp.json()
    return data.get("login") or "connected"


# --- Notion & Linear: personal access token, verified with one call -----

def notion_verify_token(token):
    _require_requests()
    resp = requests.get(
        "https://api.notion.com/v1/users/me",
        headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise IntegrationError("Notion rejected that integration token.")
    data = resp.json()
    return data.get("name") or data.get("bot", {}).get("owner", {}).get("type") or "connected"


def linear_verify_token(token):
    _require_requests()
    resp = requests.post(
        "https://api.linear.app/graphql",
        headers={"Authorization": token, "Content-Type": "application/json"},
        json={"query": "{ viewer { name email } }"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise IntegrationError("Linear rejected that API key.")
    data = resp.json().get("data", {}).get("viewer")
    if not data:
        raise IntegrationError("Linear rejected that API key.")
    return data.get("name") or data.get("email") or "connected"


def slack_verify_token(token):
    """auth.test is read-only and returns workspace + user identity."""
    _require_requests()
    resp = requests.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": "Bearer %s" % token},
        timeout=15,
    )
    data = resp.json() if resp.content else {}
    if not data.get("ok"):
        raise IntegrationError(data.get("error") or "Slack rejected that token.")
    team = data.get("team") or "workspace"
    user = data.get("user") or data.get("user_id") or "connected"
    return "%s @ %s" % (user, team)


def slack_post_message(token, channel, text):
    _require_requests()
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": "Bearer %s" % token, "Content-Type": "application/json"},
        json={"channel": channel, "text": text},
        timeout=15,
    )
    data = resp.json() if resp.content else {}
    if not data.get("ok"):
        raise IntegrationError(data.get("error") or "Slack could not send that message.")
    return data.get("ts") or "sent"


CONNECTION_VERIFIERS = {
    "notion": notion_verify_token,
    "linear": linear_verify_token,
    "slack": slack_verify_token,
}
