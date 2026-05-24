#!/bin/zsh
# Homebrew maintenance: update, upgrade, autoremove, cleanup, doctor,
# and interactive stale-cask review via Telegram.
#
# Usage: brew-maintenance.sh [--dry-run]
#   --dry-run  Print actions without executing them. No Telegram prompts.

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$HOME/Library/Logs/claude-agents/brew-maintenance.log"
TELEGRAM="python3 $REPO_DIR/skills/telegram/telegram.py"
STALE_DAYS=180
# Skip bogus atime values (e.g. epoch-0 from some apps like Cursor).
MIN_VALID_ATIME=946684800  # 2000-01-01

mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

if $DRY_RUN; then
  log "=== Brew Maintenance DRY RUN ==="
else
  log "=== Starting brew maintenance ==="
fi

# ── Phase 1: Auto maintenance ──────────────────────────────────────────────────

log "Updating Homebrew..."
brew update >> "$LOG_FILE" 2>&1 || true

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
AUTOREMOVE_ARGS=()
$DRY_RUN && AUTOREMOVE_ARGS+=(--dry-run)
AUTOREMOVE_OUT=$(brew autoremove "${AUTOREMOVE_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE" || true)
# Match both "Uninstalling foo" (real) and "Would uninstall foo" (dry-run).
AUTOREMOVED=$(echo "$AUTOREMOVE_OUT" | grep -ciE '^(Uninstalling|Would uninstall) ' || true)
if $DRY_RUN; then
  if (( AUTOREMOVED > 0 )); then
    echo "Would autoremove: ${AUTOREMOVED} package(s)"
  else
    echo "Nothing to autoremove."
  fi
fi

log "Cleaning up cache..."
CLEANUP_ARGS=()
$DRY_RUN && CLEANUP_ARGS+=(--dry-run)
CLEANUP_OUT=$(brew cleanup "${CLEANUP_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE" || true)
# brew prints e.g. "This operation would free approximately 17MB of disk space."
CLEANUP_FREED=$(echo "$CLEANUP_OUT" \
  | grep -oE "(free|freed)( approximately)? [0-9]+(\.[0-9]+)?(B|KB|MB|GB)" \
  | grep -oE "[0-9]+(\.[0-9]+)?(B|KB|MB|GB)" \
  | head -1 || true)
CLEANUP_FREED="${CLEANUP_FREED:-0B}"
if $DRY_RUN; then
  if [[ "$CLEANUP_FREED" != "0B" ]]; then
    echo "Would free: ${CLEANUP_FREED}"
  else
    echo "Nothing to clean up."
  fi
fi

# ── Phase 2: Doctor ────────────────────────────────────────────────────────────

log "Running brew doctor..."
DOCTOR_OUT=$(brew doctor 2>&1 | tee -a "$LOG_FILE" || true)
DOCTOR_WARNINGS=$(echo "$DOCTOR_OUT" | grep '^Warning:' || true)
WARNINGS=$([[ -z "$DOCTOR_WARNINGS" ]] && echo 0 || echo "$DOCTOR_WARNINGS" | wc -l | tr -d ' ')

if $DRY_RUN; then
  echo ""
  echo "=== Doctor output ==="
  echo "$DOCTOR_OUT"
fi

# ── Phase 3: Stale cask detection ──────────────────────────────────────────────
# Only casks: their .app bundle has a reliable atime. Formulae lack an
# equivalent signal, so we skip them.

log "Identifying stale casks (threshold: ${STALE_DAYS} days)..."

NOW=$(date +%s)
MANUALLY_REMOVED=0
MANUALLY_KEPT=0
NO_RESPONSE=0
typeset -a stale_casks  # entries: "name|YYYY-MM-DD|age_days"

while IFS= read -r cask; do
  app=$(brew info --cask --json=v2 "$cask" 2>/dev/null | python3 -c \
    "import sys,json; d=json.load(sys.stdin); arts=d['casks'][0].get('artifacts',[]); apps=[a['app'][0] for a in arts if isinstance(a,dict) and 'app' in a]; print(apps[0] if apps else '')" \
    2>/dev/null || echo "")
  [[ -z "$app" ]] && continue
  app_path="/Applications/$app"
  [[ ! -e "$app_path" ]] && continue
  atime=$(stat -f "%a" "$app_path" 2>/dev/null || echo 0)
  (( atime < MIN_VALID_ATIME )) && continue
  age=$(( (NOW - atime) / 86400 ))
  if (( age > STALE_DAYS )); then
    stale_casks+=("${cask}|$(date -r "$atime" '+%Y-%m-%d')|${age}")
  fi
done < <(brew list --cask 2>/dev/null)

STALE_COUNT=${#stale_casks[@]}
log "Found ${STALE_COUNT} stale cask(s)."

if (( STALE_COUNT > 0 )) && $DRY_RUN; then
  echo ""
  echo "=== Stale casks that would be reviewed ==="
  for item in "${stale_casks[@]}"; do
    IFS='|' read -r name date_str age <<< "$item"
    printf "  %-35s  last used %s  (%s days ago)\n" "$name" "$date_str" "$age"
  done
elif (( STALE_COUNT > 0 )); then
  # Phase 3a: send all prompts up front so the user can answer them in any order.
  typeset -A name_by_id
  ids=()
  current=0
  for item in "${stale_casks[@]}"; do
    current=$(( current + 1 ))
    IFS='|' read -r name date_str age <<< "$item"
    mid=$($TELEGRAM send \
      "🍺 *${name}* (cask)
📅 Last used: ${date_str} (${age} days ago)
${current}/${STALE_COUNT}" \
      --keyboard '[["✅ Keep:keep", "🗑 Remove:remove"]]') \
      || { log "Telegram send failed for $name; skipping"; continue; }
    name_by_id[$mid]=$name
    ids+=("$mid")
  done

  if (( ${#ids[@]} > 0 )); then
    log "Sent ${#ids[@]} prompt(s); waiting up to 10 minutes for replies..."
    ids_csv="${(j:,:)ids}"

    # Phase 3b: stream replies as they arrive. wait-many prints "<msg_id> <data>"
    # per reply and clears keyboards on un-answered prompts when the window closes.
    while IFS=' ' read -r mid reply; do
      name="${name_by_id[$mid]:-}"
      [[ -z "$name" ]] && continue
      if [[ "$reply" == "remove" ]]; then
        if brew uninstall --cask "$name" >> "$LOG_FILE" 2>&1; then
          MANUALLY_REMOVED=$(( MANUALLY_REMOVED + 1 ))
          log "Removed cask: $name"
        else
          log "Failed to remove cask: $name"
        fi
      else
        MANUALLY_KEPT=$(( MANUALLY_KEPT + 1 ))
        log "Kept cask: $name"
      fi
      unset "name_by_id[$mid]"
    done < <($TELEGRAM wait-many --message-ids "$ids_csv" --timeout 600 2>/dev/null)

    # Anything still in name_by_id never got a response.
    for mid in "${(@k)name_by_id}"; do
      NO_RESPONSE=$(( NO_RESPONSE + 1 ))
      log "No response for cask: ${name_by_id[$mid]} (will be re-asked next run)"
    done

    if (( NO_RESPONSE > 0 )); then
      $TELEGRAM send "⏰ Review window closed. ${NO_RESPONSE} cask(s) didn't get a response — they'll be prompted again next run." || true
    fi
  fi
fi

# ── Phase 4: Summary ───────────────────────────────────────────────────────────

TOTAL_REMOVED=$(( AUTOREMOVED + MANUALLY_REMOVED ))

if $DRY_RUN; then
  echo ""
  echo "=== Brew Maintenance Dry Run ==="
  printf "Upgrades:    %s package(s)\n" "$UPGRADED_COUNT"
  printf "Autoremove:  %s package(s)\n" "$AUTOREMOVED"
  printf "Cleanup:     %s freed\n" "$CLEANUP_FREED"
  printf "Warnings:    %s\n" "$WARNINGS"
  printf "Stale casks: %s would be prompted for review\n" "$STALE_COUNT"
else
  if (( WARNINGS == 0 )); then
    WARNINGS_LINE="✅ No doctor warnings"
  else
    WARNINGS_LINE="⚠️ ${WARNINGS} doctor warning(s)"
  fi

  $TELEGRAM send "🍺 *Brew maintenance complete*
⬆️ ${UPGRADED_COUNT} package(s) upgraded
🗑 ${TOTAL_REMOVED} package(s) removed (${AUTOREMOVED} auto + ${MANUALLY_REMOVED} manual)
🧹 ${CLEANUP_FREED} freed
${WARNINGS_LINE}" || true

  if (( WARNINGS > 0 )); then
    $TELEGRAM send "\`\`\`
${DOCTOR_WARNINGS}
\`\`\`" || true
  fi
fi

log "Done: ${UPGRADED_COUNT} upgraded, ${TOTAL_REMOVED} removed, ${CLEANUP_FREED} freed, ${WARNINGS} warnings"
echo "Brew maintenance complete: ${UPGRADED_COUNT} upgraded, ${TOTAL_REMOVED} removed, ${CLEANUP_FREED} freed, ${WARNINGS} warnings"
