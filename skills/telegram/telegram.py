#!/usr/bin/env python3
"""
Telegram connector for Claude Code workflows.

Subcommands:
  send "text" [--keyboard '[["Label:data", ...], ...]']  → prints message_id
  wait [--message-id ID] [--timeout 300]                 → prints callback_data or exits 1
  wait-many --message-ids ID1,ID2,... [--timeout 600]    → streams "<id> <data>" per reply;
                                                           remaining IDs get keyboards cleared
                                                           on timeout and are NOT printed.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path


def load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def api(token, method, data=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def cmd_send(token, chat_id, text, keyboard_json=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}

    if keyboard_json:
        # Each row is a list of "Label:callback_data" strings.
        # Single-word buttons without ":" use the label as both text and data.
        rows = []
        for row in json.loads(keyboard_json):
            buttons = []
            for btn in row:
                label, cb = btn.split(":", 1) if ":" in btn else (btn, btn)
                buttons.append({"text": label, "callback_data": cb})
            rows.append(buttons)
        data["reply_markup"] = {"inline_keyboard": rows}

    result = api(token, "sendMessage", data)
    print(result["result"]["message_id"])


def clear_keyboard(token, chat_id, message_id):
    api(token, "editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": {"inline_keyboard": []},
    })


def cmd_wait(token, message_id=None, timeout=300):
    # Flush all pending updates so we only catch callbacks that arrive after this call.
    result = api(token, "getUpdates", {"timeout": 0})
    offset = (result["result"][-1]["update_id"] + 1) if result["result"] else 0

    deadline = time.time() + timeout
    while time.time() < deadline:
        poll_secs = min(30, int(deadline - time.time()))
        if poll_secs <= 0:
            break
        result = api(token, "getUpdates", {
            "offset": offset,
            "timeout": poll_secs,
            "allowed_updates": ["callback_query"],
        })
        for update in result["result"]:
            offset = update["update_id"] + 1
            cq = update.get("callback_query")
            if not cq:
                continue
            if message_id is None or cq["message"]["message_id"] == message_id:
                api(token, "answerCallbackQuery", {"callback_query_id": cq["id"]})
                clear_keyboard(token, cq["message"]["chat"]["id"], cq["message"]["message_id"])
                print(cq["data"])
                return

    print("timeout", file=sys.stderr)
    sys.exit(1)


def cmd_wait_many(token, chat_id, message_ids, timeout=600):
    pending = set(message_ids)

    # Flush pending updates so we only catch callbacks that arrive after this call.
    result = api(token, "getUpdates", {"timeout": 0})
    offset = (result["result"][-1]["update_id"] + 1) if result["result"] else 0

    deadline = time.time() + timeout
    while pending and time.time() < deadline:
        poll_secs = min(30, int(deadline - time.time()))
        if poll_secs <= 0:
            break
        result = api(token, "getUpdates", {
            "offset": offset,
            "timeout": poll_secs,
            "allowed_updates": ["callback_query"],
        })
        for update in result["result"]:
            offset = update["update_id"] + 1
            cq = update.get("callback_query")
            if not cq:
                continue
            mid = cq["message"]["message_id"]
            if mid not in pending:
                continue
            api(token, "answerCallbackQuery", {"callback_query_id": cq["id"]})
            clear_keyboard(token, cq["message"]["chat"]["id"], mid)
            print(f"{mid} {cq['data']}", flush=True)
            pending.discard(mid)

    # Window closed: clear keyboards on un-answered prompts so the user
    # can't tap them after the workflow has moved on.
    for mid in pending:
        try:
            clear_keyboard(token, chat_id, mid)
        except Exception:
            pass


def main():
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required in skills/telegram/.env", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_send = sub.add_parser("send")
    p_send.add_argument("text")
    p_send.add_argument("--keyboard", metavar="JSON",
                        help='Rows of buttons: [["Label:data", ...], ...]')

    p_wait = sub.add_parser("wait")
    p_wait.add_argument("--message-id", type=int,
                        help="Only accept callbacks for this message (recommended)")
    p_wait.add_argument("--timeout", type=int, default=300,
                        help="Seconds to wait before giving up (default 300)")

    p_many = sub.add_parser("wait-many")
    p_many.add_argument("--message-ids", required=True,
                        help="Comma-separated message IDs to listen for")
    p_many.add_argument("--timeout", type=int, default=600,
                        help="Seconds to wait before giving up (default 600)")

    args = parser.parse_args()

    if args.cmd == "send":
        cmd_send(token, chat_id, args.text, args.keyboard)
    elif args.cmd == "wait":
        cmd_wait(token, args.message_id, args.timeout)
    elif args.cmd == "wait-many":
        ids = [int(x) for x in args.message_ids.split(",") if x.strip()]
        cmd_wait_many(token, chat_id, ids, args.timeout)


if __name__ == "__main__":
    main()
