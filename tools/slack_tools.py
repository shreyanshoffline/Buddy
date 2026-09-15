"""Slack tools Buddy calls from the desktop chat — not from Slack itself."""
import core
import billing_client


def _uid():
    return core.get_or_create_buddy_user_id()


def slack_list_channels() -> str:
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
    data = billing_client.slack_post_message(_uid(), channel, text)
    if not data.get("ok"):
        return data.get("error") or "Slack could not send that message."
    return "Sent to Slack."