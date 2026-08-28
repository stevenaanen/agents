#!/usr/bin/env python3
"""Deterministic discovery + classification for the /jenius-card skill.

Exists because hand-rolling discovery is how the June-August 2026 backlog
happened: `spark search <topic>` caps at "top 20 matches", so two topic
searches silently returned 40 of 182 transaction emails. Discovery here uses
list mode (`--filter`, no topic argument), which is exhaustive and paginated.

  scan.py            classify only; print JSON plan to stdout, touch nothing
  scan.py --apply    label+archive the auto set, write unknowns to pending
  scan.py --verify   exit 1 if any transaction email since the cutoff lacks
                     the `checked` label and is not sitting in pending

Both classify modes take --limit N to work through only the N oldest
unprocessed emails, so a large backlog can be drained in sittings. --verify
always reports the whole picture and ignores --limit.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

CUTOFF = "2026/06/12"
ACCOUNT = "ssaanen@gmail.com"
LABEL = f"{ACCOUNT}:checked"
FILTER = f'from:jenius_noreply@smbci.com after:{CUTOFF} subject:"Credit Card Transaction"'
PAGE_SIZE = 200
LIVING_EXPENSE_MAX = 200_000

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PENDING = os.path.join(DATA, "pending-jenius-transactions.json")
TRUSTED = os.path.join(HERE, "trusted-merchants.json")

ROW_RE = re.compile(
    r"^\s{2}(\d{4,})\s+\S+@\S+\s+.*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s", re.M
)
FOOTER_RE = re.compile(r"Page (\d+) of (\d+) \((\d+) total emails\)")


def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout, r.returncode


def list_ids(scope=None):
    """{id: received date} for FILTER, following pagination to the last page."""
    ids, page, pages = {}, 1, 1
    while page <= pages:
        scope_arg = f' --in "{scope}"' if scope else ""
        out, _ = sh(
            f"spark search --filter '{FILTER}'{scope_arg}"
            f" --page-size {PAGE_SIZE} --page {page}"
        )
        ids.update(ROW_RE.findall(out))
        m = FOOTER_RE.search(out)
        if not m:
            raise SystemExit(
                f"spark returned no pagination footer for page {page} "
                f"(scope={scope!r}) — refusing to guess at coverage.\n{out[-500:]}"
            )
        pages, total = int(m.group(2)), int(m.group(3))
        page += 1
    if len(ids) != total:
        raise SystemExit(
            f"coverage mismatch (scope={scope!r}): parsed {len(ids)} ids "
            f"but spark reported {total} total — refusing to proceed."
        )
    return ids


def fetch(eid):
    """Merchant / amount / transaction date for one email, or None if unparseable."""
    out, _ = sh(f"spark email {eid}")
    subject = re.search(r"^\s+Subject:\s*(.+?)\s*$", out, re.M)
    # "... Credit Card Transaction Unsuccessful" — a declined attempt (wrong PIN
    # etc). No money moved, and the body has no Merchant:/Total: lines at all.
    if subject and subject.group(1).endswith("Unsuccessful"):
        return {"email_id": eid, "declined": True}
    merchant = re.search(r"^\s+Merchant:\s*(.+?)\s*$", out, re.M)
    amount = re.search(r"^\s+Total: ([A-Z]{3}) ([\d,]+(?:\.\d+)?)\s*$", out, re.M)
    date = re.search(r"^\s+Transaction date & time:\s*(.+?)\s*$", out, re.M)
    if not (merchant and amount):
        return None
    return {
        "email_id": eid,
        "merchant": merchant.group(1),
        "currency": amount.group(1),
        "amount_idr": int(float(amount.group(2).replace(",", ""))),
        "date": date.group(1) if date else "",
    }


def classify(txn, trusted):
    if txn.get("declined"):
        return "declined"
    # The IDR threshold is meaningless against another currency, so anything
    # not denominated in IDR always goes to a human.
    if txn["currency"] != "IDR":
        return "unknown"
    if txn["amount_idr"] < LIVING_EXPENSE_MAX:
        return "cheap"
    up = txn["merchant"].upper()
    return "trusted" if any(t.upper() in up for t in trusted) else "unknown"


def mark_checked(eid):
    _, rc = sh(f'spark action attachLabel {eid} --folder "{LABEL}"')
    if rc != 0:
        return False
    # Already-archived mail reports "action not applicable"; the label is what
    # marks the email handled, so a failed archive is not a failure.
    sh(f"spark action archive {eid}")
    return True


def main():
    argv = sys.argv[1:]
    limit = None
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = int(argv[i + 1])
        del argv[i : i + 2]
    mode = argv[0] if argv else ""

    pending = json.load(open(PENDING)) if os.path.exists(PENDING) else []
    pending_ids = {p["email_id"] for p in pending}

    all_ids = list_ids()
    checked = set(list_ids(scope=LABEL))
    outstanding = set(all_ids) - checked - pending_ids
    # Oldest first, so a limited run always drains the top of the backlog.
    todo = sorted(outstanding, key=lambda i: (all_ids[i], i))
    deferred = 0
    if limit is not None and len(todo) > limit:
        deferred = len(todo) - limit
        todo = todo[:limit]

    if mode == "--verify":
        print(
            f"{len(all_ids)} transaction emails since {CUTOFF}: "
            f"{len(set(all_ids) & checked)} checked, {len(pending_ids)} pending review, "
            f"{len(outstanding)} unprocessed"
        )
        todo = sorted(outstanding, key=lambda i: (all_ids[i], i))
        if todo:
            print("UNPROCESSED: " + " ".join(todo))
        return 1 if todo else 0

    trusted = json.load(open(TRUSTED))["merchants"]
    auto, unknown, declined, unparseable = [], [], [], []
    for eid in todo:
        txn = fetch(eid)
        if txn is None:
            unparseable.append(eid)
            continue
        kind = classify(txn, trusted)
        {"unknown": unknown, "declined": declined}.get(kind, auto).append(txn)

    plan = {
        "total_since_cutoff": len(all_ids),
        "already_checked": len(set(all_ids) & checked),
        "already_pending": len(pending_ids),
        "deferred_to_next_run": deferred,
        "auto_checked": auto,
        "declined": declined,
        "needs_review": unknown,
        "unparseable": unparseable,
    }

    if mode != "--apply":
        print(json.dumps(plan, indent=2))
        return 0

    failed = [t["email_id"] for t in auto + declined if not mark_checked(t["email_id"])]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending += [dict(t, processed_at=now) for t in unknown]
    json.dump(pending, open(PENDING, "w"), indent=2)

    print(
        f"Processed {len(auto) + len(declined) + len(unknown)}: "
        f"{len(auto) + len(declined) - len(failed)} checked "
        f"({len(declined)} declined), {len(unknown)} pending"
    )
    if failed:
        print("LABEL FAILED (left for next run): " + " ".join(failed))
    if unparseable:
        print("UNPARSEABLE (left for next run): " + " ".join(unparseable))
    if deferred:
        print(f"{deferred} older-backlog email(s) deferred to a later run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
