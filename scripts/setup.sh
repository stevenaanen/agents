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

for skill in jenius jenius-card jenius-review telegram use-spark; do
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

# ── 5. Install crontab entry ──────────────────────────────────────────────────

info "Installing crontab..."

CRON_LINE="0 9 * * * $REPO_DIR/scripts/run-jenius.sh"
TZ_LINE="TZ=Europe/Amsterdam"

# Check if entry already present
if crontab -l 2>/dev/null | grep -qF "run-jenius.sh"; then
  ok "crontab entry already present"
else
  # Append to existing crontab, adding TZ line only if not already there
  (
    existing="$(crontab -l 2>/dev/null || true)"
    if [[ -z "$existing" ]]; then
      printf '%s\n%s\n' "$TZ_LINE" "$CRON_LINE"
    elif echo "$existing" | grep -qF "TZ=Europe/Amsterdam"; then
      printf '%s\n%s\n' "$existing" "$CRON_LINE"
    else
      printf '%s\n%s\n%s\n' "$TZ_LINE" "$existing" "$CRON_LINE"
    fi
  ) | crontab -
  ok "crontab entry installed (daily 9am Amsterdam time)"
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
