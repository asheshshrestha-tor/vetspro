from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.dashboard.forms import DashboardForm, DashboardModelForm, DateInput, TimeInput, style_fields

from .models import WEEKDAY_CHOICES, DoctorShift, ScheduleChange

# Up to two blocks a day covers a split shift, e.g. 10:00–13:00 and 16:00–19:00.
BLOCKS = 2


class WeeklyHoursForm(DashboardForm):
    """A doctor's regular week at one branch: one row per weekday, up to two blocks each."""

    def __init__(self, *args, staff, branch, **kwargs):
        self.staff = staff
        self.branch = branch
        super().__init__(*args, **kwargs)
        current = {}
        for shift in DoctorShift.objects.filter(staff=staff, branch=branch).order_by("weekday", "start_time"):
            current.setdefault(shift.weekday, []).append(shift)
        for weekday, _ in WEEKDAY_CHOICES:
            shifts = current.get(weekday, [])
            for index in range(BLOCKS):
                shift = shifts[index] if index < len(shifts) else None
                for part in ("start", "end"):
                    name = self.field_name(weekday, index, part)
                    self.fields[name] = forms.TimeField(required=False, widget=TimeInput, label="")
                    if shift is not None:
                        self.fields[name].initial = getattr(shift, f"{part}_time")
        # The time fields are added after DashboardForm styled the (then empty) form.
        style_fields(self)
        for field in self.fields.values():
            field.widget.attrs["class"] += " form-control-sm"

    @staticmethod
    def field_name(weekday, index, part):
        return f"d{weekday}_{index}_{part}"

    def rows(self):
        """Weekday rows for the template: label and the bound fields of each block."""
        return [
            {
                "weekday": weekday,
                "label": label,
                "blocks": [
                    (self[self.field_name(weekday, index, "start")], self[self.field_name(weekday, index, "end")])
                    for index in range(BLOCKS)
                ],
            }
            for weekday, label in WEEKDAY_CHOICES
        ]

    def clean(self):
        cleaned = super().clean()
        self.blocks = []
        for weekday, _ in WEEKDAY_CHOICES:
            previous_end = None
            for index in range(BLOCKS):
                start_name = self.field_name(weekday, index, "start")
                end_name = self.field_name(weekday, index, "end")
                start, end = cleaned.get(start_name), cleaned.get(end_name)
                if start is None and end is None:
                    continue
                if start is None or end is None:
                    self.add_error(end_name if end is None else start_name, "Give both times.")
                    continue
                if end <= start:
                    self.add_error(end_name, "Must be after the start.")
                    continue
                if previous_end is not None and start < previous_end:
                    self.add_error(start_name, "Overlaps the first block.")
                    continue
                previous_end = end
                self.blocks.append((weekday, start, end))
        return cleaned

    def save(self):
        with transaction.atomic():
            DoctorShift.objects.filter(staff=self.staff, branch=self.branch).delete()
            DoctorShift.objects.bulk_create([
                DoctorShift(staff=self.staff, branch=self.branch, weekday=weekday, start_time=start, end_time=end)
                for weekday, start, end in self.blocks
            ])
        return len(self.blocks)


class StaffChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        name = user.get_full_name() or user.get_username()
        profile = getattr(user, "staff_profile", None)
        return f"{name} · {profile.designation}" if profile and profile.designation else name


class ScheduleChangeForm(DashboardModelForm):
    staff = StaffChoiceField(queryset=None, label="Doctor")

    class Meta:
        model = ScheduleChange
        fields = ["staff", "kind", "start_date", "end_date", "start_time", "end_time", "branch", "reason"]
        widgets = {"start_date": DateInput, "end_date": DateInput, "start_time": TimeInput, "end_time": TimeInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.appointments.models import attending_staff
        from apps.branches.context import allowed_branches
        from apps.branches.models import Branch

        # Doctors who can attend, plus whoever this entry is for (they may no longer attend).
        self.fields["staff"].queryset = (
            get_user_model().objects.filter(Q(pk__in=attending_staff().values("pk")) | Q(pk=self.instance.staff_id))
            .select_related("staff_profile").order_by("first_name", "last_name", "username")
        )
        if self.request is not None:
            branches = Branch.objects.filter(pk__in=[b.pk for b in allowed_branches(self.request)])
        else:
            branches = Branch.objects.filter(is_active=True)
        self.fields["branch"].queryset = branches
        self.fields["reason"].widget.attrs["placeholder"] = "e.g. Annual leave, conference, covering Saturday"
