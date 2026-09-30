from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView

from apps.appointments import permissions as appointment_perms
from apps.appointments.models import Appointment, VaccinationRecord
from apps.appointments.records import pet_tracking
from apps.dashboard.mixins import ModuleMixin
from apps.dashboard.registry import site

from .models import Client, Pet


class RecordPage(ModuleMixin, TemplateView):
    app_label = "clients"
    model_name = ""

    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", self.app_label)
        kwargs.setdefault("model_name", self.model_name)
        super().setup(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        return super().get(request, *args, **kwargs)

    def visit_permissions(self):
        user = self.request.user
        visits = site.for_model(Appointment)
        return {
            "can_view_visits": bool(visits and visits.can_view(user)),
            "can_add_visit": bool(visits and visits.user_can_add(user)),
            "can_view_clinical": appointment_perms.can_view_clinical(user),
        }


class ClientRecordView(RecordPage):
    template_name = "clients/client_record.html"
    model_name = "client"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = get_object_or_404(Client, pk=self.kwargs["pk"])
        access = self.visit_permissions()
        visits = []
        if access["can_view_visits"]:
            visits = client.appointments.select_related("pet__species", "attended_by").order_by("-visit_date", "-id")[:50]
        context.update(
            client=client,
            object=client,
            pets=client.pets.select_related("species").order_by("is_deceased", "-is_active", "name"),
            visits=visits,
            same_phone=client.same_phone()[:5],
            invoices=client.invoices.order_by("-created_at")[:20] if self.request.user.has_perm("billing.view_invoice") else None,
            can_sell=self.request.user.has_perm("billing.add_invoice"),
            can_edit=self.module.user_can_change(self.request.user),
            **access,
        )
        return context


class PetRecordView(RecordPage):
    """The pet's medical record: profile, weight trend, visits and vaccination card."""

    template_name = "clients/pet_record.html"
    model_name = "pet"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pet = get_object_or_404(Pet.objects.select_related("client", "species"), pk=self.kwargs["pk"])
        access = self.visit_permissions()

        visits, weights, vaccination_card = [], [], []
        if access["can_view_visits"]:
            visits = list(
                pet.appointments.select_related("attended_by")
                .prefetch_related("treatments", "vaccinations__vaccine", "examinations__exam_type")
                .order_by("-visit_date", "-id")
            )
            weights = [
                {"date": visit.visit_date.isoformat(), "label": visit.visit_date.strftime("%d %b %Y"), "kg": float(visit.weight_kg)}
                for visit in reversed(visits)
                if visit.weight_kg is not None and visit.status != Appointment.CANCELLED
            ]
            vaccination_card = self.vaccination_card(pet)
        tracking = pet_tracking(pet) if access["can_view_visits"] and access["can_view_clinical"] else None

        context.update(
            pet=pet,
            object=pet,
            client=pet.client,
            visits=visits,
            weights=weights,
            latest_weight=weights[-1] if weights else None,
            vaccination_card=vaccination_card,
            tracking=tracking,
            can_edit=self.module.user_can_change(self.request.user),
            **access,
        )
        return context

    @staticmethod
    def vaccination_card(pet):
        """The latest dose of each vaccine, with how many times it has been given."""
        records = (
            VaccinationRecord.objects.filter(appointment__pet=pet)
            .exclude(appointment__status=Appointment.CANCELLED)
            .select_related("vaccine", "appointment")
            .order_by("-appointment__visit_date", "-given_on", "-id")
        )
        today = timezone.localdate()
        card = {}
        for record in records:
            entry = card.setdefault(record.vaccine_id, {"latest": record, "doses": 0})
            entry["doses"] += 1
        for entry in card.values():
            due = entry["latest"].next_due_date
            entry["overdue"] = bool(due and due < today)
        return sorted(card.values(), key=lambda entry: entry["latest"].vaccine.name)
