---
name: apple-invoices
description: Find new Apple invoice emails (since 2025), classify each service as business or personal, and write business invoices as PDFs to the Aanen Holding -TO-SUBMIT/apple folder. Tracks processed email IDs so repeated runs only handle new invoices. Use when the user says "/apple-invoices", "process Apple invoices", "submit Apple receipts", or asks to handle new Apple billing emails.
---

# Apple Invoice Processor

Pulls Apple invoice emails out of `ssaanen@gmail.com`, classifies each unique
service as **business** or **personal** (asking the user once per new service),
renders the business invoices as PDFs, and drops them in the Aanen Holding
submission folder for bookkeeping.

State is split into two files:

| File | Purpose | Tracked in git |
|---|---|---|
| `services.json` (skill root) | `{service_key: "business" \| "personal"}` — durable classifications | yes |
| `data/processed.json` (gitignored) | `{email_id: {invoice_date, service, classification, total_eur, pdf_path?}}` | no |

PDFs are written to `/Users/steven/Dropbox (Personal)/Aanen Holding/Administration/-TO-SUBMIT/apple` with the filename `YYYY-MM-DD - Apple-<service>.pdf`.

## Workflow

Run the three commands below in order. The script handles all parsing, dedupe,
PDF rendering, and state updates — your job is just to relay the user's
business/personal answers for any service that hasn't been classified yet.

### 1. Scan

```bash
python3 skills/apple-invoices/run.py scan
```

Output is a JSON document with two sections:
- `new_invoices` — every invoice email that isn't yet in `processed.json`
- `unknown_services` — services seen in those invoices that aren't yet in `services.json`

Exit code is `2` when classification is needed, `0` when everything is already classified.

### 2. Classify new services (only if scan returned `unknown_services`)

For **each** entry in `unknown_services`, ask the user via `AskUserQuestion`
whether it's a business or personal expense. Include the sample invoice's
price and product header in the question so the user has context. Example
phrasing: *"`App Store: Claude` — Claude Pro Monthly, €22,00 (sample invoice 229919). Business or personal?"*

Then record each answer:

```bash
python3 skills/apple-invoices/run.py classify "<service_key>" business
python3 skills/apple-invoices/run.py classify "<service_key>" personal
```

Quote the service key exactly as it appeared in the scan output — it may
contain spaces, colons, `+`, etc.

### 3. Process

```bash
python3 skills/apple-invoices/run.py process
```

For every new invoice:
- **business** → render PDF, save to the Dropbox folder, record in `processed.json`
- **personal** → record in `processed.json` (skipped, no PDF)
- **still unclassified** → skipped with a warning (re-run scan + classify)

Output is a JSON summary: counts of PDFs written, personal skipped, errors.

## When to use which command

| Situation | Command |
|---|---|
| Routine check ("are there any new Apple invoices?") | `scan` → if classified, `process` |
| User asks what's been processed / which services are flagged | `status` |
| User adds/changes a classification ahead of time | `classify <key> <business\|personal>` |

## Notes

- The scan window starts at 2025-01-01 and never moves. Dedupe is by email ID,
  so the cutoff just keeps the spark query cheap.
- "Apple TV" rentals (e.g. movies) collapse into one `Apple TV` service key —
  individual titles aren't separate classifications.
- `services.json` is repo-tracked so classifications survive across machines
  and worktrees. `data/processed.json` is per-worktree (gitignored, like other
  skill data files in this repo).
- Filename collisions (same service + same date) get the email ID appended.
- Required tools, all already present on this Mac: `spark` (Spark Desktop CLI),
  `python3`, and Chrome at `/Applications/Google Chrome.app`.
