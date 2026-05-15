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

Skills are Markdown files that Claude Code loads and executes when the user types `/<skill-name>`. Name the file to match the intended slash command (e.g., `skills/review.md` → `/review`).

Register skills in `.claude/settings.json` under the `skills` key pointing to the file path.

## Conventions

- **Secrets**: use `.env` files (gitignored) and document required vars in a `.env.example` alongside each skill or script.
- **Dependencies**: scripts or skills that need packages include their own `requirements.txt` (Python) or `package.json` (Node) in their subdirectory.
- **Naming**: kebab-case for all files and directories.
