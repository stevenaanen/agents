---
name: calendar
description: Plan a single item onto the right calendar at a reasonable time, moving or suggesting moves to make it fit — or edit an existing event (e.g. add discussion notes to a meeting). Reads Steven's routing table, working-hours template, weekly cadence, and importance/reschedule rules from reference.md, then acts through the Spark CLI. Use when the user says "/calendar <thing>", "schedule X", "find time for Y", "book Z", "add/change something on my 1:1", or otherwise wants one item placed or adjusted on a calendar.
metadata:
  requires:
    bins: [spark]
---

# /calendar — plan or adjust one calendar item

Places **one item** on the right calendar at a sensible time (moving flexible things around
if needed), or **edits an existing event**. Always driven by the rules in
[`reference.md`](reference.md) — **read that file first, every run.** It holds the calendar
routing table, tag taxonomy, timezone, working-hours template, duration defaults, and the
importance/reschedule + write-policy rules. Do not hardcode any of that here.

Today's date and the user's timezone (Bali, UTC+8) come from the session context.

## Tooling — Spark CLI

```bash
spark events --start <yyyy-MM-dd> --end <yyyy-MM-dd> --in <account:Calendar>   # read (≤31-day window)
spark event create --title "..." --start <yyyy-MM-ddTHH:mm> --end <...> --calendar <account:Calendar> [--alerts 1800s] [--description "..."] [--video-conference meet] [--all-day] [--add a@b.com]
spark event update <event-id> [--title|--start|--end|--description|--location|--add|--remove ...]
spark event delete <event-id>
```

- Date range per read is capped at **31 days** — chunk longer windows.
- Get an event's `ID:` from `spark events` output before `update`/`delete`.
- If Spark errors with "can't access … Spark Desktop application", tell the user to open the
  Spark app / enable CLI access, then retry.
- **Writes need account "send" access.** Reading works at *triage*/*read-only*, but
  `spark event create/update/delete` fails with `account "…" does not have send access` unless
  the account is set to **send** in **Spark Desktop → Settings**. If a write is rejected this
  way, stop and ask the user to grant send access to that account — don't retry the batch.

## Decide the mode

- **EDIT** — the request references an existing event ("add X to my 1:1 with Derk", "move date
  night to Thursday", "rename …", "make the sync 30 min"). → find it, then update.
- **SCHEDULE** — the request is a new thing to place ("90 min deep work on Listings 2.0 this
  week", "coffee with Jor Friday afternoon", "gym Saturday with opa"). → find a slot, then create.

If ambiguous, ask one short question.

## SCHEDULE flow

1. **Parse the item:** what it is → pick the **tag** and **target calendar** (routing table);
   infer **duration** from the defaults if unstated; note any window/constraint the user gave
   ("this week", "Friday afternoon", "before the Empowr standup") and any **attendees**.
2. **Read the candidate window** with `spark events` for the target calendar — and also the
   other calendars that share those hours, so conflicts across calendars are visible (e.g. a
   Pro focus block must not collide with an Empowr meeting or gym).
3. **Find a reasonable slot** respecting, in priority order:
   - the ANCHOR (never overlap gym) and `[BLOCK]`/`OOO`;
   - the working-hours template (right time-of-day for the category);
   - the NL overlap window if it involves the Empowr team;
   - sensible spacing (don't wedge deep work between two meetings).
4. **If a free slot fits** → apply the write policy:
   - free/low-risk (solo focus block, no conflict) → **create it, then report**;
   - involves attendees / Monica's calendar → **propose, then confirm** before creating.
5. **If nothing fits without moving something:**
   - if only Steven's **own solo focus blocks** (no attendees) need to shift → that's
     low-risk: **do the moves + create, then report** what moved and where;
   - if it would require touching a **PROTECTED** item (attendees / date night / ministry) →
     **do not touch it silently.** Present the option ("I can fit this if we move your 1:1
     with Joao to 15:00 — want me to?") and wait for confirmation;
   - **never** offer to move the gym anchor — always route around it.
6. **Name & set fields:** `[Tag] Description`; `--alerts 1800s`; correct `--calendar`;
   `--video-conference meet` for Empowr meetings with others; emoji only if it matches the
   surrounding style.
7. **Report:** what was created/moved (with times), and anything still awaiting confirmation.

## EDIT flow

1. **Locate the event** via `spark events` in the likely window; confirm you have the right one
   (show its title + time) if there's any doubt.
2. **Apply the write policy:**
   - editing **title / description / notes** → low-risk, **just do it** (this never emails
     anyone). Appending discussion points to a meeting description is the common case — merge
     into any existing notes, don't clobber them.
   - changing **time** of a PROTECTED item, or `--add`/`--remove` **attendees** → **confirm
     first** (attendee changes send invitation/cancellation emails).
   - **delete** → always confirm.
3. **Report** the change.

## Guardrails

- Read `reference.md` before acting — the rules there win over any assumption here.
- One item per invocation. For rebuilding a whole recurring split, that's a different job.
- Never write to `steven@empowr.nl:Feestdagen in Nederland` (read-only).
- When you auto-apply a low-risk change, still tell the user exactly what you did so nothing is
  a surprise.
- If the working-hours boundaries feel wrong for a specific request, say so and offer to update
  `reference.md` rather than silently overriding.
