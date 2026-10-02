import datetime

from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from apps.appointments.models import Appointment, PlannedVaccination, VaccinationRecord, due_vaccinations
from apps.billing.models import Invoice
from apps.branches.context import allowed_ids, current_branch, scope_ids
from apps.clients.models import Client, Pet
from apps.dashboard.forms import DashboardForm
from apps.dashboard.mixins import ModuleMixin
from apps.dashboard.views import safe_next

from . import providers
from .models import MessageTemplate, OutboundMessage
from .services import message_values, send, template_for


class ComposeForm(DashboardForm):
    channel = forms.ChoiceField(choices=OutboundMessage.CHANNELS, widget=forms.RadioSelect)
    to = forms.CharField(max_length=150, label="Send to")
    subject = forms.CharField(max_length=150, required=False, help_text="For emails only.")
    body = forms.CharField(label="Message", widget=forms.Textarea(attrs={"rows": 6}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["channel"].widget.attrs["class"] = "form-check-input"

    def clean(self):
        cleaned = super().clean()
        to, channel = cleaned.get("to", "").strip(), cleaned.get("channel")
        if channel == OutboundMessage.EMAIL and to and "@" not in to:
            self.add_error("to", "Enter an email address.")
        elif channel in (OutboundMessage.SMS, OutboundMessage.WHATSAPP) and to and len(providers.local_number(to)) < 7:
            self.add_error("to", "Enter a phone number.")
        return cleaned


def _get(model, value, queryset=None):
    if not str(value or "").isdigit():
        return None
    return (queryset if queryset is not None else model.objects).filter(pk=value).first()


class MessagePage(ModuleMixin, TemplateView):
    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "messaging")
        kwargs.setdefault("model_name", "outboundmessage")
        super().setup(request, *args, **kwargs)


class ComposeView(MessagePage):
    """Write a message to an owner, filled in from a template, and send it by SMS, WhatsApp or email."""

    template_name = "messaging/compose.html"

    def related(self, source):
        ids = allowed_ids(self.request)
        appointment = _get(Appointment, source.get("appointment"), Appointment.objects.filter(branch_id__in=ids))
        invoice = _get(Invoice, source.get("invoice"), Invoice.objects.filter(branch_id__in=ids))
        vaccination = _get(VaccinationRecord, source.get("vaccination"), VaccinationRecord.objects.select_related("appointment"))
        planned = _get(PlannedVaccination, source.get("planned"), PlannedVaccination.objects.select_related("pet__client"))
        client = _get(Client, source.get("client"))
        pet = _get(Pet, source.get("pet"))
        return {
            "client": client, "pet": pet, "appointment": appointment, "invoice": invoice,
            "vaccination": vaccination, "planned": planned,
        }

    def purpose(self, source, related):
        purpose = source.get("purpose", "")
        if purpose in dict(MessageTemplate.PURPOSES):
            return purpose
        if related["vaccination"] or related["planned"]:
            return MessageTemplate.VACCINATION_DUE
        if related["invoice"]:
            return MessageTemplate.INVOICE
        if related["appointment"]:
            return MessageTemplate.BOOKING if related["appointment"].status == Appointment.SCHEDULED else MessageTemplate.FOLLOW_UP
        return MessageTemplate.GENERAL

    def get(self, request, *args, **kwargs):
        self.require(self.module.user_can_add(request.user))
        related = self.related(request.GET)
        purpose = self.purpose(request.GET, related)
        values, client = message_values(branch=current_branch(request), **related)
        template = template_for(purpose)
        chosen = _get(MessageTemplate, request.GET.get("template"))
        if chosen is not None:
            template = chosen
        body, subject = template.render(values) if template else ("", "")
        channel = OutboundMessage.WHATSAPP
        form = ComposeForm(initial={
            "channel": channel, "to": client.phone if client else "", "subject": subject, "body": body,
        })
        return self.render_to_response(self.get_context_data(
            form=form, related=related, client=client, purpose=purpose, template=template,
        ))

    def post(self, request, *args, **kwargs):
        self.require(self.module.user_can_add(request.user))
        related = self.related(request.POST)
        purpose = self.purpose(request.POST, related)
        _, client = message_values(**related)
        form = ComposeForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form, related=related, client=client, purpose=purpose))
        data = form.cleaned_data
        appointment = related["appointment"] or (related["vaccination"].appointment if related["vaccination"] else None)
        branch = (
            (related["invoice"].branch if related["invoice"] else None)
            or (appointment.branch if appointment else None)
            or current_branch(request)
        )
        message = send(
            data["channel"], data["to"].strip(), data["body"], user=request.user, subject=data.get("subject", ""),
            purpose=purpose, mark=[r for r in (related["vaccination"], related["planned"]) if r is not None],
            client=client, pet=related["pet"] or (appointment.pet if appointment else None) or (related["planned"].pet if related["planned"] else None),
            appointment=appointment, invoice=related["invoice"], branch=branch,
        )
        if message.status == OutboundMessage.FAILED:
            messages.error(request, f"The message could not be sent: {message.error}")
            return self.render_to_response(self.get_context_data(form=form, related=related, client=client, purpose=purpose))
        if message.url:
            return self.render_to_response(self.get_context_data(whatsapp_url=message.url, message=message,
                                                                 back=safe_next(request, self.module.list_url)),
                                           template_name="messaging/whatsapp.html")
        if message.status == OutboundMessage.LOGGED:
            messages.warning(request, "Saved in the message log. No SMS provider is set up, so it was not delivered.")
        else:
            messages.success(request, f"{message.get_channel_display()} sent to {message.to}.")
        return redirect(safe_next(request, self.module.list_url))

    def render_to_response(self, context, template_name=None, **kwargs):
        if template_name:
            self.template_name = template_name
        return super().render_to_response(context, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = kwargs.get("client")
        context.update(
            channels=providers.channel_status(),
            templates=MessageTemplate.objects.filter(is_active=True),
            client_email=client.email if client else "",
            client_phone=client.phone if client else "",
            placeholders=MessageTemplate.PLACEHOLDERS,
            next_url=self.request.GET.get("next") or self.request.POST.get("next", ""),
        )
        return context


class RemindersView(MessagePage):
    """Who to remind: vaccinations and planned doses coming due, and tomorrow's bookings."""

    template_name = "messaging/reminders.html"

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user) or self.module.user_can_add(request.user))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Record a reminder given by phone or in person."""
        self.require(self.module.user_can_add(request.user))
        record = _get(VaccinationRecord, request.POST.get("vaccination"),
                      VaccinationRecord.objects.filter(appointment__branch_id__in=allowed_ids(request)))
        record = record or _get(PlannedVaccination, request.POST.get("planned"))
        if record is not None:
            record.reminded_at = timezone.now()
            record.save(update_fields=["reminded_at"])
            messages.success(request, "Marked as reminded.")
        return redirect(request.get_full_path())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        try:
            days = max(1, min(int(self.request.GET.get("days", 14)), 90))
        except ValueError:
            days = 14
        branch_ids = scope_ids(self.request)
        start, end = today - datetime.timedelta(days=30), today + datetime.timedelta(days=days)
        vaccinations = list(due_vaccinations(start, end, branch_ids))
        planned = list(
            PlannedVaccination.objects.filter(status=PlannedVaccination.DUE, due_date__range=(start, end))
            .exclude(pet__is_deceased=True)
            .select_related("pet__client", "pet__species", "vaccine")
        )
        bookings = list(
            Appointment.objects.filter(
                status=Appointment.SCHEDULED, branch_id__in=branch_ids,
                visit_date__range=(today, today + datetime.timedelta(days=1)),
            ).select_related("client", "pet", "branch").order_by("visit_date", "scheduled_time")
        )
        context.update(
            today=today, days=days, day_options=[7, 14, 30, 60],
            vaccinations=vaccinations, planned=planned, bookings=bookings,
            can_send=self.module.user_can_add(self.request.user),
            show_branch=len(branch_ids) > 1,
        )
        return context
