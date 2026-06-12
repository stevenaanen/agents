---
name: jenius-card
description: Process Jenius s-Card and d-Card transaction emails in ssaanen@gmail.com. Picks up any email (inbox or archive) without the `checked` label and newer than the cutoff; tags trusted/cheap immediately, sends unknowns to pending for telegram review.
---

# Jenius Card Processor

Scans Monica's Jenius credit card transaction notifications (both s-Card and
d-Card) and classifies them as living expenses (ignore) or reimbursable (track
for later).

**Selection rule:** any Jenius email newer than `2026/06/12` (the cutoff when
this change shipped) that does NOT already carry the `checked` Gmail label —
regardless of whether it sits in Inbox or Archive. The `checked` label is what
marks "fully handled"; emails without it are reprocessed on every run.

## Find candidate emails

Run both searches across **all folders** (omit `--in`) and combine results,
deduplicating by ID:

```bash
spark search "s-Card Credit Card Transaction" --filter "from:jenius_noreply@smbci.com after:2026/06/12"
spark search "d-Card Credit Card Transaction" --filter "from:jenius_noreply@smbci.com after:2026/06/12"
```

Then list the IDs already in the `checked` label so we can exclude them — spark
has no negative-label filter, so this is a separate query:

```bash
spark search --in "ssaanen@gmail.com:checked" --filter "from:jenius_noreply@smbci.com after:2026/06/12" --page-size 200
```

Drop any candidate whose ID appears in the checked set. Also drop any candidate
whose ID already appears in `data/pending-jenius-transactions.json` (it's
awaiting telegram review — don't double-enqueue).

For each remaining result, parse: `ID`, `Merchant:`, `Total: IDR`, `Transaction date & time:`.

## Classification

| Condition | Action |
|-----------|--------|
| Amount < IDR 200,000 | living expense → `attachLabel checked` + `archive` |
| Amount ≥ 200,000, merchant in `trusted-merchants.json` | trusted spend → `attachLabel checked` + `archive` |
| Amount ≥ 200,000, merchant NOT trusted | unknown → append to `data/pending-jenius-transactions.json` (do **not** tag or archive) |

Trusted merchant matching is partial + case-insensitive against `merchants[]`.

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:checked"
spark action archive <id>
```

Unknowns are NOT tagged or archived here — `/jenius-review` tags them only
after the user replies in Telegram. If the user never replies, the email stays
unlabeled and will reappear on the next run.

Unknown merchant entry: `{ email_id, merchant, amount_idr, date, processed_at }` — use `$(date -u +%Y-%m-%dT%H:%M:%SZ)` for `processed_at`.

## Output

One line when done: `Processed X: Y checked, Z pending`
