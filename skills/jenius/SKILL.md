---
name: jenius
description: >-
  Full Jenius pipeline: process inbox transactions then review unknowns via
  Telegram. Runs jenius-card then jenius-review in sequence.
---

# Jenius Pipeline

Runs the two Jenius skills in order. Each step is fully documented in its own skill.

1. **`/jenius-card`** — scan ssaanen@gmail.com inbox (s-Card + d-Card), classify,
   label, archive. Unknown merchants go to `pending-jenius-transactions.json`.

2. **`/jenius-review`** — if pending is non-empty, prompt via Telegram for each
   unknown, update reimbursements and trusted-merchants, send summary message.

Execute each step fully before starting the next. If jenius-card reports
0 pending, skip jenius-review.
