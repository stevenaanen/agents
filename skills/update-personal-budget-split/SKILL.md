---
name: update-personal-budget-split
description: Reconcile the monthly personal-budget split in bunq to a user-supplied from/to/amount table of internal transfers. Diffs the desired table against the live recurring "Monthly budget" scheduled payments and applies only the delta (add missing, delete removed, change differing, leave matches alone) — gathering money INTO the auto-sort account on the 27th and distributing OUT of it on the 28th. Always shows the full delete/add/change plan and waits for explicit confirmation before any bulk write. Use when the user says "/update-personal-budget-split", "update the budget split", "redo the monthly budget", or pastes a budget table to schedule.
metadata:
  requires:
    bins: [python3]
---

# /update-personal-budget-split

Reconcile the monthly personal-budget split (bunq scheduled payments) to a from/to/amount table the user supplies. It **diffs desired vs. live** and applies only the delta — add what's missing, delete what's been removed, change what differs, leave matches untouched — then writes nothing until the user approves the plan.

All work runs through `budget_split.py`, which **reuses the sibling `/to-pay` skill's venv and bunq context** (same registered device — no second registration):

```bash
cd /Users/steven/git/agents/skills/update-personal-budget-split
python3 budget_split.py <subcommand>
```

## ⚠️ Live, irreversible bunq changes — plan first, then confirm

Unlike `/to-pay` (which uses DraftPayments you approve in the app), scheduled-payment **create and delete take effect immediately with no in-app approval** — the API key is the authorization.

**The mandatory flow is: `plan` (read-only) → show the full delete/add/change table → get the user's explicit go-ahead → only then run `delete`/`create`.** Never run the bulk writes without an approved plan. `accounts`, `list-matching`, and `plan` make no changes and are safe anytime.

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

### Step 1 — Resolve the table to desired entries

The table rows are `<from>  <to>  <amount>` (e.g. `Autosort  Tithes  € 160` means **from** Autosort **to** Tithes, €160). Build a resolved JSON array — one object per row — resolving *both* ends against the `accounts` output:

```json
[
  {
    "from_account_id": 4002682,
    "from_label": "Real estate",
    "to_account_id": 1983471,
    "to_label": "Autosort",
    "to_iban": "<autosort IBAN>",
    "to_name": "<autosort holder_name>",
    "amount": "182"
  }
]
```

- `from_account_id` = the account the money leaves (the schedule is created *on* this account).
- `to_account_id` + `to_iban` + `to_name` = the destination account (from its `accounts` entry: `id`, `iban`, `holder_name`).
- `amount` = positive number, no symbol. `currency` defaults to EUR; `description` defaults to `Monthly budget` — **keep the default** so reconciliation matches.

To avoid IBAN transcription errors with many rows, it's fine to generate this array programmatically by looking up each account's IBAN/holder by id from the `accounts` output.

### Step 2 — Plan (read-only diff)

Pipe the desired array to `plan` with the auto-sort id. This **makes no changes** — it diffs desired vs. the live `Monthly budget` payments:

```bash
echo '[...]' | python3 budget_split.py plan --autosort-id 1983471
```

It returns `summary` + four lists and two ready-to-run payloads:

- `unchanged` — already correct (same from→to, amount, day): **left alone**.
- `add` — in the table, not yet in bunq → to create.
- `change` — same from→to but amount/day differs → old deleted, new created.
- `delete` — a live `Monthly budget` payment whose from→to is no longer in the table → to remove.
- `execute_delete` — id pairs to feed `delete` (= `delete` + each `change` old).
- `execute_create` — entries to feed `create` (= `add` + each `change` new).

### Step 3 — Show the plan and STOP for confirmation 🔒

**This is a hard gate. Do not run `delete` or `create` until the user explicitly approves.** Render the plan as a clear table:

- **To delete** (account, to, amount, day)
- **To add** (from → to, amount, day 27/28)
- **To change** (from → to, amount old→new, day old→new)
- **Unchanged**: just the count

State the net effect (e.g. "−€81/mo, +€980/mo") and flag any `add`/`change` whose `direction` contains `WARNING` or that targets a `PENDING_ACCEPTANCE` account. Then ask for a clear go-ahead. If `add`, `change`, and `delete` are all empty, tell the user everything's already in sync and stop — nothing to do.

### Step 4 — Execute (only after approval)

Capture the plan JSON, then run the two payloads. Skip either if empty:

```bash
echo '<execute_delete from the plan>' | python3 budget_split.py delete
echo '<execute_create from the plan>' | python3 budget_split.py create --autosort-id 1983471
```

Report created/deleted ids and any failures (e.g. pending-account rejections). Then re-run Step 2's `plan` to verify it converged — ideally everything is now `unchanged` (apart from rows that legitimately failed, like still-pending accounts).

---

## Notes

- **Idempotent by reconciliation:** re-running with the same table is a no-op; re-running with an edited table applies only the delta. Nothing is deleted-and-recreated unnecessarily. Payments with other descriptions (salary, VvE, parking, etc.) are never touched.
- The diff key is **(from account, to IBAN)**; amount and day are compared as attributes. Changing an amount or moving the 27/28 day shows up as a `change`.
- `next_run`/dates are anchored to the 27th/28th of the next month that hasn't passed, at 07:00 UTC.
- Never run `delete`/`create` (the bulk writes) without an approved plan. `accounts`, `list-matching`, and `plan` are all read-only and safe to run anytime.
