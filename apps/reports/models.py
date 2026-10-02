from django.db import models


class Report(models.Model):
    """No table: this only gives the Reports page a place in the menu and its permission."""

    class Meta:
        managed = False
        default_permissions = ("view",)
        verbose_name = "report"
        verbose_name_plural = "reports"
