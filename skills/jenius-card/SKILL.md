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

Gmail labels must also exist. Create them at mail.google.com → Labels if missing:
- `checked`
- `to-reimburse`

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

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:to-reimburse"
spark action archive <id>
```

Then inform the user:

> ⚠️ **Reimbursable transaction flagged**
> - Merchant: [merchant name]
> - Amount: IDR [amount formatted with thousand separators]
> - Date: [date]

Ask: **"Should [MERCHANT] be added to the trusted merchants list for future transactions? (yes/no)"**

If yes: add the merchant name (without location suffix — use just the first meaningful segment before any location codes) to `merchants[]` in `skills/jenius-card/trusted-merchants.json`, save the file.

### Step 4 — Summary

After processing all emails, output a compact summary:

```
Processed X transaction(s):
  ✓ Y checked (living expenses / trusted merchants)
  ⚠ Z flagged for reimbursement:
      - [MERCHANT] · IDR [amount] · [date]
      - ...
```

If the trusted-merchants list was updated, mention it.

## Merchant name normalization

When adding to the trusted list, strip trailing location noise. Jenius appends city/region codes to merchant names:
- `SHAKE UP! BADUNG (KAB) ID` → store `SHAKE UP!`
- `INDOMARET CANGGU HO BADUNG ID` → store `INDOMARET`
- `MAI MAIN CANGGU HO BADUNG ID` → store `MAI MAIN`

Use your judgment on where the merchant name ends and the location starts.
