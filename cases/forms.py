import re
from decimal import Decimal

from django import forms
from django.db import models
from django.utils import timezone

from accounts.models import Doctor
from contacts.models import Contact, Surgeon
from contacts.services import ensure_affiliation, find_surgeon
from core.forms import StyledModelForm
from hospitals.models import Hospital
from payments.models import Payment

from .models import Case

COMMON_PROCEDURES = [
    "General anaesthesia (GA)",
    "Spinal anaesthesia",
    "Epidural",
    "Combined spinal-epidural (CSE)",
    "LSCS - spinal",
    "Peripheral nerve block",
    "Monitored anaesthesia care / sedation",
    "Labour analgesia",
    "Endoscopy sedation",
    "ICU / emergency call",
]


class CaseForm(StyledModelForm):
    paid_now = forms.BooleanField(
        required=False, label="Payment already received",
        help_text="Tick if the hospital/patient paid on the spot.",
    )
    paid_amount = forms.DecimalField(required=False, min_value=Decimal("0.01"), max_digits=10, decimal_places=2)
    paid_mode = forms.ChoiceField(choices=Payment.MODE_CHOICES, required=False, initial="upi", label="Mode")
    # Quick "new contact" on the case form
    new_contact_name = forms.CharField(required=False, max_length=100, label="Contact name")
    new_contact_phone = forms.CharField(required=False, max_length=20, label="Mobile",
                                        widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel"}))
    new_contact_role = forms.ChoiceField(required=False, choices=Contact.ROLE_CHOICES, initial="billing", label="Role")
    # Quick "new surgeon" on the case form
    new_surgeon_name = forms.CharField(required=False, max_length=100, label="Surgeon name",
                                       widget=forms.TextInput(attrs={"placeholder": "e.g. Dr. Kulkarni"}))
    new_surgeon_phone = forms.CharField(required=False, max_length=20, label="Mobile (optional)",
                                        widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel"}))

    class Meta:
        model = Case
        fields = ["doctor", "hospital", "case_date", "patient_name", "surgeon", "contact", "patient_reference",
                  "procedure_type", "fee", "due_date", "notes"]
        widgets = {
            "case_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fee": forms.NumberInput(attrs={"inputmode": "decimal", "step": "1", "placeholder": "e.g. 6000"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "procedure_type": forms.TextInput(attrs={"list": "procedure-options", "autocomplete": "off"}),
            "patient_reference": forms.TextInput(attrs={"autocomplete": "off", "placeholder": "e.g. IP 45821 / bill no."}),
            "patient_name": forms.TextInput(attrs={"autocomplete": "off", "placeholder": "e.g. Sunita Patil"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Often the amount is only known when the hospital pays: leave it empty (= 0, "to be decided")
        # and enter it on Record payment.
        self.fields["fee"].required = False
        self.fields["fee"].label = "Fee (₹)"
        self.fields["fee"].help_text = "Not decided yet? Leave it empty - enter it when the payment is received."
        if not self.is_bound and not self.initial.get("fee"):
            self.initial["fee"] = None  # show an empty box, not "0"

        # Hospital: type-to-search against the whole directory (server-side).
        hospital_field = self.fields["hospital"]
        hospital_field.queryset = Hospital.objects.all()
        selected = self.data.get(self.add_prefix("hospital")) or self.initial.get("hospital") or (
            self.instance.hospital_id if self.instance.pk else None)
        choices = [("", "Search hospital")]
        if selected and str(selected).isdigit():
            h = Hospital.objects.filter(pk=selected).first()
            if h:
                choices.append((h.pk, h.label))
        hospital_field.widget.choices = choices
        hospital_field.widget.attrs.update({
            "data-searchable": "", "data-search-url": "/hospitals/search/",
            "data-placeholder": "Type hospital name or area", "data-add-url": "/hospitals/add/?next=/cases/add/",
        })

        # Surgeons and contacts are shared by the whole practice
        # (re-ordered in the browser once a hospital is picked).
        self.fields["surgeon"].queryset = Surgeon.objects.filter(is_active=True)
        self.fields["surgeon"].empty_label = "Not specified"
        self.fields["surgeon"].label = "Surgeon"
        self.fields["surgeon"].widget.attrs.update({"data-searchable": "", "data-placeholder": "Type surgeon name"})
        self.fields["contact"].queryset = Contact.objects.filter(is_active=True)
        self.fields["contact"].empty_label = "Not specified"
        self.fields["contact"].label = "Contact person"
        self.fields["contact"].widget.attrs.update({"data-searchable": "", "data-placeholder": "Type contact name"})

        # Anaesthetist who did the case: left empty = the person adding it ("Self").
        # The list holds everyone who has signed up (plus the current one when editing).
        self.self_doctor = getattr(user, "doctor_profile", None) if user else None
        doctors = Doctor.objects.registered()
        if self.instance.pk:
            doctors = Doctor.objects.filter(models.Q(pk__in=doctors) | models.Q(pk=self.instance.doctor_id))
        field = self.fields["doctor"]
        field.queryset = doctors.order_by("display_name")
        field.label = "Anaesthetist"
        field.required = self.self_doctor is None
        field.empty_label = f"Self ({self.self_doctor})" if self.self_doctor else "Choose anaesthetist"
        if self.self_doctor:  # own name is the "Self" option; still accepted if posted explicitly
            field.widget.choices = [(k, v) for k, v in field.choices if str(k) != str(self.self_doctor.pk)]

        if self.instance.pk:
            for name in ("paid_now", "paid_amount", "paid_mode"):
                self.fields.pop(name)

    def clean_fee(self):
        fee = self.cleaned_data.get("fee")
        return Decimal("0") if fee is None else fee

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("paid_now"):
            fee = cleaned.get("fee")
            amount = cleaned.get("paid_amount") or fee
            if not amount:
                self.add_error("paid_amount", "Enter the amount received.")
            elif not fee or amount > fee:
                # No fee entered, or more was received: the amount received is the fee.
                cleaned["fee"] = self.instance.fee = amount
            cleaned["paid_amount"] = amount
        case_date = cleaned.get("case_date")
        if case_date and case_date > timezone.localdate():
            self.add_error("case_date", "Case date cannot be in the future.")
        due = cleaned.get("due_date")
        if due and case_date and due < case_date:
            self.add_error("due_date", "Expected payment date cannot be before the case date.")
        if cleaned.get("new_contact_name") and not cleaned.get("new_contact_phone"):
            self.add_error("new_contact_phone", "Add a mobile number for the new contact.")
        if not cleaned.get("doctor") and self.self_doctor:
            cleaned["doctor"] = self.instance.doctor = self.self_doctor  # nothing chosen = Self
        return cleaned

    def save_contact(self, case):
        """Create the quick new contact / surgeon and link them to this case's hospital."""
        data = self.cleaned_data
        surgeon = case.surgeon if case.surgeon_id else None
        if data.get("new_surgeon_name"):
            name = re.sub(r"\s+", " ", data["new_surgeon_name"]).strip()
            # Same name already in the practice list -> reuse instead of a duplicate.
            surgeon = find_surgeon(name)
            if surgeon is None:
                surgeon = Surgeon.objects.create(doctor=case.doctor, name=name,
                                                 phone=(data.get("new_surgeon_phone") or "").strip())
            case.surgeon = surgeon
            case.save(update_fields=["surgeon", "updated_at"])
        if surgeon:
            surgeon.link_hospital(case.hospital)
        contact = None
        if data.get("new_contact_name"):
            phone = data["new_contact_phone"].strip()
            # Same mobile already in the practice list -> reuse that contact instead of a duplicate.
            digits = re.sub(r"\D", "", phone)[-10:]
            contact = next((c for c in Contact.objects.all()
                            if digits and re.sub(r"\D", "", c.phone)[-10:] == digits), None)
            if contact is None:
                contact = Contact.objects.create(
                    doctor=case.doctor, name=data["new_contact_name"].strip(),
                    phone=phone, role=data.get("new_contact_role") or "billing",
                )
            case.contact = contact
            case.save(update_fields=["contact", "updated_at"])
        elif case.contact_id:
            contact = case.contact
        if contact:
            ensure_affiliation(contact, case.hospital)
        return contact


class CaseImportForm(forms.Form):
    file = forms.FileField(
        label="Excel file (.xlsx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    )
    doctor = forms.ModelChoiceField(
        queryset=Doctor.objects.none(), required=False, label="Anaesthetist",
        help_text="Used for rows where the Anaesthetist column is empty. Empty here = yourself.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs["class"] = "form-control"
        self.fields["doctor"].queryset = Doctor.objects.registered()
        me = getattr(user, "doctor_profile", None) if user else None
        self.fields["doctor"].empty_label = f"Self ({me})" if me else "Anaesthetist for rows without one"
        self.fields["doctor"].widget.attrs.update({"class": "form-select"})

    def clean_file(self):
        from .importer import MAX_FILE_BYTES

        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Please upload an Excel .xlsx file. (In Excel: File > Save As > Excel Workbook.)")
        if f.size > MAX_FILE_BYTES:
            raise forms.ValidationError("File is larger than 5 MB. Please split it into smaller files.")
        return f
