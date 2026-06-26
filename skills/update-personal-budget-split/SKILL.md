---
name: update-personal-budget-split
description: Rebuild the monthly personal-budget split in bunq. Deletes the existing recurring "Monthly budget" scheduled payments (with a confirmation), then recreates them from a user-supplied from/to/amount table of internal transfers — gathering money INTO the auto-sort account on the 27th and distributing OUT of it on the 28th. Use when the user says "/update-personal-budget-split", "update the budget split", "redo the monthly budget", or pastes a budget table to schedule.
metadata:
  requires:
    bins: [python3]
---

# /update-personal-budget-split

Rebuild the monthly personal-budget split as bunq scheduled payments. Two halves:

1. **Delete** every existing recurring payment whose description is exactly `Monthly budget`.
2. **Create** fresh monthly scheduled payments from a from/to/amount table the user supplies.

All work runs through `budget_split.py`, which **reuses the sibling `/to-pay` skill's venv and bunq context** (same registered device — no second registration):

```bash
cd /Users/steven/git/agents/skills/update-personal-budget-split
python3 budget_split.py <subcommand>
```

## ⚠️ These are live, irreversible bunq changes

Unlike `/to-pay` (which uses DraftPayments you approve in the app), scheduled-payment **create and delete take effect immediately with no in-app approval** — the API key is the authorization. So **always preview and get explicit confirmation before deleting and before creating.** Never fire either without showing the exact list first.

## Prerequisite

`/to-pay` must already be bootstrapped (its `.venv/` and `data/bunq-api-context.prod.conf` must exist). If not, tell the user to bootstrap `/to-pay` first, or set `BUNQ_CONTEXT_PATH` in this skill's `.env`. A bunq session that fails with *"Incorrect API key or IP address"* means the key is IP-locked to where it was registered — the user must connect from that network or regenerate the key (see `/to-pay`).

## The date rule (owned by the script, not by you)

- Money flowing **INTO** the auto-sort account runs on the **27th** (gather first).
- Money flowing **OUT OF** the auto-sort account runs on the **28th** (then distribute).

You only need to identify the **auto-sort account id** and pass it as `--autosort-id`. `budget_split.py create` computes the 27th/28th per row itself from the from/to account ids. Both ends of every transfer are internal bunq accounts, so resolve both.

---

## Flow

### Step 0 — Load accounts

```bash
python3 budget_split.py accounts
```

Returns all 32-ish active accounts as JSON: `{id, type, description, iban, holder_name}`. Use this to fuzzy-match the names in the user's table — **table names differ slightly from bunq descriptions** (e.g. "IB Boterstraat" → "Reserve IB Boterstraat", "Real estate" → "Real Estate"). For each table name pick the best-matching account; if a match is ambiguous or missing, ask the user.

**Identify the auto-sort account.** The user's table uses a code like `Autosort` for the account where all money arrives and is redistributed. Fuzzy-match it; if there's no obvious account named like it, ask the user which account id is the auto-sort account. Confirm this mapping explicitly — it drives every date.

**Known account-name aliases** (table name → bunq account description; confirmed by the user). Apply these before fuzzy-matching; if anything new/ambiguous comes up, ask:

| Table name | bunq account |
|---|---|
| `Autosort` | the joint account literally named **Autosort** (`NL70BUNQ2045309959`) |
| `Pocket Money Mo` / `Pocket Money Monica` | **Pocket Money** (Monica's; the un-suffixed one) |
| `Pocket Money Steve` | **Pocket Money Steve** |
| `Parent Pranoto` / `Papa` | **Papa** |
| `Parents Aanen` | **Parents Aanen** |
| `IB Boterstraat` | **IB Boterstraat** savings (`NL44BUNQ2175248038`), *not* the joint "Boterstraat" |

Watch for accounts that are **`PENDING_ACCEPTANCE`** (e.g. a freshly created Provisions/Depreciation): bunq rejects scheduled payments to them with *"Unable to make a payment to the chosen account."* — flag these and ask whether to target an active account instead or skip until accepted. Some names (e.g. **Depreciation**) may exist as both an active and a pending account — confirm which.

### Step 1 — Delete existing "Monthly budget" payments

```bash
python3 budget_split.py list-matching            # default --description "Monthly budget"
```

Show the user a table of every match: **account (from), to_name + to_iban, amount, recurrence, start_date, next_run**. State plainly that these will be deleted and that it is immediate. Get a clear yes.

On confirmation, pipe the targets (just the id pairs) to delete:

```bash
echo '[{"monetary_account_id":10834704,"schedule_payment_id":2030638}, ...]' \
  | python3 budget_split.py delete
```

Report how many were deleted / any failures.

### Step 2 — Create the new split from the table

The table rows are `<from>  <to>  <amount>` (e.g. `Autosort  Tithes  € 159` means **from** Autosort **to** Tithes, €159).

Build a resolved JSON array — one object per row — resolving both ends against the `accounts` output:

```json
[
  {
    "from_account_id": 4002682,
    "from_label": "Real estate",
    "to_account_id": <autosort id>,
    "to_label": "Autosort",
    "to_iban": "<autosort IBAN>",
    "to_name": "<autosort holder_name>",
    "amount": "182"
  }
]
```

- `from_account_id` = the account the money leaves (the schedule is created *on* this account).
- `to_account_id` + `to_iban` + `to_name` = the destination account (from its `accounts` entry: `id`, `iban`, `holder_name`).
- `amount` = positive number, no currency symbol. `currency` defaults to EUR; `description` defaults to `Monthly budget` (keep this default so the skill stays re-runnable).

**Preview first** with `--dry-run`, passing the auto-sort id:

```bash
echo '[...]' | python3 budget_split.py create --autosort-id <autosort id> --dry-run
```

Show the returned `plan`: each row's **from_label → to_label, amount, day_of_month (27/28), direction, next_run**. This is the reconciliation step — confirm amounts and dates with the user, especially that into-auto-sort rows are on the 27th and out-of-auto-sort rows on the 28th. Watch for any `direction` containing `WARNING` (a row that touches neither side of auto-sort) and flag it.

On confirmation, run the same command **without `--dry-run`** to create them. Report created ids and any failures.

---

## Notes

- Re-running is safe and idempotent: Step 1 deletes all `Monthly budget` payments, Step 2 recreates from the current table. External recurring payments with other descriptions (salary, VvE, parking, etc.) are never touched.
- `next_run`/dates are anchored to the 27th/28th of the next month that hasn't passed, at 07:00 UTC.
- If the user only wants one half (just delete, or just create), do that half.
