#!/bin/zsh
# Resolve a podcast episode page (or direct audio URL) to its audio file and
# download it.
#
# Usage: podcast-download.sh [--output-dir DIR] <url>
#   --output-dir DIR  Where the audio lands (default: ~/Downloads)
#
# Accepts a direct audio URL or an episode page (pca.st and most web players
# embed the enclosure URL in the HTML).
#
# Prints the downloaded file path to stdout; progress goes to stderr, so it
# composes:  transcribe.sh "$(podcast-download.sh <url>)"

set -euo pipefail

OUTPUT_DIR="$HOME/Downloads"
URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    -h|--help)    sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)           echo "Unknown option: $1" >&2; exit 1 ;;
    *)            URL="$1"; shift ;;
  esac
done

[[ -z "$URL" ]] && { echo "Usage: podcast-download.sh [--output-dir DIR] <url>" >&2; exit 1; }

mkdir -p "$OUTPUT_DIR"

echo "Resolving $URL ..." >&2
RESOLVED="$(python3 - "$URL" <<'PY'
import html, re, sys, urllib.parse, urllib.request

url = sys.argv[1]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
AUDIO_RE = r"https?://[^\"'\\ <>]+?\.(?:mp3|m4a|aac|ogg|opus|wav)(?:\?[^\"'\\ <>]*)?"


def emit(link, name):
    print(link)
    print(re.sub(r"[/:\\]", "-", name).strip() or "episode")


# Already a direct audio link — nothing to scrape.
if re.search(r"\.(mp3|m4a|aac|ogg|opus|wav)(\?|$)", url, re.I):
    emit(url, urllib.parse.unquote(url.split("/")[-1].split("?")[0]))
    sys.exit()

page = urllib.request.urlopen(
    urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30
).read().decode("utf-8", "replace")

# Episode pages often embed the podcast's whole feed, so pick the enclosure
# whose URL best matches the page title rather than blindly taking the first.
seen, candidates = set(), []
for m in re.findall(AUDIO_RE, page):
    if m not in seen:
        seen.add(m)
        candidates.append(m)

if not candidates:
    sys.exit("No audio URL found on that page")

t = re.search(r'property="og:title"[^>]*content="([^"]*)"', page)
title = html.unescape(t.group(1)) if t else ""
words = [w.lower() for w in re.findall(r"[A-Za-z0-9]{4,}", title)][:5]

best, best_score = candidates[0], -1
for c in candidates:
    decoded = urllib.parse.unquote(c).lower()
    score = sum(1 for w in words if w in decoded)
    if score > best_score:
        best, best_score = c, score

ext = re.search(r"\.(mp3|m4a|aac|ogg|opus|wav)(?:\?|$)", best, re.I).group(1)
stem = title or urllib.parse.unquote(best.split("/")[-1].split("?")[0]).rsplit(".", 1)[0]
emit(best, f"{stem}.{ext}")
PY
)"

AUDIO_URL="$(echo "$RESOLVED" | sed -n 1p)"
AUDIO="$OUTPUT_DIR/$(echo "$RESOLVED" | sed -n 2p)"

echo "Downloading: $AUDIO_URL" >&2
curl -fL --progress-bar -o "$AUDIO" "$AUDIO_URL" >&2

echo "$AUDIO"
