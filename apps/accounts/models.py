from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models


class StaffProfile(models.Model):
    """Hospital details for a dashboard login. Every user has one, created automatically."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="staff_profile", on_delete=models.CASCADE)
    role = models.ForeignKey(
        Group,
        related_name="staff_profiles",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Decides what this person can see and do in the dashboard.",
    )
    designation = models.CharField(max_length=100, blank=True, help_text="e.g. Senior Veterinarian")
    phone = models.CharField(max_length=30, blank=True)
    licence_number = models.CharField("registration / licence number", max_length=60, blank=True)
    can_attend = models.BooleanField(
        "can attend appointments",
        default=True,
        help_text="Shown in the “Attended by” list on appointments. Untick for non-clinical staff.",
    )

    class Meta:
        verbose_name = "staff profile"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.get_username()
