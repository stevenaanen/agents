# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Personal repository for storing AI automation assets: Claude Code skills, multi-agent workflows, reusable prompts, utility scripts, and custom tools for personal productivity.

## Repository Structure

| Directory | Contents |
|-----------|----------|
| `skills/` | Everything Claude Code invokes — slash commands, workflows, agent prompts |
| `scripts/` | Executable scripts (shell, Python) you run directly, not through Claude |
| `docs/` | Notes, guides, and references |

Rule of thumb: if Claude runs it → `skills/`. If you run it → `scripts/`.

As `skills/` grows, organize by domain subdirectory (e.g., `skills/git/`, `skills/email/`) rather than by type.

## Skills

Skills are Markdown files that Claude Code loads and executes when the user types `/<skill-name>`. Each skill lives in `skills/<name>/SKILL.md` (the data/config files for that skill sit alongside it in the same directory).

To make a skill available as a slash command, create a symlink in `.claude/skills/`:
```bash
ln -s ../../skills/<name> .claude/skills/<name>
```
The directory name under `.claude/skills/` becomes the slash command name (`/name`). A session restart is required if `.claude/skills/` was created mid-session.

## Conventions

- **Secrets**: use `.env` files (gitignored) and document required vars in a `.env.example` alongside each skill or script.
- **Dependencies**: scripts or skills that need packages include their own `requirements.txt` (Python) or `package.json` (Node) in their subdirectory.
- **Naming**: kebab-case for all files and directories.
- **Output**: see below.

## Output location

Files produced *for the user* go in a dated per-session folder under
`~/Downloads` — never loose in `~/Downloads` itself:

```
~/Downloads/YYYY-MM-DD-<short-topic>/
```

Get the folder from the shared helper, which creates it and prints the path.
The same topic on the same day reuses the same folder, so a session can call it
repeatedly and keep all its output together:

```bash
OUT="$(bash scripts/session-dir.sh 'podcast transcription')"
# -> ~/Downloads/2026-08-31-podcast-transcription
```

Scripts that write user-facing files take an `--output-dir` and default to a
session folder of their own. Pick a topic describing the *work*, not the tool.

This applies only to deliverables. It does **not** apply to:

| Kind | Location |
|---|---|
| Persistent skill state | `data/` (gitignored, per-skill) |
| Logs | `~/Library/Logs/claude-agents/` |
| Filed business documents | their destination folder (e.g. `apple-invoices` → Dropbox bookkeeping) |
| Scratch/intermediate files | the session scratchpad, not `~/Downloads` |
