# Calendar reference — Steven's scheduling system

This is the durable knowledge the `/calendar` skill reads on every run. It was derived
from ~614 real events across 12 weeks (Jun–Sep 2026). Keep it up to date; when Steven
corrects a preference, edit this file, not the skill logic.

---

## Timezone (and European DST — important)

- **Steven lives in Bali** — WITA, **UTC+8**, no DST. All times below are Bali time.
- **Empowr team is in the Netherlands** — CET/CEST. **The Empowr workday starts at 09:00 NL,
  year-round.** The *Bali* clock time of that start shifts with European DST:
  - **NL summer time (CEST, UTC+2)** → Bali is **+6 h** → 09:00 NL = **15:00 Bali**
  - **NL winter time (CET, UTC+1)** → Bali is **+7 h** → 09:00 NL = **16:00 Bali**
- **European DST rule:** CEST runs from the **last Sunday of March** to the **last Sunday of
  October**; CET the rest of the year. **Always compute the offset from the meeting's own date**
  — don't assume "current" season for an event weeks away.
- **Empowr meeting window = 09:00–12:00 NL**, i.e. **15:00–18:00 Bali in summer / 16:00–19:00
  Bali in winter.** Right now (Aug 2026, summer) that is **15:00–18:00 Bali**.
- ⇒ Anything **collaborative with Empowr must land in this NL-overlap window**. Solo work does
  not need the overlap and belongs in the Bali morning/midday.

---

## Calendars & routing

Route every new item to the correct calendar by life-domain. Calendar IDs are the
`account:calendar` strings `spark` expects in `--in` / `--calendar`.

| Domain | Calendar (`--calendar` value) | Belongs here |
|---|---|---|
| **Personal operating system / solo-founder** | `hi@stevenaanen.com:hi@stevenaanen.com` ("Pro") | `[Plan] Day/Week`, `[Process] Mail & notes`, `[Admin]` finances/budgets, `[Lunch]`, `[Webinar]` learning — Steven's own daily rhythm & solo ventures |
| **Empowr day job** | `steven@empowr.nl:Steven @ Empowr` | All team-facing work: `[1:1]`, `[Session]`, `[Sync]`, `[Review]`, `[Write] Shaping`, `[Research]`, `[Ship]`, `[BLOCK]`, `OOO`, team check-ins |
| **Life & self** | `ssaanen@gmail.com:ssaanen@gmail.com` ("Personal") | `[Health] Gym`, `[Health] Meditate`, `[PG]`, `[Dinner]`, `[Sync] Fam week plan`, `[Travel] Pickup Jae`, church/`Filled` ministry, travel/holidays |
| **Monica (wife)** | `ssaanen@gmail.com:monica.aanen@gmail.com` (shared, read-write) | Her ministry (Foundation lessons, `[Ezekiel 47]`), her appointments, family calls, birthdays/anniversaries, household payments. **Never write here automatically** — see the Monica rule below. |

Read-only calendar (never write): `steven@empowr.nl:Feestdagen in Nederland` (Dutch holidays).

---

## Naming convention

Format: **`[Tag] Description`**, optional trailing emoji (😍 ☘️ 🎸 🥳) — match the vibe of
neighbouring events; don't force emoji.

> **Forward-only:** this is the tag set for **new** events the skill creates. **Do not retag
> historic events** — leave their original tags untouched.

**Canonical tags (use only these):**

- **Deep work / creation:** `[Plan]` `[Process]` `[Write]` `[Research]` `[Review]` `[Ship]` `[Prep]` `[Design]` `[Strategy]`
- **Collaboration:** `[1:1]` `[Sync]` `[Session]` `[Call]` `[Webinar]`
- **Self:** `[Health]` (physical **and** wellbeing — gym, meditation, rest) · `[PG]` (Personal Growth — reflection, learning, goal/quarter reviews)
- **Life:** `[Travel]` `[Event]` `[Lunch]` `[Dinner]` `[Fam]`
- **Admin:** `[Admin]` (finances/budgets included — no separate finance tag)
- **Ministry:** `[Teach]` · `[Event] Filled …` · `[Ezekiel 47]` (Monica's project)
- **Availability:** `[BLOCK]` (reserved capacity — do not book over) · `OOO`
- **`[~Tag]` prefix** = **tentative / soft / freely movable** (e.g. `[~Sync] Lara`, `[~Call] Jor`).

Pick the tag that matches the item's domain; reuse an exact existing title when scheduling
a recurring instance (e.g. `[Health] Gym`, `[Plan] Day`).

**Retired tags → what to use instead** (never create these on new events):
`[Wellbeing]` → `[Health]` · `[Reflect]`/`[Learn]`/`[PIM]` → `[PG]` · `[FI]` → `[Admin]`
(or the fitting deep-work tag) · `[Shape]` → `[Write]` · `[Interview]` → `[Session]` ·
`[Cowork]`/`[LAUNCH]` → `[Ship]` · `[Home]` → `[Fam]` · `[Breakfast]` → `[Lunch]` · `[Setup]` → `[Ship]`/`[Prep]`.

---

## Peer & team availability (meetings with others)

When placing or moving anything that has **other attendees**, their availability is a
first-class constraint — not just Steven's. Two tiers of colleagues, plus everyone else.

**Roster (Empowr emails):**

| Person | Email | Tier |
|---|---|---|
| Derk van Haastert | `derk@empowr.nl` | 🔴 MT — most busy |
| Reinier de van der Schueren | `reinier@empowr.nl` | 🔴 MT — most busy |
| Robin Meijer | `robin@empowr.nl` | 🔴 MT — most busy |
| João Domingues | `joao@empowr.nl` | 🟢 Steven's team — flexible |
| Pieter Hussaarts | `pieter@empowr.nl` | 🟢 Steven's team — flexible |
| Edward Phillips | `edward@empowr.nl` | 🟢 Steven's team — flexible |

### 🔴 MT (Derk, Reinier, Robin) — hardest to schedule; their agenda binds

- Plan meetings into slots where they are **genuinely free**. Their calendar is the binding
  constraint — schedule *around* it, don't book *over* it.
- If nothing fits, you may **propose** a time that displaces only **low-value** items already
  in their agenda: internal focus blocks, tasks, or clearly tentative things that could easily
  be **rescheduled internally**. Always propose — never assume.
- **External meetings are a hard no-go.** Never propose to book over or move a meeting they
  have with someone outside the company.
- Because free/busy alone can't tell an external meeting from a movable block, **read the
  detail** before proposing to displace anything of theirs (see tooling below).

### 🟢 Steven's own team (Joao, Pieter, Ed) — flexible

- They flex to whatever Steven proposes — optimise for **Steven's ideal time**, don't
  contort the plan around them.
- One hard constraint: **respect their OOO / holiday days** — never book them on a day
  they're out.

### Everyone else (other colleagues, externals)

- Still check their availability (`spark availability`) and avoid conflicts; treat as normal
  — propose around them rather than over them.

### When a meeting mixes tiers

Satisfy the **MT member's availability first**, then slot the flexible teammate(s) around
that. (This is exactly the Aug-2026 case that motivated the rule: given a Derk 1:1 and a
Pieter 1:1 competing for the same afternoon, place Derk where *he's* free and move flexible
Pieter to the leftover slot — not the reverse.)

### Tooling — how to actually see a peer's availability

Steven has enabled his colleagues' **delegated calendars inside Spark Desktop**, so the CLI
can now read each peer's full agenda directly. Two tools, in order of usefulness:

1. **Full detail — `spark events --in "steven@empowr.nl:<peer>@empowr.nl" --start … --end …`.**
   Returns the peer's real events with **titles, attendees, and notes** — the authoritative
   source for judging *what's* in their agenda (external vs internal, focus block vs meeting,
   movable vs fixed). The delegated calendars are the ones listed under the `steven@empowr.nl`
   account whose name is a colleague's email (`steven@empowr.nl:derk@empowr.nl`,
   `…:reinier@empowr.nl`, `…:robin@empowr.nl`, `…:joao@empowr.nl`, `…:pieter@empowr.nl`). Run
   `spark accounts` to see the current set.
2. **Quick free/busy — `spark availability --attendees a@empowr.nl,b@empowr.nl --start … --end …`.**
   Mutual free windows in Bali time (respects events marked "free", skips weekends). Handy for
   a fast "when is everyone free?" pass, but it is **intersected with Steven's own calendar**
   and is **free/busy only (no titles)**, so it can't judge movability. Prefer `events --in`
   when an MT decision hinges on the detail.

> 🔒 **HARD RULE — delegated peer calendars are READ-ONLY for us.** Spark lists them as
> *read-write*, but we **only ever read them for availability**. **Never** `event
> create/update/delete` against `steven@empowr.nl:<peer>@empowr.nl` — that would write to a
> colleague's calendar. Treat this exactly like the Monica rule. To change a *meeting* with a
> peer, edit the event on **Steven's own** calendar (`steven@empowr.nl:Steven @ Empowr`), which
> notifies them as an attendee — never touch their calendar copy.
>
> ⚠️ **Organizer caveat:** if Steven is *not* the organizer of a meeting, moving his own copy
> may not propagate to the other person's copy (their copy can stay at the old time → the two
> desync). After moving any meeting with attendees, **read the peer's delegated calendar back**
> to confirm their copy actually moved; if it didn't, flag it — the change likely needs the
> organizer to make it.

### When does a peer's calendar matter?

**Only when that person is an actual invitee** to the item being planned or moved. A peer's
agenda constrains a meeting *they're in* — it must **not** constrain Steven's solo blocks or
meetings they aren't part of. Don't pull a colleague's calendar into scheduling decisions
they have nothing to do with.

---

## Working-hours template (Bali time, Mon–Fri)

> ⚠️ Boundaries are Steven's current defaults — he flagged he wants to fine-tune them.
> Treat as a soft skeleton, not hard walls; confirm edge cases.

| Window | Use |
|---|---|
| **08:00–11:00** | Self + personal deep work — gym, meditate, `[Plan] Day`, `[Process]` |
| **11:00–15:00** | Pro focus blocks + `[Lunch]` — `[Plan]` `[Process]` `[Admin]` `[Write]` |
| **15:00–18:00** (summer) / **16:00–19:00** (winter) | **Empowr meetings** — starts at 09:00 NL; compute Bali time from the meeting's date (see Timezone) |
| after Empowr window | Dinner / family / ministry |

Weekends: family, church, travel — keep light, no default work blocks.

### Weekly cadence (Mon–Fri intent — shape the week around this)

- **Monday** — planning / orchestration / alignment. Kick-offs, week planning, roadmap,
  syncs, `[1:1]`s. Don't fill Monday with heads-down deep work.
- **Tuesday** — **deep work day.** Protect it; pack in as much focused creation
  (`[Write]` `[Research]` `[Ship]` `[Design]`) as possible. Minimise meetings.
- **Wednesday** — continue deep work, **but also** review and orchestrate what the team
  needs (`[Review]`, `[Sync]`, unblocking). A hybrid maker/manager day.
- **Thu / Fri** — no fixed rule yet; default to the working-hours template.

When choosing *which day* to place something, prefer the day whose intent matches the item
(orchestration/meetings → Mon/Wed; heads-down → Tue/Wed).

### Empowr afternoon-block priorities (within the 15:00–18:00 Bali window)

- **Front-load meetings** — put Empowr meetings as early in the block as possible (from 15:00
  Bali / 09:00 NL).
- **Keep after 17:00 Bali free** where possible.
- **17:00–18:00 Bali is still OK for planning-type work**, just not the default — avoid
  putting hard meetings there unless the earlier slots are full.

---

## Duration & alert defaults (when unspecified)

| Category | Default duration |
|---|---|
| `[Plan] Day` | 30 min |
| `[Plan] Week` / `[Plan] Roadmap` | 60 min |
| `[Process] Mail & notes` | 30–45 min |
| Meetings `[1:1]` `[Sync]` `[Session]` `[Call]` | 45 min |
| Deep focus `[Write]` `[Research]` `[Review]` `[Ship]` `[Prep]` | 90–120 min |
| `[Health] Gym` | 120 min · `[Health] Meditate` 15–30 min |
| `[PG]` (reflection / goal review) | 30 min |
| `[Lunch]` | 60 min · `[Dinner]` 120–180 min |

- **Default alert:** 30 min before → `--alerts 1800s` (matches Steven's norm).
- **Empowr meetings with others:** attach a video conference (`--video-conference meet`) unless in-person.

---

## Importance / reschedule rules

Three tiers, from the answers Steven gave:

### 🔒 ANCHOR — never move, never even propose moving; always plan *around* it
- **Workout / `[Health] Gym` hours.** Steven wants these kept the same, always. Treat as a
  fixed wall the plan must route around.

### 🟡 PROTECTED — never auto-move; may *propose* a move but require explicit confirmation
- **Anything with other attendees** — Empowr `[1:1]`, `[Session]`, team check-ins, external
  invites. (Some 1:1s *can* be moved — but always suggest first because others are involved.)
- **`[Dinner] Date night`** and **family-with-others** — always confirm with Steven first.
- **Church / `Filled` ministry** (`[Event]`/`[Teach] Filled`, Bible study) and **`[Ezekiel 47]`**.

### 🟢 FREE — safe to auto-create / auto-move (this is the "low-risk" bucket)
- **Steven's own solo focus blocks with no attendees:** `[Plan]` `[Process]` `[Write]`
  `[Research]` `[Review]` `[Prep]` `[Design]` `[Strategy]` `[Admin]` `[PG]`.
- **Any `[~…]` tentative item.**

### 🚫 Monica's calendar — HARD RULE, never edit it

`monica.aanen@gmail.com` is **Steven's wife's** calendar. **Always skip it for any write.**

- **NEVER create, move, edit, retag, or delete events on `monica.aanen@gmail.com`** — not
  automatically, not in a batch, not "while we're at it." It is hers, full stop. When a task
  sweeps calendars (migrations, retagging, cleanups), **exclude this calendar entirely.**
- The **only** way Steven's planning touches Monica is by **inviting her to one of *his own*
  Personal-calendar events** that's also relevant to her: create the event on
  `ssaanen@gmail.com:ssaanen@gmail.com` and add her as an attendee (`--add
  monica.aanen@gmail.com`). She accepts on her own side. (Inviting emails her → still confirm
  first, per the attendee rule.)
- Reading her calendar (to see availability) is fine; **writing to it is not.**

### Placement guards (when finding a slot for something new)
- Never schedule over `[BLOCK]` or `OOO`.
- Never overlap an ANCHOR (gym).
- Keep meetings inside the NL overlap window if they involve the Empowr team — i.e. **09:00 NL
  or later**, converted to Bali for the meeting's date (15:00 Bali in summer, 16:00 in winter).
  Never propose an Empowr team meeting before that.
- **Respect `OOO`** — when placing any **Empowr** work, first check the Empowr calendar for
  `OOO` / holiday blocks in the candidate window and **only schedule on available (non-OOO)
  days.** Never plan Empowr work on an OOO day.

---

## Write policy (Steven's choice: "auto-apply low-risk, confirm the rest")

**Do automatically, then report what was done:**
- Create a new **solo focus block** in a genuinely free slot.
- Move one of Steven's **own solo focus blocks** (no attendees) to free up space.
- Edit the **title / description / notes** of any event (does not notify anyone).

**Show the plan and wait for explicit confirmation before writing:**
- Anything that **invites / removes attendees** (`--add`/`--remove` send emails).
- Any **move or time-change of a PROTECTED item** (attendees / date night / ministry).
- Any **delete**.

**Never:**
- Move the gym / workout ANCHOR.
- **Write to Monica's calendar automatically** — put shared family events on Steven's own
  calendar and invite her as an attendee instead (see the Monica rule above).
- Write to the read-only Dutch-holidays calendar.
