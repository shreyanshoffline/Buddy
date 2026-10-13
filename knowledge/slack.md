# Slack guide — connecting and using Slack from Buddy
Tools: slack_list_channels, slack_recent_messages(channel, limit), slack_send_message(channel, text). Slack runs through a bot (xoxb- token); Buddy can only see channels the bot was invited to.

## Connect (fastest, always works): paste a bot token
1. https://api.slack.com/apps > Create New App > From scratch > pick workspace.
2. OAuth & Permissions > Bot Token Scopes: channels:read, channels:history, groups:read, groups:history, chat:write, users:read.
3. Install to Workspace > copy the "Bot User OAuth Token" (starts with xoxb-).
4. Buddy > Plugins > Slack > Connect > paste the token.
5. In each Slack channel Buddy should use: /invite @Buddy (the bot's app name).

## Connect via hosted backend (one-click "Add to Slack" for many users)
- Needs the Flask backend deployed with SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, and the redirect URL https://<backend>/slack/callback registered in the Slack app. See PROJECT_STATUS.md.

## Using it
- "What did I miss in #general?" -> slack_list_channels to get the id, slack_recent_messages, summarise.
- Sending: show channel + exact text, get a yes, then slack_send_message. Never DM or post without confirmation.
- Messages show user ids (U123...). Slack's users:read lets you resolve names; if unresolved, say "a teammate".

## Errors
- not_in_channel / channel_not_found: the bot isn't in that channel. Tell the user to /invite it.
- invalid_auth / token_revoked: token is wrong or removed. Reconnect in Plugins.
- missing_scope: add the scope in the Slack app and reinstall, then paste the new token.
