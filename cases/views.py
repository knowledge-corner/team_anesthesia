from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from contacts.services import attach_call_targets
from core.models import AppSettings
from core.permissions import require_doctor_profile, scoped_cases, selected_doctor, visible_doctors
from contacts.models import Surgeon
from hospitals.models import Hospital
from payments.models import Payment
from payments.services import reminder_state

from . import importer
from .forms import COMMON_PROCEDURES, CaseForm, CaseImportForm
from .models import Case, PaymentStatus


def procedure_suggestions(user):
    recent = (
        Case.objects.for_user(user).exclude(procedure_type="")
        .order_by("-case_date").values_list("procedure_type", flat=True)[:200]
    )
    seen, result = set(), []
    for name in list(recent) + COMMON_PROCEDURES:
        if name.lower() not in seen:
            seen.add(name.lower())
            result.append(name)
    return result[:25]


def get_case_for_user(request, pk):
    # Cases are shared by the practice: every signed-in user can open, edit and delete them.
    return get_object_or_404(Case.objects.select_related("hospital", "doctor"), pk=pk)


@login_required
def case_list(request):
    qs = scoped_cases(request).with_totals().select_related("hospital", "doctor")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    hospital = request.GET.get("hospital", "")
    month = request.GET.get("month", "")  # YYYY-MM
    if q:
        qs = qs.filter(
            Q(patient_reference__icontains=q) | Q(patient_name__icontains=q) | Q(procedure_type__icontains=q)
            | Q(hospital__name__icontains=q) | Q(surgeon__name__icontains=q) | Q(notes__icontains=q)
        )
    if status in PaymentStatus.LABELS:
        qs = qs.filter(status=status)
    elif status == "unpaid":
        qs = qs.filter(is_open=True)
    if hospital.isdigit():
        qs = qs.filter(hospital_id=hospital)
    surgeon = request.GET.get("surgeon", "")
    if surgeon.isdigit():
        qs = qs.filter(surgeon_id=surgeon)
    if len(month) == 7 and month[4] == "-":
        try:
            qs = qs.filter(case_date__year=int(month[:4]), case_date__month=int(month[5:]))
        except ValueError:
            pass
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    context = {
        "page": page,
        "q": q,
        "status": status,
        "hospital": hospital,
        "month": month,
        "status_choices": PaymentStatus.CHOICES,
        "selected_hospital": Hospital.objects.filter(pk=hospital).first() if hospital.isdigit() else None,
        "surgeons": Surgeon.objects.for_user(request.user),
        "surgeon": surgeon,
        "doctors": visible_doctors(request.user),
        "selected_doctor": selected_doctor(request),
    }
    return render(request, "cases/case_list.html", context)


@require_doctor_profile
def case_add(request):
    user = request.user
    initial = {}
    hospital_id = request.GET.get("hospital")
    if hospital_id and hospital_id.isdigit():
        initial["hospital"] = hospital_id
    if request.GET.get("date"):
        initial["case_date"] = request.GET["date"]
    # Anaesthetist: empty = Self; "Save & add" keeps a colleague chosen for the previous case.
    if str(request.GET.get("doctor", "")).isdigit():
        initial["doctor"] = request.GET["doctor"]

    form = CaseForm(request.POST or None, user=user, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            case = form.save(commit=False)
            case.created_by = user
            auto_due = not case.due_date
            case.save()
            form.save_contact(case)
            if form.cleaned_data.get("paid_now"):
                payment = Payment(
                    case=case,
                    amount=form.cleaned_data["paid_amount"],
                    payment_date=case.case_date,
                    mode=form.cleaned_data.get("paid_mode") or "upi",
                    created_by=user,
                )
                payment.save()
        messages.success(request, f"Case saved: {case.hospital} - "
                                  + (f"{case.fee:.0f}" if case.fee > 0 else "fee to be decided (enter it on Record payment)"))
        if auto_due:
            messages.info(request, f"Expected payment date set to {case.due_date:%d %b %Y} "
                                   f"({AppSettings.load().default_payment_terms_days} days). Edit the case to change it.")
        if "save_add" in request.POST:
            url = f"{reverse('cases:add')}?hospital={case.hospital_id}&date={case.case_date:%Y-%m-%d}"
            if case.doctor != user.doctor_profile:
                url += f"&doctor={case.doctor_id}"
            return redirect(url)
        return redirect("dashboard:home")
    return render(request, "cases/case_form.html", {
        "form": form, "procedures": procedure_suggestions(user), "is_new": True,
        "default_days": AppSettings.load().default_payment_terms_days,
    })


@login_required
def case_edit(request, pk):
    case = get_case_for_user(request, pk)
    form = CaseForm(request.POST or None, instance=case, user=request.user)
    if request.method == "POST" and form.is_valid():
        case = form.save()
        form.save_contact(case)
        messages.success(request, "Case updated.")
        return redirect(case)
    return render(request, "cases/case_form.html", {
        "form": form, "case": case, "procedures": procedure_suggestions(request.user), "is_new": False,
        "default_days": AppSettings.load().default_payment_terms_days,
    })


@login_required
def case_detail(request, pk):
    get_case_for_user(request, pk)
    case = (
        Case.objects.with_totals().with_last_followup()
        .select_related("hospital", "doctor", "surgeon", "contact").get(pk=pk)
    )
    attach_call_targets([case])
    context = {
        "case": case,
        "payments": case.payments.all(),
        "followups": case.followups.select_related("contact"),
        "reminder": reminder_state(case) if case.open_case else None,
    }
    return render(request, "cases/case_detail.html", context)


@login_required
def case_delete(request, pk):
    case = get_case_for_user(request, pk)
    if request.method == "POST":
        case.delete()
        messages.success(request, "Case deleted.")
        return redirect("cases:list")
    return render(request, "cases/case_confirm_delete.html", {"case": case})


# --- Excel import ------------------------------------------------------------


@require_doctor_profile
def import_template(request):
    content = importer.build_template()
    response = HttpResponse(
        content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="cases_import_template.xlsx"'
    return response


@require_doctor_profile
def import_cases(request):
    """Bulk upload: valid file -> saved at once; any problem -> nothing saved, rows highlighted."""
    form = CaseImportForm(request.POST or None, request.FILES or None, user=request.user)
    context = {"form": form}
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        result = importer.parse_workbook(upload, request.user, default_doctor=form.cleaned_data.get("doctor") or request.user.doctor_profile)
        if result.fatal and not result.rows:
            messages.error(request, result.fatal)
        elif result.fatal or any(r.errors for r in result.rows):
            columns = [(key, header) for key, header in importer.COLUMN_HEADERS if key in result.columns]
            context.update({
                "result": result, "counts": result.counts(), "columns": columns, "filename": upload.name,
                "error_rows": [r for r in result.rows if r.errors],
            })
        else:
            rows = importer.serialise(result)
            counts = importer.commit_rows(rows, request.user, upload.name)
            skipped = result.counts()["duplicate"]
            msg = f"Uploaded {counts['cases']} case(s)"
            if counts["payments"]:
                msg += f" with {counts['payments']} payment(s)"
            extras = []
            if counts["hospitals"]:
                extras.append(f"{counts['hospitals']} new hospital(s)")
            if counts["surgeons"]:
                extras.append(f"{counts['surgeons']} new surgeon(s)")
            if extras:
                msg += "; added " + " and ".join(extras)
            if skipped:
                msg += f". {skipped} row(s) were already in the app and were skipped"
            messages.success(request, msg + ".")
            return redirect("cases:list")
    return render(request, "cases/import.html", context)
