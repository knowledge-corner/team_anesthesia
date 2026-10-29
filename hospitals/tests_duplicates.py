import datetime
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cases.models import Case
from contacts.models import ContactAffiliation, Surgeon, SurgeonHospital
from core.testing import make_admin, make_case, make_contact, make_doctor, make_hospital, sign_in
from payments.models import Payment, PaymentFollowUp

from .matching import core_name, duplicate_groups, find_similar
from .merge import MergeError, merge_hospitals, undo_merge
from .models import Hospital, HospitalMerge


class MatchingTests(TestCase):
    def setUp(self):
        self.sea = make_hospital("Seatherney Hospital", city="Pune", area="Kothrud")

    def test_core_name_drops_generic_words(self):
        self.assertEqual(core_name("Seatherney Multispeciality Hospital Pvt. Ltd."), "seatherney")
        self.assertEqual(core_name("Care Hospital"), "care hospital")  # nothing left -> keep the name

    def test_similar_names_and_typos(self):
        for typed in ("Seatherney", "seatherney hosp", "Seathurney", "seatherny"):
            self.assertIn(self.sea, find_similar(typed), typed)
        self.assertNotIn(self.sea, find_similar("Ruby Hall"))

    def test_search_ignores_generic_words(self):
        plain = make_hospital("Jupiter", city="Pune")
        self.assertIn(plain, Hospital.objects.active().search("jupiter hospital"))
        self.assertIn(self.sea, Hospital.objects.active().search("seatherney clinic"))

    def test_duplicate_groups_same_city_only(self):
        dup = make_hospital("Seatherney", city="Pune", source="doctor")
        make_hospital("Seatherney", city="Nashik", source="doctor")  # other city: not grouped with Pune
        groups = duplicate_groups()
        self.assertEqual([{h.pk for h in g} for g in groups], [{self.sea.pk, dup.pk}])


class SearchAndAddTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        sign_in(self.client, self.doctor)
        self.sea = make_hospital("Seatherney Hospital", city="Pune", area="Kothrud")

    def test_search_suggests_on_spelling_mistake(self):
        data = self.client.get(reverse("hospitals:search"), {"q": "seathurney"}).json()
        hit = [r for r in data["results"] if r["id"] == self.sea.pk]
        self.assertEqual(hit[0]["group"], "Did you mean?")
        exact = self.client.get(reverse("hospitals:search"), {"q": "seatherney"}).json()["results"]
        self.assertEqual(exact[0]["id"], self.sea.pk)
        self.assertNotIn("group", exact[0])

    def test_add_warns_and_offers_existing(self):
        form = {"name": "Seatherney", "city": "Pune", "category": "hospital", "next": "/cases/add/"}
        response = self.client.post(reverse("hospitals:add"), form)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Is it one of these?")
        self.assertContains(response, f"/cases/add/?hospital={self.sea.pk}")
        self.assertEqual(Hospital.objects.filter(name="Seatherney").count(), 0)  # not added yet
        response = self.client.post(reverse("hospitals:add"), {**form, "confirm_new": "1"})
        added = Hospital.objects.get(name="Seatherney")
        self.assertRedirects(response, f"/cases/add/?hospital={added.pk}", fetch_redirect_response=False)

    def test_add_unrelated_name_saves_straight_away(self):
        response = self.client.post(reverse("hospitals:add"), {"name": "Lotus Care", "city": "Pune", "category": "hospital"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Hospital.objects.filter(name="Lotus Care").exists())


class MergeTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.doctor = make_doctor()
        self.keep = make_hospital("Seatherney Hospital", city="Pune", area="Kothrud")
        self.dup = make_hospital("Seatherney", city="Pune", source="doctor", phone="020-111", aliases="STH")
        # data on the duplicate
        self.case = make_case(self.doctor, self.dup, fee=5000)
        Payment.objects.create(case=self.case, amount=Decimal("2000"))
        PaymentFollowUp.objects.create(case=self.case, followup_date=timezone.localdate(), notes="Call again")
        self.only_dup_contact = make_contact(self.doctor, "Mr. A", "+91 90000 00001", self.dup)
        self.both_contact = make_contact(self.doctor, "Ms. B", "+91 90000 00002", self.keep, primary=False)
        ContactAffiliation.objects.create(contact=self.both_contact, hospital=self.dup, is_primary=True,
                                          start_date=timezone.localdate() - datetime.timedelta(days=100))
        self.s1 = Surgeon.objects.create(doctor=self.doctor, name="Dr. One")
        self.s1.link_hospital(self.dup)
        self.s2 = Surgeon.objects.create(doctor=self.doctor, name="Dr. Two")
        self.s2.link_hospital(self.dup)
        self.s2.link_hospital(self.keep)
        self.keep_case = make_case(self.doctor, self.keep, fee=3000)

    def snapshot(self):
        return {
            "cases": sorted(Case.objects.values_list("pk", "hospital_id", "fee")),
            "payments": sorted(Payment.objects.values_list("pk", "case_id", "amount")),
            "followups": sorted(PaymentFollowUp.objects.values_list("pk", "case_id")),
            "aff": sorted((a.contact_id, a.hospital_id, a.is_primary, a.start_date, a.end_date)
                          for a in ContactAffiliation.objects.all()),
            "surg": sorted(SurgeonHospital.objects.values_list("surgeon_id", "hospital_id")),
            "hosp": sorted(Hospital.objects.filter(pk__in=[self.keep.pk, self.dup.pk]).values_list(
                "pk", "name", "aliases", "phone", "is_active", "merged_into")),
        }

    def test_merge_moves_everything_and_loses_nothing(self):
        counts = (Case.objects.count(), Payment.objects.count(), PaymentFollowUp.objects.count())
        log = merge_hospitals(self.keep, self.dup, user=self.admin)
        self.assertEqual((Case.objects.count(), Payment.objects.count(), PaymentFollowUp.objects.count()), counts)
        self.assertEqual(Case.objects.filter(hospital=self.keep).count(), 2)
        self.case.refresh_from_db()
        self.assertEqual(self.case.payments.count(), 1)  # payment still on the case
        # contacts: moved, and the contact linked to both has one combined current link
        self.assertTrue(ContactAffiliation.objects.filter(contact=self.only_dup_contact, hospital=self.keep).exists())
        combined = ContactAffiliation.objects.get(contact=self.both_contact, hospital=self.keep)
        self.assertTrue(combined.is_primary)
        self.assertEqual(combined.start_date, timezone.localdate() - datetime.timedelta(days=100))
        self.assertFalse(ContactAffiliation.objects.filter(hospital=self.dup).exists())
        # surgeons: one link each at the kept hospital
        self.assertEqual(set(SurgeonHospital.objects.filter(hospital=self.keep).values_list("surgeon_id", flat=True)),
                         {self.s1.pk, self.s2.pk})
        # kept hospital: names searchable, missing phone filled; duplicate hidden but not deleted
        self.keep.refresh_from_db()
        self.dup.refresh_from_db()
        self.assertIn("Seatherney", self.keep.aliases)
        self.assertIn("STH", self.keep.aliases)
        self.assertEqual(self.keep.phone, "020-111")
        self.assertEqual((self.dup.merged_into, self.dup.is_active), (self.keep, False))
        self.assertNotIn(self.dup, Hospital.objects.active())
        self.assertIn(self.keep, Hospital.objects.active().search("STH"))
        self.assertEqual(json.loads(json.dumps(log.details))["cases"], [self.case.pk])

    def test_undo_restores_exactly(self):
        before = self.snapshot()
        log = merge_hospitals(self.keep, self.dup, user=self.admin)
        later = make_case(self.doctor, self.keep, fee=999)  # entered after the merge: stays on the kept hospital
        undo_merge(log, user=self.admin)
        later.delete()
        self.assertEqual(self.snapshot(), before)
        log.refresh_from_db()
        self.assertIsNotNone(log.undone_at)
        with self.assertRaises(MergeError):
            undo_merge(log)

    def test_cannot_merge_twice_or_into_itself(self):
        with self.assertRaises(MergeError):
            merge_hospitals(self.keep, self.keep)
        merge_hospitals(self.keep, self.dup)
        with self.assertRaises(MergeError):
            merge_hospitals(self.keep, self.dup)

    def test_chain_merges_redirect_to_final_hospital(self):
        third = make_hospital("Seatherny", city="Pune", source="doctor")
        merge_hospitals(self.dup, third)
        merge_hospitals(self.keep, self.dup)
        third.refresh_from_db()
        self.assertEqual(third.merged_into, self.keep)

    def test_admin_pages_and_confirmation(self):
        sign_in(self.client, self.doctor)
        self.assertEqual(self.client.get(reverse("hospitals:duplicates")).status_code, 403)
        self.assertEqual(self.client.post(reverse("hospitals:merge"), {"keep": self.keep.pk, "merge": self.dup.pk}).status_code, 403)
        self.client.force_login(self.admin)
        page = self.client.get(reverse("hospitals:duplicates"))
        self.assertContains(page, "Seatherney Hospital")
        confirm = self.client.post(reverse("hospitals:merge"), {"keep": self.keep.pk, "merge": [self.dup.pk, self.keep.pk]})
        self.assertContains(confirm, "Yes, merge")
        self.assertContains(confirm, "moves 1 case")
        self.dup.refresh_from_db()
        self.assertIsNone(self.dup.merged_into)  # nothing happens before confirming
        done = self.client.post(reverse("hospitals:merge"), {"keep": self.keep.pk, "merge": self.dup.pk, "confirm": "1"})
        self.assertRedirects(done, reverse("hospitals:duplicates"))
        log = HospitalMerge.objects.get()
        self.assertEqual((log.kept, log.merged, log.merged_by), (self.keep, self.dup, self.admin))
        # the old hospital page now opens the kept hospital
        self.assertRedirects(self.client.get(self.dup.get_absolute_url()), self.keep.get_absolute_url(),
                             fetch_redirect_response=False)
        self.client.post(reverse("hospitals:merge_undo", args=[log.pk]))
        self.dup.refresh_from_db()
        self.assertTrue(self.dup.is_active)
        self.assertEqual(Case.objects.get(pk=self.case.pk).hospital, self.dup)
