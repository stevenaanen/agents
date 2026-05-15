---
name: jenius-review
description: >-
  Review pending Jenius transactions via Telegram. For each unknown merchant,
  prompts to reimburse, skip once, or always ignore. Updates trusted-merchants
  and reimbursements db accordingly.
---

# Jenius Transaction Review

Drains `skills/jenius-card/data/pending-jenius-transactions.json` by prompting
the user in Telegram for each entry. Separates reimbursable spend from living
expenses so the pending file stays clean after each review run.

## Data files (all under skills/jenius-card/data/)

- `pending-jenius-transactions.json` — input; entries are removed after review
- `reimbursements.json` — approved-for-reimbursement entries accumulate here
- `skills/jenius-card/trusted-merchants.json` — updated when "always ignore"

## Execution

Read `pending-jenius-transactions.json`. If empty, output "Nothing to review." and stop.

For each entry, send a Telegram prompt and wait up to 5 minutes for a tap:

```bash
MSG_ID=$(python3 skills/telegram/telegram.py send \
  "*Transaction review* [current]/[count]
🏪 [merchant]
💰 IDR [amount with thousand separators]
📅 [date]" \
  --keyboard '[["💰 Reimburse:reimburse", "⏭ Skip:skip", "✅ Always skip:always"]]')

REPLY=$(python3 skills/telegram/telegram.py wait --message-id "$MSG_ID" --timeout 300)
```

Act on `$REPLY`:

| Response    | Action                                                                    |
| ----------- | ------------------------------------------------------------------------- |
| `reimburse` | Append entry to `reimbursements.json`, remove from pending                |
| `skip`      | Remove from pending (one-time living expense, no further tracking)        |
| `always`    | Remove from pending + add normalized merchant to `trusted-merchants.json` |

**Merchant normalization for "always ignore":** strip trailing location noise
(city, region, country code). `"SURF BREW TABANAN KOT. ID"` → `"SURF BREW"`.
Use the shortest prefix that uniquely identifies the merchant.

After processing all entries, write the updated (empty) array back to
`pending-jenius-transactions.json`.

Then read `reimbursements.json` to get the total count and send a closing
Telegram message (no keyboard):

```
✅ *Review complete*
X reviewed: Y reimbursable, Z skipped, W always ignored
💰 [total] transaction(s) total pending reimbursement
```

## Output

One line: `Reviewed X: Y reimbursable, Z skipped, W always ignored`
