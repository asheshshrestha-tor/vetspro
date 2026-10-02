from django.utils import timezone

from apps.core.models import SiteSettings

from . import providers
from .models import MessageTemplate, OutboundMessage


def money(value):
    return f"Rs. {value:,.2f}"


def message_values(client=None, pet=None, appointment=None, invoice=None, vaccination=None, planned=None, branch=None):
    """What the {placeholders} stand for, from the records the message is about."""
    site = SiteSettings.load()
    if appointment is not None:
        client, pet, branch = client or appointment.client, pet or appointment.pet, branch or appointment.branch
    if invoice is not None:
        client, branch = client or invoice.client, branch or invoice.branch
    if vaccination is not None:
        appointment_ = vaccination.appointment
        client, pet, branch = client or appointment_.client, pet or appointment_.pet, branch or appointment_.branch
    if planned is not None:
        pet = pet or planned.pet
        client = client or planned.pet.client
    values = {
        "client": client.full_name if client else "",
        "pet": pet.name if pet else "",
        "hospital": site.short_name or site.name,
        "branch": branch.name if branch else "",
        "phone": (branch.effective_phone if branch else site.phone) or "",
        "date": "", "time": "", "vaccine": "", "invoice": "", "amount": "", "balance": "",
    }
    if appointment is not None:
        values["date"] = f"{appointment.visit_date:%d %b %Y}"
        if appointment.scheduled_time:
            values["time"] = f"{appointment.scheduled_time:%H:%M}"
    if vaccination is not None:
        values["vaccine"] = str(vaccination.vaccine)
        if vaccination.next_due_date:
            values["date"] = f"{vaccination.next_due_date:%d %b %Y}"
    if planned is not None:
        values["vaccine"] = str(planned.vaccine)
        values["date"] = f"{planned.due_date:%d %b %Y}"
    if invoice is not None:
        values["invoice"] = invoice.display_number
        values["amount"] = money(invoice.total)
        values["balance"] = money(invoice.balance)
        values["date"] = values["date"] or f"{invoice.invoice_date:%d %b %Y}"
    return values, client


def template_for(purpose):
    return MessageTemplate.objects.filter(purpose=purpose, is_active=True).first() or MessageTemplate.objects.filter(
        purpose=MessageTemplate.GENERAL, is_active=True
    ).first()


def send(channel, to, body, user=None, subject="", purpose=MessageTemplate.GENERAL, mark=(), **related):
    """Send one message and log it. Returns the OutboundMessage; for WhatsApp links, `.url` opens it.

    `mark` are reminders (vaccinations, planned doses) to record as reminded once it has gone out.
    """
    if channel == OutboundMessage.SMS:
        result = providers.send_sms(to, body)
    elif channel == OutboundMessage.WHATSAPP:
        result = providers.send_whatsapp(to, body)
    else:
        result = providers.send_email(to, subject, body)
    message = OutboundMessage.objects.create(
        channel=channel, to=to, subject=subject, body=body, purpose=purpose, status=result.status,
        error=result.error, provider_reference=result.reference, sent_by=user, **related,
    )
    message.url = result.url
    # A reminder that went out (or was opened to send) marks the dose as reminded.
    if result.status != OutboundMessage.FAILED:
        now = timezone.now()
        for record in mark:
            record.reminded_at = now
            record.save(update_fields=["reminded_at"])
    return message
