#!/usr/bin/env python3
"""to-pay skill — turn to-pay-tagged Spark emails into a bunq DraftPayment batch.

Subcommands:
  bootstrap    one-time setup: create .venv, install deps, register bunq API key
  list         list to-pay-tagged emails that haven't been processed yet (JSON)
  fetch <id>   return one email's body + extracted PDF text (JSON)
  draft        read payments JSON on stdin → create bunq DraftPayment batch
  swap-tags    after bunq approval, swap to-pay → paid on each source email
  status       show counts of processed/pending/failed
"""

import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
VENV_DIR = SKILL_DIR / ".venv"
VENV_PY = VENV_DIR / "bin" / "python"

# Auto re-exec under the skill's venv (if it exists and we aren't already in it).
# Comparing sys.prefix is reliable; comparing sys.executable paths isn't because
# venv `python` symlinks resolve back to the same system interpreter.
if VENV_PY.exists() and Path(sys.prefix).resolve() != VENV_DIR.resolve():
    os.execv(str(VENV_PY), [str(VENV_PY), *sys.argv])

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone

DATA_DIR = SKILL_DIR / "data"
ENV_FILE = SKILL_DIR / ".env"
PROCESSED_FILE = DATA_DIR / "processed.json"
LAST_BATCH_FILE = DATA_DIR / "last-batch.json"
FAILED_FILE = DATA_DIR / "failed.json"
TRUSTED_VENDORS_FILE = SKILL_DIR / "trusted-vendors.json"
BUNQ_CONTEXT_PROD = DATA_DIR / "bunq-api-context.prod.conf"
BUNQ_CONTEXT_SANDBOX = DATA_DIR / "bunq-api-context.sandbox.conf"


# ---------- shared helpers ----------

def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def spark(*args, timeout=180):
    res = subprocess.run(
        ["spark", *args], capture_output=True, text=True, timeout=timeout
    )
    if res.returncode != 0:
        raise RuntimeError(f"spark {list(args)} failed: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def env_folder(name, default):
    return os.environ.get(name, "").strip() or default


def to_pay_folder():
    return env_folder("SPARK_TO_PAY_FOLDER", "hi@stevenaanen.com:to-pay")


def paid_folder():
    return env_folder("SPARK_PAID_FOLDER", "hi@stevenaanen.com:paid")


def is_sandbox():
    return os.environ.get("BUNQ_SANDBOX", "false").strip().lower() in ("true", "1", "yes")


def bunq_context_path():
    return BUNQ_CONTEXT_SANDBOX if is_sandbox() else BUNQ_CONTEXT_PROD


# ---------- list ----------

_EMAIL_ROW = re.compile(
    r"^\s+(\d+)\s+\S+\s+(.+?)\s{2,}(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s{2,}(.+?)(?:\s{2,}\S+)?\s*$"
)


def parse_email_list(raw):
    out = []
    for line in raw.splitlines():
        # Skip the header row.
        if line.lstrip().startswith("ID "):
            continue
        m = _EMAIL_ROW.match(line)
        if not m:
            continue
        out.append({
            "id": m.group(1),
            "from": m.group(2).strip(),
            "date": m.group(3).strip(),
            "subject": m.group(4).strip(),
        })
    return out


def cmd_list(_args):
    folder = to_pay_folder()
    raw = spark("emails", folder, "--page-size", "500")
    emails = parse_email_list(raw)
    processed = read_json(PROCESSED_FILE, {})
    failed = read_json(FAILED_FILE, [])
    failed_ids = {f["email_id"] for f in failed} if failed else set()
    new = [e for e in emails if e["id"] not in processed and e["id"] not in failed_ids]
    print(json.dumps({
        "folder": folder,
        "total_tagged": len(emails),
        "new": new,
        "skipped_already_processed": len(emails) - len(new) - len(failed_ids & {e["id"] for e in emails}),
        "skipped_failed": len(failed_ids & {e["id"] for e in emails}),
        "pending_batch": read_json(LAST_BATCH_FILE, None),
    }, indent=2, ensure_ascii=False))


# ---------- fetch ----------

_FIELD_RE = {
    "id": re.compile(r"^\s+ID:\s+(\d+)\s*$", re.MULTILINE),
    "subject": re.compile(r"^\s+Subject:\s+(.+?)\s*$", re.MULTILINE),
    "from": re.compile(r"^\s+From:\s+(.+?)\s*$", re.MULTILINE),
    "date": re.compile(r"^\s+Date:\s+(.+?)\s*$", re.MULTILINE),
}
_LINK_RE = re.compile(r"^Link:\s*(\S+)\s*$", re.MULTILINE)
_PDF_ROW = re.compile(
    r"^\s+\d+\s+(.+?\.pdf)\s+\S+\s+\S+\s+application/[Pp][Dd][Ff]\s+(.+?)\s*$"
)


def extract_pdf_text(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"error": "pypdf missing — run `python3 to-pay.py bootstrap`"}
    try:
        reader = PdfReader(path)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        return {"text": text}
    except Exception as e:
        return {"error": f"pdf extraction failed: {e}"}


def parse_thread(raw):
    info = {
        "id": None,
        "subject": None,
        "from": None,
        "date": None,
        "link": None,
        "body": "",
        "pdfs": [],
    }
    m = _LINK_RE.search(raw)
    if m:
        info["link"] = m.group(1).strip()
    for k, rx in _FIELD_RE.items():
        m = rx.search(raw)
        if m:
            info[k] = m.group(1).strip()

    # Body: between the "Flags:" line and "Attachments:" (or end of thread).
    body_match = re.search(
        r"^\s+Flags:.*?\n(.*?)(?=^\s+Attachments:|\Z)",
        raw, re.MULTILINE | re.DOTALL,
    )
    if body_match:
        info["body"] = body_match.group(1).strip()

    for line in raw.splitlines():
        m = _PDF_ROW.match(line)
        if m:
            info["pdfs"].append({"name": m.group(1).strip(), "path": m.group(2).strip()})
    return info


def cmd_fetch(args):
    raw = spark("thread", "--download-attachments", str(args.id), timeout=180)
    info = parse_thread(raw)
    for pdf in info["pdfs"]:
        pdf.update(extract_pdf_text(pdf["path"]))
    print(json.dumps(info, indent=2, ensure_ascii=False))


# ---------- bunq init ----------

def init_bunq():
    """Load existing bunq context; return (api_context, monetary_account_id)."""
    try:
        from bunq.sdk.context.api_context import ApiContext
        from bunq.sdk.context.bunq_context import BunqContext
        from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
    except ImportError as e:
        raise RuntimeError(
            "bunq_sdk not installed — run `python3 to-pay.py bootstrap` first"
        ) from e

    ctx_path = bunq_context_path()
    if not ctx_path.exists():
        raise RuntimeError(
            f"No bunq context at {ctx_path}. Set BUNQ_API_KEY in .env and "
            "run `python3 to-pay.py bootstrap`."
        )
    api_ctx = ApiContext.restore(str(ctx_path))
    api_ctx.ensure_session_active()
    api_ctx.save(str(ctx_path))
    BunqContext.load_api_context(api_ctx)

    forced = os.environ.get("BUNQ_MONETARY_ACCOUNT_ID", "").strip()
    if forced:
        return api_ctx, int(forced)

    accounts = MonetaryAccountBankApiObject.list().value
    active = [a for a in accounts if a.status == "ACTIVE"]
    if len(active) == 1:
        return api_ctx, active[0].id_
    raise RuntimeError(
        f"Found {len(active)} active monetary accounts. Set BUNQ_MONETARY_ACCOUNT_ID in .env. "
        f"Choices: {[(a.id_, a.description) for a in active]}"
    )


# ---------- draft ----------

def cmd_draft(_args):
    if LAST_BATCH_FILE.exists():
        raise RuntimeError(
            f"Pending batch at {LAST_BATCH_FILE} — approve in bunq and run swap-tags, "
            "or delete the file to discard."
        )

    payments = json.loads(sys.stdin.read())
    if not isinstance(payments, list) or not payments:
        raise RuntimeError("expected non-empty JSON array on stdin")
    if len(payments) > 350:
        raise RuntimeError(f"bunq batch limit is 350 entries, got {len(payments)}")
    for p in payments:
        for k in ("email_id", "vendor", "iban", "amount", "description"):
            if not p.get(k):
                raise RuntimeError(f"missing '{k}' in payment: {p}")

    from bunq.sdk.model.generated.endpoint import DraftPaymentApiObject
    from bunq.sdk.model.generated.object_ import (
        AmountObject,
        DraftPaymentEntryObject,
        PointerObject,
    )

    _, mid = init_bunq()

    entries = []
    for p in payments:
        entries.append(DraftPaymentEntryObject(
            amount=AmountObject(str(p["amount"]), p.get("currency", "EUR")),
            counterparty_alias=PointerObject("IBAN", p["iban"].replace(" ", ""), p["vendor"]),
            description=p["description"][:140],
        ))

    draft_id = DraftPaymentApiObject.create(
        entries=entries,
        number_of_required_accepts=1,
        monetary_account_id=mid,
    ).value

    batch = {
        "draft_payment_id": draft_id,
        "monetary_account_id": mid,
        "sandbox": is_sandbox(),
        "created_at": now_iso(),
        "entries": payments,
    }
    write_json(LAST_BATCH_FILE, batch)
    print(json.dumps({
        "draft_payment_id": draft_id,
        "monetary_account_id": mid,
        "sandbox": is_sandbox(),
        "entries": len(payments),
    }, indent=2))


# ---------- swap-tags ----------

def cmd_swap_tags(_args):
    batch = read_json(LAST_BATCH_FILE, None)
    if not batch:
        print(json.dumps({"swapped": 0, "note": "no pending batch"}))
        return

    src = to_pay_folder()
    dst = paid_folder()
    processed = read_json(PROCESSED_FILE, {})
    trusted = read_json(TRUSTED_VENDORS_FILE, {})
    errors = []

    for entry in batch["entries"]:
        eid = str(entry["email_id"])
        try:
            spark("action", "attachLabel", eid, "--folder", dst)
            spark("action", "detachLabel", eid, "--folder", src)
        except Exception as e:
            errors.append({"email_id": eid, "error": str(e)})
            continue

        processed[eid] = {
            "drafted_at": batch["created_at"],
            "draft_payment_id": batch["draft_payment_id"],
            "vendor": entry["vendor"],
            "iban": entry["iban"],
            "amount": entry["amount"],
            "currency": entry.get("currency", "EUR"),
            "description": entry["description"],
        }

        vendor = entry["vendor"]
        if vendor and vendor not in trusted:
            trusted[vendor] = {"iban": entry["iban"], "learned_at": now_iso()}

    write_json(PROCESSED_FILE, processed)
    write_json(TRUSTED_VENDORS_FILE, trusted)

    if errors:
        existing = read_json(FAILED_FILE, [])
        existing.extend(errors)
        write_json(FAILED_FILE, existing)
        print(json.dumps({
            "swapped": len(batch["entries"]) - len(errors),
            "errors": errors,
            "note": "last-batch.json kept; rerun swap-tags after fixing",
        }, indent=2))
    else:
        LAST_BATCH_FILE.unlink()
        print(json.dumps({"swapped": len(batch["entries"])}, indent=2))


# ---------- bootstrap ----------

def cmd_bootstrap(_args):
    if not VENV_DIR.exists():
        print(f"Creating venv at {VENV_DIR} ...")
        subprocess.run(["python3", "-m", "venv", str(VENV_DIR)], check=True)
    pip = VENV_DIR / "bin" / "pip"
    print("Installing requirements ...")
    subprocess.run([str(pip), "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([str(pip), "install", "-q", "-r", str(SKILL_DIR / "requirements.txt")], check=True)

    if Path(sys.prefix).resolve() != VENV_DIR.resolve():
        print("Re-execing into venv for bunq registration ...")
        os.execv(str(VENV_PY), [str(VENV_PY), *sys.argv])

    api_key = os.environ.get("BUNQ_API_KEY", "").strip()
    if not api_key:
        print(
            "BUNQ_API_KEY is not set in .env yet — venv ready. "
            "Add the key, then re-run `python3 to-pay.py bootstrap`."
        )
        return

    ctx_path = bunq_context_path()
    if ctx_path.exists():
        print(f"bunq context already exists at {ctx_path}.")
        return

    from bunq.sdk.context.api_context import ApiContext
    from bunq.sdk.context.api_environment_type import ApiEnvironmentType

    env = ApiEnvironmentType.SANDBOX if is_sandbox() else ApiEnvironmentType.PRODUCTION
    print(f"Registering bunq API key ({'sandbox' if is_sandbox() else 'production'}) ...")
    ctx = ApiContext.create(env, api_key, "to-pay-skill")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ctx.save(str(ctx_path))
    print(f"Bunq context saved to {ctx_path}.")


# ---------- status ----------

def cmd_status(_args):
    print(json.dumps({
        "processed": len(read_json(PROCESSED_FILE, {})),
        "pending_batch": read_json(LAST_BATCH_FILE, None),
        "failed": read_json(FAILED_FILE, []),
        "sandbox": is_sandbox(),
        "bunq_context_exists": bunq_context_path().exists(),
        "to_pay_folder": to_pay_folder(),
        "paid_folder": paid_folder(),
    }, indent=2, ensure_ascii=False))


# ---------- entrypoint ----------

def main():
    load_env()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(prog="to-pay.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("id")
    sub.add_parser("draft")
    sub.add_parser("swap-tags")
    sub.add_parser("bootstrap")
    sub.add_parser("status")

    args = parser.parse_args()
    handlers = {
        "list": cmd_list,
        "fetch": cmd_fetch,
        "draft": cmd_draft,
        "swap-tags": cmd_swap_tags,
        "bootstrap": cmd_bootstrap,
        "status": cmd_status,
    }
    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
