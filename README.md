# Adopt Me House Shop Bot

## Features
- `/setup` — choose the ticket panel channel, ticket category, vouch channel and optional staff role.
- `/ticketpanel channel:#channel` — send a ticket panel anywhere.
- `/say channel:#channel message:...` — send a styled announcement.
- `/vouch message:...` — posts a designed customer vouch to the configured vouch channel.
- Private ticket channels and staff-only close button.

## Install

```bash
pip install -r requirements.txt
```

Set the bot token:

### Windows PowerShell
```powershell
$env:DISCORD_TOKEN="YOUR_BOT_TOKEN"
python bot.py
```

Invite the bot with `bot` and `applications.commands` scopes. Give it View Channels, Send Messages, Embed Links, Manage Channels, and Read Message History.

## First setup

Run:

```text
/setup
```

Choose:
- `panel_channel` → `#・open-ticket`
- `ticket_category` → your `🎫 SUPPORT TICKETS` category
- `vouch_channel` → `#・vouches`
- `staff_role` → your staff role

Then members can use:

```text
/vouch message: Amazing build! Fast and friendly service ⭐⭐⭐⭐⭐
```

Keep the bot token private.
