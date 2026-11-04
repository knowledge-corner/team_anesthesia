import datetime
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Case as DbCase
from django.db.models import BooleanField, DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from core.models import AppSettings, ImportableModel

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=12, decimal_places=2)


class PaymentStatus:
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    CHOICES = [
        (PENDING, "Pending"),
        (PARTIAL, "Partially Paid"),
        (PAID, "Paid"),
        (OVERDUE, "Overdue"),
    ]
    LABELS = dict(CHOICES)
    BADGES = {PENDING: "secondary", PARTIAL: "info", PAID: "success", OVERDUE: "danger"}


def compute_status(fee, total_paid, due_date, today=None):
    """Single source of truth for status (mirrored by CaseQuerySet.with_totals).

    A fee of 0 with nothing received means "fee to be decided" (entered when the payment
    comes in): the case stays open - pending, or overdue after its expected payment date.
    """
    today = today or timezone.localdate()
    if fee <= 0 and total_paid <= 0:
        return PaymentStatus.OVERDUE if due_date and due_date < today else PaymentStatus.PENDING
    if fee - total_paid <= 0:
        return PaymentStatus.PAID
    if due_date and due_date < today:
        return PaymentStatus.OVERDUE
    if total_paid > 0:
        return PaymentStatus.PARTIAL
    return PaymentStatus.PENDING


def default_due_date(case_date):
    return case_date + datetime.timedelta(days=AppSettings.load().default_payment_terms_days)


class CaseQuerySet(models.QuerySet):
    def for_user(self, user):
        """Organisation-level data: every signed-in user sees every case of the practice."""
        return self if user.is_authenticated else self.none()

    def with_totals(self, today=None):
        from payments.models import Payment

        today = today or timezone.localdate()
        paid_sq = (
            Payment.objects.filter(case=OuterRef("pk"))
            .order_by()
            .values("case")
            .annotate(total=Sum("amount"))
            .values("total")
        )
        return self.annotate(
            total_paid=Coalesce(Subquery(paid_sq, output_field=MONEY), Value(ZERO), output_field=MONEY),
        ).annotate(
            outstanding=ExpressionWrapper(F("fee") - F("total_paid"), output_field=MONEY),
        ).annotate(
            # Still to be collected: money outstanding, or the fee is not decided yet.
            is_open=ExpressionWrapper(Q(outstanding__gt=0) | Q(fee__lte=0, total_paid__lte=0), output_field=BooleanField()),
        ).annotate(
            status=DbCase(
                When(fee__lte=0, total_paid__lte=0, due_date__lt=today, then=Value(PaymentStatus.OVERDUE)),
                When(fee__lte=0, total_paid__lte=0, then=Value(PaymentStatus.PENDING)),
                When(outstanding__lte=0, then=Value(PaymentStatus.PAID)),
                When(due_date__lt=today, then=Value(PaymentStatus.OVERDUE)),
                When(total_paid__gt=0, then=Value(PaymentStatus.PARTIAL)),
                default=Value(PaymentStatus.PENDING),
                output_field=models.CharField(),
            )
        )

    def with_last_followup(self):
        from payments.models import PaymentFollowUp

        last_sq = (
            PaymentFollowUp.objects.filter(case=OuterRef("pk"))
            .order_by("-followup_date")
            .values("followup_date")[:1]
        )
        return self.annotate(last_followup_date=Subquery(last_sq, output_field=models.DateField()))

    def outstanding(self):
        """Cases still to be collected (including cases whose fee is not decided yet)."""
        return self.with_totals().filter(is_open=True)


class Case(ImportableModel):
    """A completed piece of anaesthesia work that is billable. Not a clinical record."""

    doctor = models.ForeignKey("accounts.Doctor", on_delete=models.PROTECT, related_name="cases")
    hospital = models.ForeignKey("hospitals.Hospital", on_delete=models.PROTECT, related_name="cases")
    case_date = models.DateField(default=timezone.localdate, db_index=True)
    patient_reference = models.CharField(
        "Case / patient ref", max_length=100, blank=True,
        help_text="IP number, initials or bill number - no clinical details needed.",
    )
    patient_name = models.CharField(max_length=150, blank=True)
    surgeon = models.ForeignKey("contacts.Surgeon", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="cases")
    contact = models.ForeignKey("contacts.Contact", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="cases", help_text="Person to contact about this payment.")
    procedure_type = models.CharField("Procedure / case type", max_length=150, blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
                              help_text="0 = not decided yet; enter it when the payment comes in.")
    due_date = models.DateField(
        "Expected payment date", null=True, blank=True, db_index=True,
        help_text="If left empty, it is set to the default payment period (30 days) after the case date.",
    )
    notes = models.TextField(blank=True)
    followup_snoozed_until = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = CaseQuerySet.as_manager()

    class Meta:
        ordering = ["-case_date", "-id"]
        indexes = [models.Index(fields=["doctor", "case_date"])]

    def __str__(self):
        ref = f" ({self.patient_reference})" if self.patient_reference else ""
        return f"{self.hospital} - {self.case_date:%d %b %Y}{ref}"

    def get_absolute_url(self):
        return reverse("cases:detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.due_date and self.case_date:
            self.due_date = default_due_date(self.case_date)
        super().save(*args, **kwargs)

    # --- Python-side helpers (used when the queryset was not annotated) ---
    @property
    def amount_paid(self):
        if hasattr(self, "total_paid"):
            return self.total_paid
        return self.payments.aggregate(t=Coalesce(Sum("amount"), Value(ZERO), output_field=MONEY))["t"]

    @property
    def balance(self):
        if hasattr(self, "outstanding"):
            return self.outstanding
        return self.fee - self.amount_paid

    @property
    def fee_to_be_decided(self):
        return self.fee <= 0 and self.amount_paid <= 0

    @property
    def open_case(self):
        """Still to be collected (works with or without with_totals())."""
        if hasattr(self, "is_open"):
            return bool(self.is_open)
        return self.balance > 0 or self.fee_to_be_decided

    @property
    def payment_status(self):
        if hasattr(self, "status"):
            return self.status
        return compute_status(self.fee, self.amount_paid, self.due_date)

    @property
    def payment_status_label(self):
        return PaymentStatus.LABELS[self.payment_status]

    @property
    def payment_status_badge(self):
        return PaymentStatus.BADGES[self.payment_status]

    @property
    def age_days(self):
        return (timezone.localdate() - self.case_date).days

    @property
    def days_overdue(self):
        if not self.due_date:
            return 0
        return max((timezone.localdate() - self.due_date).days, 0)
