from apps.dashboard.registry import Module, site

from .models import ContactMessage


@site.register(ContactMessage)
class ContactMessageModule(Module):
    group = "Inbox"
    icon = "ki-sms"
    description = "Messages sent from the website's contact form."
    list_display = ["name", "email", "phone", "branch", "message", "created_at", "is_read"]
    search_fields = ["name", "email", "phone", "message"]
    list_filter = ["is_read", "branch"]
    toggle_fields = ["is_read"]
    fields = ["name", "email", "phone", "branch", "message", "created_at"]
    # Messages for no particular branch are seen by every branch.
    branch_field = "branch"
    branch_optional = True

    # Messages come from visitors, so they are read here but never written.
    can_add = False
    can_change = False

    def badge_count(self, request=None):
        if request is None:
            return None
        return self.queryset_for(request).filter(is_read=False).count() or None

    def on_view(self, obj):
        if not obj.is_read:
            obj.is_read = True
            obj.save(update_fields=["is_read"])
