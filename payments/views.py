import datetime
from decimal import Decimal

from django.contrib import messages
from django.core import signing
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from cases.models import Case
from cases.views import get_case_for_user
from contacts.services import attach_call_targets
from core.permissions import selected_doctor, visible_doctors

from core.templatetags.money import inr

from . import bulk, recent, services
from .forms import BulkPaymentForm, BulkUploadForm, PaymentForm, followup_form
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
        recent.mark_paid(request, [payment.case_id])
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
            fee_changed = form.save_fee(payment.case)
            form.save()
            recent.mark_paid(request, [payment.case_id])
            messages.success(request, "Payment updated."
                                      + (f" Case fee set to {payment.case.fee:,.0f}." if fee_changed else ""))
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
    # Paid a moment ago (e.g. with the Paid button here): keep it in the list, marked Paid.
    shown = {c.pk for c in cases}
    paid_now = [pk for pk in recent.just_paid_ids(request) if pk not in shown]
    if paid_now:
        extra = Case.objects.for_user(request.user).with_totals().filter(pk__in=paid_now, is_open=False)
        if doctor:
            extra = extra.filter(doctor=doctor)
        if hospital.isdigit():
            extra = extra.filter(hospital_id=hospital)
        for c in extra.select_related("hospital", "doctor", "surgeon"):
            c.just_paid = True
            cases.insert(0, c)
    attach_call_targets(cases)

    return render(request, "payments/receivables.html", {
        "cases": cases, "summary": summary, "ageing": ageing, "view": view, "sort": sort,
        "sorts": [(k, v[0]) for k, v in SORTS.items()], "hospital": hospital,
        "doctors": visible_doctors(request.user), "selected_doctor": doctor,
    })


# --- Bulk payment ------------------------------------------------------------

def _bulk_context(request):
    from cases.views import filter_cases
    qs, ctx = filter_cases(request)
    just_paid = recent.just_paid_ids(request)
    cases = list(qs.filter(Q(is_open=True) | Q(pk__in=just_paid)).order_by("case_date", "id"))
    for c in cases:
        c.just_paid = c.pk in just_paid and not c.is_open
        c.tickable = bulk.tickable(c) and not c.just_paid
    ctx["cases"] = cases
    ctx["open_cases"] = [c for c in cases if not c.just_paid]
    ctx["tickable_count"] = sum(c.tickable for c in cases)
    parts = []
    if ctx["selected_doctor"]:
        parts.append(str(ctx["selected_doctor"]))
    if ctx["selected_hospital"]:
        parts.append(ctx["selected_hospital"].name)
    if ctx["selected_surgeon"]:
        parts.append(ctx["selected_surgeon"].name)
    if ctx["month"]:
        try:
            parts.append(datetime.date.fromisoformat(ctx["month"] + "-01").strftime("%b %Y"))
        except ValueError:
            pass
    ctx["filter_label"] = " · ".join(parts) or "All hospitals and anaesthetists"
    return ctx


@login_required
def bulk_payment(request):
    """Tick cases (phone) or CSV download / upload (laptop) for the cases filtered on the Cases list."""
    ctx = _bulk_context(request)
    form = BulkPaymentForm(request.POST or None)
    if request.method == "POST" and request.POST.get("action") == "tick":
        ids = {int(x) for x in request.POST.getlist("case") if x.isdigit()}
        chosen = [c for c in ctx["cases"] if c.pk in ids]
        if not chosen:
            messages.error(request, "Tick at least one case.")
        elif form.is_valid():
            d = form.cleaned_data
            created = bulk.record_ticked(chosen, d["payment_date"], d["mode"], d["reference_no"],
                                         d["received_by"], d["notes"], request.user)
            recent.mark_paid(request, [p.case_id for p in created])
            total = sum(p.amount for p in created)
            messages.success(request, f"{len(created)} payment{'s' if len(created) != 1 else ''} recorded "
                                      f"· {inr(total)}.")
            return redirect(reverse("payments:bulk") + (f"?{ctx['filter_query']}" if ctx["filter_query"] else ""))
        ctx["ticked"] = ids
    ctx.update({"form": form, "upload_form": BulkUploadForm(),
                "received_by_suggestions": received_by_suggestions(request.user)})
    return render(request, "payments/bulk.html", ctx)


@login_required
def bulk_csv(request):
    ctx = _bulk_context(request)
    response = HttpResponse(bulk.build_csv(ctx["open_cases"]), content_type="text/csv; charset=utf-8")
    name = slugify(ctx["selected_hospital"].name) if ctx["selected_hospital"] else "pending"
    response["Content-Disposition"] = (f'attachment; filename="bulk-payment-{name}-'
                                       f'{timezone.localdate():%Y-%m-%d}.csv"')
    return response


@login_required
@require_POST
def bulk_upload(request):
    back = reverse("payments:bulk") + (f"?{request.POST.get('filter_query')}" if request.POST.get("filter_query") else "")
    if request.POST.get("action") == "confirm":
        try:
            rows = signing.loads(request.POST.get("rows", ""), salt="bulk-payment", max_age=6 * 3600)
        except signing.BadSignature:
            messages.error(request, "This summary has expired. Please upload the file again.")
            return redirect(back)
        pending = request.session.get("bulk_review")
        if not pending or pending.get("done"):
            messages.info(request, "These payments were already recorded.")
            return redirect(back)
        created = bulk.commit_upload(rows, request.user)
        pending["done"] = True
        request.session["bulk_review"] = pending
        recent.mark_paid(request, [p.case_id for p in created])
        total = sum(p.amount for p in created)
        messages.success(request, f"{len(created)} payment{'s' if len(created) != 1 else ''} recorded from the file "
                                  f"· {inr(total)}.")
        return redirect(back)
    form = BulkUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose the filled-in CSV file first.")
        return redirect(back + ("&" if "?" in back else "?") + "tab=csv")
    rows, error = bulk.parse_upload(form.cleaned_data["file"])
    if error or not rows:
        messages.error(request, error or "No amounts found in the file. Fill the 'Amount received' column.")
        return redirect(back + ("&" if "?" in back else "?") + "tab=csv")
    from dataclasses import asdict
    request.session["bulk_review"] = {
        "rows": [asdict(r) for r in rows], "filename": form.cleaned_data["file"].name,
        "filter_query": request.POST.get("filter_query", ""),
    }
    return redirect("payments:bulk_review")


@login_required
def bulk_review(request):
    """'Check before saving' for an uploaded file (a normal page, so Back works)."""
    data = request.session.get("bulk_review")
    if not data:
        return redirect("payments:bulk")
    if data.get("done"):
        fq = data["filter_query"]
        return render(request, "payments/bulk_review.html", {
            "done": True, "rows": [], "filename": data["filename"], "filter_query": fq,
            "back": reverse("payments:bulk") + (f"?{fq}" if fq else ""),
        })
    rows = data["rows"]
    good = [r for r in rows if not r["error"]]
    fq = data["filter_query"]
    back = reverse("payments:bulk") + (f"?{fq}" if fq else "")
    return render(request, "payments/bulk_review.html", {
        "rows": rows, "good_count": len(good), "error_count": len(rows) - len(good),
        "total": sum(Decimal(r["amount"]) for r in good),
        "signed_rows": signing.dumps(good, salt="bulk-payment", compress=True),
        "filter_query": fq, "back": back, "filename": data["filename"],
    })
