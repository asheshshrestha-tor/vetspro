from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel

WEEKDAY_CHOICES = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
]


class DoctorShift(models.Model):
    """One block of a doctor's regular week, e.g. Monday 10:00–17:00 at the main branch."""

    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="shifts", on_delete=models.CASCADE, limit_choices_to={"is_staff": True},
        verbose_name="doctor",
    )
    branch = models.ForeignKey("branches.Branch", related_name="shifts", on_delete=models.CASCADE)
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField("from")
    end_time = models.TimeField("to")

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name = "doctor schedule"
        verbose_name_plural = "doctor schedule"

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Must be after the start time."})


class ScheduleChange(TimeStampedModel):
    """A change to a doctor's regular week: leave (whole days or a few hours) or an extra shift."""

    LEAVE = "leave"
    EXTRA = "extra"
    KIND_CHOICES = [(LEAVE, "Leave / away"), (EXTRA, "Extra shift")]
    KIND_COLORS = {LEAVE: "danger", EXTRA: "success"}

    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="schedule_changes", on_delete=models.CASCADE,
        limit_choices_to={"is_staff": True}, verbose_name="doctor",
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=LEAVE)
    start_date = models.DateField("from date")
    end_date = models.DateField("to date", blank=True, help_text="Leave blank for a single day.")
    start_time = models.TimeField(
        "from time", null=True, blank=True, help_text="Leave the times blank for leave that lasts the whole day."
    )
    end_time = models.TimeField("to time", null=True, blank=True)
    branch = models.ForeignKey(
        "branches.Branch", related_name="+", on_delete=models.CASCADE, null=True, blank=True,
        help_text="Where the extra shift is. Leave applies at every branch.",
    )
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False, related_name="+"
    )

    class Meta:
        ordering = ["-start_date", "start_time"]
        verbose_name = "leave or change"
        verbose_name_plural = "leave & changes"

    def __str__(self):
        name = (self.staff.get_full_name() or self.staff.get_username()) if self.staff_id else ""
        return f"{self.get_kind_display()}: {name}, {self.dates_label}"

    @property
    def dates_label(self):
        if not self.start_date:
            return ""
        end = self.end_date or self.start_date
        if end == self.start_date:
            return f"{self.start_date:%d %b %Y}"
        return f"{self.start_date:%d %b} – {end:%d %b %Y}"

    @property
    def times_label(self):
        if self.start_time and self.end_time:
            return f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        return "Whole day"

    @property
    def is_whole_day(self):
        return self.start_time is None

    def covers_day(self, day):
        return self.start_date <= day <= (self.end_date or self.start_date)

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "Cannot be before the from date."
        if (self.start_time is None) != (self.end_time is None):
            errors["end_time"] = "Give both times, or leave both blank for the whole day."
        elif self.start_time and self.end_time <= self.start_time:
            errors["end_time"] = "Must be after the from time."
        if self.kind == self.EXTRA:
            if self.start_time is None:
                errors.setdefault("start_time", "An extra shift needs its hours.")
            if self.branch_id is None:
                errors["branch"] = "Choose where the extra shift is."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.end_date is None:
            self.end_date = self.start_date
        if self.kind == self.LEAVE:
            self.branch = None
        super().save(*args, **kwargs)
