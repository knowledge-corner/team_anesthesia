from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from contacts.models import ContactAffiliation
from core.permissions import admin_required, scoped_cases

from .directory import import_directory
from .forms import CITY_SUGGESTIONS, AdminHospitalForm, DirectoryImportForm, HospitalForm
from .matching import duplicate_groups, find_similar
from .merge import MergeError, merge_hospitals, merge_preview, undo_merge
from .models import Hospital, HospitalMerge


def my_hospital_ids(request):
    """Hospitals the user works with: hospitals of their cases + where their contacts work."""
    ids = set(scoped_cases(request).values_list("hospital_id", flat=True).distinct())
    links = ContactAffiliation.objects.current()
    if not request.user.is_app_admin:
        links = links.filter(contact__doctor__user=request.user)
    ids.update(links.values_list("hospital_id", flat=True))
    return ids


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return None


@login_required
def hospital_list(request):
    q = request.GET.get("q", "").strip()
    mine = my_hospital_ids(request)
    # Outstanding per hospital for the user's own cases.
    counts, totals = {}, {}
    for case in scoped_cases(request).outstanding().only("id", "hospital_id", "fee"):
        counts[case.hospital_id] = counts.get(case.hospital_id, 0) + 1
        totals[case.hospital_id] = totals.get(case.hospital_id, 0) + case.outstanding

    if q:
        results = list(Hospital.objects.active().search(q).order_by("name")[:60])
        results.sort(key=lambda h: (h.pk not in mine, h.name.lower()))
    else:
        last_case = {
            r["hospital_id"]: r["last"]
            for r in scoped_cases(request).values("hospital_id").annotate(last=Max("case_date")).order_by()
        }
        results = list(Hospital.objects.filter(pk__in=mine))
        results.sort(key=lambda h: (-(totals.get(h.pk) or 0), h.name.lower()))
        for h in results:
            h.last_case = last_case.get(h.pk)
    for h in results:
        h.is_mine = h.pk in mine
        h.open_cases = counts.get(h.pk, 0)
        h.outstanding_total = totals.get(h.pk, 0)
    return render(request, "hospitals/hospital_list.html", {
        "hospitals": results, "q": q, "directory_size": Hospital.objects.active().count(),
    })


@login_required
def hospital_search(request):
    """JSON for the type-to-search hospital picker: user's hospitals first."""
    q = request.GET.get("q", "").strip()
    mine = my_hospital_ids(request)
    if q:
        qs = list(Hospital.objects.active().search(q).order_by("name")[:40])
    else:
        qs = list(Hospital.objects.filter(pk__in=mine, is_active=True))
    qs.sort(key=lambda h: (h.pk not in mine, h.name.lower()))
    results = [{"id": h.pk, "label": h.name, "sub": h.place, "mine": h.pk in mine} for h in qs[:20]]
    # Spelling mistakes: offer close matches so nobody adds the same hospital twice.
    if q and len(results) < 5:
        shown = {r["id"] for r in results}
        for h in find_similar(q, exclude_ids=shown, limit=5 - len(results)):
            results.append({"id": h.pk, "label": h.name, "sub": h.place, "mine": h.pk in mine,
                            "group": "Did you mean?"})
    return JsonResponse({"results": results})


@login_required
def hospital_detail(request, pk):
    hospital = get_object_or_404(Hospital, pk=pk)
    if hospital.merged_into_id:
        return redirect(hospital.merged_into)
    cases = scoped_cases(request).filter(hospital=hospital).with_totals().select_related("doctor", "surgeon")
    open_cases = [c for c in cases if c.outstanding > 0]
    links = hospital.contact_links.select_related("contact").order_by("end_date", "-is_primary")
    if not request.user.is_app_admin:
        links = links.filter(contact__doctor__user=request.user)
    return render(request, "hospitals/hospital_detail.html", {
        "hospital": hospital,
        "recent_cases": cases[:10],
        "open_cases": open_cases,
        "outstanding_total": sum(c.outstanding for c in open_cases),
        "case_count": cases.count(),
        "current_links": [link for link in links if link.is_current],
        "past_links": [link for link in links if not link.is_current],
        "can_edit": _can_edit(request.user, hospital),
    })


def _can_edit(user, hospital):
    if user.is_app_admin:
        return True
    return hospital.created_by_id == user.pk


@login_required
def hospital_add(request):
    is_admin = request.user.is_app_admin
    form_class = AdminHospitalForm if is_admin else HospitalForm
    initial = {"name": request.GET.get("name", ""), "city": request.GET.get("city", "")}
    form = form_class(request.POST or None, initial=initial)
    nxt = _safe_next(request)
    similar = []
    if request.method == "POST" and form.is_valid():
        # Before creating a new hospital, show ones that look the same ("Seatherney" vs "Seatherney Hospital").
        if not request.POST.get("confirm_new"):
            similar = find_similar(form.cleaned_data["name"], form.cleaned_data.get("city", ""))
    elif initial["name"]:
        similar = find_similar(initial["name"], initial["city"])
    if request.method == "POST" and form.is_valid() and not similar:
        hospital = form.save(commit=False)
        hospital.source = "admin" if is_admin else "doctor"
        hospital.created_by = request.user
        hospital.verified = True
        hospital.save()
        messages.success(request, f"{hospital} added to the hospital list.")
        if nxt:
            sep = "&" if "?" in nxt else "?"
            return redirect(f"{nxt}{sep}hospital={hospital.pk}")
        return redirect(hospital)
    for h in similar:
        if nxt:
            h.use_url = f"{nxt}{'&' if '?' in nxt else '?'}hospital={h.pk}"
        else:
            h.use_url = h.get_absolute_url()
    return render(request, "hospitals/hospital_form.html", {
        "form": form, "hospital": None, "cities": CITY_SUGGESTIONS, "next": nxt or "",
        "similar": similar, "similar_checked": request.method == "POST",
    })


@login_required
def hospital_edit(request, pk):
    hospital = get_object_or_404(Hospital, pk=pk)
    if not _can_edit(request.user, hospital):
        raise PermissionDenied
    form_class = AdminHospitalForm if request.user.is_app_admin else HospitalForm
    form = form_class(request.POST or None, instance=hospital)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Hospital updated.")
        return redirect(hospital)
    return render(request, "hospitals/hospital_form.html", {"form": form, "hospital": hospital, "cities": CITY_SUGGESTIONS})


@admin_required
def directory_import(request):
    form = DirectoryImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            counts = import_directory(form.cleaned_data["file"], form.cleaned_data["districts"].split(","))
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Imported: {counts['created']} new and {counts['updated']} updated hospitals "
                f"({counts['matched']} rows matched the districts; {counts['skipped_system']} non-allopathic skipped).",
            )
            return redirect("hospitals:list")
    stats = {s: Hospital.objects.active().filter(source=s).count() for s, _ in Hospital.SOURCE_CHOICES}
    return render(request, "hospitals/directory_import.html", {"form": form, "stats": stats})




# --------------------------------------------------------------------------- #
# Duplicates and merging (administrators only)
# --------------------------------------------------------------------------- #

def _with_usage(hospitals):
    ids = [h.pk for h in hospitals]
    usage = {h["pk"]: h for h in Hospital.objects.filter(pk__in=ids).values("pk").annotate(
        n_cases=Count("cases", distinct=True), n_contacts=Count("contact_links", distinct=True),
        n_surgeons=Count("surgeon_links", distinct=True))}
    for h in hospitals:
        u = usage.get(h.pk, {})
        h.n_cases, h.n_contacts, h.n_surgeons = u.get("n_cases", 0), u.get("n_contacts", 0), u.get("n_surgeons", 0)
    return hospitals


@admin_required
def duplicates(request):
    groups = duplicate_groups()
    for group in groups:
        _with_usage(group)
        # Suggest keeping the official entry, then one added by an admin, then the fuller name
        # (cases always move to the kept hospital, so their number does not matter).
        keep = max(group, key=lambda h: (h.source in ("directory", "starter"), h.source == "admin", len(h.name), -h.pk))
        for h in group:
            h.suggest_keep = h.pk == keep.pk
    prefill = Hospital.objects.filter(pk=request.GET.get("merge") or 0).first() if str(request.GET.get("merge", "")).isdigit() else None
    return render(request, "hospitals/duplicates.html", {
        "groups": groups, "prefill": prefill,
        "history": HospitalMerge.objects.select_related("kept", "merged", "merged_by", "undone_by")[:30],
    })


@admin_required
@require_POST
def merge(request):
    keep = Hospital.objects.filter(pk=request.POST.get("keep") or 0).first()
    merge_ids = [int(x) for x in request.POST.getlist("merge") if x.isdigit()]
    others = [h for h in Hospital.objects.filter(pk__in=merge_ids) if keep and h.pk != keep.pk]
    if not keep or not others:
        messages.error(request, "Choose the hospital to keep and at least one other hospital to merge into it.")
        return redirect("hospitals:duplicates")
    if not request.POST.get("confirm"):
        for h in others:
            h.preview = merge_preview(keep, h)
        return render(request, "hospitals/merge_confirm.html", {"keep": _with_usage([keep])[0], "others": others})
    done = []
    for h in others:
        try:
            merge_hospitals(keep, h, user=request.user)
            done.append(h.name)
        except MergeError as exc:
            messages.error(request, str(exc))
    if done:
        messages.success(request, f"Merged into {keep.name}: {', '.join(done)}. "
                                  "All their cases, contacts and surgeons are now under this hospital.")
    return redirect("hospitals:duplicates")


@admin_required
@require_POST
def merge_undo(request, pk):
    log = get_object_or_404(HospitalMerge, pk=pk)
    try:
        undo_merge(log, user=request.user)
    except MergeError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Undone: {log.merged.name} is a separate hospital again, with its cases, "
                                  "contacts and surgeons.")
    return redirect("hospitals:duplicates")
