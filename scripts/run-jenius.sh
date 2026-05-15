#!/bin/zsh
# Runs the /jenius pipeline non-interactively.
# Invoked by the LaunchAgent — do not run manually (use /jenius in Claude Code instead).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/claude-agents"
LOG_FILE="$LOG_DIR/jenius.log"

mkdir -p "$LOG_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') Starting /jenius" >> "$LOG_FILE"

cd "$REPO_DIR"

# Source shell environment so spark, python3, etc. are available
source "$HOME/.zshrc" 2>/dev/null || true

/opt/homebrew/bin/claude \
  --dangerously-skip-permissions \
  --print "/jenius" \
  >> "$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') Done" >> "$LOG_FILE"
