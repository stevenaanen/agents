---
name: telegram
description: >-
  Send Telegram messages to the user and optionally wait for inline keyboard
  responses. Use in any workflow that needs to notify or prompt the user.
---

# Telegram Connector

Sends messages to the user's Telegram chat via a bot. Supports inline keyboards
so the user can tap a button to send a structured reply back to the workflow.

## Setup (one-time)

1. Create a bot via @BotFather → copy the token
2. Send any message to your new bot, then call:
   `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` → copy the `chat.id`
3. Create `skills/telegram/.env` from `.env.example` with both values

## Send a message

```bash
python3 skills/telegram/telegram.py send "Your message here"
# → prints message_id
```

Supports Markdown: `*bold*`, `_italic_`, `` `code` ``

## Send with inline keyboard

```bash
python3 skills/telegram/telegram.py send "Approve transaction?" \
  --keyboard '[["Yes:yes", "No:no"], ["Remind me later:later"]]'
# → prints message_id
```

Keyboard format: `[["Label:callback_data", ...], ...]`
Each inner array is one row of buttons. If no `:` is present, label = callback_data.

## Wait for a button tap

```bash
python3 skills/telegram/telegram.py wait --message-id <id> --timeout 120
# → prints callback_data (e.g. "yes"), or exits 1 on timeout
```

`--message-id` scopes the wait to a specific message (recommended).
`--timeout` defaults to 300s.

## Typical pattern in a workflow

```bash
MSG_ID=$(python3 skills/telegram/telegram.py send "Do X?" \
  --keyboard '[["Do it:yes", "Skip:no"]]')
REPLY=$(python3 skills/telegram/telegram.py wait --message-id "$MSG_ID" --timeout 120)
# $REPLY is "yes" or "no"
```
