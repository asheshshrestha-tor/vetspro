from apps.dashboard.registry import Module, site

from .models import ContactMessage


@site.register(ContactMessage)
class ContactMessageModule(Module):
    group = "Inbox"
    icon = "ki-sms"
    description = "Messages sent from the website's contact form."
    list_display = ["name", "email", "phone", "message", "created_at", "is_read"]
    search_fields = ["name", "email", "phone", "message"]
    list_filter = ["is_read"]
    toggle_fields = ["is_read"]
    fields = ["name", "email", "phone", "message", "created_at"]

    # Messages come from visitors, so they are read here but never written.
    can_add = False
    can_change = False

    def badge_count(self):
        return ContactMessage.objects.filter(is_read=False).count() or None

    def on_view(self, obj):
        if not obj.is_read:
            obj.is_read = True
            obj.save(update_fields=["is_read"])
