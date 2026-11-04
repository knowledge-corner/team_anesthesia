from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from cases.models import Case
from cases.views import get_case_for_user
from contacts.services import attach_call_targets
from core.permissions import selected_doctor, visible_doctors

from . import services
from .forms import PaymentForm, followup_form
from .models import Payment, PaymentFollowUp


def _next_url(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return default


def received_by_suggestions(user):
    """Names used before in 'Received by' (most recent first) for quick picking."""
    names = (Payment.objects.filter(case__in=Case.objects.for_user(user)).exclude(received_by="")
             .order_by("-payment_date", "-id").values_list("received_by", flat=True)[:200])
    return list(dict.fromkeys(names))[:15]


@login_required
def record_payment(request, case_pk=None):
    """Record a payment - either against a chosen case or picked from the unpaid list."""
    fixed_case = get_case_for_user(request, case_pk) if case_pk else None
    unpaid = (
        Case.objects.for_user(request.user).outstanding()
        .select_related("hospital").order_by("case_date")
    )
    initial = {}
    if fixed_case is not None:
        fixed = Case.objects.with_totals().get(pk=fixed_case.pk)
        initial["amount"] = fixed.outstanding if fixed.outstanding > 0 else None
    form = PaymentForm(
        request.POST or None, initial=initial,
        case_queryset=unpaid, fixed_case=fixed_case,
    )
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        if fixed_case is not None:
            payment.case = fixed_case
        payment.created_by = request.user
        fee_changed = form.save_fee(payment.case)
        payment.save()
        messages.success(request, f"Payment of {payment.amount:,.0f} recorded."
                                  + (f" Case fee set to {payment.case.fee:,.0f}." if fee_changed else ""))
        return redirect(_next_url(request, reverse("cases:detail", args=[payment.case_id])))
    return render(request, "payments/payment_form.html", {
        "form": form, "case": fixed_case, "unpaid_count": unpaid.count(), "next": _next_url(request, ""),
        "received_by_suggestions": received_by_suggestions(request.user),
    })


def _get_payment(request, pk):
    # Payments are shared by the practice like their cases.
    return get_object_or_404(Payment.objects.select_related("case__doctor", "case__hospital"), pk=pk)


@login_required
def edit_payment(request, pk):
    payment = _get_payment(request, pk)
    form = PaymentForm(request.POST or None, instance=payment, fixed_case=payment.case)
    if request.method == "POST":
        if "delete" in request.POST:
            case = payment.case
            payment.delete()
            messages.success(request, "Payment deleted.")
            return redirect(case)
        if form.is_valid():
            form.save_fee(payment.case)
            form.save()
            messages.success(request, "Payment updated.")
            return redirect(payment.case)
    return render(request, "payments/payment_form.html", {
        "form": form, "case": payment.case, "payment": payment,
        "received_by_suggestions": received_by_suggestions(request.user),
    })


# --- Follow-ups --------------------------------------------------------------

@login_required
def add_followup(request, case_pk):
    case = get_case_for_user(request, case_pk)
    attach_call_targets([case])
    initial = {"contact": case.call.contact_id} if case.call and case.call.contact_id else {}
    form = followup_form(case, request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        followup = form.save(commit=False)
        followup.case = case
        followup.contact_person = followup.contact.name if followup.contact_id else ""
        followup.created_by = request.user
        followup.save()
        services.apply_followup(followup)
        messages.success(request, "Follow-up recorded.")
        return redirect(_next_url(request, reverse("cases:detail", args=[case.pk])))
    return render(request, "payments/followup_form.html", {"form": form, "case": case, "next": _next_url(request, "")})


@login_required
@require_POST
def quick_followed_up(request, case_pk):
    """One-tap 'Followed up' from the receivables list (phone call, today)."""
    case = get_case_for_user(request, case_pk)
    attach_call_targets([case])
    followup = PaymentFollowUp.objects.create(
        case=case, method=request.POST.get("method", "call"),
        contact_id=case.call.contact_id if case.call else None,
        contact_person=case.call.name if case.call and case.call.contact_id else "",
        created_by=request.user, notes="Marked as followed up from receivables list.",
    )
    services.apply_followup(followup)
    messages.success(request, f"Marked {case.hospital} as followed up today.")
    return redirect(_next_url(request, reverse("receivables:list")))


@login_required
@require_POST
def snooze_followup(request, case_pk):
    case = get_case_for_user(request, case_pk)
    try:
        days = max(1, min(int(request.POST.get("days", 3)), 90))
    except ValueError:
        days = 3
    services.snooze(case, days)
    messages.info(request, f"You will be reminded about {case.hospital} on "
                           f"{case.followup_snoozed_until:%d %b %Y}.")
    return redirect(_next_url(request, reverse("receivables:list")))


# --- Receivables -------------------------------------------------------------

SORTS = {
    "oldest": ("Oldest first", lambda c: (c.case_date, c.pk)),
    "amount": ("Highest amount", lambda c: (-c.outstanding, c.case_date)),
    "hospital": ("Hospital", lambda c: (c.hospital.name.lower(), c.case_date)),
}


@login_required
def receivables(request):
    cases = services.receivables_for(request.user)
    doctor = selected_doctor(request)
    if doctor:
        cases = [c for c in cases if c.doctor_id == doctor.pk]

    summary = {
        "total": sum(c.outstanding for c in cases),
        "overdue": sum(c.outstanding for c in cases if c.status == "overdue"),
        "overdue_count": sum(1 for c in cases if c.status == "overdue"),
        "followup_count": sum(1 for c in cases if c.reminder.due),
        "pending_count": sum(1 for c in cases if c.status != "overdue"),
        "count": len(cases),
    }
    buckets = [("0-30 days", 0, 30), ("31-60 days", 31, 60), ("61-90 days", 61, 90), ("90+ days", 91, 10**6)]
    ageing = [
        {"label": label, "amount": sum(c.outstanding for c in cases if lo <= c.age_days <= hi),
         "count": sum(1 for c in cases if lo <= c.age_days <= hi)}
        for label, lo, hi in buckets
    ]

    view = request.GET.get("view", "all")
    if view == "overdue":
        cases = [c for c in cases if c.status == "overdue"]
    elif view == "pending":
        cases = [c for c in cases if c.status != "overdue"]
    elif view == "followup":
        cases = [c for c in cases if c.reminder.due]
    elif view == "snoozed":
        cases = [c for c in cases if c.reminder.snoozed_until]
    hospital = request.GET.get("hospital", "")
    if hospital.isdigit():
        cases = [c for c in cases if c.hospital_id == int(hospital)]

    sort = request.GET.get("sort", "oldest")
    if sort not in SORTS:
        sort = "oldest"
    cases.sort(key=SORTS[sort][1])
    attach_call_targets(cases)

    return render(request, "payments/receivables.html", {
        "cases": cases, "summary": summary, "ageing": ageing, "view": view, "sort": sort,
        "sorts": [(k, v[0]) for k, v in SORTS.items()], "hospital": hospital,
        "doctors": visible_doctors(request.user), "selected_doctor": doctor,
    })
