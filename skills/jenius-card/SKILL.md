---
name: jenius-card
description: Process Jenius s-Card and d-Card transaction emails in ssaanen@gmail.com. Picks up any email (inbox or archive) without the `checked` label and newer than the cutoff; tags trusted/cheap immediately, sends unknowns to pending for telegram review.
---

# Jenius Card Processor

Scans Monica's Jenius credit card transaction notifications (both s-Card and
d-Card) and classifies them as living expenses (ignore) or reimbursable (track
for later).

**Selection rule:** any Jenius transaction email newer than `2026/06/12` (the
cutoff when this change shipped) that does NOT already carry the `checked`
Gmail label — regardless of whether it sits in Inbox or Archive. The `checked`
label is what marks "fully handled"; emails without it are reprocessed on every
run.

## Run it

Discovery and classification are done by `scan.py`, not by hand:

```bash
python3 skills/jenius-card/scan.py            # dry run — prints the JSON plan
python3 skills/jenius-card/scan.py --apply    # label + archive, write pending
python3 skills/jenius-card/scan.py --verify   # exit 1 if anything is unprocessed
```

Run the dry run first when the backlog is large, report the split to the user,
then `--apply`. Always finish with `--verify`.

Both classify modes take the **32 oldest** unprocessed emails by default
(`DEFAULT_LIMIT`), and report how many they deferred. Every unknown becomes a
Telegram prompt a human has to answer, so an uncapped run over a big backlog is
unanswerable in one sitting — and this path also runs unattended from
`scripts/run-jenius.sh`. Pass `--limit N` for a different cap, or `--limit 0`
to take everything. A limited run always starts from the oldest, so repeated
runs drain the backlog in date order.

## Do NOT use topic search for discovery

`spark search <topic>` is capped at **the top 20 matches** (it says so in
`spark help search`). Using it for discovery is what silently hid 130 of 182
transaction emails between June and August 2026. Discovery must use **list
mode** — `--filter` with no topic argument — which is exhaustive and paginated:

```bash
spark search --filter 'from:jenius_noreply@smbci.com after:2026/06/12 subject:"Credit Card Transaction"' --page-size 200
```

List mode returns a table without bodies, so `scan.py` fetches each candidate's
merchant and amount with `spark email <id>`. It follows the `Page X of Y (N
total emails)` footer to the last page and aborts if the parsed count does not
match `N`, rather than proceeding on a partial set.

The `checked` set is a separate query (spark has no negative-label filter),
also in list mode:

```bash
spark search --in "ssaanen@gmail.com:checked" --filter '<same filter>' --page-size 200
```

Candidates already listed in `data/pending-jenius-transactions.json` are
skipped too — they are awaiting telegram review, don't double-enqueue.

## Classification

| Condition | Action |
|-----------|--------|
| Amount < IDR 200,000 | living expense → `attachLabel checked` + `archive` |
| Amount ≥ 200,000, merchant in `trusted-merchants.json` | trusted spend → `attachLabel checked` + `archive` |
| Amount ≥ 200,000, merchant NOT trusted | unknown → append to `data/pending-jenius-transactions.json` (do **not** tag or archive) |

Trusted merchant matching is partial + case-insensitive against `merchants[]`.

Two cases the amount rule can't decide on its own:

- **Declined attempts** — subject ends `Credit Card Transaction Unsuccessful`
  (wrong PIN etc). No money moved and the body carries no `Merchant:`/`Total:`
  lines, so these are labelled `checked` without review. The matching
  successful retry, if any, arrives as its own email and is classified
  normally.
- **Non-IDR charges** — some foreign merchants are billed in their own
  currency (`Total: USD 280.00`). An IDR threshold says nothing about those, so
  any non-IDR amount goes to review regardless of size.

Out of scope: `... Refund Transaction` emails (money coming back), bill
payments, and billing statements. The `subject:"Credit Card Transaction"`
filter excludes them by design.

```bash
spark action attachLabel <id> --folder "ssaanen@gmail.com:checked"
spark action archive <id>
```

`attachLabel` is what marks an email handled. `archive` reports `action not
applicable` for mail that is already archived — that is expected and not a
failure. An email whose `attachLabel` fails, or whose body won't parse, is left
untouched so it reappears on the next run.

Unknowns are NOT tagged or archived here — `/jenius-review` tags them only
after the user replies in Telegram. If the user never replies, the email stays
unlabeled and will reappear on the next run.

Unknown merchant entry: `{ email_id, merchant, amount_idr, date, processed_at }`.

## Output

One line when done: `Processed X: Y checked, Z pending`
