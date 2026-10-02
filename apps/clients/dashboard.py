from django.db.models import Q
from django.urls import path, reverse

from apps.dashboard.registry import Action, Inline, Module, site

from . import views
from .forms import PET_FIELDS, ClientForm, PetForm, PetInlineForm
from .models import Client, Pet, normalize_phone


class PetInline(Inline):
    model = Pet
    fields = ["name", "species", "breed", "sex", "date_of_birth", "color"]
    title = "Pets"
    form_class = PetInlineForm


class PhoneSearchMixin:
    phone_lookup = "phone_digits"

    def search_conditions(self, term):
        conditions = super().search_conditions(term)
        digits = normalize_phone(term)
        if len(digits) >= 4:
            conditions.append(Q(**{f"{self.phone_lookup}__contains": digits}))
        return conditions


@site.register(Client)
class ClientModule(PhoneSearchMixin, Module):
    group = "Clinic"
    icon = "ki-profile-circle"
    description = "Pet owners. Find a returning owner by name or phone number."
    menu_order = 20

    list_display = ["full_name", "phone", "area", "pet_names", "is_active"]
    search_fields = ["full_name", "phone", "alt_phone", "email", "pets__name"]
    list_filter = ["is_active"]
    form_class = ClientForm
    fields = ClientForm.Meta.fields
    inlines = [PetInline]

    def get_queryset(self):
        return Client.objects.prefetch_related("pets")

    def get_urls(self):
        return [path("<int:pk>/record/", views.ClientRecordView.as_view(), name="client_record")]

    def autocomplete_queryset(self, request):
        return super().autocomplete_queryset(request).prefetch_related("pets")

    def autocomplete_label(self, obj, request=None):
        label = f"{obj.full_name} · {obj.phone}" + (f" · {obj.area}" if obj.area else "")
        pets = [pet.name for pet in obj.pets.all() if pet.is_active and not pet.is_deceased]
        return f"{label} — pets: {', '.join(pets)}" if pets else label

    def row_actions(self, obj, request):
        return [Action("Record", reverse("dashboard:client_record", args=[obj.pk]), icon="ki-document", color="light-primary")]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user

    def pet_names(self, obj):
        return ", ".join(pet.name for pet in obj.pets.all())

    pet_names.short_description = "Pets"


@site.register(Pet)
class PetModule(PhoneSearchMixin, Module):
    group = "Clinic"
    icon = "ki-heart"
    description = "Every pet with its owner. Open a pet's record for its full medical history."
    menu_order = 30
    phone_lookup = "client__phone_digits"

    list_display = ["photo", "name", "client", "species", "breed", "sex", "age", "is_active"]
    search_fields = ["name", "client__full_name", "client__phone", "microchip_number", "breed"]
    list_filter = ["species", "sex", "is_deceased", "is_active"]
    form_class = PetForm
    fields = PET_FIELDS
    autocomplete_fields = ["client"]
    autocomplete_filters = ["client"]

    def get_queryset(self):
        return Pet.objects.select_related("client", "species")

    def autocomplete_queryset(self, request):
        return self.get_queryset().filter(is_active=True, is_deceased=False)

    def autocomplete_label(self, obj, request=None):
        details = ", ".join(part for part in [str(obj.species), obj.breed, obj.age_display] if part)
        return f"{obj.name} ({details})"

    def get_urls(self):
        return [
            path("<int:pk>/record/", views.PetRecordView.as_view(), name="pet_record"),
            path("<int:pk>/documents/add/", views.DocumentUploadView.as_view(), name="pet_document_add"),
            path("<int:pk>/vaccination-plan/", views.PetPlanView.as_view(), name="pet_plan"),
            path("<int:pk>/documents/<int:document_pk>/", views.DocumentFileView.as_view(), name="pet_document"),
            path("<int:pk>/documents/<int:document_pk>/delete/", views.DocumentDeleteView.as_view(), name="pet_document_delete"),
        ]

    def row_actions(self, obj, request):
        return [Action("Record", reverse("dashboard:pet_record", args=[obj.pk]), icon="ki-document", color="light-primary")]

    def age(self, obj):
        return obj.age_display

    age.short_description = "Age"
