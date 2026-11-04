import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Doctor
from core.models import AppSettings
from core.testing import make_admin, make_case, make_doctor, make_hospital, sign_in
from payments.models import Payment

from .models import Case, PaymentStatus, compute_status


class CaseStatusTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.hospital = make_hospital()

    def status_of(self, case):
        return Case.objects.with_totals().get(pk=case.pk)

    def test_due_date_defaults_to_30_days(self):
        case = make_case(self.doctor, self.hospital, days_ago=0)
        self.assertEqual(case.due_date, case.case_date + datetime.timedelta(days=30))

    def test_due_date_default_follows_setting(self):
        settings = AppSettings.load()
        settings.default_payment_terms_days = 45
        settings.save()
        case = make_case(self.doctor, self.hospital)
        self.assertEqual(case.due_date, case.case_date + datetime.timedelta(days=45))

    def test_expected_payment_date_kept_when_given(self):
        due = timezone.localdate() + datetime.timedelta(days=10)
        case = make_case(self.doctor, self.hospital, due_date=due)
        self.assertEqual(case.due_date, due)

    def test_pending_partial_paid_overdue(self):
        case = make_case(self.doctor, self.hospital, days_ago=5, fee=5000)
        self.assertEqual(self.status_of(case).status, PaymentStatus.PENDING)

        Payment.objects.create(case=case, amount=Decimal("2000"))
        annotated = self.status_of(case)
        self.assertEqual(annotated.status, PaymentStatus.PARTIAL)
        self.assertEqual(annotated.outstanding, Decimal("3000"))

        Payment.objects.create(case=case, amount=Decimal("3000"))
        self.assertEqual(self.status_of(case).status, PaymentStatus.PAID)
        self.assertEqual(self.status_of(case).outstanding, Decimal("0"))

        old = make_case(self.doctor, self.hospital, days_ago=40, fee=5000)
        Payment.objects.create(case=old, amount=Decimal("1000"))
        self.assertEqual(self.status_of(old).status, PaymentStatus.OVERDUE)

    def test_python_and_sql_status_agree(self):
        case = make_case(self.doctor, self.hospital, days_ago=40, fee=5000)
        Payment.objects.create(case=case, amount=Decimal("500"))
        fresh = Case.objects.get(pk=case.pk)
        self.assertEqual(fresh.payment_status, self.status_of(case).status)
        self.assertEqual(
            compute_status(Decimal("100"), Decimal("100"), timezone.localdate() - datetime.timedelta(days=1)),
            PaymentStatus.PAID,
        )


class CaseViewTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.other = make_doctor("dr.other", "Dr. Other")
        self.hospital = make_hospital()
        sign_in(self.client, self.doctor)

    def test_add_case_does_not_prefill_fee(self):
        response = self.client.get(reverse("cases:add") + f"?hospital={self.hospital.pk}")
        self.assertIsNone(response.context["form"].initial.get("fee"))
        self.assertEqual(str(response.context["form"].initial.get("hospital")), str(self.hospital.pk))

    def test_fee_is_optional_and_case_stays_open(self):
        form = self.client.get(reverse("cases:add")).context["form"]
        self.assertFalse(form.fields["fee"].required)
        self.assertIsNone(form.initial.get("fee"))  # empty box, not "0"
        self.client.post(reverse("cases:add"), {
            "hospital": self.hospital.pk, "case_date": timezone.localdate().isoformat(), "fee": "",
        })
        case = Case.objects.with_totals().get()
        self.assertEqual(case.fee, 0)
        self.assertTrue(case.is_open)
        self.assertEqual(case.status, PaymentStatus.PENDING)  # not "Paid"
        self.assertTrue(case.fee_to_be_decided)
        self.assertEqual(Case.objects.outstanding().count(), 1)  # still listed for follow-up
        self.assertEqual(self.client.get(reverse("cases:list") + "?status=unpaid").context["page"].paginator.count, 1)
        self.assertContains(self.client.get(case.get_absolute_url()), "To be decided")

    def test_fee_to_be_decided_becomes_overdue_and_reminds(self):
        from payments.services import receivables_for

        case = make_case(self.doctor, self.hospital, days_ago=40, fee=0)
        self.assertEqual(Case.objects.with_totals().get(pk=case.pk).status, PaymentStatus.OVERDUE)
        self.assertEqual(compute_status(Decimal("0"), Decimal("0"), case.due_date), PaymentStatus.OVERDUE)
        self.assertEqual(compute_status(Decimal("0"), Decimal("0"), None), PaymentStatus.PENDING)
        listed = [c for c in receivables_for(self.doctor.user) if c.pk == case.pk]
        self.assertTrue(listed and listed[0].reminder.due)

    def test_paid_on_the_spot_without_fee_uses_amount(self):
        self.client.post(reverse("cases:add"), {
            "hospital": self.hospital.pk, "case_date": timezone.localdate().isoformat(), "fee": "",
            "paid_now": "on", "paid_amount": "4500", "paid_mode": "cash",
        })
        case = Case.objects.get()
        self.assertEqual((case.fee, case.payment_status), (Decimal("4500"), PaymentStatus.PAID))

    def test_add_case_with_custom_fee_and_payment(self):
        response = self.client.post(reverse("cases:add"), {
            "doctor": self.doctor.pk, "hospital": self.hospital.pk, "case_date": timezone.localdate().isoformat(),
            "fee": "7000", "procedure_type": "Spinal", "paid_now": "on", "paid_amount": "7000", "paid_mode": "upi",
        })
        self.assertRedirects(response, reverse("dashboard:home"))
        case = Case.objects.get()
        self.assertEqual(case.doctor, self.doctor)
        self.assertEqual(case.fee, Decimal("7000"))
        self.assertEqual(case.payment_status, PaymentStatus.PAID)

    def test_future_case_date_rejected(self):
        response = self.client.post(reverse("cases:add"), {
            "hospital": self.hospital.pk, "fee": "100",
            "case_date": (timezone.localdate() + datetime.timedelta(days=2)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Case.objects.exists())

    def test_everyone_sees_all_cases_and_can_filter_by_anaesthetist(self):
        make_case(self.doctor, self.hospital)
        case = make_case(self.other, self.hospital)
        self.assertEqual(self.client.get(reverse("cases:detail", args=[case.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("cases:list")).context["page"].paginator.count, 2)
        filtered = self.client.get(reverse("cases:list") + f"?doctor={self.other.pk}")
        self.assertEqual(filtered.context["page"].paginator.count, 1)

    def test_no_anaesthetist_chosen_means_self(self):
        self.client.post(reverse("cases:add"), {
            "hospital": self.hospital.pk, "case_date": timezone.localdate().isoformat(), "fee": "5000",
        })
        self.assertEqual(Case.objects.get().doctor, self.doctor)

    def test_case_for_a_colleague_from_the_dropdown(self):
        no_login = Doctor.objects.create(display_name="Dr. Not Joined")
        form = self.client.get(reverse("cases:add")).context["form"]
        self.assertIn("Self (Dr. Test)", form["doctor"].as_widget())
        widget = form["doctor"].as_widget()
        self.assertIn("Dr. Other", widget)  # colleagues who signed up
        self.assertEqual(widget.count("Dr. Test"), 1)  # own name only as "Self"
        self.assertNotIn("Not Joined", widget)
        self.assertNotIn("new_doctor_name", form.fields)
        response = self.client.post(reverse("cases:add"), {
            "doctor": self.other.pk, "hospital": self.hospital.pk,
            "case_date": timezone.localdate().isoformat(), "fee": "5000", "save_add": "1",
        })
        self.assertEqual(Case.objects.get().doctor, self.other)
        self.assertIn(f"doctor={self.other.pk}", response["Location"])  # next case keeps the colleague
        response = self.client.post(reverse("cases:add"), {
            "doctor": no_login.pk, "hospital": self.hospital.pk,
            "case_date": timezone.localdate().isoformat(), "fee": "5000",
        })
        self.assertIn("doctor", response.context["form"].errors)

    def test_admin_without_profile_must_choose(self):
        self.client.force_login(make_admin())
        response = self.client.post(reverse("cases:add"), {
            "hospital": self.hospital.pk, "case_date": timezone.localdate().isoformat(), "fee": "5000",
        })
        self.assertIn("doctor", response.context["form"].errors)
        self.assertFalse(Case.objects.exists())

    def test_new_anaesthetist_not_created_when_form_has_errors(self):
        from accounts.models import Doctor

        self.client.post(reverse("cases:add"), {
            "hospital": self.hospital.pk, "case_date": timezone.localdate().isoformat(), "fee": "",
            "new_doctor_name": "Ghost Doctor",
        })
        self.assertFalse(Doctor.objects.filter(display_name="Dr. Ghost Doctor").exists())

    def test_admin_sees_all_and_can_filter_by_doctor(self):
        make_case(self.doctor, self.hospital)
        make_case(self.other, self.hospital)
        self.client.force_login(make_admin())
        self.assertEqual(self.client.get(reverse("cases:list")).context["page"].paginator.count, 2)
        filtered = self.client.get(reverse("cases:list") + f"?doctor={self.other.pk}")
        self.assertEqual(filtered.context["page"].paginator.count, 1)


class CaseSearchTests(TestCase):
    def test_search_by_patient_name_and_surgeon(self):
        from contacts.models import Surgeon

        doctor = make_doctor()
        hospital = make_hospital()
        surgeon = Surgeon.objects.create(doctor=doctor, name="Dr. Amit Shah")
        a = make_case(doctor, hospital, patient_name="Sunita Patil")
        b = make_case(doctor, hospital, surgeon=surgeon)
        sign_in(self.client, doctor)
        ids = lambda q: {c.pk for c in self.client.get(reverse("cases:list"), {"q": q}).context["page"]}
        self.assertEqual(ids("sunita"), {a.pk})
        self.assertEqual(ids("amit shah"), {b.pk})


class CaseDeleteTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.case = make_case(self.doctor, make_hospital(), patient_name="Sunita Patil")
        Payment.objects.create(case=self.case, amount=Decimal("100"))
        sign_in(self.client, self.doctor)
        self.delete_url = reverse("cases:delete", args=[self.case.pk])

    def test_delete_buttons_on_case_and_edit_pages(self):
        self.assertContains(self.client.get(self.case.get_absolute_url()), f'href="{self.delete_url}"')
        self.assertContains(self.client.get(reverse("cases:edit", args=[self.case.pk])), f'href="{self.delete_url}"')
        self.assertNotContains(self.client.get(reverse("cases:add")), "Delete case")

    def test_confirm_then_delete(self):
        page = self.client.get(self.delete_url)
        self.assertContains(page, "Delete this case?")
        self.assertContains(page, "Sunita Patil")
        self.assertTrue(Case.objects.filter(pk=self.case.pk).exists())  # GET only asks
        self.assertRedirects(self.client.post(self.delete_url), reverse("cases:list"))
        self.assertFalse(Case.objects.filter(pk=self.case.pk).exists())
        self.assertFalse(Payment.objects.filter(case_id=self.case.pk).exists())

    def test_anyone_can_delete_any_case(self):
        sign_in(self.client, make_doctor("dr.other", "Dr. Other"))
        self.assertRedirects(self.client.post(self.delete_url), reverse("cases:list"))
        self.assertFalse(Case.objects.filter(pk=self.case.pk).exists())
