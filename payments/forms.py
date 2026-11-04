from django import forms
from django.utils import timezone

from contacts.models import Contact
from core.forms import StyledModelForm

from .models import Payment, PaymentFollowUp


class CaseChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, case):
        ref = f" · {case.patient_reference}" if case.patient_reference else ""
        due = "fee to be decided" if case.fee <= 0 and case.total_paid <= 0 else f"due {case.outstanding:,.0f}"
        return f"{case.hospital.name} · {case.case_date:%d %b %Y}{ref} · {due}"


class PaymentForm(StyledModelForm):
    # The fee is often only known when the hospital pays: set or correct it here.
    case_fee = forms.DecimalField(
        label="Case fee (₹)", required=False, min_value=0, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "1"}),
        help_text="Total fee for this case. Change it if the final amount is different.",
    )

    class Meta:
        model = Payment
        fields = ["case", "amount", "payment_date", "mode", "received_by", "reference_no", "notes"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "amount": forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "received_by": forms.TextInput(attrs={"placeholder": "e.g. Dr. Mehta / clinic reception", "list": "received-by-options"}),
        }

    def __init__(self, *args, case_queryset=None, fixed_case=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_case = fixed_case
        if fixed_case is not None and fixed_case.fee > 0 and not self.is_bound:
            fee = fixed_case.fee
            self.initial.setdefault("case_fee", fee.quantize(1) if fee == fee.to_integral() else fee)
            self.fields["case_fee"].help_text = ("Total fee for this case. Leave it as it is: if more is received, "
                                                 "the fee goes up automatically.")
        if fixed_case is not None and fixed_case.fee <= 0:
            self.fields["case_fee"].help_text = ("Optional. Leave empty and the amount received becomes the fee; "
                                                 "enter a total only if more is still to come.")
        if fixed_case is None:
            self.fields["case_fee"].help_text = ("Optional. Leave empty to keep the case's fee (if no fee was set, "
                                                 "the amount received becomes the fee).")
        # Show the fee box right after the amount.
        order = list(self.fields)
        order.remove("case_fee")
        order.insert(order.index("amount") + 1, "case_fee")
        self.order_fields(order)
        if fixed_case is not None:
            self.fields.pop("case")
        else:
            self.fields["case"] = CaseChoiceField(
                queryset=case_queryset, empty_label="Select an unpaid case",
                widget=forms.Select(attrs={
                    "class": "form-select", "data-searchable": "",
                    "data-placeholder": "Search hospital, date or case ref",
                }),
            )

    def _case(self):
        return self.fixed_case or self.cleaned_data.get("case")

    def clean_payment_date(self):
        value = self.cleaned_data["payment_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("Payment date cannot be in the future.")
        return value

    def clean(self):
        cleaned = super().clean()
        case = self._case()
        amount = cleaned.get("amount")
        # Never block a payment: what was received decides the fee (see save_fee).
        self.total_received = None
        if case is not None and amount:
            paid_elsewhere = sum(p.amount for p in case.payments.all() if p.pk != self.instance.pk)
            self.total_received = paid_elsewhere + amount
        return cleaned

    def save_fee(self, case):
        """Set the case's final fee. Returns True if it changed.

        * a fee typed in "Case fee" is used as it is;
        * otherwise, if no fee was set or more was received than the fee,
          the total received becomes the fee.
        """
        new_fee = self.cleaned_data.get("case_fee")
        if new_fee == case.fee:
            new_fee = None  # the pre-filled fee left as it is
        total = getattr(self, "total_received", None)
        if not new_fee and total is not None and (case.fee <= 0 or total > case.fee):
            new_fee = total
        if new_fee and new_fee != case.fee:
            case.fee = new_fee
            case.save(update_fields=["fee", "updated_at"])
            return True
        return False


class FollowUpForm(StyledModelForm):
    class Meta:
        model = PaymentFollowUp
        fields = ["followup_date", "method", "contact", "promised_payment_date", "next_reminder", "notes"]
        widgets = {
            "followup_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "promised_payment_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "next_reminder": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "What did the hospital say?"}),
        }

    def clean_next_reminder(self):
        value = self.cleaned_data.get("next_reminder")
        if value and value <= timezone.localdate():
            raise forms.ValidationError("Choose a date after today.")
        return value


def followup_form(case, *args, **kwargs):
    """FollowUpForm limited to the case doctor's contacts (people at this hospital first)."""
    from contacts.services import contacts_for_hospital

    form = FollowUpForm(*args, **kwargs)
    here, others = contacts_for_hospital(case.hospital_id)
    field = form.fields["contact"]
    field.queryset = Contact.objects.filter(is_active=True)
    field.label = "Spoke to"
    choices = [("", "Not specified")]
    if here:
        choices.append(("At this hospital", [(c.pk, c.name) for c, _ in here]))
    if others:
        choices.append(("Other contacts", [(c.pk, c.name) for c in others]))
    field.widget.choices = choices
    return form
