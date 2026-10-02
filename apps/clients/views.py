import mimetypes

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import TemplateView

from apps.appointments import permissions as appointment_perms
from apps.appointments.models import Appointment, VaccinationRecord
from apps.appointments.records import pet_tracking
from apps.dashboard.mixins import ModuleMixin
from apps.dashboard.registry import site

from apps.dashboard.views import safe_next

from .forms import PetDocumentForm
from .models import Client, Pet, PetDocument


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
            **document_context(self.request, pet),
            **plan_context(self.request, pet),
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


def document_context(request, pet, visit=None):
    """The documents panel: the pet's files, and an upload form for those allowed to add them."""
    user = request.user
    if not user.has_perm("clients.view_petdocument"):
        return {"documents": None}
    documents = pet.documents.select_related("appointment", "uploaded_by")
    return {
        "documents": documents,
        "document_form": PetDocumentForm(prefix="document") if user.has_perm("clients.add_petdocument") else None,
        "can_delete_documents": user.has_perm("clients.delete_petdocument"),
        "document_visit": visit,
    }


class DocumentPage(ModuleMixin, View):
    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "clients")
        kwargs.setdefault("model_name", "pet")
        super().setup(request, *args, **kwargs)

    def get_pet(self):
        return get_object_or_404(Pet, pk=self.kwargs["pk"])


class DocumentUploadView(DocumentPage):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        self.require(request.user.has_perm("clients.add_petdocument"))
        pet = self.get_pet()
        form = PetDocumentForm(request.POST, request.FILES, prefix="document")
        back = safe_next(request, reverse_pet(pet))
        if not form.is_valid():
            errors = " ".join(error for field_errors in form.errors.values() for error in field_errors)
            messages.error(request, errors or "The file could not be added.")
            return redirect(back)
        document = form.save(commit=False)
        document.pet = pet
        document.uploaded_by = request.user
        visit_id = request.POST.get("appointment", "")
        if visit_id.isdigit():
            document.appointment = pet.appointments.filter(pk=visit_id).first()
        document.save()
        messages.success(request, f"“{document}” added to {pet.name}'s record.")
        return redirect(back)


class DocumentFileView(DocumentPage):
    """Sends a document to someone allowed to see it. The files are never served directly."""

    def get(self, request, *args, **kwargs):
        self.require(request.user.has_perm("clients.view_petdocument"))
        document = get_object_or_404(PetDocument, pk=kwargs["document_pk"], pet_id=kwargs["pk"])
        try:
            handle = document.file.open("rb")
        except FileNotFoundError:
            raise Http404("The file is missing.")
        content_type = mimetypes.guess_type(document.filename)[0] or "application/octet-stream"
        inline = content_type.startswith("image/") or content_type == "application/pdf"
        response = FileResponse(handle, content_type=content_type, as_attachment=not inline, filename=document.filename)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class DocumentDeleteView(DocumentPage):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        self.require(request.user.has_perm("clients.delete_petdocument"))
        document = get_object_or_404(PetDocument, pk=kwargs["document_pk"], pet_id=kwargs["pk"])
        name = str(document)
        document.delete()
        messages.success(request, f"“{name}” was removed.")
        return redirect(safe_next(request, reverse_pet(document.pet)))


def reverse_pet(pet):
    from django.urls import reverse

    return reverse("dashboard:pet_record", args=[pet.pk])


def plan_context(request, pet):
    """The pet's vaccination plan doses, and the plans it can be put on."""
    from apps.appointments.models import PlannedVaccination
    from apps.clinic_setup.models import VaccinationPlan

    can_plan = request.user.has_perm("appointments.change_appointment")
    planned = list(pet.planned_vaccinations.select_related("vaccine", "plan", "record__appointment"))
    plans = []
    if can_plan:
        plans = VaccinationPlan.objects.filter(is_active=True).exclude(doses=None).filter(
            Q(species__isnull=True) | Q(species=pet.species_id)
        ).distinct()
    return {
        "planned_vaccinations": planned,
        "vaccination_plans": plans,
        "can_plan": can_plan,
        "plan_due": sum(1 for dose in planned if dose.status == PlannedVaccination.DUE),
        "today": timezone.localdate(),
    }


class PetPlanView(DocumentPage):
    """Put the pet on a vaccination plan, or skip / restore a planned dose."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        from apps.appointments.models import PlannedVaccination
        from apps.clinic_setup.models import VaccinationPlan

        self.require(request.user.has_perm("appointments.change_appointment"))
        pet = self.get_pet()
        back = reverse_pet(pet) + "#vaccination-plan"
        dose_id = request.POST.get("dose", "")
        if dose_id.isdigit():
            dose = get_object_or_404(PlannedVaccination, pk=dose_id, pet=pet)
            if dose.status == PlannedVaccination.DUE:
                dose.status = PlannedVaccination.SKIPPED
            elif dose.status == PlannedVaccination.SKIPPED:
                dose.status = PlannedVaccination.DUE
            dose.save(update_fields=["status"])
            return redirect(back)
        plan = get_object_or_404(VaccinationPlan, pk=request.POST.get("plan") or 0, is_active=True)
        start = parse_date(request.POST.get("start") or "") or timezone.localdate()
        doses = PlannedVaccination.enrol(pet, plan, start, request.user)
        messages.success(request, f"{pet.name} is on “{plan}”: {len(doses)} dose{'s' if len(doses) != 1 else ''} planned from {start:%d %b %Y}.")
        return redirect(back)

