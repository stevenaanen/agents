---
name: transcribe
description: Download a podcast episode or audio/video file, transcribe it locally with Whisper, and summarize it in one paragraph. Use when the user says "/transcribe", "transcribe this", "transcribe this podcast", pastes a podcast episode link (pca.st, Spotify, Apple Podcasts, any web player) or an audio file path and wants the text, or asks what an episode is about. Runs entirely on-machine — nothing is uploaded.
---

# Transcribe

Two independent scripts. Use either alone or chained.

| Script | Takes | Prints |
|---|---|---|
| `scripts/podcast-download.sh` | episode page or audio URL | audio file path |
| `scripts/transcribe.sh` | local audio/video file | transcript path |

Both write progress to stderr and the resulting path to stdout, so the result
is captured with `$(...)` — no output parsing.

Audio and transcript land together in a dated session folder under
`~/Downloads` (see *Output location* in `CLAUDE.md`). Pass `--topic` describing
the episode so the folder is findable later — e.g. `--topic "worship sermon"`
gives `~/Downloads/2026-08-31-worship-sermon/`. Without it you get a generic
`-podcast` / `-transcript` folder, which is tidy but vague.

## Steps

Skip step 1 if the user already has a local file; skip step 2 if they only
want the audio.

**1. Download.**

```bash
bash scripts/podcast-download.sh --topic "<topic>" "<url>"
```

**2. Transcribe.** Run in the background — a full episode takes several minutes.

```bash
bash scripts/transcribe.sh --language <code> "<file>"
```

The transcript joins the audio's session folder automatically when the audio is
already in one, so the chained form needs `--topic` only once:

```bash
bash scripts/transcribe.sh --language en \
  "$(bash scripts/podcast-download.sh --topic 'worship sermon' '<url>')"
```

Pass `--language` whenever the language is known or stated (`en`, `nl`, ...).
Omit it only if genuinely unknown; auto-detect samples just the first 30
seconds and applies that guess to the whole file, which fails on recordings
that open with music or a foreign-language intro.

Other options: `--model` (default `large-v3`; don't go smaller for non-English),
`--format txt|srt|vtt|json`, `--output-dir` to override the session folder.

**3. Summarize with a cheap model.** Transcripts are long and summarizing them
is easy work, so delegate to Haiku instead of spending main-context tokens:

```
Agent tool → subagent_type: general-purpose, model: haiku
Prompt: "Read <transcript path>. Return ONE paragraph (4-6 sentences) covering
what it is, who is speaking if identifiable, and the main points. Plain prose,
no preamble, no bullets."
```

**4. Report.** Give the user the transcript path, the audio path, word count,
and the paragraph.

## Notes

- First transcription downloads the model (~1.5 GB) and caches it; later runs
  skip that.
- Whisper occasionally gets stuck repeating a phrase for a few seconds. If the
  user cares about a specific passage, re-run just that window by cutting it
  out first: `ffmpeg -ss <start> -to <end> -i in.mp3 -c copy clip.mp3`.
- No speaker diarization — Whisper produces continuous text, not "who said
  what". Say so if the user expects labelled speakers.
- Paid/private feeds (Patreon, Wondery+) won't resolve: their URLs are
  token-gated per subscriber. Ask the user to download the file manually, then
  run `transcribe.sh` on it.
