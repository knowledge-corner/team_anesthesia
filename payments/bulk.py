"""Bulk payment: tick many unpaid cases at once, or fill a CSV and upload it.

Tick cases  - only cases with a fee and nothing paid yet; the fee is recorded as paid.
CSV upload  - the amount typed is recorded as is: less than due -> partly paid,
              no fee yet -> the amount becomes the fee, more than the fee -> the fee goes up.
Nothing from a file is saved until the doctor has checked the summary.
"""
import csv
import datetime
import io
from dataclasses import asdict, dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from core.templatetags.money import inr
from cases.importer import parse_amount, parse_date, parse_mode
from cases.models import Case

from .models import Payment

CSV_COLUMNS = [
    "Case ID", "Case date", "Hospital", "Patient", "Surgeon", "Procedure", "Anaesthetist",
    "Fee", "Paid so far", "Due",
    "Amount received", "Payment date", "Mode", "Reference no", "Received by", "Notes",
]
FILL_COLUMNS = CSV_COLUMNS[CSV_COLUMNS.index("Amount received"):]
HEADER_KEYS = {
    "caseid": "case_id", "id": "case_id",
    "amountreceived": "amount", "amount": "amount", "received": "amount",
    "paymentdate": "payment_date", "date": "payment_date",
    "mode": "mode", "paymentmode": "mode",
    "referenceno": "reference_no", "reference": "reference_no", "ref": "reference_no",
    "receivedby": "received_by", "notes": "notes",
}
MAX_ROWS = 2000


def _key(text):
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _num(value):
    value = Decimal(value or 0)
    return value.quantize(1) if value == value.to_integral() else value


# --- Tick cases ---------------------------------------------------------------

def tickable(case):
    """A fee is set and nothing has been paid yet: ticking records the fee."""
    return case.fee > 0 and case.total_paid <= 0


@transaction.atomic
def record_ticked(cases, payment_date, mode, reference_no, received_by, notes, user):
    """One payment per case for its full fee. Returns the payments created."""
    created = []
    for case in cases:
        if not tickable(case):
            continue
        created.append(Payment.objects.create(
            case_id=case.pk, amount=case.fee, payment_date=payment_date, mode=mode,
            reference_no=reference_no, received_by=received_by, notes=notes, created_by=user,
        ))
    return created


# --- CSV download ---------------------------------------------------------------

def build_csv(cases):
    out = io.StringIO()
    out.write("﻿")  # so Excel opens ₹ and names correctly
    w = csv.writer(out)
    w.writerow(CSV_COLUMNS)
    for c in cases:
        w.writerow([
            c.pk, c.case_date.strftime("%d/%m/%Y"), c.hospital.name, c.patient_name,
            c.surgeon.name if c.surgeon_id else "", c.procedure_type, str(c.doctor),
            _num(c.fee) if c.fee > 0 else "TBD", _num(c.total_paid), _num(c.outstanding) if c.fee > 0 else "TBD",
            "", "", "", "", "", "",
        ])
    return out.getvalue()


# --- CSV / Excel upload ---------------------------------------------------------------

@dataclass
class UploadRow:
    line: int
    case_id: int | None = None
    hospital: str = ""
    case_date: str = ""
    patient: str = ""
    amount: str = ""
    payment_date: str = ""
    payment_label: str = ""
    mode: str = "bank"
    mode_label: str = ""
    reference_no: str = ""
    received_by: str = ""
    notes: str = ""
    result: str = ""       # Full payment / Partly paid / Fee set to ... / Fee raised to ...
    error: str = ""


def _read_rows(uploaded_file):
    name = (uploaded_file.name or "").lower()
    data = uploaded_file.read()
    if name.endswith((".xlsx", ".xlsm")):
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def parse_upload(uploaded_file):
    """Read a filled-in file. Returns (rows, error). Rows with no amount are skipped."""
    try:
        raw = _read_rows(uploaded_file)
    except Exception:
        return [], "This file could not be read. Upload the CSV you downloaded (or an Excel .xlsx file)."
    header_idx, mapping = None, {}
    for i, row in enumerate(raw[:10]):
        m = {}
        for col, cell in enumerate(row):
            field = HEADER_KEYS.get(_key(cell))
            if field and field not in m:
                m[field] = col
        if {"case_id", "amount"} <= set(m):
            header_idx, mapping = i, m
            break
    if header_idx is None:
        return [], "Columns 'Case ID' and 'Amount received' were not found. Please use the downloaded CSV."

    def cell(row, field):
        col = mapping.get(field)
        if col is None or col >= len(row):
            return None
        value = row[col]
        return value.strip() if isinstance(value, str) else value

    rows, seen = [], {}
    today = timezone.localdate()
    for offset, row in enumerate(raw[header_idx + 1:header_idx + 1 + MAX_ROWS], start=header_idx + 2):
        amount_raw = cell(row, "amount")
        if amount_raw in (None, ""):
            continue
        r = UploadRow(line=offset)
        try:
            amount = parse_amount(amount_raw)
        except ValueError as e:
            r.error = str(e)
            amount = None
        if amount is not None and amount <= 0 and not r.error:
            r.error = "Amount must be more than 0"
        cid = cell(row, "case_id")
        try:
            r.case_id = int(float(str(cid).strip()))
        except (TypeError, ValueError):
            r.error = r.error or "Case ID is missing"
        try:
            pdate = parse_date(cell(row, "payment_date")) or today
            if pdate > today:
                r.error = r.error or "Payment date is in the future"
        except ValueError as e:
            pdate = today
            r.error = r.error or str(e)
        r.amount = str(amount) if amount is not None else str(amount_raw)
        r.payment_date = pdate.isoformat()
        r.payment_label = pdate.strftime("%d %b %Y")
        r.mode = parse_mode(cell(row, "mode"))
        r.mode_label = dict(Payment.MODE_CHOICES)[r.mode]
        r.reference_no = str(cell(row, "reference_no") or "")[:100]
        r.received_by = str(cell(row, "received_by") or "")[:100]
        r.notes = str(cell(row, "notes") or "")
        if r.case_id in seen and not r.error:
            r.error = f"Case {r.case_id} is also on line {seen[r.case_id]}"
        if r.case_id is not None:
            seen.setdefault(r.case_id, r.line)
        rows.append(r)

    cases = {c.pk: c for c in Case.objects.with_totals().select_related("hospital")
             .filter(pk__in=[r.case_id for r in rows if r.case_id])}
    for r in rows:
        case = cases.get(r.case_id)
        if case is None:
            r.error = r.error or f"No case with ID {r.case_id}"
            continue
        r.hospital, r.patient = case.hospital.name, case.patient_name
        r.case_date = case.case_date.strftime("%d %b %Y")
        if r.error:
            continue
        r.result = describe(case, Decimal(r.amount))
    return rows, ""


def describe(case, amount):
    """What recording `amount` will do to the case, in words."""
    total = case.total_paid + amount
    if case.fee <= 0:
        return f"Fee set to {inr(total)}"
    if total > case.fee:
        return f"Paid · fee raised to {inr(total)}"
    if total == case.fee:
        return "Paid in full"
    return f"Partly paid · {inr(case.fee - total)} still due"


def rows_to_json(rows):
    return [asdict(r) for r in rows if not r.error]


@transaction.atomic
def commit_upload(rows, user):
    """Record the checked rows. Fee rule as in Record payment: no fee or more received -> fee = total."""
    created = []
    for r in rows:
        case = Case.objects.with_totals().filter(pk=r["case_id"]).first()
        if case is None:
            continue
        amount = Decimal(r["amount"])
        total = case.total_paid + amount
        if case.fee <= 0 or total > case.fee:
            Case.objects.filter(pk=case.pk).update(fee=total, updated_at=timezone.now())
        created.append(Payment.objects.create(
            case_id=case.pk, amount=amount, payment_date=datetime.date.fromisoformat(r["payment_date"]),
            mode=r["mode"], reference_no=r["reference_no"], received_by=r["received_by"],
            notes=r["notes"], created_by=user,
        ))
    return created
