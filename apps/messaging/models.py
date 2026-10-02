from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class MessageTemplate(TimeStampedModel):
    """Wording for a message to owners. Words in {braces} are filled in when it is sent."""

    VACCINATION_DUE = "vaccination_due"
    FOLLOW_UP = "follow_up"
    BOOKING = "booking"
    INVOICE = "invoice"
    GENERAL = "general"
    PURPOSES = [
        (VACCINATION_DUE, "Vaccination reminder"),
        (FOLLOW_UP, "Follow-up reminder"),
        (BOOKING, "Booking confirmation"),
        (INVOICE, "Bill / receipt"),
        (GENERAL, "General message"),
    ]
    PLACEHOLDERS = {
        "client": "owner's name",
        "pet": "pet's name",
        "date": "due or visit date",
        "time": "booked time",
        "vaccine": "vaccine name",
        "invoice": "invoice number",
        "amount": "bill total",
        "balance": "amount still due",
        "hospital": "hospital name",
        "branch": "branch name",
        "phone": "branch phone",
    }

    name = models.CharField(max_length=100, unique=True)
    purpose = models.CharField(max_length=20, choices=PURPOSES, default=GENERAL, db_index=True)
    subject = models.CharField(max_length=150, blank=True, help_text="For emails only.")
    body = models.TextField(
        help_text="You can use {client}, {pet}, {date}, {time}, {vaccine}, {invoice}, {amount}, {balance}, "
        "{hospital}, {branch} and {phone}."
    )
    is_active = models.BooleanField("in use", default=True)

    class Meta:
        ordering = ["purpose", "name"]
        verbose_name = "message template"

    def __str__(self):
        return self.name

    def render(self, values):
        return render_text(self.body, values), render_text(self.subject, values)


class _Blank(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render_text(text, values):
    """Fill {placeholders}; unknown ones are left as they are rather than failing."""
    try:
        return (text or "").format_map(_Blank({k: "" if v is None else v for k, v in values.items()}))
    except (ValueError, IndexError):
        return text or ""


class OutboundMessage(models.Model):
    """Every message sent (or opened in WhatsApp) to an owner, so the team can see who was contacted."""

    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CHANNELS = [(SMS, "SMS"), (WHATSAPP, "WhatsApp"), (EMAIL, "Email")]

    SENT = "sent"
    OPENED = "opened"
    LOGGED = "logged"
    FAILED = "failed"
    STATUSES = [
        (SENT, "Sent"),
        (OPENED, "Opened in WhatsApp"),
        (LOGGED, "Logged only (no provider set up)"),
        (FAILED, "Failed"),
    ]
    STATUS_COLORS = {SENT: "success", OPENED: "info", LOGGED: "secondary", FAILED: "danger"}

    channel = models.CharField(max_length=10, choices=CHANNELS)
    to = models.CharField(max_length=150)
    subject = models.CharField(max_length=150, blank=True)
    body = models.TextField()
    purpose = models.CharField(max_length=20, choices=MessageTemplate.PURPOSES, default=MessageTemplate.GENERAL)
    status = models.CharField(max_length=10, choices=STATUSES, default=LOGGED, db_index=True)
    error = models.CharField(max_length=255, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True)

    client = models.ForeignKey("clients.Client", related_name="messages", on_delete=models.SET_NULL, null=True, blank=True)
    pet = models.ForeignKey("clients.Pet", related_name="+", on_delete=models.SET_NULL, null=True, blank=True)
    appointment = models.ForeignKey(
        "appointments.Appointment", related_name="+", on_delete=models.SET_NULL, null=True, blank=True
    )
    invoice = models.ForeignKey("billing.Invoice", related_name="+", on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey("branches.Branch", related_name="+", on_delete=models.SET_NULL, null=True, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "message"
        verbose_name_plural = "messages sent"

    def __str__(self):
        return f"{self.get_channel_display()} to {self.to}"

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, "secondary")
