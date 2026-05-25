#!/bin/zsh
# One-time machine setup for the agents repo.
# Run this after cloning on a new machine.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

ok()   { print -P "%F{green}✓%f $1" }
warn() { print -P "%F{yellow}⚠%f $1" }
info() { print -P "%F{blue}→%f $1" }
fail() { print -P "%F{red}✗%f $1"; exit 1 }

echo ""
echo "Setting up agents repo at $REPO_DIR"
echo "======================================"

# ── 1. Check dependencies ────────────────────────────────────────────────────

info "Checking dependencies..."

[[ -x /opt/homebrew/bin/claude ]] \
  && ok "claude found at /opt/homebrew/bin/claude" \
  || warn "claude not found at /opt/homebrew/bin/claude — install from https://claude.ai/code"

command -v spark &>/dev/null \
  && ok "spark found at $(command -v spark)" \
  || warn "spark not found — install Spark Desktop and enable CLI from Settings → Integrations"

command -v python3 &>/dev/null \
  && ok "python3 found at $(command -v python3)" \
  || fail "python3 not found — install via brew install python"

# ── 2. Create .claude/skills/ symlinks ───────────────────────────────────────

info "Registering skills..."

mkdir -p .claude/skills

for skill in jenius jenius-card jenius-review telegram use-spark brew-maintenance; do
  link=".claude/skills/$skill"
  target="../../skills/$skill"
  if [[ -L "$link" ]]; then
    ok "skill /$skill already linked"
  elif [[ -e "$link" ]]; then
    warn "skill /$skill exists but is not a symlink — skipping"
  else
    ln -s "$target" "$link"
    ok "skill /$skill linked"
  fi
done

# ── 3. Create runtime data directories ───────────────────────────────────────

info "Creating data directories..."

mkdir -p skills/jenius-card/data
ok "skills/jenius-card/data/ ready"

# Seed empty pending file if missing
PENDING="skills/jenius-card/data/pending-jenius-transactions.json"
[[ -f "$PENDING" ]] || { echo "[]" > "$PENDING"; ok "seeded $PENDING"; }

REIMBURSEMENTS="skills/jenius-card/data/reimbursements.json"
[[ -f "$REIMBURSEMENTS" ]] || { echo "[]" > "$REIMBURSEMENTS"; ok "seeded $REIMBURSEMENTS"; }

# ── 4. Copy .env.example → .env files ────────────────────────────────────────

info "Setting up .env files..."

for example in skills/*/.env.example; do
  dir="$(dirname "$example")"
  env_file="$dir/.env"
  if [[ -f "$env_file" ]]; then
    ok "$env_file already exists — skipping"
  else
    cp "$example" "$env_file"
    warn "$env_file created from example — fill in your credentials"
  fi
done

# ── 5. Install LaunchAgent ────────────────────────────────────────────────────
# launchd (not cron) because:
#   1. cron on modern macOS can't reach the Keychain → claude CLI fails with
#      "Not logged in". LaunchAgents run in the user session and have access.
#   2. If the laptop is asleep at 09:00, launchd runs the job on next wake.
#      RunAtLoad in the plist also catches full-shutdown days (run-jenius.sh
#      has a "ran today" guard so it doesn't double-fire after a same-day reboot).

info "Installing LaunchAgent..."

LAUNCH_AGENT_LABEL="com.steven.jenius"
LAUNCH_AGENT_SRC="$REPO_DIR/scripts/${LAUNCH_AGENT_LABEL}.plist"
LAUNCH_AGENT_DST="$HOME/Library/LaunchAgents/${LAUNCH_AGENT_LABEL}.plist"

mkdir -p "$HOME/Library/LaunchAgents"

# Migrate away from the old cron entry, if present
if crontab -l 2>/dev/null | grep -qF "run-jenius.sh"; then
  crontab -l 2>/dev/null \
    | grep -vF "run-jenius.sh" \
    | grep -vF "TZ=Europe/Amsterdam" \
    | crontab -
  ok "removed stale cron entry"
fi

# Symlink the plist so repo updates propagate without re-copying
if [[ -L "$LAUNCH_AGENT_DST" ]]; then
  ok "LaunchAgent symlink already present"
elif [[ -e "$LAUNCH_AGENT_DST" ]]; then
  warn "$LAUNCH_AGENT_DST exists but is not a symlink — leaving alone"
else
  ln -s "$LAUNCH_AGENT_SRC" "$LAUNCH_AGENT_DST"
  ok "LaunchAgent linked at $LAUNCH_AGENT_DST"
fi

# (Re)load so changes take effect immediately
if launchctl print "gui/$UID/$LAUNCH_AGENT_LABEL" &>/dev/null; then
  launchctl bootout "gui/$UID/$LAUNCH_AGENT_LABEL" 2>/dev/null || true
fi
if launchctl bootstrap "gui/$UID" "$LAUNCH_AGENT_DST" 2>/dev/null; then
  ok "LaunchAgent loaded (daily 09:00 local, catches up on wake/boot)"
else
  warn "failed to load LaunchAgent — try: launchctl bootstrap gui/\$UID $LAUNCH_AGENT_DST"
fi

# ── 6. Log directory ──────────────────────────────────────────────────────────

mkdir -p "$HOME/Library/Logs/claude-agents"
ok "log directory ready at ~/Library/Logs/claude-agents/"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "======================================"
echo "Setup complete. Next steps:"
echo ""
echo "  1. Fill in credentials:"
echo "     \$ nano skills/telegram/.env"
echo "        TELEGRAM_BOT_TOKEN=<your bot token from @BotFather>"
echo "        TELEGRAM_CHAT_ID=<your chat ID from @userinfobot>"
echo ""
echo "  2. Restart Claude Code so new skills are available as slash commands."
echo ""
echo "  3. Run /jenius manually to verify the pipeline works:"
echo "     In Claude Code: /jenius"
echo ""
