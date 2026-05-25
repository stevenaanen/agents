#!/bin/zsh
# Runs the /jenius pipeline non-interactively.
# Invoked by the LaunchAgent — do not run manually (use /jenius in Claude Code instead).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/claude-agents"
LOG_FILE="$LOG_DIR/jenius.log"
LAST_RUN_FILE="$LOG_DIR/jenius.last-run-date"

mkdir -p "$LOG_DIR"

# Skip if we already ran today — RunAtLoad fires on every login/boot, this
# guard makes sure we only do the work once per calendar day.
today="$(date +%Y-%m-%d)"
if [[ -f "$LAST_RUN_FILE" && "$(cat "$LAST_RUN_FILE")" == "$today" ]]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Already ran today — skipping" >> "$LOG_FILE"
  exit 0
fi

notify() {
  local msg="$1"
  local env_file="$REPO_DIR/skills/telegram/.env"
  [[ -f "$env_file" ]] || return 0
  set -a; source "$env_file"; set +a
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]] || return 0
  curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
       -d chat_id="$TELEGRAM_CHAT_ID" \
       -d text="$msg" \
       >/dev/null 2>&1 || true
}

echo "$(date '+%Y-%m-%d %H:%M:%S') Starting /jenius" >> "$LOG_FILE"

cd "$REPO_DIR"

# Source shell environment so spark, python3, etc. are on PATH
source "$HOME/.zshrc" 2>/dev/null || true

# Pre-flight: /jenius is useless without Spark Desktop reachable. Bail early with
# a clear message instead of letting claude run a half-broken pipeline.
if ! command -v spark >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') spark CLI not found on PATH" >> "$LOG_FILE"
  notify "⚠️ Jenius skipped — spark CLI not found on PATH"
  echo "$today" > "$LAST_RUN_FILE"
  exit 1
fi
if ! spark accounts >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Spark Desktop not running — skipping" >> "$LOG_FILE"
  notify "⚠️ Jenius skipped — Spark Desktop is not running. Launch it and rerun if you want today's run."
  # Don't mark today as done: if Spark comes up later and the agent reloads
  # (next login/boot), we'll retry. Avoids losing a day silently.
  exit 1
fi

if /opt/homebrew/bin/claude \
     --dangerously-skip-permissions \
     --print "/jenius" \
     >> "$LOG_FILE" 2>&1; then
  echo "$today" > "$LAST_RUN_FILE"
  echo "$(date '+%Y-%m-%d %H:%M:%S') Done" >> "$LOG_FILE"
  notify "✅ Jenius ran $(date '+%a %H:%M')"
else
  exit_code=$?
  echo "$(date '+%Y-%m-%d %H:%M:%S') Failed (exit $exit_code)" >> "$LOG_FILE"
  # Mark today done so we don't keep retrying on every wake/login — a hard
  # failure means the user needs to look, not have launchd spam them.
  echo "$today" > "$LAST_RUN_FILE"
  notify "❌ Jenius failed $(date '+%a %H:%M') (exit $exit_code) — see ~/Library/Logs/claude-agents/jenius.log"
  exit 1
fi
