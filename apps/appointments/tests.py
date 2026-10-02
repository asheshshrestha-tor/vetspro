import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import ADMINISTRATOR, RECEPTIONIST, VETERINARIAN
from apps.clients.models import Client, Pet
from apps.clinic_setup.models import ExaminationType, HistoryOption, Species, VaccinationType

from .models import Appointment, AppointmentHistory, ExaminationResult, VaccinationRecord, due_vaccinations

User = get_user_model()
PASSWORD = "pw-Test-12345"


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username, password=PASSWORD, is_staff=True, first_name=username.title(), **extra)
    if role:
        group = Group.objects.get(name=role)
        user.groups.add(group)
        user.staff_profile.role = group
        user.staff_profile.save()
    return user


class ClinicTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dog = Species.objects.get(name="Dog")
        cls.client_a = Client.objects.create(full_name="Ram Shrestha", phone="+977 980-1234567")
        cls.client_b = Client.objects.create(full_name="Sita Rai", phone="9811111111")
        cls.pet = Pet.objects.create(client=cls.client_a, name="Bruno", species=cls.dog)
        cls.other_pet = Pet.objects.create(client=cls.client_b, name="Tiger", species=cls.dog)
        cls.vet = make_user("vet", VETERINARIAN)
        cls.reception = make_user("reception", RECEPTIONIST)
        cls.reception.staff_profile.can_attend = False
        cls.reception.staff_profile.save()
        cls.admin = make_user("manager", ADMINISTRATOR)

    def visit(self, **kwargs):
        data = {"client": self.client_a, "pet": self.pet, "reason": "Check-up"}
        data.update(kwargs)
        return Appointment.objects.create(**data)

    def login(self, user):
        self.client.force_login(user)


class NumbersAndTokensTests(ClinicTestCase):
    def test_numbers_are_sequential_per_year(self):
        first, second = self.visit(), self.visit()
        year = timezone.localdate().year
        self.assertEqual(first.number, f"APT-{year}-00001")
        self.assertEqual(second.number, f"APT-{year}-00002")

    def test_tokens_restart_each_day_and_skip_scheduled_visits(self):
        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        self.assertEqual(self.visit().token, 1)
        self.assertEqual(self.visit().token, 2)
        scheduled = self.visit(visit_date=tomorrow, status=Appointment.SCHEDULED)
        self.assertIsNone(scheduled.token)
        self.assertEqual(self.visit(visit_date=tomorrow).token, 1)

    def test_checking_in_a_follow_up_gives_it_todays_token(self):
        self.visit()
        follow_up = self.visit(visit_date=timezone.localdate() - datetime.timedelta(days=2), status=Appointment.SCHEDULED)
        follow_up.apply("check_in", user=self.reception)
        self.assertEqual(follow_up.status, Appointment.WAITING)
        self.assertEqual(follow_up.visit_date, timezone.localdate())
        self.assertEqual(follow_up.token, 2)
        self.assertIsNotNone(follow_up.arrival_time)


class RuleTests(ClinicTestCase):
    def test_pet_must_belong_to_the_owner(self):
        visit = Appointment(client=self.client_a, pet=self.other_pet, reason="x")
        with self.assertRaises(ValidationError):
            visit.full_clean()

    def test_status_changes_follow_the_allowed_flow(self):
        visit = self.visit()
        with self.assertRaises(ValidationError):
            visit.apply("reopen")
        visit.apply("start", user=self.vet)
        self.assertEqual(visit.attended_by, self.vet)
        visit.apply("complete", user=self.vet)
        self.assertIsNotNone(visit.completed_at)
        with self.assertRaises(ValidationError):
            visit.apply("cancel")

    def test_examination_flags_values_outside_the_range(self):
        visit = self.visit()
        temperature = ExaminationType.objects.get(code="temperature")
        anaemia = ExaminationType.objects.get(code="mucous_membranes")
        high = ExaminationResult.objects.create(appointment=visit, exam_type=temperature, value="40.1")
        pale = ExaminationResult.objects.create(appointment=visit, exam_type=anaemia, value="Pale")
        self.assertTrue(high.is_abnormal)
        self.assertTrue(pale.is_abnormal)
        self.assertFalse(temperature.is_abnormal("38.5"))
        self.assertFalse(anaemia.is_abnormal("pink"))

    def test_next_due_date_comes_from_the_booster_interval(self):
        vaccine = VaccinationType.objects.create(name="Test vaccine", booster_interval_days=365)
        visit = self.visit()
        given = visit.visit_date - datetime.timedelta(days=30)
        record = VaccinationRecord.objects.create(appointment=visit, vaccine=vaccine, given_on=given)
        self.assertEqual(record.next_due_date, given + datetime.timedelta(days=365))

    def test_history_and_examination_fields_flag_by_value_type(self):
        visit = self.visit()
        parasites = HistoryOption.objects.create(name="Fleas seen", value_kind="yesno", normal_options="No")
        yes = AppointmentHistory.objects.create(appointment=visit, option=parasites, value="Yes")
        self.assertTrue(yes.is_abnormal)
        skin = ExaminationType.objects.get(code="skin")
        self.assertFalse(skin.is_abnormal("Dry, flaky"))
        dehydration = ExaminationType.objects.get(code="hydration")
        self.assertTrue(dehydration.is_abnormal("Moderate"))

    def test_due_vaccinations_ignore_doses_already_repeated(self):
        vaccine = VaccinationType.objects.create(name="Test vaccine")
        today = timezone.localdate()
        old = self.visit(visit_date=today - datetime.timedelta(days=360))
        VaccinationRecord.objects.create(appointment=old, vaccine=vaccine, next_due_date=today + datetime.timedelta(days=5))
        self.assertEqual(due_vaccinations(today, today + datetime.timedelta(days=14)).count(), 1)
        repeat = self.visit(visit_date=today - datetime.timedelta(days=1))
        VaccinationRecord.objects.create(appointment=repeat, vaccine=vaccine, next_due_date=today + datetime.timedelta(days=364))
        self.assertEqual(due_vaccinations(today, today + datetime.timedelta(days=14)).count(), 0)

    def test_follow_up_is_booked_once(self):
        visit = self.visit(follow_up_date=timezone.localdate() + datetime.timedelta(days=7), diagnosis="Otitis")
        follow_up, created = visit.create_follow_up(self.vet)
        self.assertTrue(created)
        self.assertEqual(follow_up.status, Appointment.SCHEDULED)
        self.assertEqual(follow_up.reason, "Follow-up: Otitis")
        self.assertEqual(visit.create_follow_up(self.vet), (follow_up, False))

    def test_phone_numbers_match_however_they_are_typed(self):
        self.assertEqual(self.client_a.phone_digits, "9801234567")


class WalkInTests(ClinicTestCase):
    url = reverse("dashboard:add", args=["appointments", "appointment"])

    def form_data(self, **extra):
        data = {"visit_date": timezone.localdate().isoformat(), "reason": "Vomiting"}
        data.update(extra)
        return data

    def test_reception_registers_a_new_owner_and_pet(self):
        self.login(self.reception)
        response = self.client.post(self.url, self.form_data(
            new_client_name="Hari Thapa", new_client_phone="9841000000",
            new_pet_name="Kali", new_pet_species=self.dog.pk, new_pet_age_years="2",
        ))
        self.assertRedirects(response, reverse("dashboard:appointment_queue"))
        visit = Appointment.objects.get()
        self.assertEqual((visit.status, visit.token), (Appointment.WAITING, 1))
        self.assertEqual(visit.pet.name, "Kali")
        self.assertTrue(visit.pet.dob_is_estimate)
        self.assertEqual(visit.created_by, self.reception)

    def test_existing_phone_needs_confirmation(self):
        self.login(self.reception)
        data = self.form_data(new_client_name="Ram S", new_client_phone="980-1234567",
                              new_pet_name="Kali", new_pet_species=self.dog.pk)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use this owner")
        self.assertFalse(Appointment.objects.exists())
        response = self.client.post(self.url, {**data, "confirm_new_client": "on"})
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Client.objects.filter(phone_digits="9801234567").count(), 2)

    def test_pet_of_another_owner_is_rejected(self):
        self.login(self.reception)
        response = self.client.post(self.url, self.form_data(client=self.client_a.pk, pet=self.other_pet.pk))
        self.assertContains(response, "belongs to a different owner")
        self.assertFalse(Appointment.objects.exists())

    def test_future_date_books_a_follow_up_without_token(self):
        self.login(self.reception)
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.client.post(self.url, self.form_data(client=self.client_a.pk, pet=self.pet.pk, visit_date=tomorrow.isoformat()))
        visit = Appointment.objects.get()
        self.assertEqual(visit.status, Appointment.SCHEDULED)
        self.assertIsNone(visit.token)

    def test_pet_search_only_offers_the_owners_pets(self):
        self.login(self.reception)
        url = reverse("dashboard:autocomplete", args=["clients", "pet"])
        results = self.client.get(url, {"client": self.client_a.pk}).json()["results"]
        self.assertEqual([r["id"] for r in results], [self.pet.pk])
        results = self.client.get(reverse("dashboard:autocomplete", args=["clients", "client"]), {"q": "98012"}).json()["results"]
        self.assertEqual([r["id"] for r in results], [self.client_a.pk])


class ConsultationPermissionTests(ClinicTestCase):
    def consultation_data(self, visit, **extra):
        data = {
            "visit-reason": visit.reason,
            "visit-attended_by": self.vet.pk,
            "visit-weight_kg": "12.5",
            "clinical-clinical_notes": "Alert and responsive",
            "clinical-diagnosis": "Gastritis",
            "clinical-outcome": "improving",
            "clinical-result_notes": "",
            "clinical-follow_up_date": "",
        }
        data.update({"treatment-TOTAL_FORMS": "0", "treatment-INITIAL_FORMS": "0",
                     "treatment-MIN_NUM_FORMS": "0", "treatment-MAX_NUM_FORMS": "1000"})
        for option in HistoryOption.objects.filter(is_active=True):
            data[f"history-{option.pk}-value"] = ""
        for exam_type in ExaminationType.objects.filter(is_active=True):
            data[f"exam-{exam_type.pk}-value"] = ""
        for vaccine in VaccinationType.objects.filter(is_active=True):
            for name in ("given_on", "next_due_date", "batch_number", "notes"):
                data[f"vaccine-{vaccine.pk}-{name}"] = ""
        data.update(extra)
        return data

    def test_vet_records_the_consultation_and_completes_it(self):
        visit = self.visit()
        option = HistoryOption.objects.get(name="Vomiting / Diarrhoea")
        temperature = ExaminationType.objects.get(code="temperature")
        rabies = VaccinationType.objects.get(name="Rabies")
        rabies.booster_interval_days = 365
        rabies.save()
        self.login(self.vet)
        url = visit.get_absolute_url()
        page = self.client.get(url)
        self.assertContains(page, "Diagnosis &amp; treatment")
        self.assertContains(page, "External parasites")
        data = self.consultation_data(visit, **{
            f"exam-{temperature.pk}-value": "39.9",
            f"history-{option.pk}-value": "2 days",
            f"vaccine-{rabies.pk}-given_on": visit.visit_date.isoformat(),
            "treatment-TOTAL_FORMS": "1", "treatment-0-kind": "medication", "treatment-0-name": "Omeprazole",
            "treatment-0-quantity": "1",
            "_complete": "1",
        })
        response = self.client.post(url, data)
        self.assertRedirects(response, url)
        visit.refresh_from_db()
        self.assertEqual(visit.status, Appointment.COMPLETED)
        self.assertEqual(visit.weight_kg, Decimal("12.5"))
        self.assertEqual(visit.diagnosis, "Gastritis")
        self.assertTrue(visit.examinations.get().is_abnormal)
        self.assertEqual(visit.history.get().value, "2 days")
        vaccination = visit.vaccinations.get()
        self.assertEqual(vaccination.next_due_date, visit.visit_date + datetime.timedelta(days=365))
        # Only filled-in rows are stored.
        self.assertEqual(visit.examinations.count(), 1)
        self.assertEqual(visit.treatments.get().name, "Omeprazole")
        self.assertEqual(visit.updated_by, self.vet)

    def test_bad_examination_value_keeps_the_page_and_saves_nothing(self):
        visit = self.visit()
        temperature = ExaminationType.objects.get(code="temperature")
        self.login(self.vet)
        response = self.client.post(visit.get_absolute_url(), self.consultation_data(visit, **{f"exam-{temperature.pk}-value": "hot"}))
        self.assertContains(response, "Enter a number.")
        visit.refresh_from_db()
        self.assertEqual(visit.diagnosis, "")

    def test_reception_cannot_see_or_record_clinical_details(self):
        visit = self.visit(diagnosis="Secret")
        self.login(self.reception)
        response = self.client.get(visit.get_absolute_url())
        self.assertNotContains(response, "Diagnosis &amp; treatment")
        self.assertNotContains(response, "Secret")
        self.client.post(visit.get_absolute_url(), self.consultation_data(visit, **{"clinical-diagnosis": "Changed"}))
        visit.refresh_from_db()
        self.assertEqual(visit.diagnosis, "Secret")
        self.assertEqual(visit.weight_kg, Decimal("12.5"))
        status_url = reverse("dashboard:appointment_status", args=[visit.pk, "complete"])
        self.assertEqual(self.client.post(status_url).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:appointment_print", args=[visit.pk])).status_code, 403)

    def test_completed_visit_is_locked_for_reception(self):
        visit = self.visit(reason="Original")
        visit.apply("complete", user=self.vet)
        self.login(self.reception)
        response = self.client.post(visit.get_absolute_url(), {"visit-reason": "Changed"})
        self.assertEqual(response.status_code, 403)
        visit.refresh_from_db()
        self.assertEqual(visit.reason, "Original")

    def test_vet_can_reopen_a_completed_visit(self):
        visit = self.visit()
        visit.apply("complete", user=self.vet)
        self.login(self.vet)
        self.client.post(reverse("dashboard:appointment_status", args=[visit.pk, "reopen"]))
        visit.refresh_from_db()
        self.assertEqual(visit.status, Appointment.IN_CONSULTATION)

    def test_cancel_keeps_the_reason(self):
        visit = self.visit()
        self.login(self.reception)
        self.client.post(reverse("dashboard:appointment_status", args=[visit.pk, "cancel"]), {"reason": "Owner left"})
        visit.refresh_from_db()
        self.assertEqual((visit.status, visit.cancellation_reason), (Appointment.CANCELLED, "Owner left"))

    def test_only_attending_staff_can_be_chosen(self):
        visit = self.visit()
        self.login(self.vet)
        response = self.client.post(visit.get_absolute_url(), self.consultation_data(visit, **{"visit-attended_by": self.reception.pk}))
        self.assertContains(response, "Select a valid choice")


class PageTests(ClinicTestCase):
    def test_pages_open_for_each_role(self):
        visit = self.visit(weight_kg=Decimal("10"))
        pages = [
            reverse("dashboard:home"),
            reverse("dashboard:appointment_queue"),
            reverse("dashboard:list", args=["appointments", "appointment"]) + "?period=today&status=waiting&q=9801",
            reverse("dashboard:add", args=["appointments", "appointment"]) + f"?pet={self.pet.pk}",
            visit.get_absolute_url(),
            reverse("dashboard:client_record", args=[self.client_a.pk]),
            reverse("dashboard:pet_record", args=[self.pet.pk]),
            reverse("dashboard:list", args=["clients", "pet"]),
            reverse("dashboard:add", args=["clients", "pet"]),
            reverse("dashboard:my_profile"),
        ]
        for user in (self.vet, self.reception, self.admin):
            self.login(user)
            for url in pages:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_queue_remembers_list_or_board(self):
        self.login(self.reception)
        queue = reverse("dashboard:appointment_queue")
        self.assertFalse(self.client.get(queue).context["board"])
        self.assertTrue(self.client.get(queue + "?view=board").context["board"])
        self.assertTrue(self.client.get(queue).context["board"])
        self.assertFalse(self.client.get(queue + "?view=list").context["board"])
        self.assertFalse(self.client.get(queue).context["board"])

    def test_print_summary(self):
        visit = self.visit(diagnosis="Otitis externa")
        self.login(self.vet)
        response = self.client.get(reverse("dashboard:appointment_print", args=[visit.pk]))
        self.assertContains(response, "Otitis externa")
        self.assertContains(response, visit.number)

    def test_default_fields_match_the_paper_form(self):
        exams = list(ExaminationType.objects.filter(is_active=True).values_list("name", flat=True))
        self.assertEqual(exams, [
            "Temperature", "Respiration rate", "Pulse / heart rate", "Mucous membranes (M.M.)", "Skin",
            "Capillary refill time (CRT)", "Anaemia", "Vomiting / Diarrhoea", "Dehydration",
        ])
        self.assertEqual(
            list(VaccinationType.objects.values_list("name", flat=True)), ["Rabies", "DHPPiL", "Corona", "Deworming"]
        )
        self.assertEqual(HistoryOption.objects.count(), 6)

    def test_admin_adds_a_field_and_it_appears_on_every_visit(self):
        self.login(self.admin)
        response = self.client.post(reverse("dashboard:add", args=["clinic_setup", "examinationtype"]), {
            "name": "Blood glucose", "value_kind": "number", "unit": "mg/dL", "min_value": "70", "max_value": "140",
            "options": "", "normal_options": "", "description": "", "order": "20", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        glucose = ExaminationType.objects.get(name="Blood glucose")
        self.assertEqual(glucose.code, "blood-glucose")
        visit = self.visit()
        self.login(self.vet)
        self.assertContains(self.client.get(visit.get_absolute_url()), "Blood glucose")

    def test_choice_field_needs_options(self):
        self.login(self.admin)
        response = self.client.post(reverse("dashboard:add", args=["clinic_setup", "historyoption"]), {
            "name": "Diet", "value_kind": "choice", "options": "", "normal_options": "", "order": "0",
            "is_active": "on",
        })
        self.assertContains(response, "Enter at least one option")

    def test_field_in_use_cannot_be_deleted_and_keeps_its_type(self):
        temperature = ExaminationType.objects.get(code="temperature")
        ExaminationResult.objects.create(appointment=self.visit(), exam_type=temperature, value="38.5")
        self.login(self.admin)
        url = reverse("dashboard:delete", args=["clinic_setup", "examinationtype", temperature.pk])
        self.assertContains(self.client.post(url, follow=True), "cannot be deleted")
        edit = self.client.get(reverse("dashboard:edit", args=["clinic_setup", "examinationtype", temperature.pk]))
        self.assertContains(edit, "Locked because visits already have values")

    def test_printed_forms(self):
        visit = self.visit(weight_kg=Decimal("12.5"), diagnosis="Otitis externa")
        temperature = ExaminationType.objects.get(code="temperature")
        ExaminationResult.objects.create(appointment=visit, exam_type=temperature, value="40.2")
        self.login(self.vet)
        response = self.client.get(reverse("dashboard:appointment_form", args=[visit.pk]))
        for text in ("REGISTRATION", "Patient's History", "Vaccination Record", "Clinical Examination",
                     "AUTHORIZATION", "Otitis externa", "40.2 °C", visit.number, self.client_a.full_name):
            self.assertContains(response, text)
        blank = self.client.get(reverse("dashboard:appointment_blank_form"))
        self.assertContains(blank, "DHPPiL")
        self.assertNotContains(blank, self.client_a.full_name)
        self.login(self.reception)
        self.assertEqual(self.client.get(reverse("dashboard:appointment_blank_form")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:appointment_form", args=[visit.pk])).status_code, 403)

    def test_pet_record_tracks_values_across_visits(self):
        temperature = ExaminationType.objects.get(code="temperature")
        first = self.visit(visit_date=timezone.localdate() - datetime.timedelta(days=10))
        ExaminationResult.objects.create(appointment=first, exam_type=temperature, value="38.4")
        second = self.visit()
        ExaminationResult.objects.create(appointment=second, exam_type=temperature, value="40.1")
        self.login(self.vet)
        response = self.client.get(reverse("dashboard:pet_record", args=[self.pet.pk]))
        self.assertContains(response, "Clinical history")
        self.assertContains(response, "38.4")
        self.assertContains(response, "40.1")
        # The visit page shows the value from the previous visit next to the field.
        self.assertContains(self.client.get(second.get_absolute_url()), "38.4")

    def test_species_in_use_cannot_be_deleted(self):
        self.login(self.admin)
        response = self.client.post(reverse("dashboard:delete", args=["clinic_setup", "species", self.dog.pk]), follow=True)
        self.assertContains(response, "cannot be deleted")
        self.assertTrue(Species.objects.filter(pk=self.dog.pk).exists())


class ReadOnlyClinicalTests(ClinicTestCase):
    def test_reception_with_clinical_view_sees_values_read_only(self):
        from django.contrib.auth.models import Permission

        self.reception.user_permissions.add(Permission.objects.get(codename="view_clinical"))
        visit = self.visit()
        ExaminationResult.objects.create(appointment=visit, exam_type=ExaminationType.objects.get(code="temperature"), value="40.3")
        AppointmentHistory.objects.create(appointment=visit, option=HistoryOption.objects.get(name="Skin"), value="Itching")
        self.login(self.reception)
        response = self.client.get(visit.get_absolute_url())
        self.assertContains(response, "40.3")
        self.assertContains(response, "Itching")
        self.assertNotContains(response, 'name="exam-')
