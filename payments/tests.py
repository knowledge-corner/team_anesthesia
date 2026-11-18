import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cases.models import Case
from core.testing import make_case, make_doctor, make_hospital, sign_in

from .models import Payment, PaymentFollowUp
from .services import receivables_for, reminder_state


class PaymentViewTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.hospital = make_hospital()
        self.case = make_case(self.doctor, self.hospital, days_ago=3, fee=5000)
        sign_in(self.client, self.doctor)

    def test_partial_payments(self):
        url = reverse("payments:record_for_case", args=[self.case.pk])
        for amount in ("2000", "1500"):
            self.client.post(url, {"amount": amount, "payment_date": timezone.localdate().isoformat(), "mode": "upi"})
        case = Case.objects.with_totals().get(pk=self.case.pk)
        self.assertEqual(case.total_paid, Decimal("3500"))
        self.assertEqual(case.outstanding, Decimal("1500"))
        self.assertEqual(case.status, "partial")

    def test_more_than_the_fee_raises_the_fee(self):
        response = self.client.post(
            reverse("payments:record_for_case", args=[self.case.pk]),
            {"amount": "6000", "payment_date": timezone.localdate().isoformat(), "mode": "cash"},
        )
        self.assertEqual(response.status_code, 302)  # saved, not blocked
        case = Case.objects.with_totals().get(pk=self.case.pk)
        self.assertEqual((case.fee, case.total_paid, case.status), (Decimal("6000"), Decimal("6000"), "paid"))

    def test_record_payment_from_unpaid_list(self):
        response = self.client.post(reverse("payments:record"), {
            "case": self.case.pk, "amount": "5000", "payment_date": timezone.localdate().isoformat(), "mode": "bank",
        })
        self.assertRedirects(response, self.case.get_absolute_url())
        self.assertEqual(Case.objects.get(pk=self.case.pk).payment_status, "paid")

    def test_fee_decided_at_payment_time(self):
        open_case = make_case(self.doctor, self.hospital, days_ago=3, fee=0)
        url = reverse("payments:record_for_case", args=[open_case.pk])
        page = self.client.get(url)
        self.assertContains(page, "the amount you enter becomes the fee")
        self.assertFalse(page.context["form"].fields["case_fee"].required)
        today = timezone.localdate().isoformat()
        # only the amount -> saved straight away, the amount is the fee
        response = self.client.post(url, {"amount": "7000", "payment_date": today, "mode": "upi"})
        self.assertEqual(response.status_code, 302)
        case = Case.objects.with_totals().get(pk=open_case.pk)
        self.assertEqual((case.fee, case.status), (Decimal("7000"), "paid"))
        # a total can still be given when more is to come
        other = make_case(self.doctor, self.hospital, days_ago=3, fee=0)
        self.client.post(reverse("payments:record_for_case", args=[other.pk]),
                         {"amount": "3000", "case_fee": "8000", "payment_date": today, "mode": "upi"})
        other = Case.objects.with_totals().get(pk=other.pk)
        self.assertEqual((other.fee, other.status), (Decimal("8000"), "partial"))

    def test_fee_typed_at_payment_is_final_even_if_lower(self):
        url = reverse("payments:record_for_case", args=[self.case.pk])
        self.assertEqual(self.client.get(url).context["form"].initial["case_fee"], 5000)
        today = timezone.localdate().isoformat()
        Payment.objects.create(case=self.case, amount=Decimal("4000"))
        response = self.client.post(url, {"amount": "500", "case_fee": "4200", "payment_date": today, "mode": "bank"})
        self.assertEqual(response.status_code, 302)  # no "cannot be less than received" check
        case = Case.objects.with_totals().get(pk=self.case.pk)
        self.assertEqual((case.fee, case.status), (Decimal("4200"), "paid"))

    def test_prefilled_fee_left_as_is_still_rises_with_overpayment(self):
        url = reverse("payments:record_for_case", args=[self.case.pk])
        self.assertEqual(str(self.client.get(url).context["form"].initial["case_fee"]), "5000")
        self.client.post(url, {"amount": "6500", "case_fee": "5000", "payment_date": timezone.localdate().isoformat(),
                               "mode": "upi"})
        self.assertEqual(Case.objects.get(pk=self.case.pk).fee, Decimal("6500"))

    def test_partial_payment_keeps_the_fee(self):
        self.client.post(reverse("payments:record_for_case", args=[self.case.pk]),
                         {"amount": "1000", "payment_date": timezone.localdate().isoformat(), "mode": "upi"})
        self.assertEqual(Case.objects.get(pk=self.case.pk).fee, Decimal("5000"))

    def test_paid_case_shows_edit_button_for_each_payment(self):
        payment = Payment.objects.create(case=self.case, amount=Decimal("5000"))
        page = self.client.get(self.case.get_absolute_url())
        self.assertNotContains(page, "Record payment")  # fully paid
        self.assertContains(page, "Edit payment</a>", count=1)  # one green button where "Record payment" was
        self.assertEqual(page.content.decode().count('<i class="bi bi-pencil"></i> Edit</a>'), 1)  # only the case's own Edit; no Edit button per payment
        Payment.objects.create(case=make_case(self.doctor, self.hospital, fee=0), amount=Decimal("1"))
        second = Payment.objects.create(case=self.case, amount=Decimal("0.01"))
        self.assertContains(self.client.get(self.case.get_absolute_url()), 'href="#payments"')
        second.delete()
        edit = self.client.get(reverse("payments:edit", args=[payment.pk]))
        self.assertContains(edit, "Edit payment")
        self.client.post(reverse("payments:edit", args=[payment.pk]), {
            "amount": "4500", "payment_date": timezone.localdate().isoformat(), "mode": "upi"})
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("4500"))

    def test_edit_payment_allows_same_amount(self):
        payment = Payment.objects.create(case=self.case, amount=Decimal("5000"))
        response = self.client.post(reverse("payments:edit", args=[payment.pk]), {
            "amount": "5000", "payment_date": timezone.localdate().isoformat(), "mode": "cheque",
        })
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.mode, "cheque")


class ReminderTests(TestCase):
    """Reminders fire only on the expected payment date (default: 30 days) and on dates set in a follow-up."""

    def setUp(self):
        self.doctor = make_doctor()
        self.hospital = make_hospital()
        self.today = timezone.localdate()

    def day(self, n):
        return self.today + datetime.timedelta(days=n)

    def test_no_reminder_before_expected_date(self):
        case = make_case(self.doctor, self.hospital, days_ago=10)  # default expected date = case + 30 days
        state = reminder_state(case)
        self.assertFalse(state.due)
        self.assertEqual(state.next_trigger, case.case_date + datetime.timedelta(days=30))

    def test_old_7_14_21_day_reminders_are_gone(self):
        for age in (7, 8, 14, 21, 28, 29):
            case = make_case(self.doctor, self.hospital, days_ago=age)
            self.assertFalse(reminder_state(case).due, age)

    def test_due_on_default_30_days(self):
        self.assertTrue(reminder_state(make_case(self.doctor, self.hospital, days_ago=30)).due)

    def test_due_on_expected_date_that_was_entered(self):
        case = make_case(self.doctor, self.hospital, days_ago=1, due_date=self.day(1))
        self.assertFalse(reminder_state(case).due)
        self.assertTrue(reminder_state(case, today=self.day(1)).due)  # on the expected date itself
        self.assertTrue(reminder_state(case, today=self.day(5)).due)  # still due until followed up

    def test_followup_clears_and_remind_again_date_raises_it(self):
        case = make_case(self.doctor, self.hospital, days_ago=31)
        self.assertTrue(reminder_state(case).due)
        sign_in(self.client, self.doctor)
        self.client.post(reverse("payments:followup_add", args=[case.pk]), {
            "followup_date": self.today.isoformat(), "method": "call", "next_reminder": self.day(4).isoformat(),
        })
        case = Case.objects.get(pk=case.pk)
        self.assertEqual(case.followup_snoozed_until, self.day(4))
        self.assertFalse(reminder_state(case).due)
        self.assertEqual(reminder_state(case).next_trigger, self.day(4))
        self.assertTrue(reminder_state(case, today=self.day(4)).due)

    def test_followup_without_date_means_no_more_reminders(self):
        case = make_case(self.doctor, self.hospital, days_ago=31)
        PaymentFollowUp.objects.create(case=case, followup_date=self.today)
        state = reminder_state(case, today=self.day(60))
        self.assertFalse(state.due)
        self.assertIsNone(state.next_trigger)

    def test_followup_before_expected_date_keeps_that_reminder(self):
        case = make_case(self.doctor, self.hospital, days_ago=2, due_date=self.day(3))
        PaymentFollowUp.objects.create(case=case, followup_date=self.today)
        self.assertTrue(reminder_state(case, today=self.day(3)).due)

    def test_remind_again_date_must_be_in_future(self):
        case = make_case(self.doctor, self.hospital, days_ago=31)
        sign_in(self.client, self.doctor)
        response = self.client.post(reverse("payments:followup_add", args=[case.pk]), {
            "followup_date": self.today.isoformat(), "method": "call", "next_reminder": self.today.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("next_reminder", response.context["form"].errors)

    def test_remind_me_in_days(self):
        case = make_case(self.doctor, self.hospital, days_ago=31)
        sign_in(self.client, self.doctor)
        self.client.post(reverse("payments:followup_snooze", args=[case.pk]), {"days": "3"})
        case.refresh_from_db()
        self.assertEqual(case.followup_snoozed_until, self.day(3))
        self.assertFalse(reminder_state(case).due)
        self.assertTrue(reminder_state(case, today=self.day(3)).due)

    def test_promised_date_becomes_the_reminder(self):
        case = make_case(self.doctor, self.hospital, days_ago=31)
        sign_in(self.client, self.doctor)
        self.client.post(reverse("payments:followup_add", args=[case.pk]), {
            "followup_date": self.today.isoformat(), "method": "call",
            "promised_payment_date": self.day(5).isoformat(), "notes": "Will pay Friday",
        })
        case.refresh_from_db()
        self.assertEqual(case.followup_snoozed_until, self.day(5))
        self.assertTrue(reminder_state(case, today=self.day(5)).due)

    def test_quick_mark_followed_up(self):
        case = make_case(self.doctor, self.hospital, days_ago=31)
        self.assertTrue(reminder_state(case).due)
        sign_in(self.client, self.doctor)
        self.client.post(reverse("payments:followup_quick", args=[case.pk]))
        self.assertEqual(case.followups.count(), 1)
        self.assertFalse(reminder_state(Case.objects.get(pk=case.pk)).due)

    def test_paid_cases_never_need_followup(self):
        case = make_case(self.doctor, self.hospital, days_ago=50, fee=1000)
        Payment.objects.create(case=case, amount=Decimal("1000"))
        self.assertEqual(receivables_for(self.doctor.user), [])

    def test_receivables_sorted_oldest_first(self):
        newer = make_case(self.doctor, self.hospital, days_ago=5)
        older = make_case(self.doctor, self.hospital, days_ago=50)
        sign_in(self.client, self.doctor)
        response = self.client.get(reverse("receivables:list"))
        self.assertEqual([c.pk for c in response.context["cases"]], [older.pk, newer.pk])
        response = self.client.get(reverse("receivables:list") + "?view=overdue")
        self.assertEqual([c.pk for c in response.context["cases"]], [older.pk])


class ReceivedByTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.case = make_case(self.doctor, make_hospital(), fee=5000)
        sign_in(self.client, self.doctor)

    def test_record_payment_with_received_by(self):
        url = reverse("payments:record_for_case", args=[self.case.pk])
        self.assertContains(self.client.get(url), 'name="received_by"')
        self.client.post(url, {"amount": "2000", "payment_date": timezone.localdate().isoformat(), "mode": "upi",
                               "received_by": "Clinic reception"})
        payment = Payment.objects.get()
        self.assertEqual(payment.received_by, "Clinic reception")
        self.assertContains(self.client.get(self.case.get_absolute_url()), "received by Clinic reception")
        # offered as a suggestion next time
        self.assertContains(self.client.get(url), '<option value="Clinic reception">')

    def test_received_by_is_optional_and_in_excel(self):
        import io

        from openpyxl import load_workbook

        url = reverse("payments:record_for_case", args=[self.case.pk])
        self.client.post(url, {"amount": "1000", "payment_date": timezone.localdate().isoformat(), "mode": "cash"})
        Payment.objects.create(case=self.case, amount=Decimal("500"), received_by="Dr. Mehta")
        self.assertEqual(Payment.objects.count(), 2)
        response = self.client.get(reverse("reports:payments") + "?period=all&export=xlsx")
        values = [c.value for row in load_workbook(io.BytesIO(response.content)).active.iter_rows() for c in row]
        self.assertIn("Received by", values)
        self.assertIn("Dr. Mehta", values)


class BulkPaymentTests(TestCase):
    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.upload = SimpleUploadedFile
        self.doctor = make_doctor()
        self.hospital = make_hospital()
        self.other = make_hospital(name="Other Hospital")
        self.unpaid = make_case(self.doctor, self.hospital, days_ago=5, fee=9000)
        self.partial = make_case(self.doctor, self.hospital, days_ago=4, fee=11000)
        Payment.objects.create(case=self.partial, amount=Decimal("5500"))
        self.tbd = make_case(self.doctor, self.hospital, days_ago=3, fee=0)
        self.paid = make_case(self.doctor, self.hospital, days_ago=2, fee=4000)
        Payment.objects.create(case=self.paid, amount=Decimal("4000"))
        self.elsewhere = make_case(self.doctor, self.other, days_ago=1, fee=7000)
        sign_in(self.client, self.doctor)
        self.url = reverse("payments:bulk") + f"?hospital={self.hospital.pk}"

    def _status(self, case):
        return Case.objects.with_totals().get(pk=case.pk)

    def test_cases_list_has_bulk_button_and_no_search_box(self):
        page = self.client.get(reverse("cases:list") + f"?hospital={self.hospital.pk}&status=unpaid")
        self.assertNotContains(page, "Search patient")
        self.assertContains(page, f'href="/payments/bulk/?status=unpaid&amp;hospital={self.hospital.pk}"')
        for label in ("Status", "Month", "Hospital", "Surgeon"):
            self.assertContains(page, f">{label}</label>")

    def test_page_lists_only_unpaid_cases_of_the_filter(self):
        page = self.client.get(self.url)
        ids = [c.pk for c in page.context["cases"]]
        self.assertEqual(ids, [self.unpaid.pk, self.partial.pk, self.tbd.pk])
        tickable = {c.pk: c.tickable for c in page.context["cases"]}
        self.assertEqual(tickable, {self.unpaid.pk: True, self.partial.pk: False, self.tbd.pk: False})

    def test_ticked_cases_are_paid_for_their_fee(self):
        today = timezone.localdate().isoformat()
        r = self.client.post(self.url, {"action": "tick", "case": [self.unpaid.pk, self.partial.pk, self.tbd.pk, self.elsewhere.pk],
                                        "payment_date": today, "mode": "bank", "reference_no": "NEFT 1"})
        self.assertRedirects(r, self.url, fetch_redirect_response=False)
        self.assertEqual(self._status(self.unpaid).status, "paid")
        self.assertEqual(self.unpaid.payments.get().reference_no, "NEFT 1")
        # partly paid, fee TBD and cases outside the filter are never touched by ticking
        self.assertEqual(self.partial.payments.count(), 1)
        self.assertEqual(self.tbd.payments.count(), 0)
        self.assertEqual(self.elsewhere.payments.count(), 0)

    def test_tick_needs_a_case(self):
        r = self.client.post(self.url, {"action": "tick", "payment_date": timezone.localdate().isoformat(), "mode": "bank"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Payment.objects.count(), 2)

    def test_csv_download_has_the_filtered_unpaid_cases(self):
        r = self.client.get(reverse("payments:bulk_csv") + f"?hospital={self.hospital.pk}")
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        lines = r.content.decode("utf-8-sig").strip().splitlines()
        self.assertTrue(lines[0].startswith("Case ID,Case date,Hospital"))
        self.assertEqual([int(l.split(",")[0]) for l in lines[1:]], [self.unpaid.pk, self.partial.pk, self.tbd.pk])
        self.assertIn("TBD", lines[3])

    def _upload(self, text, name="pay.csv"):
        return self.client.post(reverse("payments:bulk_upload"), {
            "file": self.upload(name, text.encode("utf-8-sig"), content_type="text/csv"),
            "filter_query": f"hospital={self.hospital.pk}"})

    def test_upload_checks_then_records(self):
        csv_text = self.client.get(reverse("payments:bulk_csv") + f"?hospital={self.hospital.pk}").content.decode("utf-8-sig")
        lines = csv_text.strip().splitlines()
        filled = [lines[0],
                  lines[1].rstrip(",") + ",4000,01/11/2026,cheque,CHQ 77,,",   # less than due -> partly paid
                  lines[2].rstrip(",") + ",5500,,,,,",                        # the rest -> paid
                  lines[3].rstrip(",") + ",8000,,upi,,,",                     # fee TBD -> fee 8000
                  "99999,,,,,,,,,,100,,,,,",                                  # unknown case
                  str(self.paid.pk) + ",,,,,,,,,,abc,,,,,"]                   # not a number
        review = self._upload("\n".join(filled))
        self.assertEqual(review.status_code, 200)
        self.assertEqual((review.context["good_count"], review.context["error_count"]), (3, 2))
        self.assertContains(review, "Partly paid")
        self.assertContains(review, "Fee set to ₹8,000")
        self.assertEqual(Payment.objects.count(), 2)  # nothing saved yet
        r = self.client.post(reverse("payments:bulk_upload"), {
            "action": "confirm", "rows": review.context["signed_rows"], "filter_query": f"hospital={self.hospital.pk}"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._status(self.unpaid).status, "partial")
        p = self.unpaid.payments.get()
        self.assertEqual((p.amount, p.mode, p.reference_no, p.payment_date), (Decimal("4000"), "cheque", "CHQ 77", datetime.date(2026, 11, 1)))
        self.assertEqual(self._status(self.partial).status, "paid")
        tbd = self._status(self.tbd)
        self.assertEqual((tbd.fee, tbd.status), (Decimal("8000"), "paid"))

    def test_upload_overpayment_raises_fee_and_tampering_is_refused(self):
        review = self._upload(f"Case ID,Amount received\n{self.unpaid.pk},9500\n")
        self.assertContains(review, "fee raised to ₹9,500")
        r = self.client.post(reverse("payments:bulk_upload"), {"action": "confirm", "rows": review.context["signed_rows"] + "x"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.unpaid.payments.count(), 0)

    def test_upload_without_amount_column(self):
        r = self._upload("hello,world\n1,2\n")
        self.assertEqual(r.status_code, 302)
        self.assertIn("tab=csv", r["Location"])

    def test_upload_excel_file(self):
        import io
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        ws.append(["Case ID", "Amount received", "Payment date"])
        ws.append([self.unpaid.pk, 9000, datetime.date(2026, 11, 2)])
        buf = io.BytesIO(); wb.save(buf)
        r = self.client.post(reverse("payments:bulk_upload"), {"file": self.upload("pay.xlsx", buf.getvalue())})
        self.assertEqual(r.context["good_count"], 1)
        self.assertContains(r, "Paid in full")
