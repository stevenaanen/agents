---
name: jenius-card
description: Process Jenius s-Card transaction emails in ssaanen@gmail.com inbox. Labels and archives each email; saves unknown merchants to pending file.
---

# Jenius s-Card Processor

```bash
spark search "s-Card Credit Card Transaction" --in ssaanen@gmail.com:Inbox
```

For each result, parse: `ID`, `Merchant:`, `Total: IDR`, `Transaction date & time:`. For each, run silently:

1. **Amount < 200,000** → checked + archive
2. **Amount ≥ 200,000, merchant in `trusted-merchants.json`** (partial case-insensitive) → checked + archive
3. **Amount ≥ 200,000, merchant NOT trusted** → append to `data/pending-jenius-transactions.json`, then checked + archive

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:checked"
spark action archive <id>
```

Pending entry shape: `{ email_id, merchant, amount_idr, date, processed_at }`

When done, output one line: `Processed X: Y checked, Z pending`
