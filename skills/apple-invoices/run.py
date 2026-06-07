#!/usr/bin/env python3
"""Apple Invoice Processor.

Commands:
  scan       Discover new invoices since 2025-01-01, parse them, identify any
             services that aren't yet classified in services.json. Outputs JSON.
             Exit 0 if everything is classified, exit 2 if classification is needed.
  classify   Set a service's classification. Args: <service_key> <business|personal>
  process    Generate PDFs for business-flagged new invoices, save to the
             Aanen Holding submission folder, and append email IDs to processed.json.
             Outputs a summary.
  status     Show counts of processed vs pending and current classifications.

State files (kept relative to this script):
  services.json          {service_key: "business" | "personal"}   (committed)
  data/processed.json    {email_id: {date, service, pdf_path?, classification}} (gitignored)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DATA_DIR = SKILL_DIR / "data"
SERVICES_FILE = SKILL_DIR / "services.json"
PROCESSED_FILE = DATA_DIR / "processed.json"

OUTPUT_DIR = Path("/Users/steven/Dropbox (Personal)/Aanen Holding/Administration/-TO-SUBMIT/apple")

EARLIEST_INVOICE_DATE = "2025/01/01"
SPARK_FOLDER = "ssaanen@gmail.com:Archive"
SPARK_FROM = "no_reply@email.apple.com"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ---------- Spark helpers ----------

def spark(*args, timeout=120):
    res = subprocess.run(["spark", *args], capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"spark {args} failed: {res.stderr}")
    return res.stdout


def list_invoice_emails():
    """Return list of (email_id, subject, date) for every Apple invoice email since EARLIEST_INVOICE_DATE."""
    out = []
    # Two subject variants: English and Dutch
    for subj_filter in ("subject:invoice", "subject:factuur"):
        raw = spark(
            "emails", SPARK_FOLDER,
            "--filter", f"from:{SPARK_FROM} {subj_filter} after:{EARLIEST_INVOICE_DATE}",
            "--page-size", "500",
        )
        for line in raw.splitlines():
            m = re.match(r"\s*(\d+)\s+\S+\s+.*?(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}\s+(.+?)\s{2,}", line)
            if m:
                out.append({"id": m.group(1), "date": m.group(2), "subject": m.group(3).strip()})
    # Dedupe by ID
    seen = set()
    uniq = []
    for e in out:
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq.append(e)
    return uniq


def fetch_thread(email_id):
    return spark("thread", str(email_id), timeout=60)


# ---------- Invoice parsing ----------

def parse_amount(s):
    m = re.search(r"€\s*([\d.,]+)", s)
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def parse_invoice(text):
    """Return {invoice_date, year, total_eur, service, body} from a spark-thread dump."""
    lines = [l.strip() for l in text.splitlines()]

    # Email Date: header → fallback
    email_date = None
    for l in lines:
        m = re.match(r"Date:\s*(\d{4}-\d{2}-\d{2})", l)
        if m:
            email_date = m.group(1)
            break

    # Old format: "INVOICE DATE\n<date> SEQUENCE NO."
    invoice_date = None
    for i, l in enumerate(lines):
        if l == "INVOICE DATE":
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r"(\d{1,2}\s+\w+\s+\d{4})", lines[j])
                if m:
                    invoice_date = m.group(1)
                    break
            break

    # New format: "# Invoice" then date line
    if not invoice_date:
        for i, l in enumerate(lines):
            if l == "# Invoice":
                for j in range(i + 1, min(i + 8, len(lines))):
                    if re.match(r"^\d{1,2}\s+\w+\s+\d{4}$", lines[j]):
                        invoice_date = lines[j]
                        break
                break

    # Normalize invoice date → YYYY-MM-DD
    invoice_date_iso = email_date  # fallback
    if invoice_date:
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                invoice_date_iso = datetime.strptime(invoice_date, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass

    year = int(invoice_date_iso[:4]) if invoice_date_iso else None

    body = "\n".join(lines)

    # Total
    total = None
    m = re.search(r"\bTOTAL\b\s*€\s*([\d.,]+)|\bTOTAAL\b\s*€\s*([\d.,]+)", body)
    if m:
        total = float((m.group(1) or m.group(2)).replace(".", "").replace(",", "."))
    if total is None:
        m = re.search(
            r"(?:MasterCard|VISA|Visa|American Express|Amex)\s*[•.]+\s*\d{4}[^\n]*\n+\s*€\s*([\d.,]+)",
            body,
        )
        if m:
            total = float(m.group(1).replace(".", "").replace(",", "."))

    # Locate product block start
    start = None
    for i, l in enumerate(lines):
        if l == "Apple Account:":
            j = i + 1
            while j < len(lines) and not lines[j]:
                j += 1
            if j < len(lines) and "@" in lines[j]:
                j += 1
                while j < len(lines) and not lines[j]:
                    j += 1
                start = j
                break
    if start is None:
        for i, l in enumerate(lines):
            if "DOCUMENT NO." in l:
                j = i + 1
                while j < len(lines) and not lines[j]:
                    j += 1
                if j < len(lines):
                    j += 1
                while j < len(lines) and not lines[j]:
                    j += 1
                start = j
                break

    # Locate first € amount line
    first_eur_idx = None
    for i, l in enumerate(lines):
        if re.match(r"^€\s*[\d.,]+$", l):
            first_eur_idx = i
            break
    if first_eur_idx is None:
        for i, l in enumerate(lines):
            if re.search(r"€\s*\d", l) and "Inclusive" not in l and "Inclusief" not in l:
                first_eur_idx = i
                break

    product_lines = []
    if start is not None and first_eur_idx is not None and start < first_eur_idx:
        skip_re = [
            r"^Renews\b", r"^Vernieuwt\b", r"^Inclusive of VAT", r"^Inclusief btw",
            r"^\[Report a Problem", r"^Police Surveillance Van",
            r"^Monthly$", r"^Maandelijks$", r"^Yearly$", r"^Annual$",
        ]
        for j in range(start, first_eur_idx):
            l = lines[j]
            if not l:
                continue
            if any(re.search(p, l) for p in skip_re):
                continue
            product_lines.append(l)

    product_header = product_lines[0] if product_lines else None
    product_detail = product_lines[1] if len(product_lines) >= 2 else None

    service = classify_service(product_header, product_detail, body)

    return {
        "invoice_date": invoice_date_iso,
        "year": year,
        "total_eur": total,
        "service": service,
        "product_header": product_header,
        "product_detail": product_detail,
    }


def classify_service(h, d, body):
    h = h or ""
    d = d or ""
    if h in ("iCloud", "iCloud+") or re.search(r"iCloud\+", body):
        if re.search(r"iCloud\+\s*(?:with|met)\s*2\s*TB", body):
            return "iCloud+ 2TB"
        if re.search(r"iCloud\+\s*(?:with|met)\s*200\s*GB", body):
            return "iCloud+ 200GB"
        return "iCloud+"
    if h == "Apple Music" or "Apple Music Family Subscription" in body:
        return "Apple Music Family"
    if h == "Apple Services":
        if "Apple Music" in d:
            return "Apple Music Family"
        return f"Apple Services: {d}"
    if h == "Apple TV":
        return "Apple TV"  # rentals/purchases — single bucket, title varies per invoice
    if h == "App Store":
        name = d or "Unknown"
        return f"App Store: {_norm_app(name)}"
    if h:
        return f"App Store: {_norm_app(h)}"
    return "Unknown"


_APP_ALIASES = {
    "Everand: Audiobooks & Ebooks": "Everand",
    "Everand: Audiobooks and ebooks": "Everand",
    "Everand: Ebooks and audiobooks": "Everand",
    "Bear: Markdown Notes": "Bear",
    "Bear Markdown Notes": "Bear",
    "AllTrails: Hike, Run & Walk": "AllTrails",
    "AllTrails: Wandel, Fiets & Run": "AllTrails",
    "Claude by Anthropic": "Claude",
}


def _norm_app(name):
    return _APP_ALIASES.get(name, name)


# ---------- State ----------

def load_services():
    if SERVICES_FILE.exists():
        return json.loads(SERVICES_FILE.read_text())
    return {}


def save_services(d):
    SERVICES_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def load_processed():
    if PROCESSED_FILE.exists():
        return json.loads(PROCESSED_FILE.read_text())
    return {}


def save_processed(d):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


# ---------- Commands ----------

def cmd_scan():
    services = load_services()
    processed = load_processed()
    emails = list_invoice_emails()
    new_emails = [e for e in emails if e["id"] not in processed]

    invoices = []
    unknown = {}  # service_key -> sample invoice
    for e in new_emails:
        text = fetch_thread(e["id"])
        parsed = parse_invoice(text)
        rec = {
            "email_id": e["id"],
            "email_date": e["date"],
            "subject": e["subject"],
            **parsed,
        }
        invoices.append(rec)
        svc = parsed["service"]
        if svc not in services and svc != "Unknown":
            unknown.setdefault(svc, rec)

    out = {
        "new_invoice_count": len(invoices),
        "new_invoices": invoices,
        "unknown_services": [
            {
                "service": svc,
                "sample": {
                    "email_id": s["email_id"],
                    "invoice_date": s["invoice_date"],
                    "total_eur": s["total_eur"],
                    "product_header": s["product_header"],
                    "product_detail": s["product_detail"],
                },
            }
            for svc, s in unknown.items()
        ],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    sys.exit(2 if unknown else 0)


def cmd_classify(service_key, classification):
    if classification not in ("business", "personal"):
        sys.exit("classification must be 'business' or 'personal'")
    services = load_services()
    services[service_key] = classification
    save_services(services)
    print(f"Classified {service_key!r} as {classification}")


def cmd_process():
    services = load_services()
    processed = load_processed()
    emails = list_invoice_emails()
    new_emails = [e for e in emails if e["id"] not in processed]

    pdf_count = 0
    skipped_personal = 0
    skipped_unknown = 0
    errors = []

    for e in new_emails:
        text = fetch_thread(e["id"])
        parsed = parse_invoice(text)
        svc = parsed["service"]
        cls = services.get(svc)
        if cls is None:
            skipped_unknown += 1
            print(f"SKIP unclassified service {svc!r} (email {e['id']}) — run scan + classify first", file=sys.stderr)
            continue

        if cls == "business":
            try:
                pdf_path = render_pdf(text, parsed, e["id"])
            except Exception as exc:
                errors.append({"email_id": e["id"], "error": str(exc)})
                continue
            pdf_count += 1
            processed[e["id"]] = {
                "invoice_date": parsed["invoice_date"],
                "service": svc,
                "classification": cls,
                "total_eur": parsed["total_eur"],
                "pdf_path": str(pdf_path),
            }
        else:
            skipped_personal += 1
            processed[e["id"]] = {
                "invoice_date": parsed["invoice_date"],
                "service": svc,
                "classification": cls,
                "total_eur": parsed["total_eur"],
            }

    save_processed(processed)

    summary = {
        "scanned": len(new_emails),
        "business_pdfs_written": pdf_count,
        "personal_skipped": skipped_personal,
        "unclassified_skipped": skipped_unknown,
        "errors": errors,
        "output_dir": str(OUTPUT_DIR),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def cmd_status():
    services = load_services()
    processed = load_processed()
    print(f"Services classified : {len(services)}")
    for k, v in sorted(services.items()):
        print(f"  {v:8s}  {k}")
    print(f"\nInvoices processed  : {len(processed)}")
    biz = sum(1 for r in processed.values() if r["classification"] == "business")
    per = len(processed) - biz
    print(f"  business: {biz}   personal: {per}")


# ---------- PDF rendering ----------

def render_pdf(thread_text, parsed, email_id):
    """Render the invoice email body to PDF via Chrome headless. Returns the Path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    body = extract_invoice_body(thread_text)
    html = markdown_to_html(body)
    full_html = wrap_html(html, parsed)

    service_slug = sanitize_filename(service_to_filename(parsed["service"]))
    date = parsed["invoice_date"] or "0000-00-00"
    filename = f"{date} - Apple-{service_slug}.pdf"
    out_path = OUTPUT_DIR / filename

    # Ensure uniqueness if same service+date appears twice
    if out_path.exists():
        out_path = OUTPUT_DIR / f"{date} - Apple-{service_slug} ({email_id}).pdf"

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(full_html)
        html_path = f.name

    try:
        subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={out_path}",
                f"file://{html_path}",
            ],
            capture_output=True,
            check=True,
            timeout=60,
        )
    finally:
        os.unlink(html_path)

    return out_path


def extract_invoice_body(thread_text):
    """Strip spark headers and footer to get just the email body."""
    lines = thread_text.splitlines()
    # find first blank line after the "Type: Email" header block
    body_start = 0
    for i, l in enumerate(lines):
        if l.strip().startswith("Type:"):
            body_start = i + 1
            break
    body_lines = lines[body_start:]
    # Strip the 2-space indent spark adds
    body_lines = [(l[2:] if l.startswith("  ") else l) for l in body_lines]
    return "\n".join(body_lines).strip()


def markdown_to_html(md):
    """Minimal markdown -> HTML. Handles headers, bold, links, paragraphs."""
    import html as _html
    out = []
    para = []
    def flush():
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()
    for line in md.splitlines():
        s = line.rstrip()
        if not s:
            flush()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            level = len(m.group(1))
            out.append(f"<h{level}>{render_inline(m.group(2))}</h{level}>")
            continue
        para.append(render_inline(s))
    flush()
    return "\n".join(out)


def render_inline(s):
    # Links [text](url)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)
    # Bold **text** (allow loose: ** text**)
    s = re.sub(r"\*\*\s*([^*]+?)\s*\*\*", r"<strong>\1</strong>", s)
    return s


def wrap_html(body_html, parsed):
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
           color: #1d1d1f; max-width: 720px; margin: 40px auto; padding: 0 24px;
           font-size: 13px; line-height: 1.5; }
    h1 { font-size: 22px; border-bottom: 1px solid #d2d2d7; padding-bottom: 8px; }
    h2 { font-size: 16px; margin-top: 28px; }
    h3 { font-size: 14px; }
    p { margin: 6px 0; }
    a { color: #0066cc; text-decoration: none; }
    .meta { color: #6e6e73; font-size: 11px; border-top: 1px solid #d2d2d7;
            margin-top: 32px; padding-top: 12px; }
    """
    meta = (
        f"Invoice date: {parsed.get('invoice_date') or 'unknown'} · "
        f"Service: {parsed.get('service') or 'unknown'} · "
        f"Total: €{parsed.get('total_eur'):.2f}".replace(".", ",")
        if parsed.get("total_eur") is not None
        else "Invoice"
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body>
{body_html}
<div class="meta">{meta}</div>
</body></html>"""


_FILENAME_BAD = re.compile(r"[/:\x00-\x1f]")


def sanitize_filename(s):
    s = _FILENAME_BAD.sub("-", s)
    s = s.replace("  ", " ").strip()
    return s


def service_to_filename(service_key):
    """Map an internal service key to the user-facing filename fragment.
    Strips the 'App Store: ' grouping prefix so filenames read 'Apple-<App>.pdf'.
    """
    if service_key.startswith("App Store: "):
        return service_key[len("App Store: "):]
    return service_key


# ---------- Main ----------

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    c = sub.add_parser("classify")
    c.add_argument("service_key")
    c.add_argument("classification", choices=["business", "personal"])
    sub.add_parser("process")
    sub.add_parser("status")
    args = p.parse_args()

    if args.cmd == "scan":
        cmd_scan()
    elif args.cmd == "classify":
        cmd_classify(args.service_key, args.classification)
    elif args.cmd == "process":
        cmd_process()
    elif args.cmd == "status":
        cmd_status()


if __name__ == "__main__":
    main()
