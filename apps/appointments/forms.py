from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.urls import reverse
from django.utils import timezone

from apps.clients.models import Client, Pet, normalize_phone
from apps.clinic_setup.models import Species
from apps.dashboard.forms import (
    AutocompleteSelect,
    DashboardForm,
    DashboardModelForm,
    DateInput,
    TimeInput,
    formfield_callback,
    style_fields,
)

from .models import Appointment, Treatment, attending_staff


class StaffChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        name = user.get_full_name() or user.get_username()
        profile = getattr(user, "staff_profile", None)
        return f"{name} · {profile.designation}" if profile and profile.designation else name


def staff_queryset(current=None, branch=None):
    """Staff who can attend at the branch, plus whoever already attends this visit (they may have left since)."""
    ids = list(attending_staff(branch).values_list("pk", flat=True))
    if current is not None:
        ids.append(current.pk)
    return (
        get_user_model().objects.filter(pk__in=ids)
        .select_related("staff_profile").order_by("first_name", "last_name", "username")
    )


def active_or_current(queryset, current_ids):
    """Entries in use, plus retired ones this record already refers to."""
    return queryset.filter(is_active=True) | queryset.filter(pk__in=[pk for pk in current_ids if pk])


class WalkInForm(DashboardForm):
    """Registers a visit: pick or add the owner, pick or add the pet, and give the reason."""

    client = forms.ModelChoiceField(queryset=Client.objects.filter(is_active=True), required=False, label="Owner")
    new_client_name = forms.CharField(label="Owner's name", max_length=150, required=False)
    new_client_phone = forms.CharField(label="Phone", max_length=30, required=False)
    new_client_alt_phone = forms.CharField(label="Alternate phone", max_length=30, required=False)
    new_client_address = forms.CharField(label="Address", max_length=255, required=False)
    new_client_area = forms.CharField(label="Area / city", max_length=100, required=False)
    confirm_new_client = forms.BooleanField(
        label="This is a different person; add them as a new client", required=False
    )

    pet = forms.ModelChoiceField(queryset=Pet.objects.filter(is_active=True, is_deceased=False), required=False)
    new_pet_name = forms.CharField(label="Pet's name", max_length=100, required=False)
    new_pet_species = forms.ModelChoiceField(queryset=Species.objects.filter(is_active=True), required=False, label="Species")
    new_pet_breed = forms.CharField(label="Breed", max_length=100, required=False)
    new_pet_sex = forms.ChoiceField(label="Sex", choices=Pet.SEX_CHOICES, initial=Pet.UNKNOWN, required=False)
    new_pet_age_years = forms.IntegerField(label="Age (years)", min_value=0, max_value=40, required=False)
    new_pet_age_months = forms.IntegerField(label="Age (months)", min_value=0, max_value=11, required=False)
    new_pet_color = forms.CharField(label="Colour and markings", max_length=100, required=False)

    visit_date = forms.DateField(widget=DateInput, initial=timezone.localdate)
    scheduled_time = forms.TimeField(
        label="Booked time", required=False, widget=TimeInput,
        help_text="For a visit booked on a later date. Walk-ins today join the queue by token.",
    )
    priority = forms.ChoiceField(
        label="Triage", choices=Appointment.PRIORITY_CHOICES, initial=Appointment.ROUTINE, required=False,
        help_text="Emergency and urgent cases go to the top of the queue.",
    )
    reason = forms.CharField(label="Reason for visit", max_length=255)
    attended_by = StaffChoiceField(queryset=attending_staff(), required=False)
    weight_kg = forms.DecimalField(label="Body weight (kg)", max_digits=6, decimal_places=2, min_value=0, required=False)

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        widgets = {
            "client": AutocompleteSelect(
                reverse("dashboard:autocomplete", args=["clients", "client"]), placeholder="Search by name or phone"
            ),
            "pet": AutocompleteSelect(
                reverse("dashboard:autocomplete", args=["clients", "pet"]),
                forward=("client",),
                placeholder="Choose from the owner's pets",
            ),
        }
        for name, widget in widgets.items():
            field = self.fields[name]
            widget.choices = field.choices
            widget.attrs["class"] = "form-select form-select-solid"
            field.widget = widget
        self.fields["attended_by"].queryset = staff_queryset(branch=branch)
        self.duplicates = Client.objects.none()

    def clean_visit_date(self):
        visit_date = self.cleaned_data["visit_date"]
        if visit_date < timezone.localdate():
            raise forms.ValidationError("A visit cannot be registered for a past date.")
        return visit_date

    def clean(self):
        cleaned = super().clean()
        client = cleaned.get("client")
        pet = cleaned.get("pet")

        if client is None:
            name = cleaned.get("new_client_name", "").strip()
            phone = cleaned.get("new_client_phone", "").strip()
            if not name:
                self.add_error("new_client_name", "Choose an existing owner or enter the new owner's name.")
            if not phone:
                self.add_error("new_client_phone", "Enter a phone number for the new owner.")
            digits = normalize_phone(phone)
            if digits:
                self.duplicates = Client.objects.filter(phone_digits=digits)
                if self.duplicates.exists() and not cleaned.get("confirm_new_client"):
                    self.add_error(
                        "new_client_phone",
                        "An owner with this phone number already exists. Choose them above, "
                        "or tick the box to add a different person.",
                    )
            if pet is not None:
                self.add_error("pet", "A new owner has no pets yet; add the pet below.")
                pet = None

        if pet is not None and client is not None and pet.client_id != client.pk:
            self.add_error("pet", "This pet belongs to a different owner.")
        elif pet is None:
            if not cleaned.get("new_pet_name", "").strip():
                self.add_error("new_pet_name", "Choose one of the owner's pets or enter the new pet's name.")
            if not cleaned.get("new_pet_species"):
                self.add_error("new_pet_species", "Choose the species.")
        return cleaned

    def build_client(self, user):
        data = self.cleaned_data
        if data.get("client"):
            return data["client"]
        return Client.objects.create(
            full_name=data["new_client_name"].strip(),
            phone=data["new_client_phone"].strip(),
            alt_phone=data.get("new_client_alt_phone", "").strip(),
            address=data.get("new_client_address", "").strip(),
            area=data.get("new_client_area", "").strip(),
            created_by=user,
        )

    def build_pet(self, client):
        data = self.cleaned_data
        if data.get("pet"):
            return data["pet"]
        years, months = data.get("new_pet_age_years"), data.get("new_pet_age_months")
        birth_date = Pet.estimate_birth_date(years, months) if (years or months) else None
        return Pet.objects.create(
            client=client,
            name=data["new_pet_name"].strip(),
            species=data["new_pet_species"],
            breed=data.get("new_pet_breed", "").strip(),
            sex=data.get("new_pet_sex") or Pet.UNKNOWN,
            date_of_birth=birth_date,
            dob_is_estimate=birth_date is not None,
            color=data.get("new_pet_color", "").strip(),
        )


class VisitForm(DashboardModelForm):
    """The visit details reception can change."""

    attended_by = StaffChoiceField(queryset=attending_staff(), required=False)

    class Meta:
        model = Appointment
        fields = ["visit_date", "scheduled_time", "priority", "reason", "attended_by", "weight_kg"]
        widgets = {"visit_date": DateInput, "scheduled_time": TimeInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attended_by"].queryset = staff_queryset(self.instance.attended_by, self.instance.branch)
        # Only a booked visit can move to another day or time; a visit that has arrived stays on its day.
        if self.instance.status != Appointment.SCHEDULED:
            del self.fields["visit_date"]
            del self.fields["scheduled_time"]
        self.fields["priority"].required = False

    def clean_priority(self):
        # A form without the triage choice keeps the visit's current triage.
        return self.cleaned_data.get("priority") or self.instance.priority or Appointment.ROUTINE

    def clean_visit_date(self):
        visit_date = self.cleaned_data["visit_date"]
        if visit_date < timezone.localdate():
            raise forms.ValidationError("A follow-up cannot be moved to a past date.")
        return visit_date


class ClinicalForm(DashboardModelForm):
    class Meta:
        model = Appointment
        fields = ["clinical_notes", "diagnosis", "outcome", "result_notes", "follow_up_date"]
        widgets = {"follow_up_date": DateInput}

    def clean_follow_up_date(self):
        follow_up = self.cleaned_data.get("follow_up_date")
        if follow_up and follow_up < self.instance.visit_date:
            raise forms.ValidationError("The follow-up date cannot be before the visit.")
        return follow_up


class TreatmentForm(DashboardModelForm):
    class Meta:
        model = Treatment
        fields = ["item", "kind", "name", "dose", "route", "frequency", "duration", "quantity", "unit_price", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.shop.models import Product

        item = self.fields["item"]
        # Retired catalogue items stay selectable on treatments that already use them.
        item.queryset = Product.objects.filter(is_active=True).exclude(treatment_kind="") | Product.objects.filter(
            pk=self.instance.item_id
        )
        widget = AutocompleteSelect(
            reverse("dashboard:autocomplete", args=["shop", "treatmentitem"]), placeholder="Search the treatment catalogue"
        )
        widget.choices = item.choices
        widget.attrs["class"] = "form-select form-select-solid"
        item.widget = widget
        self.fields["name"].required = False
        self.fields["name"].widget.attrs["placeholder"] = "Medicine / procedure (filled in from the catalogue)"
        for name, hint in (("dose", "Dose"), ("route", "Route"), ("frequency", "Frequency"), ("duration", "Duration"),
                           ("notes", "Notes")):
            self.fields[name].widget.attrs["placeholder"] = hint
        for name in ("quantity", "unit_price"):
            self.fields[name].widget.attrs.update({"step": "any", "min": "0"})

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        item = cleaned.get("item")
        if item is not None:
            if not cleaned.get("name"):
                cleaned["name"] = item.name
            if cleaned.get("unit_price") is None:
                cleaned["unit_price"] = item.price or None
        if not cleaned.get("name"):
            self.add_error("name", "Choose from the catalogue or type the medicine or procedure.")
        quantity = cleaned.get("quantity")
        if quantity is not None and quantity <= 0:
            self.add_error("quantity", "Must be more than zero.")
        return cleaned

    def _post_clean(self):
        for name in ("name", "unit_price"):
            if name in self.cleaned_data:
                setattr(self.instance, name, self.cleaned_data[name])
        super()._post_clean()


TreatmentFormSet = inlineformset_factory(
    Appointment, Treatment, form=TreatmentForm, formfield_callback=formfield_callback, extra=1, can_delete=True
)


def value_formfield(definition, current=""):
    """The input for one admin-defined field, shaped by its value type."""
    if definition.has_options:
        options = definition.option_list
        if current and current not in options:
            options = options + [current]
        field = forms.ChoiceField(required=False, choices=[("", "—")] + [(o, o) for o in options])
    else:
        field = forms.CharField(required=False, max_length=60 if definition.is_number else 255)
        if definition.is_number:
            field.widget.attrs.update({"inputmode": "decimal", "autocomplete": "off"})
    field.label = definition.name
    field.initial = current or ""
    return field


class ValueForm(DashboardForm):
    """One row of the history or examination grid. A blank value means “not recorded”."""

    def __init__(self, *args, definition, current="", previous=None, **kwargs):
        self.definition = definition
        self.previous = previous
        super().__init__(*args, **kwargs)
        self.fields["value"] = value_formfield(definition, current)
        style_fields(self)

    def clean_value(self):
        value = (self.cleaned_data.get("value") or "").strip()
        if value and self.definition.is_number and self.definition.parse_number(value) is None:
            raise forms.ValidationError("Enter a number.")
        return value

    @property
    def is_abnormal(self):
        value = self.data.get(self.add_prefix("value")) if self.is_bound else self.fields["value"].initial
        return self.definition.is_abnormal(value)


class VaccinationRowForm(DashboardForm):
    """One vaccine of the vaccination grid. A row with nothing filled in is not stored."""

    given_on = forms.DateField(required=False, widget=DateInput, label="Given on")
    next_due_date = forms.DateField(required=False, widget=DateInput, label="Next due")
    batch_number = forms.CharField(required=False, max_length=60, label="Batch / lot no.")
    notes = forms.CharField(required=False, max_length=255)

    FIELDS = ("given_on", "next_due_date", "batch_number", "notes")

    def __init__(self, *args, vaccine, visit_date, record=None, previous=None, **kwargs):
        self.vaccine = vaccine
        self.visit_date = visit_date
        self.previous = previous
        super().__init__(*args, **kwargs)
        if record is not None:
            for name in self.FIELDS:
                self.fields[name].initial = getattr(record, name)

    def has_data(self):
        return any(self.cleaned_data.get(name) for name in self.FIELDS)

    def clean(self):
        cleaned = super().clean()
        given, due = cleaned.get("given_on"), cleaned.get("next_due_date")
        if given and given > self.visit_date:
            self.add_error("given_on", "Cannot be after the visit.")
        if given and due and due < given:
            self.add_error("next_due_date", "Cannot be before the date given.")
        return cleaned
