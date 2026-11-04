"""Shared report filters: period presets or exact dates, hospital, status, mode, search."""
import datetime
from dataclasses import dataclass, field

from django.utils import timezone

from cases.models import PaymentStatus
from core.periods import add_months, financial_year_start, month_start
from core.permissions import selected_doctor
from contacts.models import Surgeon
from hospitals.models import Hospital
from payments.models import Payment

PERIODS = [
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("last_3", "Last 3 months"),
    ("this_fy", "This FY (Apr-Mar)"),
    ("last_fy", "Last FY"),
    ("last_12", "Last 12 months"),
    ("all", "All time"),
    ("custom", "Custom dates"),
]
PERIOD_LABELS = dict(PERIODS)

STATUS_CHOICES = [("unpaid", "Not fully paid")] + PaymentStatus.CHOICES


def _parse_date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_month(value):
    try:
        return datetime.datetime.strptime(value, "%Y-%m").date()
    except (TypeError, ValueError):
        return None


def period_dates(period, today):
    """(start, end) for a preset; start None means no lower bound."""
    this_month = month_start(today)
    if period == "this_month":
        return this_month, today
    if period == "last_month":
        start = add_months(this_month, -1)
        return start, this_month - datetime.timedelta(days=1)
    if period == "last_3":
        return add_months(this_month, -2), today
    if period == "this_fy":
        return financial_year_start(today), today
    if period == "last_fy":
        fy = financial_year_start(today)
        return datetime.date(fy.year - 1, 4, 1), fy - datetime.timedelta(days=1)
    if period == "last_12":
        return add_months(this_month, -11), today
    return None, today  # all


@dataclass
class ReportFilters:
    period: str
    start: datetime.date | None
    end: datetime.date
    hospital: Hospital | None = None
    surgeon: object = None
    status: str = ""
    mode: str = ""
    q: str = ""
    doctor: object = None
    notes: list = field(default_factory=list)

    @property
    def label(self):
        if self.period != "custom":
            text = PERIOD_LABELS[self.period]
            if self.start:
                text += f" ({self.start:%d %b %Y} - {self.end:%d %b %Y})"
            return text
        return f"{self.start:%d %b %Y} - {self.end:%d %b %Y}" if self.start else f"Up to {self.end:%d %b %Y}"

    def describe(self):
        """Human readable summary for export headers."""
        parts = [f"Period: {self.label}"]
        if self.doctor:
            parts.append(f"Anaesthetist: {self.doctor}")
        if self.hospital:
            parts.append(f"Hospital: {self.hospital.name}")
        if self.surgeon:
            parts.append(f"Surgeon: {self.surgeon}")
        if self.status:
            parts.append(f"Status: {dict(STATUS_CHOICES).get(self.status, self.status)}")
        if self.mode:
            parts.append(f"Mode: {dict(Payment.MODE_CHOICES).get(self.mode, self.mode)}")
        if self.q:
            parts.append(f'Search: "{self.q}"')
        return " | ".join(parts)

    def date_filter(self, field_name):
        kwargs = {f"{field_name}__lte": self.end}
        if self.start:
            kwargs[f"{field_name}__gte"] = self.start
        return kwargs


def parse_filters(request, default_period="this_month"):
    params = request.GET
    today = timezone.localdate()
    period = params.get("period") or default_period
    if period not in PERIOD_LABELS:
        period = default_period

    start, end = _parse_date(params.get("start")), _parse_date(params.get("end"))
    # Older links used ?from=YYYY-MM&to=YYYY-MM
    if not (start or end) and (params.get("from") or params.get("to")):
        f, t = _parse_month(params.get("from")), _parse_month(params.get("to"))
        start = f
        end = add_months(t, 1) - datetime.timedelta(days=1) if t else None
    if period == "custom" or start or end:
        period = "custom"
        end = min(end or today, today) if end else today
        if start and start > end:
            start, end = end, start
    else:
        start, end = period_dates(period, today)

    hospital = None
    if params.get("hospital", "").isdigit():
        hospital = Hospital.objects.filter(pk=params["hospital"]).first()
    surgeon = None
    if params.get("surgeon", "").isdigit():
        surgeon = Surgeon.objects.for_user(request.user).filter(pk=params["surgeon"]).first()
    status = params.get("status", "")
    if status not in dict(STATUS_CHOICES):
        status = ""
    mode = params.get("mode", "")
    if mode not in dict(Payment.MODE_CHOICES):
        mode = ""
    return ReportFilters(
        period=period, start=start, end=end, hospital=hospital, surgeon=surgeon, status=status, mode=mode,
        q=params.get("q", "").strip()[:100], doctor=selected_doctor(request),
    )


def apply_case_status(qs, status):
    """qs must be annotated with CaseQuerySet.with_totals()."""
    if status == "unpaid":
        return qs.filter(is_open=True)
    if status:
        return qs.filter(status=status)
    return qs
