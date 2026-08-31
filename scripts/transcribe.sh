#!/bin/zsh
# Transcribe a local audio/video file with Whisper. Runs on this machine;
# nothing is uploaded.
#
# Usage: transcribe.sh [options] <file>
#   --language CODE   Force language, e.g. nl, en (default: auto-detect)
#   --model NAME      Whisper model (default: large-v3)
#   --format FMT      txt | srt | vtt | json (default: txt)
#   --output-dir DIR  Where the transcript lands (default: next to the file)
#
# Prints the transcript path to stdout; progress goes to stderr, so it
# composes:  transcribe.sh "$(podcast-download.sh <url>)"
#
# Note: --language matters. Auto-detect samples only the first 30s and applies
# that guess to the whole file, so pass it explicitly when you know the language.
# Below large-v3 quality drops sharply for non-English.

set -euo pipefail

LANGUAGE=""
MODEL="large-v3"
FORMAT="txt"
OUTPUT_DIR=""
FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --language)   LANGUAGE="$2"; shift 2 ;;
    --model)      MODEL="$2"; shift 2 ;;
    --format)     FORMAT="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    -h|--help)    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)           echo "Unknown option: $1" >&2; exit 1 ;;
    *)            FILE="$1"; shift ;;
  esac
done

[[ -z "$FILE" ]] && { echo "Usage: transcribe.sh [options] <file>" >&2; exit 1; }
[[ -f "$FILE" ]] || { echo "No such file: $FILE" >&2; exit 1; }
command -v uvx >/dev/null || { echo "uvx not found (brew install uv)" >&2; exit 1; }

# Default to writing the transcript alongside the audio.
[[ -z "$OUTPUT_DIR" ]] && OUTPUT_DIR="${FILE:a:h}"
mkdir -p "$OUTPUT_DIR"

# VAD trims silence, which suppresses Whisper's tendency to hallucinate text
# during quiet stretches.
ARGS=(--model "$MODEL" --task transcribe --vad_filter True
      --output_dir "$OUTPUT_DIR" --output_format "$FORMAT")
[[ -n "$LANGUAGE" ]] && ARGS+=(--language "$LANGUAGE")

echo "Transcribing ${FILE:t} with $MODEL (${LANGUAGE:-auto-detect}) ..." >&2
uvx whisper-ctranslate2 "${ARGS[@]}" "$FILE" >&2

echo "$OUTPUT_DIR/${${FILE:t}%.*}.$FORMAT"
