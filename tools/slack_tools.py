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
        return "Slack is not connected. Plugins > Slack > Connect, then /invite @Buddy in the channel."
    channels = data.get("channels") or []
    if not channels:
        return "No channels visible yet. In Slack run /invite @Buddy in the ones Buddy should read."
    lines = [f"Workspace: {data.get('team_name') or 'Slack'}"]
    for channel in channels:
        flag = "private" if channel.get("is_private") else "public"
        lines.append(f"#{channel.get('name')} ({channel.get('id')}, {flag})")
    return "\n".join(lines)


def slack_recent_messages(channel: str, limit: int = 15) -> str:
    token = _local_token()
    channel = _resolve_channel(token, channel)
    if token:
        integrations._require_requests()
        response = integrations.requests.get(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": "Bearer %s" % token},
            params={"channel": channel, "limit": limit},
            timeout=15,
        )
        data = response.json()
        data["messages"] = [
            "%s: %s" % (message.get("user") or "Slack", message.get("text") or "")
            for message in reversed(data.get("messages") or [])
        ]
    else:
        data = billing_client.slack_channel_history(_uid(), channel, limit=limit)
    if not data.get("ok"):
        return (
            data.get("error")
            or "Could not read that channel. Invite @Buddy first with /invite @Buddy."
        )
    messages = data.get("messages") or []
    if not messages:
        return "No recent messages, or Buddy is not in that channel yet."
    return "\n".join(messages)


def slack_send_message(channel: str, text: str) -> str:
    token = _local_token()
    channel = _resolve_channel(token, channel)
    if token:
        data = integrations.slack_post_message(token, channel, text)
        data = {"ok": True, "result": data}
    else:
        data = billing_client.slack_post_message(_uid(), channel, text)
    if not data.get("ok"):
        return data.get("error") or "Slack could not send that message."
    return "Sent to Slack."
