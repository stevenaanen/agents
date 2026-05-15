---
name: brew-maintenance
description: >-
  Full Homebrew housekeeping: update, upgrade, autoremove, cleanup, doctor
  check, and interactive stale-package review via Telegram. Safe to run
  unattended via cron.
---

# Brew Maintenance

Four phases. Phases 1–2 run silently; phase 3 prompts via Telegram for stale
packages; phase 4 sends a summary.

---

## Phase 1 — Auto maintenance

Run each command in order. Continue on non-zero exit (warnings are normal).
Capture output for the summary counters.

```bash
brew update
brew upgrade 2>&1
brew autoremove 2>&1
brew cleanup 2>&1
```

**Counters to extract from output:**

| Counter | Source |
|---------|--------|
| `UPGRADED` | Count lines matching `Upgrading <name>` in `brew upgrade` output; 0 if "Already up-to-date" |
| `AUTOREMOVED` | Count lines matching `Uninstalling` in `brew autoremove` output |
| `CLEANUP_FREED` | Capture the value in `"freed approximately X"` from `brew cleanup`; `"0 B"` if absent |

---

## Phase 2 — Doctor

```bash
brew doctor 2>&1
```

Count lines containing `"Warning:"` → `WARNINGS`. Store the raw warning lines
in `DOCTOR_LINES` for the summary. If exit code is non-zero and `WARNINGS` is
still 0, set `WARNINGS=1`.

---

## Phase 3 — Stale package review

### 3a. Identify stale formulae (install-date heuristic)

```bash
brew leaves --installed-on-request
```

For each formula, get its install Unix timestamp:

```bash
brew info --json=v1 <formula> | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d[0]['installed'][0]['time'])"
```

Flag as stale if `(now_unix - install_ts) / 86400 > 180`. If the `.installed`
array is empty, skip.

### 3b. Identify stale casks (last-accessed heuristic)

```bash
brew list --cask
```

For each cask, get the primary `.app` name:

```bash
brew info --cask --json=v2 <cask> | python3 -c \
  "import sys,json; d=json.load(sys.stdin); \
   arts=d['casks'][0].get('artifacts',[]); \
   apps=[a['app'][0] for a in arts if isinstance(a,dict) and 'app' in a]; \
   print(apps[0] if apps else '')"
```

If the `.app` name is non-empty and `/Applications/<app>` exists, get its
access time:

```bash
stat -f "%a" "/Applications/<app>"   # prints Unix timestamp
```

Flag as stale if `(now_unix - atime) / 86400 > 180`. Skip casks with no
`.app` artifact (CLI-only casks, fonts, etc.).

### 3c. Interactive review

If there are no stale formulae or casks, skip to Phase 4.

Initialise `MANUALLY_REMOVED=0`. Process formulae first, then casks.

For each stale item:

```bash
MSG_ID=$(python3 skills/telegram/telegram.py send \
  "🍺 *<name>* (<formula|cask>)
📅 Installed/last accessed: <YYYY-MM-DD> (<age> days ago)" \
  --keyboard '[["✅ Keep:keep", "🗑 Remove:remove"]]')

REPLY=$(python3 skills/telegram/telegram.py wait \
  --message-id "$MSG_ID" --timeout 300)
```

| `$REPLY` | Action |
|----------|--------|
| `keep` | Skip |
| `remove` (formula) | `brew uninstall <name>` then `MANUALLY_REMOVED++` |
| `remove` (cask) | `brew uninstall --cask <name>` then `MANUALLY_REMOVED++` |
| timeout / error | Treat as `keep` — safe default for unattended runs |

---

## Phase 4 — Telegram summary

```bash
TOTAL_REMOVED=$((AUTOREMOVED + MANUALLY_REMOVED))

python3 skills/telegram/telegram.py send \
  "🍺 *Brew maintenance complete*
⬆️ ${UPGRADED} package(s) upgraded
🗑 ${TOTAL_REMOVED} package(s) removed (${AUTOREMOVED} auto + ${MANUALLY_REMOVED} manual)
🧹 ${CLEANUP_FREED} freed
$([ "$WARNINGS" -eq 0 ] \
  && echo '✅ No doctor warnings' \
  || echo "⚠️ ${WARNINGS} doctor warning(s)")"
```

If `WARNINGS > 0`, send the raw warning lines as a follow-up (no keyboard):

```bash
python3 skills/telegram/telegram.py send "\`\`\`
${DOCTOR_LINES}
\`\`\`"
```

---

## Output

One line: `Brew maintenance complete: ${UPGRADED} upgraded, ${TOTAL_REMOVED} removed, ${CLEANUP_FREED} freed, ${WARNINGS} warnings`
