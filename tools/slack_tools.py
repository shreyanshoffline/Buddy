"""Slack tools Buddy calls from the desktop chat — not from Slack itself."""
import core
from backend import client as billing_client
from tools import integrations


def _local_token():
    connection = core.get_plugin_connection("slack") or {}
    token = connection.get("access_token") or ""
    return token if token.startswith("xox") else ""


def _uid():
    return core.get_or_create_buddy_user_id()


_SLACK_HINTS = {
    "invalid_auth": "The Slack token is invalid or was revoked. Reconnect Slack in Plugins.",
    "token_revoked": "The Slack token was revoked. Reconnect Slack in Plugins.",
    "not_authed": "Slack is not connected. Plugins > Slack > Connect.",
    "missing_scope": "The Slack app is missing a permission scope. Add it in the Slack app, reinstall, and paste the new token.",
    "not_in_channel": "Buddy's bot is not in that channel. Run /invite @Buddy there.",
    "channel_not_found": "Slack could not find that channel. Check the name, or run /invite @Buddy if it is private.",
    "ratelimited": "Slack is rate limiting requests. Try again in a minute.",
}


def _explain(error):
    return _SLACK_HINTS.get(error) or "Slack error: %s" % (error or "unknown")


def _get(token, method, **params):
    integrations._require_requests()
    return integrations.requests.get(
        "https://slack.com/api/" + method,
        headers={"Authorization": "Bearer %s" % token},
        params=params,
        timeout=15,
    ).json()


def _user_names(token, ids):
    """Best-effort id -> display name map (needs users:read, falls back to the id)."""
    names = {}
    for uid in ids:
        if not uid or uid in names:
            continue
        try:
            info = _get(token, "users.info", user=uid)
            user = info.get("user") or {}
            profile = user.get("profile") or {}
            names[uid] = profile.get("display_name") or user.get("real_name") or user.get("name") or uid
        except Exception:
            names[uid] = uid
    return names


def _resolve_channel(token, channel):
    """Slack's API wants ids (C0123...); accept '#name' / 'name' too."""
    import re
    channel = (channel or "").strip()
    if re.fullmatch(r"[CGD][A-Z0-9]{8,}", channel) or not token:
        return channel
    name = channel.lstrip("#").lower()
    cursor = ""
    for _ in range(5):
        integrations._require_requests()
        data = integrations.requests.get(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": "Bearer %s" % token},
            params={"types": "public_channel,private_channel", "limit": 200, "cursor": cursor},
            timeout=15,
        ).json()
        for ch in data.get("channels") or []:
            if (ch.get("name") or "").lower() == name:
                return ch["id"]
        cursor = (data.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return channel


def slack_list_channels() -> str:
    token = _local_token()
    if token:
        integrations._require_requests()
        response = integrations.requests.get(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": "Bearer %s" % token},
            params={"types": "public_channel,private_channel", "limit": 200},
            timeout=15,
        )
        data = response.json()
    else:
        data = billing_client.slack_list_channels(_uid())
    if not data.get("ok"):
        return _explain(data.get("error"))
    channels = data.get("channels") or []
    if not channels:
        return "No channels visible yet. In Slack run /invite @Buddy in the ones Buddy should read."
    lines = [f"Workspace: {data.get('team_name') or (core.get_plugin_connection('slack') or {}).get('account_label') or 'Slack'}"]
    for channel in channels:
        flag = "private" if channel.get("is_private") else "public"
        lines.append(f"#{channel.get('name')} ({channel.get('id')}, {flag})")
    return "\n".join(lines)


def slack_recent_messages(channel: str, limit: int = 15) -> str:
    token = _local_token()
    channel = _resolve_channel(token, channel)
    if token:
        data = _get(token, "conversations.history", channel=channel, limit=limit)
        if not data.get("ok") and data.get("error") == "not_in_channel":
            # Public channels can be joined automatically when the app has channels:join.
            integrations._require_requests()
            joined = integrations.requests.post(
                "https://slack.com/api/conversations.join",
                headers={"Authorization": "Bearer %s" % token},
                data={"channel": channel},
                timeout=15,
            ).json()
            if joined.get("ok"):
                data = _get(token, "conversations.history", channel=channel, limit=limit)
        if data.get("ok"):
            raw = list(reversed(data.get("messages") or []))
            names = _user_names(token, {m.get("user") for m in raw})
            data["messages"] = [
                "%s: %s" % (names.get(m.get("user")) or m.get("user") or m.get("username") or "Slack", m.get("text") or "")
                for m in raw
            ]
    else:
        data = billing_client.slack_channel_history(_uid(), channel, limit=limit)
    if not data.get("ok"):
        return _explain(data.get("error"))
    messages = data.get("messages") or []
    if not messages:
        return "No recent messages in that channel."
    return "\n".join(messages)


def slack_send_message(channel: str, text: str) -> str:
    token = _local_token()
    channel = _resolve_channel(token, channel)
    if token:
        try:
            integrations.slack_post_message(token, channel, text)
            data = {"ok": True}
        except integrations.IntegrationError as exc:
            data = {"ok": False, "error": str(exc)}
    else:
        data = billing_client.slack_post_message(_uid(), channel, text)
    if not data.get("ok"):
        return _explain(data.get("error"))
    return "Sent to Slack."
