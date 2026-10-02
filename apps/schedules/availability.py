"""Who works when: the regular week, with leave and extra shifts applied.

Doctors with no hours entered are treated as "hours not set": nothing warns about them,
so the roster can be adopted one doctor at a time.
"""
import datetime

from django.db.models import Q
from django.utils import timezone

from .models import DoctorShift, ScheduleChange


def staff_name(user):
    return user.get_full_name() or user.get_username()


def hours_label(blocks):
    return ", ".join(block.label for block in blocks)


class Block:
    """A stretch of working time at one branch."""

    def __init__(self, start, end, branch, extra=False):
        self.start, self.end, self.branch, self.extra = start, end, branch, extra

    @property
    def label(self):
        return f"{self.start:%H:%M}–{self.end:%H:%M}"

    def covers(self, moment):
        return self.start <= moment < self.end


class DoctorDay:
    """One doctor's working hours and leave on one date."""

    def __init__(self, staff, day, blocks, leave, has_hours, home_branch_ids):
        self.staff = staff
        self.day = day
        self.blocks = sorted(blocks, key=lambda block: block.start)
        self.leave = leave
        self.has_hours = has_hours
        # Branches where the doctor has a regular shift on some day of the week.
        self.home_branch_ids = home_branch_ids

    @property
    def leave_all_day(self):
        return next((change for change in self.leave if change.is_whole_day), None)

    @property
    def partial_leave(self):
        return [change for change in self.leave if not change.is_whole_day]

    def away_at(self, moment):
        return next((c for c in self.partial_leave if c.start_time <= moment < c.end_time), None)

    def at(self, branch_ids):
        return [block for block in self.blocks if block.branch.pk in branch_ids]

    def works_at(self, branch_ids):
        return bool(self.at(branch_ids)) or bool(self.home_branch_ids & set(branch_ids))


def roster_staff(branch_ids):
    """Staff who can attend visits at any of these branches."""
    from apps.appointments.models import attending_staff

    return attending_staff().filter(
        Q(is_superuser=True) | Q(staff_profile__all_branches=True) | Q(staff_profile__branches__in=branch_ids)
    ).distinct().select_related("staff_profile")


def load_days(staff_list, start, end):
    """{(staff id, date): DoctorDay} for every doctor and date from start to end, in two queries."""
    ids = [user.pk for user in staff_list]
    shifts = list(DoctorShift.objects.filter(staff_id__in=ids).select_related("branch"))
    changes = list(
        ScheduleChange.objects.filter(staff_id__in=ids, start_date__lte=end, end_date__gte=start).select_related("branch")
    )
    days = {}
    count = (end - start).days + 1
    for user in staff_list:
        own_shifts = [shift for shift in shifts if shift.staff_id == user.pk]
        own_changes = [change for change in changes if change.staff_id == user.pk]
        home = {shift.branch_id for shift in own_shifts}
        for offset in range(count):
            day = start + datetime.timedelta(days=offset)
            blocks = [
                Block(shift.start_time, shift.end_time, shift.branch)
                for shift in own_shifts
                if shift.weekday == day.weekday()
            ]
            on_day = [change for change in own_changes if change.covers_day(day)]
            blocks += [
                Block(change.start_time, change.end_time, change.branch, extra=True)
                for change in on_day
                if change.kind == ScheduleChange.EXTRA
            ]
            leave = [change for change in on_day if change.kind == ScheduleChange.LEAVE]
            days[(user.pk, day)] = DoctorDay(user, day, blocks, leave, bool(own_shifts), home)
    return days


def doctor_day(staff, day):
    return load_days([staff], day, day)[(staff.pk, day)]


# Statuses: (label, colour). Colours are theme names.
WITH_PATIENT = ("With patient", "primary")
ON_LEAVE = ("On leave", "danger")
AWAY = ("Away", "warning")
AVAILABLE = ("Available", "success")
LATER = ("Later today", "info")
OFF_DUTY = ("Off duty", "secondary")
OFF_TODAY = ("Off today", "secondary")
WORKING = ("Working", "success")
OFF = ("Off", "secondary")
NOT_SET = ("Hours not set", "secondary")


def status_now(day_info, branch_ids, moment, current=None):
    """(label, colour, detail) for a doctor right now."""
    blocks = day_info.at(branch_ids)
    if current is not None:
        detail = current.pet.name + (f" · token {current.token}" if current.token else "")
        return (*WITH_PATIENT, detail)
    leave = day_info.leave_all_day
    if leave is not None:
        return (*ON_LEAVE, leave.reason)
    away = day_info.away_at(moment)
    if away is not None:
        return (*AWAY, f"until {away.end_time:%H:%M}")
    now = next((block for block in blocks if block.covers(moment)), None)
    if now is not None:
        return (*AVAILABLE, f"until {now.end:%H:%M}")
    later = [block for block in blocks if block.start > moment]
    if later:
        return (*LATER, f"from {later[0].start:%H:%M}")
    if blocks:
        return (*OFF_DUTY, f"finished {blocks[-1].end:%H:%M}")
    if day_info.has_hours:
        return (*OFF_TODAY, "")
    return (*NOT_SET, "")


def status_on(day_info, branch_ids):
    """(label, colour, detail) for a doctor on a day, without the live part."""
    leave = day_info.leave_all_day
    if leave is not None:
        return (*ON_LEAVE, leave.reason)
    blocks = day_info.at(branch_ids)
    if blocks:
        away = ", ".join(f"away {c.times_label}" for c in day_info.partial_leave)
        return (*WORKING, hours_label(blocks) + (f" ({away})" if away else ""))
    if day_info.has_hours:
        return (*OFF, "")
    return (*NOT_SET, "")


def doctors_on(day, branch_ids, staff_ids=None):
    """The doctors for a day at these branches, with what they are doing (live for today).

    A doctor is listed when they have hours at these branches (on any weekday), work an extra
    shift there that day, or attend one of the day's visits. Doctors without hours anywhere
    only show up through their visits, so a clinic that does not use the roster sees no change.
    """
    from apps.appointments.models import Appointment

    today = timezone.localdate()
    staff = list(roster_staff(branch_ids))
    if staff_ids is not None:
        staff = [user for user in staff if user.pk in staff_ids]
    days = load_days(staff, day, day)
    visits = list(
        Appointment.objects.on(day).filter(
            branch_id__in=branch_ids, attended_by__isnull=False,
            status__in=[Appointment.WAITING, Appointment.IN_CONSULTATION, Appointment.SCHEDULED, Appointment.COMPLETED],
        ).select_related("pet")
    )
    moment = timezone.localtime().time()
    rows = []
    for user in staff:
        info = days[(user.pk, day)]
        own = [visit for visit in visits if visit.attended_by_id == user.pk]
        if not (info.works_at(branch_ids) or own):
            continue
        current = next((v for v in own if v.status == Appointment.IN_CONSULTATION), None)
        if day == today:
            label, color, detail = status_now(info, branch_ids, moment, current)
        else:
            label, color, detail = status_on(info, branch_ids)
        rows.append({
            "staff": user,
            "name": staff_name(user),
            "designation": getattr(getattr(user, "staff_profile", None), "designation", ""),
            "label": label,
            "color": color,
            "detail": detail,
            "hours": hours_label(info.at(branch_ids)),
            "waiting": sum(1 for v in own if v.status == Appointment.WAITING),
            "booked": sum(1 for v in own if v.status == Appointment.SCHEDULED),
            "seen": sum(1 for v in own if v.status == Appointment.COMPLETED),
        })
    order = [WITH_PATIENT[0], AVAILABLE[0], WORKING[0], AWAY[0], LATER[0], NOT_SET[0], OFF_DUTY[0], OFF_TODAY[0],
             OFF[0], ON_LEAVE[0]]
    rows.sort(key=lambda row: (order.index(row["label"]), row["name"].lower()))
    return rows


def summary_text(row):
    """A doctor's status in a few words, e.g. "Available (until 17:00) · 2 waiting". Blank when unknown."""
    if row is None or row["label"] == NOT_SET[0]:
        text = ""
    else:
        text = row["label"] + (f" ({row['detail']})" if row["detail"] else "")
    if row is not None and row["waiting"]:
        text += (" · " if text else "") + f"{row['waiting']} waiting"
    return text


def summaries(staff_list, day, branch_ids):
    """{staff id: summary_text} for these doctors on a day at these branches."""
    rows = {row["staff"].pk: row for row in doctors_on(day, branch_ids)}
    return {user.pk: summary_text(rows.get(user.pk)) for user in staff_list}


def booking_warning(staff, branch, day, moment=None):
    """Why this doctor should not be booked here then, or "" when nothing is wrong (or unknown)."""
    if staff is None or branch is None or day is None:
        return ""
    info = doctor_day(staff, day)
    name = staff_name(staff)
    when = f"{day:%a %d %b}"
    leave = info.leave_all_day
    if leave is not None:
        return f"{name} is on leave on {when}" + (f" ({leave.reason})" if leave.reason else "") + "."
    if moment is not None:
        away = info.away_at(moment)
        if away is not None:
            return f"{name} is away {away.times_label} on {when}."
    if not info.has_hours and not info.blocks:
        return ""
    blocks = info.at([branch.pk])
    if not blocks:
        return f"{name} is not working at {branch.name} on {when}."
    if moment is not None and not any(block.covers(moment) for block in blocks):
        return f"{name} works {hours_label(blocks)} at {branch.name} on {when}; {moment:%H:%M} is outside those hours."
    return ""


def affected_visits(change, branch_ids):
    """Booked visits with this doctor that fall in this leave."""
    from apps.appointments.models import Appointment

    if change.kind != ScheduleChange.LEAVE or change.pk is None:
        return Appointment.objects.none()
    visits = Appointment.objects.filter(
        attended_by_id=change.staff_id, branch_id__in=branch_ids,
        visit_date__range=(change.start_date, change.end_date or change.start_date),
        status__in=[Appointment.SCHEDULED, Appointment.WAITING],
    )
    if not change.is_whole_day:
        visits = visits.filter(scheduled_time__gte=change.start_time, scheduled_time__lt=change.end_time)
    return visits.select_related("branch", "client", "pet").order_by("visit_date", "scheduled_time")
