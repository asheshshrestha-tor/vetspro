from django.urls import path, reverse

from apps.dashboard.registry import Badge, Module, site

from . import views
from .models import MessageTemplate, OutboundMessage


@site.register(OutboundMessage)
class OutboundMessageModule(Module):
    group = "Inbox"
    icon = "ki-message-text-2"
    name = "message"
    name_plural = "messages sent"
    description = "Every SMS, WhatsApp message and email sent to owners from the dashboard."
    menu_order = 20
    show_on_home = False
    branch_field = "branch"
    branch_optional = True

    list_display = ["created_at", "channel_badge", "to", "client", "purpose", "short_body", "status_badge", "sent_by"]
    search_fields = ["to", "body", "client__full_name", "client__phone"]
    list_filter = ["channel", "purpose", "status"]
    date_filter = "created_at"
    fields = ["created_at", "channel", "to", "client", "pet", "appointment", "invoice", "purpose", "subject", "body",
              "status", "error", "sent_by"]
    per_page = 30
    can_change = False
    can_delete = False

    views = {"add": views.ComposeView}

    def get_queryset(self):
        return OutboundMessage.objects.select_related("client", "sent_by", "branch")

    def get_urls(self):
        return [path("reminders/", views.RemindersView.as_view(), name="message_reminders")]

    def menu_items(self, request=None):
        return [
            {
                "title": "Reminders",
                "url": reverse("dashboard:message_reminders"),
                "icon": "ki-notification-on",
                "badge": None,
                "url_names": ["message_reminders"],
            },
            {"title": "Send a message", "url": self.add_url, "icon": "ki-send", "badge": None, "url_names": ["add"]},
            {"title": "Messages sent", "url": self.list_url, "icon": self.icon, "badge": None, "url_names": []},
        ]

    def channel_badge(self, obj):
        colors = {OutboundMessage.SMS: "primary", OutboundMessage.WHATSAPP: "success", OutboundMessage.EMAIL: "info"}
        return Badge(obj.get_channel_display(), colors.get(obj.channel, "secondary"))

    channel_badge.short_description = "Channel"

    def status_badge(self, obj):
        return Badge(obj.get_status_display(), obj.status_color)

    status_badge.short_description = "Status"

    def short_body(self, obj):
        return obj.body[:70] + ("…" if len(obj.body) > 70 else "")

    short_body.short_description = "Message"


@site.register(MessageTemplate)
class MessageTemplateModule(Module):
    group = "Clinic setup"
    icon = "ki-message-edit"
    name = "message template"
    description = (
        "The wording of reminders and other messages to owners. Words in {braces} are filled in when sent: "
        "{client}, {pet}, {date}, {time}, {vaccine}, {invoice}, {amount}, {balance}, {hospital}, {branch}, {phone}."
    )
    menu_order = 60
    show_on_home = False

    list_display = ["name", "purpose", "body", "is_active"]
    search_fields = ["name", "body"]
    list_filter = ["purpose", "is_active"]
    toggle_fields = ["is_active"]
    fields = ["name", "purpose", "subject", "body", "is_active"]
