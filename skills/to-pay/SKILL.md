---
name: to-pay
description: Turn Spark emails tagged `to-pay` (business inbox hi@stevenaanen.com) into a single bunq DraftPayment batch. Parses PDF invoices for vendor/IBAN/amount, creates the draft for one-tap approval in the bunq app, then swaps the `to-pay` tag to `paid` after the user confirms.
metadata:
  requires:
    bins: [spark, python3]
---

# /to-pay

End-to-end flow: tagged email → parsed invoice → bunq DraftPayment batch → bunq app approval → tag swap.

All Python work runs through `to-pay.py` (auto-uses its own `.venv/`). Never `pip install` outside the venv.

```bash
cd /Users/steven/git/agents/skills/to-pay
python3 to-pay.py <subcommand>
```

## Prerequisite (one-time)

If `.venv/` or `data/bunq-api-context.prod.conf` is missing, the user hasn't bootstrapped. Tell them:

> Generate a personal API key in the bunq Developer portal, paste it into `skills/to-pay/.env` as `BUNQ_API_KEY=...`, then run `python3 to-pay.py bootstrap`.

Bootstrap is idempotent — safe to re-run.

## Pipeline

### 1. Check for a pending batch

```bash
python3 to-pay.py status
```

If `pending_batch` is non-null, **stop the new pipeline**. Tell the user:

> A bunq draft batch from `<created_at>` is still waiting. Did you approve it in bunq? Reply `done` to swap tags, `discard` to delete it, or `keep` to leave it and exit.

- `done` → run `swap-tags`, then continue with step 2.
- `discard` → delete `data/last-batch.json`, then continue.
- `keep` → exit.

### 2. List new tagged emails

```bash
python3 to-pay.py list
```

Returns JSON with `new[]`. If empty, say "No new to-pay emails." and stop.

### 3. Fetch + parse each email

For each `id` in `new[]`:

```bash
python3 to-pay.py fetch <id>
```

This downloads attachments (if not cached) and prints `{id, subject, from, date, link, body, pdfs:[{name, path, text}]}`.

**Parse each invoice yourself** from `body` + `pdfs[].text`. Produce one object per email:

```json
{
  "email_id": "231423",
  "link": "https://sparkmailapp.com/dpl/bl?token=…",
  "vendor": "Ignite Group B.V.",
  "iban": "NL77INGB0674595998",
  "currency": "EUR",
  "amount": "182.95",
  "description": "Ignite VF26IG-03480 WBSO mei-2026",
  "invoice_number": "VF26IG-03480",
  "source_subject": "Ignite Group B.V - Verkoopfactuur VF26IG-03480"
}
```

Extraction rules:

- **iban** — search PDF text for an IBAN pattern (`[A-Z]{2}\d{2}[A-Z0-9]+`, 15–34 chars total, stripped of spaces). Validate the mod-97 checksum. Dutch invoices often write it as `ING: NL77…` or `IBAN: NL77…` — strip the prefix.
- **amount** — prefer "Totaalbedrag incl. BTW" / "TOTAAL" / "Total" / "Amount due". Use a string with a `.` decimal separator (bunq's amount field is a string).
- **vendor** — the company billing, not the customer. Usually appears in the PDF header or footer (KVK number is often nearby on Dutch invoices).
- **description** — short (≤140 chars). Format: `<short vendor> <invoice number> <month/period if relevant>`. The user will see this in their bunq history.
- **currency** — default `EUR` for invoices in Netherlands. Override if the PDF clearly states USD/GBP/etc.

Cross-check `iban` against `trusted-vendors.json` if the vendor is known. **If the vendor exists in trusted-vendors but the IBAN differs, treat this as a hard stop for that entry** — print a warning, leave its tag untouched, and skip it from the batch (the user can investigate manually).

If you cannot confidently extract every required field for an email (vendor, iban, amount, description), skip that entry and surface it at the end as "left tagged `to-pay` — needs manual review: \<reason\>".

### 4. Show the summary table

Before drafting, print a table for the user:

```
# | Vendor              | Amount       | IBAN (last 6)   | Description
1 | Ignite Group B.V.   | EUR 182.95   | …595998         | Ignite VF26IG-03480 WBSO mei-2026
2 | …
```

### 5. Create the bunq draft batch

Pipe the JSON array of payment objects into `draft`:

```bash
echo '<payments-json-array>' | python3 to-pay.py draft
```

Output: `{draft_payment_id, monetary_account_id, entries}`. Save the `draft_payment_id` for the next step.

### 6. Verification list — give the user ordered email links

Print **emails in the same order as the bunq batch entries**, so the user can cross-check each one in bunq against the source. Open the link in Spark Desktop by clicking — that's where the invoice PDF lives.

```
Bunq draft batch <draft_payment_id> created with N entries. Approve in the bunq app. As you tap through each entry in order, here's the source email for that line:

  1. EUR 182.95 → Ignite Group B.V. (VF26IG-03480)
     <spark-deep-link>
  2. EUR …     → …
     <spark-deep-link>

Once you've approved (or rejected) the batch in bunq, reply:
  • `done`          → swap tags from `to-pay` → `paid` on all entries
  • `done except 2,5` → swap tags on all except entries 2 and 5 (those stay `to-pay`)
  • `discard`       → you rejected the batch; delete `data/last-batch.json`
```

### 7. Swap tags after approval

On `done` (with optional exceptions):

- If the user excludes any entries, edit `data/last-batch.json` and remove those entries from the `entries` array before running swap-tags. They'll stay tagged `to-pay` and resurface on the next `/to-pay` run.
- Then:

```bash
python3 to-pay.py swap-tags
```

This detaches `to-pay`, attaches `paid` on every entry in `last-batch.json`, records each in `data/processed.json`, and learns the `vendor → iban` mapping in `trusted-vendors.json` (only added if the vendor wasn't already there).

On `discard`: just `rm data/last-batch.json` and tell the user it's gone.

### 8. Final report

One line: `Drafted N · Paid+tagged M · Skipped K (manual: ...)`. If anything was skipped, list the email IDs + reasons so the user can chase them.

## Idempotency

- `processed.json` (gitignored) — `email_id` is the dedupe key for `list`, so re-running `/to-pay` never double-drafts.
- `last-batch.json` (gitignored) — exists only while a batch is awaiting tag swap; that's why step 1 is the pending-batch check.
- `failed.json` (gitignored) — emails that couldn't be parsed. They're skipped by `list` but stay tagged `to-pay` in Spark, so the user sees them.

## Configuration

`.env` (gitignored — see `.env.example`):

- `BUNQ_API_KEY` — personal API key from bunq Developer
- `BUNQ_MONETARY_ACCOUNT_ID` — optional; only needed if more than one active account
- `SPARK_TO_PAY_FOLDER` / `SPARK_PAID_FOLDER` — Gmail label IDs (default: `hi@stevenaanen.com:to-pay` / `:paid`)
- `BUNQ_SANDBOX=true` — use bunq sandbox env (requires its own bootstrap)

## Sandbox testing

To exercise the pipeline without touching real money:

```bash
echo 'BUNQ_SANDBOX=true' >> .env
python3 to-pay.py bootstrap          # creates sandbox context
# Tag one real email `to-pay`, run through the flow; bunq draft appears in sandbox.
# Reset .env when done.
```

## Files

| Path | Purpose | Tracked |
|---|---|---|
| `SKILL.md` | this file | yes |
| `to-pay.py` | CLI | yes |
| `requirements.txt` | pinned deps | yes |
| `.env.example` | template | yes |
| `.env` | secrets | no (gitignored) |
| `trusted-vendors.json` | learned vendor → IBAN | yes |
| `.venv/` | virtualenv | no (gitignored as `*.venv`) |
| `data/processed.json` | drafted+paid ledger | no |
| `data/last-batch.json` | in-flight batch awaiting approval | no |
| `data/failed.json` | unparseable emails | no |
| `data/bunq-api-context.{prod,sandbox}.conf` | bunq SDK context (contains private key) | no |
