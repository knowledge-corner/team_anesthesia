"""Merging a duplicate hospital into the one to keep - without losing anything.

What moves to the kept hospital:
  * cases (and with them their payments and follow-ups)
  * contact links (a contact already linked there keeps one link; the earliest
    start date and "main contact" flag are kept)
  * surgeon links (one link per surgeon + hospital)
  * earlier merges that pointed at the duplicate
Details the kept hospital is missing (area, address, phone, ...) are copied over and
the duplicate's names become "Other names" so every spelling still finds it.
The duplicate row is never deleted: it is hidden and points to the kept hospital.
Everything is logged in HospitalMerge, so undo_merge() puts it all back.
"""
from django.db import transaction
from django.utils import timezone

from cases.models import Case
from contacts.models import ContactAffiliation, SurgeonHospital

from .models import Hospital, HospitalMerge

FILL_FIELDS = ["area", "district", "address", "pincode", "phone", "email", "website", "ownership"]


class MergeError(ValueError):
    pass


def merge_preview(kept, merged):
    return {
        "cases": Case.objects.filter(hospital=merged).count(),
        "contacts": merged.contact_links.count(),
        "surgeons": merged.surgeon_links.count(),
    }


def _add_aliases(kept, merged):
    names = [a.strip() for a in (kept.aliases or "").split(",") if a.strip()]
    lower = {n.lower() for n in names} | {kept.name.lower()}
    for extra in [merged.name] + [a.strip() for a in (merged.aliases or "").split(",") if a.strip()]:
        if extra.lower() not in lower:
            names.append(extra)
            lower.add(extra.lower())
    value = ", ".join(names)
    if len(value) > Hospital._meta.get_field("aliases").max_length:
        raise MergeError(f"Too many other names on {kept.name} to add {merged.name} - shorten 'Other names' first.")
    return value


@transaction.atomic
def merge_hospitals(kept, merged, user=None):
    kept = Hospital.objects.select_for_update().get(pk=kept.pk)
    merged = Hospital.objects.select_for_update().get(pk=merged.pk)
    if kept.pk == merged.pk:
        raise MergeError("Choose two different hospitals.")
    if merged.merged_into_id or not merged.is_active:
        raise MergeError(f"{merged.name} was already merged or switched off.")
    if kept.merged_into_id or not kept.is_active:
        raise MergeError(f"{kept.name} is not an active hospital - choose another one to keep.")

    details = {"cases": [], "surgeon_links_moved": [], "surgeon_links_removed": [],
               "contact_links_moved": [], "contact_links_combined": [], "redirects": [],
               "kept_before": {}, "merged_before": {"is_active": merged.is_active}}

    # Cases (payments and follow-ups belong to the case and move with it)
    case_ids = list(Case.objects.filter(hospital=merged).values_list("pk", flat=True))
    Case.objects.filter(pk__in=case_ids).update(hospital=kept)
    details["cases"] = case_ids

    # Surgeon links: one per surgeon + hospital
    for link in SurgeonHospital.objects.filter(hospital=merged):
        if SurgeonHospital.objects.filter(surgeon_id=link.surgeon_id, hospital=kept).exists():
            details["surgeon_links_removed"].append({"surgeon": link.surgeon_id})
            link.delete()
        else:
            link.hospital = kept
            link.save(update_fields=["hospital", "updated_at"])
            details["surgeon_links_moved"].append(link.pk)

    # Contact links: combine a contact's two current links into one
    for link in ContactAffiliation.objects.filter(hospital=merged):
        twin = None
        if link.end_date is None:
            twin = ContactAffiliation.objects.filter(contact_id=link.contact_id, hospital=kept,
                                                     end_date__isnull=True).first()
        if twin:
            details["contact_links_combined"].append({
                "kept_link": twin.pk, "kept_before": {"is_primary": twin.is_primary,
                                                      "start_date": twin.start_date.isoformat()},
                "removed": {"contact": link.contact_id, "is_primary": link.is_primary,
                            "start_date": link.start_date.isoformat()},
            })
            twin.is_primary = twin.is_primary or link.is_primary
            twin.start_date = min(twin.start_date, link.start_date)
            twin.save(update_fields=["is_primary", "start_date"])
            link.delete()
        else:
            link.hospital = kept
            link.save(update_fields=["hospital"])
            details["contact_links_moved"].append(link.pk)

    # Hospitals merged earlier into the duplicate now point at the kept one
    redirects = list(Hospital.objects.filter(merged_into=merged).values_list("pk", flat=True))
    Hospital.objects.filter(pk__in=redirects).update(merged_into=kept)
    details["redirects"] = redirects

    # Kept hospital: fill missing details, remember every spelling
    changed = {"aliases": kept.aliases}
    kept.aliases = _add_aliases(kept, merged)
    for field in FILL_FIELDS:
        if not getattr(kept, field) and getattr(merged, field):
            changed[field] = getattr(kept, field)
            setattr(kept, field, getattr(merged, field))
    kept.save()
    details["kept_before"] = changed

    merged.merged_into = kept
    merged.is_active = False
    merged.save(update_fields=["merged_into", "is_active", "updated_at"])

    return HospitalMerge.objects.create(kept=kept, merged=merged, merged_by=user, details=details)


@transaction.atomic
def undo_merge(log, user=None):
    log = HospitalMerge.objects.select_for_update().get(pk=log.pk)
    if log.undone_at:
        raise MergeError("This merge was already undone.")
    kept, merged, d = log.kept, log.merged, log.details

    # Only records that are still where the merge put them go back.
    Case.objects.filter(pk__in=d["cases"], hospital=kept).update(hospital=merged)
    SurgeonHospital.objects.filter(pk__in=d["surgeon_links_moved"], hospital=kept).update(hospital=merged)
    for item in d["surgeon_links_removed"]:
        SurgeonHospital.objects.get_or_create(surgeon_id=item["surgeon"], hospital=merged)
    ContactAffiliation.objects.filter(pk__in=d["contact_links_moved"], hospital=kept).update(hospital=merged)
    for item in d["contact_links_combined"]:
        ContactAffiliation.objects.filter(pk=item["kept_link"]).update(
            is_primary=item["kept_before"]["is_primary"], start_date=item["kept_before"]["start_date"])
        removed = item["removed"]
        ContactAffiliation.objects.create(contact_id=removed["contact"], hospital=merged,
                                          is_primary=removed["is_primary"], start_date=removed["start_date"])
    Hospital.objects.filter(pk__in=d["redirects"], merged_into=kept).update(merged_into=merged)

    for field, value in d["kept_before"].items():
        setattr(kept, field, value)
    kept.save()
    merged.merged_into = None
    merged.is_active = d["merged_before"].get("is_active", True)
    merged.save(update_fields=["merged_into", "is_active", "updated_at"])

    log.undone_at = timezone.now()
    log.undone_by = user
    log.save(update_fields=["undone_at", "undone_by"])
