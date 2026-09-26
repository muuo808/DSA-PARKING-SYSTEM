"""Forms for parking operations (Bootstrap 5 styled)."""

from django import forms

from django_app.payments.models import PaymentMethod

from .models import ParkingSlot, VehicleType


class StyledFormMixin:
    """Applies Bootstrap 5 classes to every widget in a form."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.HiddenInput):
                continue
            else:
                field.widget.attrs.setdefault("class", "form-control")


class BootstrapForm(StyledFormMixin, forms.Form):
    """Base for plain (non-model) forms."""


class BootstrapModelForm(StyledFormMixin, forms.ModelForm):
    """Base for model-bound forms."""


class ParkingSlotForm(BootstrapModelForm):
    """Create a new parking slot (admin only)."""

    class Meta:
        model = ParkingSlot
        fields = ["slot_number", "status"]
        widgets = {
            "slot_number": forms.TextInput(
                attrs={"placeholder": "e.g. A01", "autofocus": True}
            ),
        }

    def clean_slot_number(self) -> str:
        slot_number = self.cleaned_data["slot_number"].strip().upper()
        if not slot_number:
            raise forms.ValidationError("Slot number is required.")
        return slot_number


class VehicleEntryForm(BootstrapForm):
    """Module 3 - register an arriving vehicle."""

    plate_number = forms.CharField(
        max_length=20,
        label="Number plate",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. KDA 123X",
                "autofocus": True,
                "autocomplete": "off",
            }
        ),
    )
    vehicle_type = forms.ChoiceField(
        choices=VehicleType.choices,
        initial=VehicleType.CAR,
        label="Vehicle type",
    )

    def clean_plate_number(self) -> str:
        plate = self.cleaned_data["plate_number"].strip()
        if len(plate) < 3:
            raise forms.ValidationError("Enter a valid number plate.")
        return plate.upper()


class ExitPaymentForm(BootstrapForm):
    """Module 4 - process payment on exit."""

    session_id = forms.IntegerField(widget=forms.HiddenInput)
    payment_method = forms.ChoiceField(
        choices=PaymentMethod.choices,
        label="Payment method",
        initial=PaymentMethod.CASH,
    )
