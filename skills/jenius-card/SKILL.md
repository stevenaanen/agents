---
name: jenius-card
description: >-
  Process unread Jenius s-Card transaction emails in ssaanen@gmail.com inbox.
  Classifies each transaction against an IDR 200,000 threshold and a trusted
  merchants list, then labels and archives. Use when asked to check, process,
  or review Jenius credit card transactions.
---

# Jenius s-Card Transaction Processor

Processes Jenius s-Card transaction notification emails from ssaanen@gmail.com.

## Prerequisites (one-time setup)

Before this workflow can label or archive, the account needs **triage** access:
- Open Spark Desktop → Settings → AI Agents → ssaanen@gmail.com → set to **Triage**

A Gmail label `checked` must exist in ssaanen@gmail.com. Create it at mail.google.com → Labels if missing.

## Execution

### Step 1 — Find unprocessed emails

Search the Inbox only (already-processed emails are archived, so Inbox = unprocessed):

```bash
spark search "s-Card Credit Card Transaction" --in ssaanen@gmail.com:Inbox
```

If there are no results, tell the user there are no pending Jenius transactions and stop.

### Step 2 — Parse each email

The search results include the full email body. For each result, extract:

- **Merchant**: the value after `Merchant:` on its own line, trimmed (e.g. `SHAKE UP! BADUNG (KAB) ID`)
- **Amount**: the integer IDR amount after `Total: IDR ` — strip commas and the `.00` decimal (e.g. `IDR 95,000.00` → `95000`)
- **Date**: the value after `Transaction date & time:`
- **Message ID**: the `ID:` from the search result header

### Step 3 — Classify and act

For each email, apply this logic in order:

#### A. Amount < 200,000 IDR → living expense

Label as checked and archive:

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:checked"
spark action archive <id>
```

Move to the next email.

#### B. Amount ≥ 200,000 IDR → check trusted merchants

Read `skills/jenius-card/trusted-merchants.json` from this repository.

Do a **partial, case-insensitive** match: check if any entry in `merchants[]` appears anywhere in the merchant name from the email. For example, `"INDOMARET"` in the list matches `"INDOMARET CANGGU ID"` from the email.

**Merchant is trusted:**

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:checked"
spark action archive <id>
```

Move to the next email.

**Merchant is NOT trusted:**

Append an entry to `skills/jenius-card/data/pending-jenius-transactions.json`:

```json
{
  "email_id": "<spark message id>",
  "merchant": "<full merchant name from email>",
  "amount_idr": <integer amount>,
  "date": "<transaction date & time string>",
  "processed_at": "<today's date ISO 8601>"
}
```

Then label as checked and archive (same as trusted — the email is done, the transaction is pending):

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:checked"
spark action archive <id>
```

### Step 4 — Summary

After processing all emails, output a compact summary:

```
Processed X transaction(s):
  ✓ Y checked (living expenses / trusted merchants)
  ⚠ Z pending reimbursement review:
      - [MERCHANT] · IDR [amount] · [date]
      - ...
```

## Notes

- The `data/pending-jenius-transactions.json` file accumulates all unknown-merchant transactions for later review and reimbursement processing.
- Trusted merchant matching is partial and case-insensitive: `"MAI MAIN RESTO"` matches `"MAI MAIN CANGGU RESTO BADUNG ID"`. Add the shortest unambiguous prefix to `trusted-merchants.json`.
