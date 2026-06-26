#!/usr/bin/env python3
"""update-personal-budget-split — manage the monthly personal-budget bunq schedule.

Two halves:
  1. Delete the existing recurring "Monthly budget" scheduled payments.
  2. Recreate them from a user-supplied from/to/amount table, all internal
     transfers, anchored on fixed days of the month:
        - money flowing INTO the auto-sort account  -> the 27th (gather first)
        - money flowing OUT of the auto-sort account -> the 28th (then distribute)

This script is a thin, deterministic executor. Account-name fuzzy matching and
the preview/confirmation live in SKILL.md (driven by Claude); the irreversible
27th/28th rule lives here in code so it can't drift.

Auth/SDK are reused from the sibling /to-pay skill (same bunq device + context),
so there is no second device registration. Override the context path with
BUNQ_CONTEXT_PATH in .env if needed.

Subcommands:
  accounts                      list active monetary accounts (JSON)
  list-matching [--description] list recurring payments whose description matches
                                (default "Monthly budget"), with next run dates
  delete                        stdin: [{monetary_account_id, schedule_payment_id}] -> delete each
  create --autosort-id N [--dry-run]
                                stdin: [{from_account_id, to_account_id, to_iban,
                                to_name, amount, ...}] -> create monthly schedules
"""

import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
TO_PAY_DIR = SKILL_DIR.parent / "to-pay"
VENV_PY = TO_PAY_DIR / ".venv" / "bin" / "python"

# Reuse /to-pay's venv (it already has bunq_sdk). Re-exec into it if present.
if VENV_PY.exists() and Path(sys.prefix).resolve() != (TO_PAY_DIR / ".venv").resolve():
    os.execv(str(VENV_PY), [str(VENV_PY), *sys.argv])

import argparse
import calendar
import json
from datetime import datetime

ENV_FILE = SKILL_DIR / ".env"
DEFAULT_CTX = TO_PAY_DIR / "data" / "bunq-api-context.prod.conf"
DEFAULT_DESCRIPTION = "Monthly budget"
DEFAULT_HOUR_UTC = 7  # 07:00 UTC — safely away from any midnight date rollover

DAY_INTO_AUTOSORT = 27   # incoming to auto-sort runs first
DAY_OUT_OF_AUTOSORT = 28  # outgoing distribution runs the next day


# ---------- env + bunq context ----------

def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ctx_path():
    p = os.environ.get("BUNQ_CONTEXT_PATH", "").strip()
    return Path(p) if p else DEFAULT_CTX


def load_bunq():
    """Restore the shared bunq context and return (user_id, api_client)."""
    from bunq.sdk.context.api_context import ApiContext
    from bunq.sdk.context.bunq_context import BunqContext
    from bunq.sdk.http.api_client import ApiClient

    cp = ctx_path()
    if not cp.exists():
        raise SystemExit(
            f"No bunq context at {cp}. Bootstrap the /to-pay skill first "
            "(it registers the bunq API key), or set BUNQ_CONTEXT_PATH in .env."
        )
    api_ctx = ApiContext.restore(str(cp))
    api_ctx.ensure_session_active()
    api_ctx.save(str(cp))
    BunqContext.load_api_context(api_ctx)
    uid = BunqContext.user_context().user_id
    return uid, ApiClient(api_ctx)


# ---------- raw API helpers (avoid the SDK's float-deserialize bug) ----------

def raw_get(client, endpoint):
    return json.loads(client.get(endpoint, {}, {}).body_bytes.decode())["Response"]


def raw_get_all(client, endpoint):
    """Paginated GET — bunq listings default to ~10 per page; follow older_url."""
    out = []
    sep = "&" if "?" in endpoint else "?"
    ep = f"{endpoint}{sep}count=200"
    while ep:
        d = json.loads(client.get(ep, {}, {}).body_bytes.decode())
        out.extend(d["Response"])
        older = (d.get("Pagination") or {}).get("older_url")
        ep = older[len("/v1/"):] if older else None
    return out


def first_val(item):
    k = next(iter(item))
    return k, item[k]


def all_accounts(client, uid):
    """Every monetary account, fully paginated (the listing pages at ~10)."""
    out = []
    ep = f"user/{uid}/monetary-account?count=200"
    while ep:
        d = json.loads(client.get(ep, {}, {}).body_bytes.decode())
        for it in d["Response"]:
            typ, o = first_val(it)
            iban = name = ""
            for a in (o.get("alias") or []):
                if a.get("type") == "IBAN":
                    iban, name = a.get("value", ""), a.get("name", "")
            out.append({
                "id": o["id"],
                "type": typ.replace("MonetaryAccount", "") or "Bank",
                "status": o.get("status"),
                "description": o.get("description") or "",
                "iban": iban,
                "holder_name": name,
            })
        older = (d.get("Pagination") or {}).get("older_url")
        ep = older[len("/v1/"):] if older else None
    return out


def active_accounts(client, uid):
    return [a for a in all_accounts(client, uid) if a["status"] == "ACTIVE"]


# ---------- date math ----------

def next_run(start_dt, unit, size):
    """Next occurrence at/after now for a recurring schedule (date only).

    Anchors on the original day-of-month so a short month (e.g. clamping a 29th
    to Feb 28) doesn't permanently drag the day down in later months.
    """
    now = datetime.now()
    if start_dt >= now:
        return start_dt.date().isoformat()
    if (unit or "").upper() == "MONTHLY":
        step = size or 1
        n = 0
        cur = start_dt
        while cur < now:
            n += step
            m0 = start_dt.month - 1 + n
            y = start_dt.year + m0 // 12
            m = m0 % 12 + 1
            d = min(start_dt.day, calendar.monthrange(y, m)[1])
            cur = start_dt.replace(year=y, month=m, day=d)
        return cur.date().isoformat()
    if (unit or "").upper() == "ONCE":
        return None  # already executed
    return start_dt.date().isoformat()  # weekly/daily not expected here


def next_day_of_month(day, hour=DEFAULT_HOUR_UTC):
    """Next future datetime landing on `day` of the month at `hour`:00 UTC."""
    now = datetime.now()
    y, m = now.year, now.month
    if day <= now.day:  # this month's day already reached -> next month
        m += 1
        if m > 12:
            m, y = 1, y + 1
    d = min(day, calendar.monthrange(y, m)[1])
    return datetime(y, m, d, hour, 0, 0)


def parse_bunq_dt(s):
    s = (s or "").split(".")[0]  # drop microseconds
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


# ---------- commands ----------

def cmd_accounts(args):
    uid, client = load_bunq()
    print(json.dumps(active_accounts(client, uid), indent=2, ensure_ascii=False))


def cmd_list_matching(args):
    uid, client = load_bunq()
    want = args.description.strip()
    matches = []
    for a in active_accounts(client, uid):
        try:
            rows = raw_get_all(client, f"user/{uid}/monetary-account/{a['id']}/schedule-payment")
        except Exception:
            rows = []
        for it in rows:
            _, sp = first_val(it)
            p = sp.get("payment") or {}
            if (p.get("description") or "").strip() != want:
                continue
            s = sp.get("schedule") or {}
            cpa = (p.get("counterparty_alias") or {})
            lbl = cpa.get("LabelMonetaryAccount") or cpa
            amt = p.get("amount") or {}
            unit, size = s.get("recurrence_unit"), s.get("recurrence_size")
            start = s.get("time_start")
            nxt = None
            try:
                nxt = next_run(parse_bunq_dt(start), unit, size)
            except Exception:
                pass
            matches.append({
                "monetary_account_id": a["id"],
                "account": a["description"],
                "schedule_payment_id": sp.get("id"),
                "amount": str(amt.get("value", "")).lstrip("-"),
                "currency": amt.get("currency", "EUR"),
                "to_name": lbl.get("display_name") or lbl.get("name") or "",
                "to_iban": lbl.get("iban") or lbl.get("value") or "",
                "description": p.get("description", ""),
                "recurrence": f"every {size or 1} {unit.lower()}" if unit else "once",
                "start_date": start,
                "next_run": nxt,
                "status": sp.get("status"),
            })
    print(json.dumps({"description_filter": want, "count": len(matches),
                      "matches": matches}, indent=2, ensure_ascii=False))


def cmd_delete(args):
    targets = json.loads(sys.stdin.read())
    if not isinstance(targets, list) or not targets:
        raise SystemExit("expected non-empty JSON array on stdin")
    load_bunq()
    from bunq.sdk.model.generated.endpoint import SchedulePaymentApiObject

    results = []
    for t in targets:
        mid = t["monetary_account_id"]
        sid = t["schedule_payment_id"]
        try:
            SchedulePaymentApiObject.delete(sid, monetary_account_id=mid)
            results.append({"schedule_payment_id": sid, "monetary_account_id": mid, "deleted": True})
        except Exception as e:
            results.append({"schedule_payment_id": sid, "monetary_account_id": mid,
                            "deleted": False, "error": str(e)[:200]})
    ok = sum(1 for r in results if r["deleted"])
    print(json.dumps({"deleted": ok, "failed": len(results) - ok, "results": results},
                     indent=2, ensure_ascii=False))


def _resolve_day(entry, autosort_id):
    """The irreversible 27th/28th rule, owned by code."""
    if entry["from_account_id"] == autosort_id:
        return DAY_OUT_OF_AUTOSORT, "out of auto-sort"
    if entry.get("to_account_id") == autosort_id:
        return DAY_INTO_AUTOSORT, "into auto-sort"
    return DAY_OUT_OF_AUTOSORT, "WARNING: does not touch auto-sort (defaulted to 28th)"


def cmd_create(args):
    entries = json.loads(sys.stdin.read())
    if not isinstance(entries, list) or not entries:
        raise SystemExit("expected non-empty JSON array on stdin")

    plan = []
    for e in entries:
        for k in ("from_account_id", "to_iban", "to_name", "amount"):
            if e.get(k) in (None, ""):
                raise SystemExit(f"missing '{k}' in entry: {e}")
        day, reason = _resolve_day(e, args.autosort_id)
        ts = next_day_of_month(day)
        plan.append({
            "from_account_id": e["from_account_id"],
            "from_label": e.get("from_label", ""),
            "to_label": e.get("to_label", ""),
            "to_iban": e["to_iban"].replace(" ", ""),
            "to_name": e["to_name"],
            "amount": str(e["amount"]).lstrip("-").replace(",", "."),
            "currency": e.get("currency", "EUR"),
            "description": e.get("description", DEFAULT_DESCRIPTION),
            "day_of_month": day,
            "direction": reason,
            "time_start": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "next_run": ts.date().isoformat(),
            "recurrence": "every 1 monthly",
        })

    if args.dry_run:
        print(json.dumps({"dry_run": True, "count": len(plan), "plan": plan},
                         indent=2, ensure_ascii=False))
        return

    load_bunq()
    from bunq.sdk.model.generated.endpoint import SchedulePaymentApiObject, ScheduleApiObject
    from bunq.sdk.model.generated.object_ import (
        AmountObject, PointerObject, SchedulePaymentEntryObject,
    )

    results = []
    for p in plan:
        try:
            payment = SchedulePaymentEntryObject(
                amount=AmountObject(p["amount"], p["currency"]),
                counterparty_alias=PointerObject("IBAN", p["to_iban"], p["to_name"]),
                description=p["description"][:140],
            )
            schedule = ScheduleApiObject(
                time_start=p["time_start"],
                recurrence_unit="MONTHLY",
                recurrence_size=1,
            )
            sid = SchedulePaymentApiObject.create(
                payment=payment, schedule=schedule,
                monetary_account_id=p["from_account_id"],
            ).value
            results.append({**p, "created": True, "schedule_payment_id": sid})
        except Exception as e:
            results.append({**p, "created": False, "error": str(e)[:200]})
    ok = sum(1 for r in results if r["created"])
    print(json.dumps({"created": ok, "failed": len(results) - ok, "results": results},
                     indent=2, ensure_ascii=False))


# ---------- entrypoint ----------

def main():
    load_env()
    parser = argparse.ArgumentParser(prog="budget_split.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("accounts")

    p_lm = sub.add_parser("list-matching")
    p_lm.add_argument("--description", default=DEFAULT_DESCRIPTION)

    sub.add_parser("delete")

    p_cr = sub.add_parser("create")
    p_cr.add_argument("--autosort-id", type=int, required=True)
    p_cr.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    {
        "accounts": cmd_accounts,
        "list-matching": cmd_list_matching,
        "delete": cmd_delete,
        "create": cmd_create,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
