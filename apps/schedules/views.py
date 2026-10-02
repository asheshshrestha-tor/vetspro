import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import TemplateView

from apps.branches.context import allowed_branches, allowed_ids, current_branch, is_all_mode, scope_ids
from apps.dashboard.mixins import ModuleMixin
from apps.dashboard.registry import site
from apps.dashboard.views import ModuleFormView, safe_next

from .availability import (
    NOT_SET, affected_visits, doctors_on, load_days, roster_staff, staff_name, summary_text,
)
from .forms import WeeklyHoursForm
from .models import DoctorShift, ScheduleChange


def schedule_url(week=None):
    url = reverse("dashboard:list", args=["schedules", "doctorshift"])
    return f"{url}?week={week.isoformat()}" if week else url


class SchedulePage(ModuleMixin):
    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "schedules")
        kwargs.setdefault("model_name", "doctorshift")
        super().setup(request, *args, **kwargs)


class ScheduleView(SchedulePage, TemplateView):
    """The week at a glance: every doctor's hours, leave and extra shifts, day by day."""

    template_name = "schedules/schedule.html"

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        start = parse_date(self.request.GET.get("week") or "") or today
        start -= datetime.timedelta(days=start.weekday())
        days = [start + datetime.timedelta(days=i) for i in range(7)]
        branch_ids = scope_ids(self.request)
        show_branch = is_all_mode(self.request)

        staff = list(roster_staff(branch_ids).order_by("first_name", "last_name", "username"))
        schedule = load_days(staff, days[0], days[-1])
        changes = site.for_model(ScheduleChange)
        can_add_change = changes is not None and changes.user_can_add(user)
        can_edit = self.module.user_can_change(user)
        rows = []
        for member in staff:
            cells = []
            for day in days:
                info = schedule[(member.pk, day)]
                cells.append({
                    "date": day,
                    "is_today": day == today,
                    "blocks": [
                        {"label": block.label, "extra": block.extra, "branch": block.branch.name}
                        for block in info.at(branch_ids)
                    ],
                    "leave": info.leave_all_day,
                    "away": info.partial_leave,
                    "has_hours": info.has_hours,
                    "add_leave_url": (
                        f"{changes.add_url}?staff={member.pk}&date={day.isoformat()}" if can_add_change else ""
                    ),
                })
            profile = getattr(member, "staff_profile", None)
            rows.append({
                "staff": member,
                "name": staff_name(member),
                "designation": profile.designation if profile else "",
                "has_hours": schedule[(member.pk, days[0])].has_hours,
                "cells": cells,
                "hours_url": reverse("dashboard:schedule_hours", args=[member.pk]) if can_edit else "",
            })
        context.update(
            days=[{"date": day, "is_today": day == today} for day in days],
            rows=rows,
            start=days[0],
            end=days[-1],
            previous_week=schedule_url(start - datetime.timedelta(days=7)),
            next_week=schedule_url(start + datetime.timedelta(days=7)),
            this_week=schedule_url(),
            is_this_week=days[0] <= today <= days[-1],
            show_branch=show_branch,
            branch=current_branch(self.request),
            changes=changes if changes and changes.can_view(user) else None,
            can_add_change=can_add_change,
            can_edit=can_edit,
        )
        return context


def doctor_branches(member, request):
    """Branches where this doctor works and the person editing may also work."""
    profile = getattr(member, "staff_profile", None)
    allowed = allowed_branches(request)
    if member.is_superuser or (profile and profile.all_branches):
        return allowed
    theirs = set(profile.branches.values_list("pk", flat=True)) if profile else set()
    return [branch for branch in allowed if branch.pk in theirs]


class WeeklyHoursView(SchedulePage, TemplateView):
    """Set a doctor's regular week at one branch."""

    template_name = "schedules/hours_form.html"

    def load(self):
        self.require(self.module.user_can_change(self.request.user))
        self.member = get_object_or_404(get_user_model().objects.filter(is_staff=True), pk=self.kwargs["user_id"])
        self.branches = doctor_branches(self.member, self.request)
        if not self.branches:
            raise Http404("This doctor does not work at any of your branches.")
        chosen = self.request.GET.get("branch") or self.request.POST.get("branch")
        current = current_branch(self.request)
        self.branch = (
            next((b for b in self.branches if str(b.pk) == str(chosen)), None)
            or next((b for b in self.branches if current and b.pk == current.pk), None)
            or self.branches[0]
        )

    def get(self, request, *args, **kwargs):
        self.load()
        form = WeeklyHoursForm(staff=self.member, branch=self.branch, request=request)
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        self.load()
        form = WeeklyHoursForm(request.POST, staff=self.member, branch=self.branch, request=request)
        if not form.is_valid():
            messages.error(request, "Please correct the errors below.")
            return self.render_to_response(self.get_context_data(form=form))
        count = form.save()
        name = staff_name(self.member)
        if count:
            messages.success(request, f"{name}'s hours at {self.branch.name} were saved.")
        else:
            messages.success(request, f"{name} has no regular hours at {self.branch.name} now.")
        return redirect(safe_next(request, schedule_url()))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        other = (
            DoctorShift.objects.filter(staff=self.member)
            .exclude(branch=self.branch)
            .select_related("branch")
            .order_by("branch__name", "weekday", "start_time")
        )
        context.update(
            member=self.member,
            name=staff_name(self.member),
            branch=self.branch,
            branches=self.branches,
            other_shifts=other,
        )
        return context


class AvailabilityView(SchedulePage, View):
    """JSON for the booking form: who works on a date at the branch, and a short status per doctor."""

    def get(self, request, *args, **kwargs):
        user = request.user
        appointments = site.get("appointments", "appointment")
        self.require(self.module.can_view(user) or (appointments and appointments.user_can_add(user)))
        day = parse_date(request.GET.get("date") or "") or timezone.localdate()
        branch_ids = scope_ids(request)
        rows = doctors_on(day, branch_ids)
        return JsonResponse({
            "date": day.isoformat(),
            "label": f"{day:%a %d %b}" if day != timezone.localdate() else "today",
            "doctors": [
                {
                    "id": row["staff"].pk,
                    "name": row["name"],
                    "status": row["label"],
                    "color": row["color"],
                    "detail": row["detail"],
                    "summary": summary_text(row),
                }
                for row in rows
                if row["label"] != NOT_SET[0]
            ],
        })


class ScheduleChangeFormView(ModuleFormView):
    """Leave and extra shifts. Saving leave that clashes with bookings stays on the page to list them."""

    def build_form(self, data=None, files=None):
        form = super().build_form(data, files)
        if data is None and self.object is None:
            get = self.request.GET
            if (get.get("staff") or "").isdigit():
                form.initial["staff"] = int(get["staff"])
            day = parse_date(get.get("date") or "")
            if day:
                form.initial["start_date"] = day
            if get.get("kind") in dict(ScheduleChange.KIND_CHOICES):
                form.initial["kind"] = get["kind"]
        return form

    def saved(self, obj):
        clashes = affected_visits(obj, allowed_ids(self.request)).count()
        if clashes:
            messages.warning(
                self.request,
                f"Saved. {clashes} booked visit{'s are' if clashes != 1 else ' is'} with "
                f"{staff_name(obj.staff)} during this leave: move {'them' if clashes != 1 else 'it'} to another "
                "doctor or day.",
            )
            return redirect(self.module.url("edit", obj.pk))
        return super().saved(obj)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object is not None:
            context["affected"] = affected_visits(self.object, allowed_ids(self.request))
        context["schedule_url"] = schedule_url()
        return context
