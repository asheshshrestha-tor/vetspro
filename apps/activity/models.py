from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """Who did what in the dashboard: records added, changed or deleted, and sign-ins."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    ACTIONS = [
        (CREATE, "Added"),
        (UPDATE, "Changed"),
        (DELETE, "Deleted"),
        (LOGIN, "Signed in"),
        (LOGOUT, "Signed out"),
        (LOGIN_FAILED, "Failed sign-in"),
    ]
    ACTION_COLORS = {CREATE: "success", UPDATE: "primary", DELETE: "danger", LOGIN: "info", LOGOUT: "secondary", LOGIN_FAILED: "warning"}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    username = models.CharField(max_length=150, blank=True, help_text="Kept if the account is later deleted.")
    action = models.CharField(max_length=15, choices=ACTIONS, db_index=True)
    app_label = models.CharField(max_length=50, blank=True)
    model_name = models.CharField("record type", max_length=100, blank=True, db_index=True)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField("record", max_length=200, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField("IP address", null=True, blank=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "activity"
        verbose_name_plural = "activity log"
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.username or 'System'} {self.get_action_display().lower()} {self.object_repr}".strip()

    @property
    def action_color(self):
        return self.ACTION_COLORS.get(self.action, "secondary")
