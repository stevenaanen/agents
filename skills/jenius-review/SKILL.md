---
name: jenius-review
description: >-
  Review pending Jenius transactions via Telegram. For each unknown merchant,
  prompts to reimburse, skip once, or always ignore. Tags the email `checked`
  + archives it only after a reply is received; on timeout the email stays
  untagged so it reappears next run.
---

# Jenius Transaction Review

Drains `skills/jenius-card/data/pending-jenius-transactions.json` by prompting
the user in Telegram for each entry. Separates reimbursable spend from living
expenses so the pending file stays clean after each review run.

## Data files (all under skills/jenius-card/data/)

- `pending-jenius-transactions.json` — input; entries are removed only after a Telegram reply
- `reimbursements.json` — approved-for-reimbursement entries accumulate here
- `skills/jenius-card/trusted-merchants.json` — updated when "always ignore"

## Execution

Read `pending-jenius-transactions.json`. If empty, output "Nothing to review." and stop.

Each entry carries a `currency` field — usually `IDR`, but Jenius bills some
foreign merchants in their own currency. Render the prompt in the entry's own
currency; never assume IDR. Entries written before this field existed have no
`currency` key — treat those as `IDR`.

For each entry, send a Telegram prompt and wait up to 5 minutes for a tap:

```bash
MSG_ID=$(python3 skills/telegram/telegram.py send \
  "*Transaction review* [current]/[count]
🏪 [merchant]
💰 [currency] [amount with thousand separators]
📅 [date]" \
  --keyboard '[["💰 Reimburse:reimburse", "⏭ Skip:skip", "✅ Always skip:always"]]')

REPLY=$(python3 skills/telegram/telegram.py wait --message-id "$MSG_ID" --timeout 300)
```

Act on `$REPLY`:

| Response    | Action                                                                                                        |
| ----------- | ------------------------------------------------------------------------------------------------------------- |
| `reimburse` | Append entry to `reimbursements.json`, remove from pending, **tag email `checked` + archive**                 |
| `skip`      | Remove from pending, **tag email `checked` + archive** (one-time living expense, no further tracking)         |
| `always`    | Remove from pending + add normalized merchant to `trusted-merchants.json`, **tag email `checked` + archive**  |
| *(timeout / no reply)* | Leave entry in pending and do **not** tag the email — it will be reprocessed next run              |

Tag + archive after each reply:

```bash
spark action attachLabel <email_id> --folder "ssaanen@gmail.com:checked"
spark action archive <email_id>
```

**Merchant normalization for "always ignore":** strip trailing location noise
(city, region, country code). `"SURF BREW TABANAN KOT. ID"` → `"SURF BREW"`.
Use the shortest prefix that uniquely identifies the merchant.

After processing all entries, write the updated pending array back (containing
only timeout entries, if any).

Then read `reimbursements.json` to get the total count and send a closing
Telegram message (no keyboard):

```
✅ *Review complete*
X reviewed: Y reimbursable, Z skipped, W always ignored, T timed out
💰 [total] transaction(s) total pending reimbursement
```

Omit the `T timed out` segment when zero.

## Output

One line: `Reviewed X: Y reimbursable, Z skipped, W always ignored, T timed out`
