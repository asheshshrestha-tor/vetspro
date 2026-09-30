from django import forms

from apps.clinic_setup.models import Species
from apps.dashboard.forms import DashboardModelForm

from .models import Client, Pet


def limit_species(form):
    """Offer species that are in use, plus the pet's current one if it has since been retired."""
    field = form.fields.get("species")
    if field is not None:
        current = form.instance.species_id if form.instance.pk else None
        field.queryset = Species.objects.filter(is_active=True) | Species.objects.filter(pk=current)


class ClientForm(DashboardModelForm):
    class Meta:
        model = Client
        fields = ["full_name", "phone", "alt_phone", "email", "address", "area", "notes", "is_active"]


PET_FIELDS = [
    "client", "name", "species", "breed", "sex", "is_neutered", "date_of_birth", "age_years", "age_months",
    "dob_is_estimate", "color", "microchip_number", "alerts", "photo", "is_deceased", "date_of_death",
    "notes", "is_active",
]


class PetForm(DashboardModelForm):
    """Pet details. Staff can give an approximate age instead of a date of birth."""

    age_years = forms.IntegerField(label="Age (years)", min_value=0, max_value=40, required=False)
    age_months = forms.IntegerField(label="Age (months)", min_value=0, max_value=11, required=False)
    field_order = PET_FIELDS

    class Meta:
        model = Pet
        fields = PET_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit_species(self)
        self.fields["age_years"].help_text = "If the date of birth is unknown, give the approximate age instead."

    def clean(self):
        cleaned = super().clean()
        years, months = cleaned.get("age_years"), cleaned.get("age_months")
        if not cleaned.get("date_of_birth") and (years or months):
            cleaned["date_of_birth"] = Pet.estimate_birth_date(years, months)
            cleaned["dob_is_estimate"] = True
        return cleaned


class PetInlineForm(DashboardModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit_species(self)
