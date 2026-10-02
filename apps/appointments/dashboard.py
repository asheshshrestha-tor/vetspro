import datetime

from django.db.models import Count, Q
from django.urls import path, reverse
from django.utils import timezone

from apps.branches.context import is_all_mode, scope_ids
from apps.clients.models import normalize_phone
from apps.dashboard.registry import Action, Badge, Module, site

from . import permissions as perms
from . import views
from .models import Appointment, due_vaccinations


@site.register(Appointment)
class AppointmentModule(Module):
    group = "Clinic"
    icon = "ki-calendar"
    description = "Every visit, walk-in or booked, with its examination, treatment and result."
    menu_order = 10
    branch_field = "branch"

    list_display = ["number", "visit_date", "token", "triage", "pet", "client", "attended_by", "status_badge"]
    search_fields = ["number", "client__full_name", "client__phone", "pet__name", "reason"]
    list_filter = ["status", "priority", "attended_by", "pet__species", "branch"]
    date_filter = "visit_date"
    per_page = 25

    views = {"add": views.WalkInView, "edit": views.ConsultationView}

    def get_queryset(self):
        return Appointment.objects.select_related("branch", "client", "pet__species", "attended_by")

    def search_conditions(self, term):
        conditions = super().search_conditions(term)
        digits = normalize_phone(term)
        if len(digits) >= 4:
            conditions.append(Q(client__phone_digits__contains=digits))
        return conditions

    def get_urls(self):
        return [
            path("queue/", views.QueueView.as_view(), name="appointment_queue"),
            path("bookings/", views.BookingsView.as_view(), name="appointment_bookings"),
            path("<int:pk>/status/<str:action>/", views.StatusView.as_view(), name="appointment_status"),
            path("<int:pk>/follow-up/", views.FollowUpView.as_view(), name="appointment_follow_up"),
            path("<int:pk>/print/", views.PrintView.as_view(), name="appointment_print"),
            path("<int:pk>/form/", views.VisitFormPrintView.as_view(), name="appointment_form"),
            path("blank-form/", views.VisitFormPrintView.as_view(), name="appointment_blank_form"),
        ]

    def menu_items(self, request=None):
        waiting = None
        if request is not None:
            waiting = (
                Appointment.objects.on(timezone.localdate())
                .filter(status=Appointment.WAITING, branch_id__in=scope_ids(request))
                .count()
            ) or None
        return [
            {
                "title": "Today's queue",
                "url": reverse("dashboard:appointment_queue"),
                "icon": "ki-time",
                "badge": waiting,
                # Registering a walk-in happens from the queue, so it keeps the queue highlighted.
                "url_names": ["appointment_queue", "add"],
            },
            {
                "title": "Bookings",
                "url": reverse("dashboard:appointment_bookings"),
                "icon": "ki-calendar-8",
                "badge": None,
                "url_names": ["appointment_bookings"],
            },
            {"title": self.title, "url": self.list_url, "icon": self.icon, "badge": None, "url_names": []},
        ]

    def row_actions(self, obj, request):
        actions = [
            Action(item["label"], item["url"], icon=item["icon"], color=item["color"], post=True,
                   confirm="Cancel this appointment?" if item["action"] == "cancel" else "")
            for item in views.status_actions(obj, request.user)
            if item["action"] in ("check_in", "start")
        ]
        if perms.can_view_clinical(request.user) and obj.status != Appointment.CANCELLED:
            actions.append(Action("", reverse("dashboard:appointment_print", args=[obj.pk]), icon="ki-printer", color="light",
                                  preview=True, title=f"Visit summary · {obj.number}"))
        return actions

    def status_badge(self, obj):
        return Badge(obj.get_status_display(), obj.status_color)

    status_badge.short_description = "Status"

    def triage(self, obj):
        return Badge(obj.get_priority_display(), obj.PRIORITY_COLORS.get(obj.priority, "secondary"))

    triage.short_description = "Triage"

    def home_panel(self, request):
        today = timezone.localdate()
        branch_ids = scope_ids(request)
        todays = Appointment.objects.on(today).filter(branch_id__in=branch_ids)
        counts = dict(todays.values_list("status").annotate(total=Count("id")))
        follow_ups = (
            Appointment.objects.filter(status=Appointment.SCHEDULED, branch_id__in=branch_ids)
            .filter(Q(visit_date=today) | Q(visit_date__lt=today))
            .select_related("branch", "client", "pet__species")
            .order_by("visit_date", "scheduled_time")[:8]
        )
        vaccinations = due_vaccinations(today, today + datetime.timedelta(days=14), branch_ids)[:8]
        return (
            "appointments/home_panel.html",
            {
                "counts": [
                    {"label": label, "count": counts.get(status, 0), "color": Appointment.STATUS_COLORS[status]}
                    for status, label in Appointment.STATUS_CHOICES
                    if status != Appointment.SCHEDULED
                ],
                "total": sum(counts.values()),
                "emergencies": todays.filter(
                    priority__in=[Appointment.EMERGENCY, Appointment.URGENT],
                    status__in=[Appointment.WAITING, Appointment.IN_CONSULTATION],
                ).count(),
                "follow_ups": follow_ups,
                "vaccinations": vaccinations,
                "today": today,
                "show_branch": is_all_mode(request),
                "can_add": self.user_can_add(request.user),
            },
        )
