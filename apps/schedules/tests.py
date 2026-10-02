import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.appointments.tests import ClinicTestCase, make_user
from apps.accounts.roles import VETERINARIAN
from apps.branches.models import Branch

from .availability import booking_warning, doctors_on
from .models import DoctorShift, ScheduleChange

ALL_DAY = (datetime.time(0, 0), datetime.time(23, 59))


class ScheduleTestCase(ClinicTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.branch = Branch.main()
        cls.today = timezone.localdate()
        cls.tomorrow = cls.today + datetime.timedelta(days=1)

    def shift(self, day, start=ALL_DAY[0], end=ALL_DAY[1], staff=None, branch=None):
        return DoctorShift.objects.create(
            staff=staff or self.vet, branch=branch or self.branch, weekday=day.weekday(), start_time=start, end_time=end
        )

    def leave(self, day, staff=None, **extra):
        return ScheduleChange.objects.create(staff=staff or self.vet, kind=ScheduleChange.LEAVE, start_date=day, **extra)

    def row_for(self, rows, user):
        return next(row for row in rows if row["staff"] == user)


class ModelTests(ScheduleTestCase):
    def test_extra_shift_needs_hours_and_a_branch(self):
        change = ScheduleChange(staff=self.vet, kind=ScheduleChange.EXTRA, start_date=self.today)
        with self.assertRaises(ValidationError) as caught:
            change.full_clean()
        self.assertIn("start_time", caught.exception.message_dict)
        self.assertIn("branch", caught.exception.message_dict)

    def test_single_day_leave_ends_on_its_start_date(self):
        change = self.leave(self.today, branch=self.branch)
        self.assertEqual(change.end_date, self.today)
        self.assertIsNone(change.branch)


class AvailabilityTests(ScheduleTestCase):
    def test_booking_warnings(self):
        # Without hours entered nothing is known, so nothing warns.
        self.assertEqual(booking_warning(self.vet, self.branch, self.tomorrow), "")

        self.shift(self.tomorrow, datetime.time(10), datetime.time(13))
        self.assertEqual(booking_warning(self.vet, self.branch, self.tomorrow, datetime.time(11)), "")
        self.assertIn("outside those hours", booking_warning(self.vet, self.branch, self.tomorrow, datetime.time(15)))
        day_after = self.tomorrow + datetime.timedelta(days=1)
        self.assertIn("not working", booking_warning(self.vet, self.branch, day_after))

        self.leave(self.tomorrow, start_time=datetime.time(10), end_time=datetime.time(11))
        self.assertIn("away 10:00–11:00", booking_warning(self.vet, self.branch, self.tomorrow, datetime.time(10, 30)))
        self.leave(self.tomorrow, reason="Conference")
        self.assertIn("on leave", booking_warning(self.vet, self.branch, self.tomorrow))
        self.assertIn("Conference", booking_warning(self.vet, self.branch, self.tomorrow))

    def test_extra_shift_counts_as_working(self):
        self.shift(self.today)
        ScheduleChange.objects.create(
            staff=self.vet, kind=ScheduleChange.EXTRA, start_date=self.tomorrow, branch=self.branch,
            start_time=datetime.time(9), end_time=datetime.time(12),
        )
        self.assertEqual(booking_warning(self.vet, self.branch, self.tomorrow, datetime.time(10)), "")

    def test_live_status_today(self):
        other = make_user("drsita", VETERINARIAN)
        third = make_user("drhari", VETERINARIAN)
        self.shift(self.today)
        self.shift(self.today, staff=other)
        self.shift(self.today, staff=third)
        self.leave(self.today, staff=third, reason="Sick")
        visit = self.visit(attended_by=other)
        visit.apply("start", user=other)
        self.visit(attended_by=self.vet)

        rows = doctors_on(self.today, [self.branch.pk])
        self.assertEqual(self.row_for(rows, self.vet)["label"], "Available")
        self.assertEqual(self.row_for(rows, self.vet)["waiting"], 1)
        self.assertEqual(self.row_for(rows, other)["label"], "With patient")
        self.assertIn("Bruno", self.row_for(rows, other)["detail"])
        self.assertEqual(self.row_for(rows, third)["label"], "On leave")
        # With a patient first, on leave last.
        self.assertEqual(rows[0]["staff"], other)
        self.assertEqual(rows[-1]["staff"], third)

    def test_doctors_without_hours_only_show_through_their_visits(self):
        self.assertEqual(doctors_on(self.today, [self.branch.pk]), [])
        self.visit(attended_by=self.vet)
        rows = doctors_on(self.today, [self.branch.pk])
        self.assertEqual(self.row_for(rows, self.vet)["label"], "Hours not set")


class WeeklyHoursTests(ScheduleTestCase):
    def url(self, user):
        return reverse("dashboard:schedule_hours", args=[user.pk])

    def test_manager_sets_a_split_week(self):
        self.login(self.admin)
        response = self.client.post(self.url(self.vet), {
            "branch": self.branch.pk,
            "d0_0_start": "10:00", "d0_0_end": "13:00", "d0_1_start": "16:00", "d0_1_end": "19:00",
            "d2_0_start": "09:00", "d2_0_end": "17:00",
        })
        self.assertEqual(response.status_code, 302)
        shifts = list(DoctorShift.objects.filter(staff=self.vet).values_list("weekday", "start_time", "end_time"))
        self.assertEqual(shifts, [
            (0, datetime.time(10), datetime.time(13)), (0, datetime.time(16), datetime.time(19)),
            (2, datetime.time(9), datetime.time(17)),
        ])
        # Saving again replaces the week.
        self.client.post(self.url(self.vet), {"branch": self.branch.pk, "d4_0_start": "08:00", "d4_0_end": "12:00"})
        self.assertEqual(DoctorShift.objects.filter(staff=self.vet).count(), 1)

    def test_bad_hours_are_rejected(self):
        self.login(self.admin)
        response = self.client.post(self.url(self.vet), {
            "branch": self.branch.pk, "d0_0_start": "13:00", "d0_0_end": "10:00",
            "d1_0_start": "10:00", "d1_0_end": "14:00", "d1_1_start": "12:00", "d1_1_end": "15:00",
        })
        self.assertContains(response, "Must be after the start.")
        self.assertContains(response, "Overlaps the first block.")
        self.assertFalse(DoctorShift.objects.exists())

    def test_reception_sees_the_schedule_but_cannot_edit_hours(self):
        self.shift(self.today, datetime.time(10), datetime.time(17))
        self.login(self.reception)
        response = self.client.get(reverse("dashboard:list", args=["schedules", "doctorshift"]))
        self.assertContains(response, "10:00–17:00")
        self.assertNotContains(response, "Edit hours")
        self.assertEqual(self.client.get(self.url(self.vet)).status_code, 403)


class LeaveTests(ScheduleTestCase):
    add_url = reverse("dashboard:add", args=["schedules", "schedulechange"])

    def test_leave_over_bookings_lists_them(self):
        self.visit(attended_by=self.vet, visit_date=self.tomorrow, status=Appointment.SCHEDULED)
        self.login(self.admin)
        response = self.client.post(self.add_url, {
            "staff": self.vet.pk, "kind": "leave", "start_date": self.tomorrow.isoformat(), "reason": "Wedding",
        }, follow=True)
        change = ScheduleChange.objects.get()
        self.assertEqual(change.created_by, self.admin)
        self.assertRedirects(response, reverse("dashboard:edit", args=["schedules", "schedulechange", change.pk]))
        self.assertContains(response, "Booked during this leave")
        self.assertContains(response, "Bruno")

    def test_leave_without_bookings_goes_back_to_the_list(self):
        self.login(self.admin)
        response = self.client.post(self.add_url, {
            "staff": self.vet.pk, "kind": "leave", "start_date": self.tomorrow.isoformat(),
        })
        self.assertRedirects(response, reverse("dashboard:list", args=["schedules", "schedulechange"]))


class AppointmentIntegrationTests(ScheduleTestCase):
    walk_in_url = reverse("dashboard:add", args=["appointments", "appointment"])

    def test_booking_a_doctor_on_leave_needs_confirmation(self):
        self.shift(self.tomorrow)
        self.leave(self.tomorrow)
        self.login(self.reception)
        data = {
            "client": self.client_a.pk, "pet": self.pet.pk, "reason": "Vaccination",
            "visit_date": self.tomorrow.isoformat(), "attended_by": self.vet.pk,
        }
        response = self.client.post(self.walk_in_url, data)
        self.assertContains(response, "is on leave")
        self.assertContains(response, "Keep this doctor")
        self.assertFalse(Appointment.objects.exists())

        self.client.post(self.walk_in_url, {**data, "confirm_schedule": "on"})
        self.assertEqual(Appointment.objects.get().attended_by, self.vet)

    def test_walk_in_form_shows_who_is_available(self):
        self.shift(self.today)
        self.login(self.reception)
        response = self.client.get(self.walk_in_url)
        self.assertContains(response, "Available (until 23:59)")

    def test_queue_lists_doctors_and_filters_by_one(self):
        other = make_user("drsita", VETERINARIAN)
        self.shift(self.today)
        self.visit(attended_by=self.vet)
        self.visit(attended_by=other, pet=self.other_pet, client=self.client_b)
        self.login(self.reception)
        queue = reverse("dashboard:appointment_queue")
        response = self.client.get(queue)
        self.assertContains(response, "Doctors today")
        self.assertContains(response, "Tiger")
        response = self.client.get(queue, {"doctor": self.vet.pk})
        self.assertContains(response, "Showing Vet's patients")
        self.assertNotContains(response, "Tiger")

    def test_availability_lookup_for_a_date(self):
        self.shift(self.tomorrow, datetime.time(10), datetime.time(17))
        self.login(self.reception)
        data = self.client.get(reverse("dashboard:schedule_availability"), {"date": self.tomorrow.isoformat()}).json()
        self.assertEqual(data["doctors"][0]["id"], self.vet.pk)
        self.assertEqual(data["doctors"][0]["summary"], "Working (10:00–17:00)")

    def test_bookings_week_shows_who_is_on_duty(self):
        self.shift(self.tomorrow, datetime.time(10), datetime.time(17))
        self.login(self.reception)
        response = self.client.get(reverse("dashboard:appointment_bookings"), {"week": self.tomorrow.isoformat()})
        self.assertContains(response, "10:00–17:00")

    def test_moving_a_booking_onto_leave_warns(self):
        self.shift(self.tomorrow)
        self.leave(self.tomorrow)
        visit = self.visit(status=Appointment.SCHEDULED, visit_date=self.tomorrow + datetime.timedelta(days=7))
        self.login(self.reception)
        response = self.client.post(reverse("dashboard:edit", args=["appointments", "appointment", visit.pk]), {
            "visit-visit_date": self.tomorrow.isoformat(), "visit-reason": "Check-up",
            "visit-attended_by": self.vet.pk, "visit-priority": "routine",
        }, follow=True)
        self.assertContains(response, "is on leave")


class PageTests(ScheduleTestCase):
    def test_home_shows_doctors_today(self):
        self.shift(self.today)
        self.login(self.reception)
        self.assertContains(self.client.get(reverse("dashboard:home")), "Doctors today")

    def test_leave_form_starts_from_the_chosen_doctor_and_day(self):
        self.login(self.admin)
        url = reverse("dashboard:add", args=["schedules", "schedulechange"])
        response = self.client.get(url, {"staff": self.vet.pk, "date": self.tomorrow.isoformat()})
        self.assertEqual(response.context["form"]["staff"].value(), self.vet.pk)
        self.assertEqual(response.context["form"]["start_date"].value(), self.tomorrow)

    def test_hours_page_opens_with_the_current_week(self):
        self.shift(self.today, datetime.time(10), datetime.time(13))
        self.login(self.admin)
        response = self.client.get(reverse("dashboard:schedule_hours", args=[self.vet.pk]))
        self.assertContains(response, 'value="10:00"')
        self.assertContains(response, "Copy to weekdays")
