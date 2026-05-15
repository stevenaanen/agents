#!/bin/zsh
# Homebrew maintenance: update, upgrade, autoremove, cleanup, doctor,
# and interactive stale-package review via Telegram.
#
# Usage: brew-maintenance.sh [--dry-run]
#   --dry-run  Print actions without executing them. No Telegram prompts.

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/claude-agents"
LOG_FILE="$LOG_DIR/brew-maintenance.log"
TELEGRAM="python3 $REPO_DIR/skills/telegram/telegram.py"
EPOCH_MIN=946684800  # 2000-01-01 — skip bogus atime=0 values

mkdir -p "$LOG_DIR"

log() {
  local msg="$(date '+%Y-%m-%d %H:%M:%S') $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

if $DRY_RUN; then
  log "=== Brew Maintenance DRY RUN ==="
else
  log "=== Starting brew maintenance ==="
fi

# ── Phase 1: Auto maintenance ──────────────────────────────────────────────────

log "Updating Homebrew..."
if $DRY_RUN; then
  brew update >> "$LOG_FILE" 2>&1 || true
else
  brew update >> "$LOG_FILE" 2>&1 || true
fi

# Count outdated before upgrading (used as upgraded count)
FORMULA_OUTDATED=$(brew outdated --formula --quiet 2>/dev/null | wc -l | tr -d ' ')
CASK_OUTDATED=$(brew outdated --cask --quiet 2>/dev/null | wc -l | tr -d ' ')
UPGRADED_COUNT=$(( FORMULA_OUTDATED + CASK_OUTDATED ))

log "Upgrading packages (${UPGRADED_COUNT} outdated)..."
if $DRY_RUN; then
  brew upgrade --dry-run >> "$LOG_FILE" 2>&1 || true
  echo "Would upgrade: ${UPGRADED_COUNT} package(s)"
else
  brew upgrade >> "$LOG_FILE" 2>&1 || true
fi

log "Removing orphaned dependencies..."
if $DRY_RUN; then
  AUTOREMOVE_OUT=$(brew autoremove --dry-run 2>&1 | tee -a "$LOG_FILE" || true)
else
  AUTOREMOVE_OUT=$(brew autoremove 2>&1 | tee -a "$LOG_FILE" || true)
fi
AUTOREMOVED=$(echo "$AUTOREMOVE_OUT" | awk '/^Uninstalling /{c++} END{print c+0}')
if $DRY_RUN; then
  if (( AUTOREMOVED > 0 )); then
    echo "Would autoremove: ${AUTOREMOVED} package(s)"
  else
    echo "Nothing to autoremove."
  fi
fi

log "Cleaning up cache..."
if $DRY_RUN; then
  CLEANUP_OUT=$(brew cleanup --dry-run 2>&1 | tee -a "$LOG_FILE" || true)
else
  CLEANUP_OUT=$(brew cleanup 2>&1 | tee -a "$LOG_FILE" || true)
fi
CLEANUP_FREED=$(echo "$CLEANUP_OUT" | grep -oE "[0-9]+(\.[0-9]+)?(B|KB|MB|GB)" | head -1 || true)
CLEANUP_FREED="${CLEANUP_FREED:-0 B}"
if $DRY_RUN; then
  if [[ -n "$CLEANUP_FREED" && "$CLEANUP_FREED" != "0 B" ]]; then
    echo "Would free: ${CLEANUP_FREED}"
  else
    echo "Nothing to clean up."
  fi
fi

# ── Phase 2: Doctor ────────────────────────────────────────────────────────────

log "Running brew doctor..."
DOCTOR_OUT=$(brew doctor 2>&1 | tee -a "$LOG_FILE" || true)
WARNINGS=$(echo "$DOCTOR_OUT" | awk '/^Warning:/{c++} END{print c+0}')
DOCTOR_LINES=$(echo "$DOCTOR_OUT" | grep "^Warning:" || true)

if $DRY_RUN; then
  echo ""
  echo "=== Doctor output ==="
  echo "$DOCTOR_OUT"
fi

# ── Phase 3: Stale package detection ──────────────────────────────────────────

log "Identifying stale packages (threshold: 180 days)..."

NOW=$(date +%s)
STALE_THRESHOLD=$((180 * 86400))
MANUALLY_REMOVED=0

# Returns the last-accessed Unix timestamp for a formula.
# Checks the binary in /opt/homebrew/bin first, then the opt directory.
formula_atime() {
  local formula=$1
  local bin_path="/opt/homebrew/bin/$formula"
  local opt_path="/opt/homebrew/opt/$formula"
  if [[ -e "$bin_path" ]]; then
    stat -f "%a" "$bin_path" 2>/dev/null || echo 0
  elif [[ -e "$opt_path" ]]; then
    stat -f "%a" "$opt_path" 2>/dev/null || echo 0
  else
    echo 0
  fi
}

# Collect stale items as "name|date|age_days|type" strings
typeset -a stale_items

while IFS= read -r formula; do
  atime=$(formula_atime "$formula")
  (( atime < EPOCH_MIN )) && continue
  age=$(( (NOW - atime) / 86400 ))
  if (( age > 180 )); then
    date_str=$(date -r "$atime" "+%Y-%m-%d")
    stale_items+=("${formula}|${date_str}|${age}|formula")
  fi
done < <(brew leaves --installed-on-request 2>/dev/null)

while IFS= read -r cask; do
  app=$(brew info --cask --json=v2 "$cask" 2>/dev/null | python3 -c \
    "import sys,json; d=json.load(sys.stdin); arts=d['casks'][0].get('artifacts',[]); apps=[a['app'][0] for a in arts if isinstance(a,dict) and 'app' in a]; print(apps[0] if apps else '')" \
    2>/dev/null || echo "")
  [[ -z "$app" ]] && continue
  app_path="/Applications/$app"
  [[ ! -e "$app_path" ]] && continue
  atime=$(stat -f "%a" "$app_path" 2>/dev/null || echo 0)
  (( atime < EPOCH_MIN )) && continue
  age=$(( (NOW - atime) / 86400 ))
  if (( age > 180 )); then
    date_str=$(date -r "$atime" "+%Y-%m-%d")
    stale_items+=("${cask}|${date_str}|${age}|cask")
  fi
done < <(brew list --cask 2>/dev/null)

STALE_COUNT=${#stale_items[@]}

if (( STALE_COUNT == 0 )); then
  log "No stale packages found."
  if $DRY_RUN; then
    echo ""
    echo "No stale packages found (threshold: 180 days)."
  fi
else
  log "Found ${STALE_COUNT} stale package(s)."

  if $DRY_RUN; then
    echo ""
    echo "=== Stale packages that would be reviewed ==="
    for item in "${stale_items[@]}"; do
      name="${item%%|*}"; rest="${item#*|}"
      date_str="${rest%%|*}"; rest="${rest#*|}"
      age="${rest%%|*}"; type="${rest##*|}"
      printf "  %-8s  %-35s  last used %s  (%s days ago)\n" "$type" "$name" "$date_str" "$age"
    done
  else
    current=0
    for item in "${stale_items[@]}"; do
      current=$(( current + 1 ))
      name="${item%%|*}"; rest="${item#*|}"
      date_str="${rest%%|*}"; rest="${rest#*|}"
      age="${rest%%|*}"; type="${rest##*|}"

      MSG_ID=$($TELEGRAM send \
        "🍺 *${name}* (${type})
📅 Last used: ${date_str} (${age} days ago)
${current}/${STALE_COUNT}" \
        --keyboard '[["✅ Keep:keep", "🗑 Remove:remove"]]') || { log "Telegram send failed for $name; skipping"; continue; }

      REPLY=$($TELEGRAM wait --message-id "$MSG_ID" --timeout 300 2>/dev/null || echo "keep")

      case "$REPLY" in
        remove)
          if [[ "$type" == "cask" ]]; then
            brew uninstall --cask "$name" >> "$LOG_FILE" 2>&1 && MANUALLY_REMOVED=$(( MANUALLY_REMOVED + 1 ))
          else
            brew uninstall "$name" >> "$LOG_FILE" 2>&1 && MANUALLY_REMOVED=$(( MANUALLY_REMOVED + 1 ))
          fi
          log "Removed $type: $name"
          ;;
        *)
          log "Kept $type: $name"
          ;;
      esac
    done
  fi
fi

# ── Phase 4: Summary ───────────────────────────────────────────────────────────

TOTAL_REMOVED=$(( AUTOREMOVED + MANUALLY_REMOVED ))

if $DRY_RUN; then
  echo ""
  echo "=== Brew Maintenance Dry Run ==="
  printf "Upgrades:    %s package(s)\n" "$UPGRADED_COUNT"
  printf "Autoremove:  %s package(s)\n" "$AUTOREMOVED"
  printf "Cleanup:     %s freed\n" "${CLEANUP_FREED:-0 B}"
  printf "Warnings:    %s\n" "$WARNINGS"
  printf "Stale:       %s package(s) would be prompted for review\n" "$STALE_COUNT"
else
  if (( WARNINGS == 0 )); then
    WARNINGS_LINE="✅ No doctor warnings"
  else
    WARNINGS_LINE="⚠️ ${WARNINGS} doctor warning(s)"
  fi

  $TELEGRAM send "🍺 *Brew maintenance complete*
⬆️ ${UPGRADED_COUNT} package(s) upgraded
🗑 ${TOTAL_REMOVED} package(s) removed (${AUTOREMOVED} auto + ${MANUALLY_REMOVED} manual)
🧹 ${CLEANUP_FREED:-0 B} freed
${WARNINGS_LINE}" || true

  if (( WARNINGS > 0 )) && [[ -n "$DOCTOR_LINES" ]]; then
    $TELEGRAM send "\`\`\`
${DOCTOR_LINES}
\`\`\`" || true
  fi
fi

log "Done: ${UPGRADED_COUNT} upgraded, ${TOTAL_REMOVED} removed, ${CLEANUP_FREED:-0 B} freed, ${WARNINGS} warnings"
echo "Brew maintenance complete: ${UPGRADED_COUNT} upgraded, ${TOTAL_REMOVED} removed, ${CLEANUP_FREED:-0 B} freed, ${WARNINGS} warnings"
