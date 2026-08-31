#!/bin/zsh
# Print (creating if needed) the output folder for the current session:
#
#   ~/Downloads/YYYY-MM-DD-<topic-slug>/
#
# Usage: session-dir.sh <topic>
#   <topic>  Short description of what this session is about, e.g.
#            "podcast transcription". Slugified into the folder name.
#
# Idempotent: the same topic on the same day reuses the same folder, so a
# session can call this repeatedly and keep all its output together.
#
# Every skill or script that produces files for the user writes them here
# rather than dumping them loose in ~/Downloads.

set -euo pipefail

TOPIC="${1:-}"
[[ -z "$TOPIC" ]] && { echo "Usage: session-dir.sh <topic>" >&2; exit 1; }

SLUG="$(echo "$TOPIC" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' \
  | cut -c1-40 \
  | sed -E 's/-+$//')"

[[ -z "$SLUG" ]] && SLUG="output"

DIR="$HOME/Downloads/$(date +%F)-$SLUG"
mkdir -p "$DIR"
echo "$DIR"
