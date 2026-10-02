from django.utils.html import format_html_join

from apps.dashboard.registry import Badge, Module, site

from .models import ActivityLog


@site.register(ActivityLog)
class ActivityLogModule(Module):
    group = "Staff"
    icon = "ki-security-user"
    name = "activity"
    name_plural = "activity log"
    description = "Who added, changed or deleted what, and when people signed in. Kept for checking, never edited."
    menu_order = 90
    show_on_home = False

    list_display = ["created_at", "username", "action_badge", "model_name", "object_repr", "changed_fields", "ip_address"]
    search_fields = ["username", "object_repr", "model_name"]
    list_filter = ["action", "model_name", "user"]
    date_filter = "created_at"
    fields = ["created_at", "username", "action_badge", "model_name", "object_repr", "object_id", "change_table", "ip_address", "branch"]
    per_page = 50
    can_add = False
    can_change = False
    can_delete = False

    def get_queryset(self):
        return ActivityLog.objects.select_related("user", "branch")

    def action_badge(self, obj):
        return Badge(obj.get_action_display(), obj.action_color)

    action_badge.short_description = "Action"

    def changed_fields(self, obj):
        if obj.action != ActivityLog.UPDATE:
            return ""
        names = [name.replace("_", " ") for name in obj.changes]
        return ", ".join(names[:5]) + ("…" if len(names) > 5 else "")

    changed_fields.short_description = "Fields"

    def change_table(self, obj):
        if not obj.changes:
            return "—"
        rows = [
            (name.replace("_", " "), "" if old is None else old, "" if new is None else new)
            for name, (old, new) in obj.changes.items()
        ]
        return format_html_join(
            "", '<div class="mb-1"><strong>{}</strong>: <span class="text-muted text-decoration-line-through">{}</span> → {}</div>', rows
        )

    change_table.short_description = "Changes"
