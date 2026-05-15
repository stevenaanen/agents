---
name: jenius-card
description: Process Jenius s-Card and d-Card transaction emails in ssaanen@gmail.com inbox. Labels and archives each email; saves unknown merchants to pending file.
---

# Jenius Card Processor

Scans Monica's Jenius credit card transaction notifications (both s-Card and
d-Card) and classifies them as living expenses (ignore) or reimbursable (track
for later). Inbox-only search means already-processed emails are naturally
excluded (they get archived).

Run both searches and combine results, deduplicating by ID:

```bash
spark search "s-Card Credit Card Transaction" --in ssaanen@gmail.com:Inbox --filter from:jenius_noreply@smbci.com
spark search "d-Card Credit Card Transaction" --in ssaanen@gmail.com:Inbox --filter from:jenius_noreply@smbci.com
```

For each result, parse: `ID`, `Merchant:`, `Total: IDR`, `Transaction date & time:`.

## Classification (run silently per email)

| Condition | Action |
|-----------|--------|
| Amount < IDR 200,000 | living expense → checked + archive |
| Amount ≥ 200,000, merchant in `trusted-merchants.json` | trusted spend → checked + archive |
| Amount ≥ 200,000, merchant NOT trusted | unknown → append to `data/pending-jenius-transactions.json`, then checked + archive |

Trusted merchant matching is partial + case-insensitive against `merchants[]`.

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:checked"
spark action archive <id>
```

Unknown merchant entry: `{ email_id, merchant, amount_idr, date, processed_at }` — use `$(date -u +%Y-%m-%dT%H:%M:%SZ)` for `processed_at`.

The pending file accumulates unknowns for `/jenius-review`, which prompts via
Telegram and routes each to reimbursements or trusted-merchants.

## Output

One line when done: `Processed X: Y checked, Z pending`
