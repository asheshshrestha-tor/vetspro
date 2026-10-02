from django.urls import path
from django.utils import timezone

from apps.branches.context import scope_ids
from apps.dashboard.registry import Badge, Module, site

from . import views
from .availability import doctors_on, staff_name
from .forms import ScheduleChangeForm
from .models import DoctorShift, ScheduleChange


@site.register(DoctorShift)
class DoctorScheduleModule(Module):
    group = "Clinic"
    icon = "ki-calendar-tick"
    description = "Each doctor's regular hours, week by week, with leave and extra shifts."
    menu_order = 11
    show_on_home = False

    list_display = ["staff", "weekday", "start_time", "end_time", "branch"]
    branch_field = "branch"
    can_add = False
    views = {"list": views.ScheduleView}

    def get_urls(self):
        return [
            path("hours/<int:user_id>/", views.WeeklyHoursView.as_view(), name="schedule_hours"),
            path("availability/", views.AvailabilityView.as_view(), name="schedule_availability"),
        ]

    def menu_items(self, request=None):
        return [{"title": "Doctor schedule", "url": self.list_url, "icon": self.icon, "badge": None, "url_names": []}]

    def home_panel(self, request):
        rows = doctors_on(timezone.localdate(), scope_ids(request))
        if not rows:
            return None
        return "schedules/home_panel.html", {"rows": rows, "schedule_url": self.list_url}


@site.register(ScheduleChange)
class ScheduleChangeModule(Module):
    group = "Clinic"
    icon = "ki-calendar-remove"
    description = "Leave, a few hours away, or an extra shift. Booked visits that clash with leave are listed after saving."
    menu_order = 12
    show_on_home = False

    list_display = ["doctor", "kind_badge", "dates", "times", "branch", "reason"]
    search_fields = ["staff__first_name", "staff__last_name", "staff__username", "reason"]
    list_filter = ["kind", "staff"]
    date_filter = "start_date"
    form_class = ScheduleChangeForm
    fields = ScheduleChangeForm.Meta.fields
    form_template = "schedules/change_form.html"
    views = {"add": views.ScheduleChangeFormView, "edit": views.ScheduleChangeFormView}

    def get_queryset(self):
        return ScheduleChange.objects.select_related("staff", "branch")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user

    def doctor(self, obj):
        return staff_name(obj.staff)

    doctor.short_description = "Doctor"

    def kind_badge(self, obj):
        return Badge(obj.get_kind_display(), ScheduleChange.KIND_COLORS.get(obj.kind, "secondary"))

    kind_badge.short_description = "Kind"

    def dates(self, obj):
        return obj.dates_label

    dates.short_description = "Dates"

    def times(self, obj):
        return obj.times_label

    times.short_description = "Hours"
