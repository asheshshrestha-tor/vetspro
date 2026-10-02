import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import TemplateView

from apps.clients.models import Client, Pet
from apps.clinic_setup.models import ExaminationType, HistoryOption, Species, VaccinationType
from apps.dashboard.mixins import ModuleMixin
from apps.dashboard.views import safe_next

from . import permissions as perms
from .forms import ClinicalForm, TreatmentFormSet, VisitForm, WalkInForm
from .models import Appointment, apply_treatment_template, can_attend
from apps.branches.context import allowed_ids, current_branch, is_all_mode, require_branch, scope_ids
from .records import build_grids, field_list, grids_have_input, save_grids


def queue_url(day=None, board=False):
    url = reverse("dashboard:appointment_queue")
    params = []
    if day and day != timezone.localdate():
        params.append(f"date={day.isoformat()}")
    if board:
        params.append("view=board")
    return url + ("?" + "&".join(params) if params else "")


def status_actions(appointment, user, in_queue=False):
    """Buttons for the status changes this user may make now."""
    labels = {
        "check_in": ("Check in", "ki-entrance-left", "light-primary"),
        "start": ("Start consultation", "ki-pulse", "primary"),
        "complete": ("Complete", "ki-check-circle", "success"),
        "cancel": ("Cancel", "ki-cross-circle", "light-danger"),
        "reopen": ("Reopen", "ki-arrows-circle", "light-warning"),
        "restore": ("Restore", "ki-arrows-circle", "light-primary"),
    }
    actions = []
    for action, (label, icon, color) in labels.items():
        if in_queue and action == "complete" and appointment.status == Appointment.WAITING:
            continue
        if perms.can_apply(user, appointment, action):
            actions.append(
                {
                    "action": action,
                    "label": label,
                    "icon": icon,
                    "color": color,
                    "url": reverse("dashboard:appointment_status", args=[appointment.pk, action]),
                    "ask_reason": action == "cancel",
                }
            )
    return actions


class AppointmentPage(ModuleMixin):
    """Base for the appointment pages: resolves the module and checks view access."""

    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "appointments")
        kwargs.setdefault("model_name", "appointment")
        super().setup(request, *args, **kwargs)

    def get_appointment(self):
        # Only visits at the person's branches can be opened.
        return get_object_or_404(
            Appointment.objects.filter(branch_id__in=allowed_ids(self.request)).select_related(
                "branch", "client", "pet__species", "attended_by__staff_profile", "created_by", "updated_by",
                "follow_up_of",
            ),
            pk=self.kwargs["pk"],
        )


class QueueView(AppointmentPage, TemplateView):
    template_name = "appointments/queue.html"

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        return super().get(request, *args, **kwargs)

    def get_day(self):
        return parse_date(self.request.GET.get("date") or "") or timezone.localdate()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        day = self.get_day()
        today = timezone.localdate()

        branch_ids = scope_ids(self.request)
        visits = (
            Appointment.objects.on(day)
            .filter(branch_id__in=branch_ids)
            .select_related("branch", "client", "pet__species", "attended_by")
            .order_by("scheduled_time", "token", "arrival_time", "id")
        )
        rows = {status: [] for status, _ in Appointment.STATUS_CHOICES}
        for visit in visits:
            rows[visit.status].append({"visit": visit, "actions": status_actions(visit, user, in_queue=True)})

        # Follow-ups that were due earlier and never arrived are shown on today's queue.
        overdue = []
        if day == today:
            for visit in (
                Appointment.objects.filter(status=Appointment.SCHEDULED, visit_date__lt=today, branch_id__in=branch_ids)
                .select_related("branch", "client", "pet__species", "attended_by")
                .order_by("visit_date")
            ):
                overdue.append({"visit": visit, "actions": status_actions(visit, user, in_queue=True)})

        counts = dict(visits.values_list("status").annotate(total=Count("id")))
        board = self.request.GET.get("view") == "board"
        context.update(
            day=day,
            is_today=day == today,
            previous_day=queue_url(day - datetime.timedelta(days=1), board),
            next_day=queue_url(day + datetime.timedelta(days=1), board),
            today_url=queue_url(board=board),
            list_url=queue_url(day),
            board_url=queue_url(day, board=True),
            # With the vet first; then waiting pets by triage (emergency first) and token.
            in_queue_sorted=sorted(
                rows[Appointment.IN_CONSULTATION] + rows[Appointment.WAITING],
                key=lambda row: (
                    row["visit"].status != Appointment.IN_CONSULTATION,
                    Appointment.PRIORITY_RANK.get(row["visit"].priority, 9),
                    row["visit"].token or 0,
                ),
            ),
            board=board,
            board_columns=[
                ("Waiting", "warning", sorted(
                    rows[Appointment.WAITING],
                    key=lambda row: (Appointment.PRIORITY_RANK.get(row["visit"].priority, 9), row["visit"].token or 0),
                )),
                ("In consultation", "primary", rows[Appointment.IN_CONSULTATION]),
                ("Completed", "success", rows[Appointment.COMPLETED]),
            ],
            show_branch=is_all_mode(self.request),
            branch=current_branch(self.request),
            scheduled=rows[Appointment.SCHEDULED],
            overdue=overdue,
            finished=rows[Appointment.COMPLETED] + rows[Appointment.CANCELLED],
            can_bill=user.has_perm("billing.add_invoice"),
            status_counts=[
                {"label": label, "count": counts.get(status, 0), "color": Appointment.STATUS_COLORS[status]}
                for status, label in Appointment.STATUS_CHOICES
            ],
            total=sum(counts.values()),
        )
        return context


class WalkInView(AppointmentPage, TemplateView):
    template_name = "appointments/walk_in.html"

    def get_initial(self):
        initial = {"visit_date": parse_date(self.request.GET.get("date") or "") or timezone.localdate()}
        user = self.request.user
        if can_attend(user, self.branch):
            initial["attended_by"] = user.pk
        client_id, pet_id = self.request.GET.get("client"), self.request.GET.get("pet")
        pet = Pet.objects.filter(pk=pet_id, is_active=True).first() if pet_id and pet_id.isdigit() else None
        if pet is not None:
            initial["client"], initial["pet"] = pet.client_id, pet.pk
        elif client_id and client_id.isdigit() and Client.objects.filter(pk=client_id).exists():
            initial["client"] = int(client_id)
        return initial

    def get(self, request, *args, **kwargs):
        self.require(self.module.user_can_add(request.user))
        self.branch = require_branch(request)
        form = WalkInForm(initial=self.get_initial(), request=request, branch=self.branch)
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        self.require(self.module.user_can_add(request.user))
        self.branch = require_branch(request)
        form = WalkInForm(request.POST, request=request, branch=self.branch)
        if not form.is_valid():
            messages.error(request, "Please correct the errors below.")
            return self.render_to_response(self.get_context_data(form=form))

        data = form.cleaned_data
        today = timezone.localdate()
        with transaction.atomic():
            client = form.build_client(request.user)
            pet = form.build_pet(client)
            visit = Appointment(
                branch=self.branch,
                client=client,
                pet=pet,
                visit_date=data["visit_date"],
                status=Appointment.WAITING if data["visit_date"] == today else Appointment.SCHEDULED,
                scheduled_time=data.get("scheduled_time") if data["visit_date"] != today else None,
                priority=data.get("priority") or Appointment.ROUTINE,
                reason=data["reason"].strip(),
                attended_by=data.get("attended_by"),
                weight_kg=data.get("weight_kg"),
                created_by=request.user,
                updated_by=request.user,
            )
            visit.full_clean()
            visit.save()
            if "_start" in request.POST and perms.can_apply(request.user, visit, "start"):
                visit.apply("start", user=request.user)

        if visit.status == Appointment.SCHEDULED:
            when = f"{visit.visit_date:%d %b %Y}" + (f" at {visit.scheduled_time:%H:%M}" if visit.scheduled_time else "")
            messages.success(request, f"{pet.name} is booked for {when} ({visit.number}).")
            return redirect(queue_url(visit.visit_date))
        messages.success(request, f"Token {visit.token}: {pet.name} ({client.full_name}) is in the queue.")
        if visit.status == Appointment.IN_CONSULTATION:
            return redirect(visit.get_absolute_url())
        return redirect(queue_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        context["duplicates"] = list(form.duplicates[:5]) if form.is_bound else []
        context["can_start"] = self.request.user.has_perm("appointments.change_appointment")
        context["branch"] = self.branch
        return context


def document_context(request, pet, visit):
    from apps.clients.views import document_context as build

    return build(request, pet, visit)


class ConsultationView(AppointmentPage, TemplateView):
    """The visit page: booking details for reception, the clinical tabs for vets."""

    template_name = "appointments/consultation.html"

    def setup_permissions(self):
        user = self.request.user
        visit = self.visit
        self.require(self.module.can_view(user))
        self.can_view_clinical = perms.can_view_clinical(user)
        self.can_edit_visit = perms.can_change(user, visit)
        self.can_edit_clinical = self.can_edit_visit and perms.can_record_clinical(user)

    def build_forms(self, data=None):
        visit = self.visit
        forms = {}
        if self.can_edit_visit:
            forms["visit_form"] = VisitForm(data, instance=visit, prefix="visit", request=self.request)
        if self.can_edit_clinical:
            forms["clinical_form"] = ClinicalForm(data, instance=visit, prefix="clinical", request=self.request)
            forms["treatment_formset"] = TreatmentFormSet(data, instance=visit, prefix="treatment")
            forms.update(build_grids(visit, data))
        return forms

    def get(self, request, *args, **kwargs):
        self.visit = self.get_appointment()
        self.setup_permissions()
        return self.render_to_response(self.get_context_data(**self.build_forms()))

    def post(self, request, *args, **kwargs):
        self.visit = self.get_appointment()
        self.setup_permissions()
        self.require(self.can_edit_visit)

        forms = self.build_forms(request.POST)
        complete = "_complete" in request.POST
        if complete and not perms.can_apply(request.user, self.visit, "complete"):
            complete = False

        if not self.all_valid(forms):
            messages.error(request, "Please correct the errors below.")
            return self.render_to_response(self.get_context_data(**forms))

        with transaction.atomic():
            visit = self.visit
            if "visit_form" in forms:
                forms["visit_form"].save(commit=False)
            if "clinical_form" in forms:
                forms["clinical_form"].save(commit=False)
                forms["treatment_formset"].save()
                save_grids(visit, forms)
                # Recording clinical details means the consultation has started.
                if visit.status == Appointment.WAITING and self.has_clinical_input(forms):
                    visit.apply("start", user=request.user)
            visit.updated_by = request.user
            visit.save()
            if complete:
                visit.apply("complete", user=request.user)

        template_id = request.POST.get("_template", "")
        if template_id.isdigit() and self.can_edit_clinical and not complete:
            from apps.clinic_setup.models import TreatmentTemplate

            template = TreatmentTemplate.objects.filter(pk=template_id, is_active=True).first()
            if template is not None:
                added = apply_treatment_template(visit, template)
                messages.success(request, f"“{template}” added {added} treatment line{'s' if added != 1 else ''}. Adjust them for {visit.pet.name} and save.")
                return redirect(visit.get_absolute_url() + "#result")

        bill = "_bill" in request.POST
        invoice = self.update_bill(visit, explicit=bill) if (bill or complete) else None

        if complete:
            messages.success(request, f"{visit.number} is complete.")
            if visit.follow_up_date and not visit.follow_ups.exists():
                messages.info(request, "A follow-up date is set. Use “Create follow-up” to book it.")
            return redirect(visit.get_absolute_url())
        if bill and invoice is not None:
            return redirect(invoice.get_absolute_url())
        messages.success(request, f"{visit.number} was saved.")
        if "_continue" in request.POST:
            return redirect(visit.get_absolute_url())
        return redirect(safe_next(request, queue_url(visit.visit_date)))

    def update_bill(self, visit, explicit):
        """Build the visit's bill from its treatment.

        Asked for explicitly, it always runs and explains any problem. On completing a visit it
        runs quietly, and only when there is something to charge and the bill is still a draft.
        """
        from apps.billing.services import build_visit_bill, current_visit_bill

        request = self.request
        existing = current_visit_bill(visit)
        needed = "billing.add_invoice" if existing is None else "billing.change_invoice"
        if not request.user.has_perm(needed):
            if explicit:
                messages.error(request, "Saved, but your role is not allowed to create or change bills.")
            return None
        if not explicit:
            if existing is not None and not existing.is_draft:
                return None
            fee = visit.branch.effective_visit_fee_item
            has_charges = visit.treatments.filter(unit_price__gt=0, quantity__gt=0).exists() or (fee and fee.is_active)
            if existing is None and not has_charges:
                return None
        try:
            invoice, created = build_visit_bill(visit, request.user)
        except ValidationError as error:
            messages.warning(request, " ".join(error.messages))
            return None
        action = "created" if created else "updated"
        messages.info(request, f"Bill {action} from the treatment: Rs. {invoice.total:,.2f}. Open it to add shop items and issue it.")
        return invoice

    @staticmethod
    def all_valid(forms):
        valid = True
        for value in forms.values():
            for form in value if isinstance(value, list) else [value]:
                valid = form.is_valid() and valid
        return valid

    @staticmethod
    def has_clinical_input(forms):
        clinical = forms["clinical_form"]
        if any(clinical.cleaned_data.get(name) for name in ("clinical_notes", "diagnosis", "outcome")):
            return True
        if grids_have_input(forms):
            return True
        return any(form.has_changed() for form in forms["treatment_formset"].forms)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visit = self.visit
        user = self.request.user
        context.update(
            visit=visit,
            object=visit,
            pet=visit.pet,
            client=visit.client,
            can_view_clinical=self.can_view_clinical,
            can_edit_visit=self.can_edit_visit,
            can_edit_clinical=self.can_edit_clinical,
            can_complete=perms.can_apply(user, visit, "complete"),
            actions=status_actions(visit, user),
            can_follow_up=(
                bool(visit.follow_up_date)
                and visit.follow_up_date >= timezone.localdate()
                and self.module.user_can_add(user)
                and visit.status != Appointment.CANCELLED
            ),
            follow_up=visit.follow_ups.exclude(status=Appointment.CANCELLED).first(),
            history=visit.history.select_related("option"),
            examinations=visit.examinations.select_related("exam_type"),
            vaccinations=visit.vaccinations.select_related("vaccine"),
            treatments=visit.treatments.all(),
            previous_visits=(
                visit.pet.appointments.exclude(pk=visit.pk)
                .exclude(status=Appointment.CANCELLED)
                .select_related("attended_by")
                .order_by("-visit_date", "-id")[:5]
            ),
            visit_date_iso=visit.visit_date.isoformat(),
            invoices=visit.invoices.order_by("-created_at") if user.has_perm("billing.view_invoice") else None,
            can_bill=user.has_perm("billing.add_invoice") or user.has_perm("billing.view_invoice"),
            can_create_bill=user.has_perm("billing.add_invoice"),
            back_url=safe_next(self.request, queue_url(visit.visit_date)),
            **document_context(self.request, visit.pet, visit),
            treatment_templates=self.treatment_templates() if self.can_edit_clinical else [],
        )
        return context

    @staticmethod
    def treatment_templates():
        from apps.clinic_setup.models import TreatmentTemplate

        return TreatmentTemplate.objects.filter(is_active=True).exclude(lines=None).distinct()


class StatusView(AppointmentPage, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        visit = self.get_appointment()
        action = kwargs["action"]
        if action not in Appointment.TRANSITIONS:
            raise Http404("Unknown action.")
        self.require(perms.can_apply(request.user, visit, action))
        try:
            visit.apply(action, user=request.user, reason=request.POST.get("reason", "").strip())
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"{visit.number} ({visit.pet.name}) is now {visit.get_status_display().lower()}.")
        return redirect(safe_next(request, queue_url(visit.visit_date)))


class FollowUpView(AppointmentPage, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        visit = self.get_appointment()
        self.require(self.module.user_can_add(request.user))
        if not visit.follow_up_date or visit.follow_up_date < timezone.localdate():
            messages.error(request, "Set a follow-up date from today onwards first.")
            return redirect(visit.get_absolute_url())
        follow_up, created = visit.create_follow_up(request.user)
        if created:
            messages.success(request, f"Follow-up {follow_up.number} booked for {follow_up.visit_date:%d %b %Y}.")
        else:
            messages.info(request, f"A follow-up is already booked: {follow_up.number}.")
        return redirect(follow_up.get_absolute_url())


class PrintView(AppointmentPage, TemplateView):
    template_name = "appointments/print.html"

    def get(self, request, *args, **kwargs):
        self.visit = self.get_appointment()
        self.require(self.module.can_view(request.user) and perms.can_view_clinical(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visit = self.visit
        context.update(
            visit=visit,
            pet=visit.pet,
            client=visit.client,
            history=visit.history.select_related("option"),
            examinations=visit.examinations.select_related("exam_type"),
            vaccinations=visit.vaccinations.select_related("vaccine"),
            treatments=visit.treatments.all(),
            printed_at=timezone.localtime(),
        )
        return context


class VisitFormPrintView(AppointmentPage, TemplateView):
    """The visit on the hospital's registration form, ready to print; blank when no visit is given."""

    template_name = "appointments/visit_form.html"

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        self.visit = None
        if "pk" in kwargs:
            self.visit = self.get_appointment()
            self.require(perms.can_view_clinical(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visit = self.visit
        history, exams, vaccines = {}, {}, {}
        if visit is not None:
            history = {r.option_id: r for r in visit.history.all()}
            exams = {r.exam_type_id: r for r in visit.examinations.all()}
            vaccines = {r.vaccine_id: r for r in visit.vaccinations.all()}

        context.update(
            visit=visit,
            pet=visit.pet if visit else None,
            client=visit.client if visit else None,
            species_list=field_list(Species, [visit.pet.species_id] if visit else []),
            history_cells=[{"field": f, "record": history.get(f.pk)} for f in field_list(HistoryOption, history)],
            vaccine_cells=[{"field": f, "record": vaccines.get(f.pk)} for f in field_list(VaccinationType, vaccines)],
            exam_cells=[{"field": f, "record": exams.get(f.pk)} for f in field_list(ExaminationType, exams)],
            treatments=visit.treatments.all() if visit else [],
            printed_at=timezone.localtime(),
        )
        return context


class BookingsView(AppointmentPage, TemplateView):
    """Booked visits for a week, day by day and in time order."""

    template_name = "appointments/bookings.html"

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        start = parse_date(self.request.GET.get("week") or "") or today
        start -= datetime.timedelta(days=start.weekday())
        days = [start + datetime.timedelta(days=i) for i in range(7)]
        bookings = (
            Appointment.objects.filter(
                branch_id__in=scope_ids(self.request), visit_date__range=(days[0], days[-1]),
                status__in=[Appointment.SCHEDULED, Appointment.WAITING, Appointment.IN_CONSULTATION, Appointment.COMPLETED],
            )
            .exclude(scheduled_time__isnull=True, status__in=[Appointment.WAITING, Appointment.IN_CONSULTATION, Appointment.COMPLETED])
            .select_related("branch", "client", "pet__species", "attended_by")
            .order_by("visit_date", "scheduled_time", "id")
        )
        by_day = {day: [] for day in days}
        for visit in bookings:
            by_day[visit.visit_date].append(visit)
        week_url = reverse("dashboard:appointment_bookings")
        context.update(
            days=[{"date": day, "is_today": day == today, "visits": by_day[day]} for day in days],
            start=days[0],
            end=days[-1],
            previous_week=f"{week_url}?week={(start - datetime.timedelta(days=7)).isoformat()}",
            next_week=f"{week_url}?week={(start + datetime.timedelta(days=7)).isoformat()}",
            this_week=week_url,
            show_branch=is_all_mode(self.request),
            total=len(bookings),
        )
        return context

