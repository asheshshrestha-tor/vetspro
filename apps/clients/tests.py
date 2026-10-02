import datetime
import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import ADMINISTRATOR, RECEPTIONIST, VETERINARIAN
from apps.appointments.models import Appointment, PlannedVaccination, Treatment, VaccinationRecord
from apps.billing.tests import make_user
from apps.clinic_setup.models import PlanDose, Species, TreatmentTemplate, TreatmentTemplateLine, VaccinationPlan, VaccinationType
from apps.shop.models import BranchPrice, Product, ProductCategory

from .models import Client, Pet, PetDocument

PRIVATE = tempfile.mkdtemp(prefix="bmb-private-")


class RecordTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = Client.objects.create(full_name="Ram Shrestha", phone="9801234567")
        cls.pet = Pet.objects.create(client=cls.owner, name="Bruno", species=Species.objects.get(name="Dog"))
        cls.vet = make_user("vet", VETERINARIAN)
        cls.reception = make_user("reception", RECEPTIONIST)
        cls.admin = make_user("manager", ADMINISTRATOR)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(PRIVATE, ignore_errors=True)


@override_settings(PRIVATE_MEDIA_ROOT=PRIVATE)
class DocumentTests(RecordTestCase):
    def upload(self, user, name="cbc.pdf", content=b"%PDF-1.4 report", **extra):
        self.client.force_login(user)
        data = {"document-file": SimpleUploadedFile(name, content), "document-kind": "lab", "document-title": "", **extra}
        return self.client.post(reverse("dashboard:pet_document_add", args=[self.pet.pk]), data)

    def test_reception_uploads_and_vet_opens_a_lab_report(self):
        self.upload(self.reception)
        document = PetDocument.objects.get()
        self.assertEqual(document.uploaded_by, self.reception)
        self.assertTrue(document.file.name.startswith(f"pets/{self.pet.pk}/"))
        self.client.force_login(self.vet)
        response = self.client.get(document.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 report")
        record = self.client.get(reverse("dashboard:pet_record", args=[self.pet.pk]))
        self.assertContains(record, str(document))

    def test_files_are_not_public_and_need_permission(self):
        self.upload(self.reception)
        document = PetDocument.objects.get()
        self.client.logout()
        self.assertNotEqual(self.client.get(document.get_absolute_url()).status_code, 200)
        with self.assertRaises(ValueError):
            document.file.url

    def test_unsafe_files_are_refused(self):
        self.upload(self.reception, name="run.exe", content=b"MZ")
        self.assertFalse(PetDocument.objects.exists())

    def test_upload_is_filed_under_the_visit_and_delete_removes_the_file(self):
        visit = Appointment.objects.create(client=self.owner, pet=self.pet, reason="Check")
        self.upload(self.vet, appointment=visit.pk)
        document = PetDocument.objects.get()
        self.assertEqual(document.appointment, visit)
        storage, name = document.file.storage, document.file.name
        self.assertTrue(storage.exists(name))
        self.client.post(reverse("dashboard:pet_document_delete", args=[self.pet.pk, document.pk]))
        self.assertFalse(PetDocument.objects.exists())
        self.assertFalse(storage.exists(name))


class TreatmentTemplateTests(RecordTestCase):
    def test_template_adds_its_lines_at_the_branch_price(self):
        medicines = ProductCategory.objects.get(name="Medicines")
        drug = Product.objects.create(
            category=medicines, name="Metronidazole 200 mg", unit="tablet", price=Decimal("10"),
            treatment_kind=Product.MEDICINE, default_dose="15 mg/kg", default_route="Oral", track_stock=False,
        )
        template = TreatmentTemplate.objects.create(name="Gastroenteritis", diagnosis="Acute gastroenteritis")
        TreatmentTemplateLine.objects.create(template=template, item=drug, frequency="Twice a day", quantity=10)
        visit = Appointment.objects.create(client=self.owner, pet=self.pet, reason="Vomiting")
        BranchPrice.objects.create(product=drug, branch=visit.branch, price=Decimal("12"))
        self.client.force_login(self.vet)
        page = self.client.get(visit.get_absolute_url())
        self.assertContains(page, "Gastroenteritis")
        data = self.visit_form(visit)
        data["_template"] = str(template.pk)
        response = self.client.post(visit.get_absolute_url(), data)
        self.assertRedirects(response, visit.get_absolute_url() + "#result", fetch_redirect_response=False)
        treatment = Treatment.objects.get(appointment=visit)
        self.assertEqual((treatment.name, treatment.dose, treatment.frequency), ("Metronidazole 200 mg", "15 mg/kg", "Twice a day"))
        self.assertEqual((treatment.quantity, treatment.unit_price), (Decimal("10"), Decimal("12")))
        visit.refresh_from_db()
        self.assertEqual(visit.diagnosis, "Acute gastroenteritis")

    def visit_form(self, visit):
        """The consultation page's current values, as the browser would post them."""
        from apps.appointments.tests import ConsultationPermissionTests

        return ConsultationPermissionTests.consultation_data(self, visit, **{"clinical-diagnosis": ""})


class VaccinationPlanTests(RecordTestCase):
    def test_plan_doses_are_planned_and_ticked_off(self):
        dhpp = VaccinationType.objects.create(name="DHPPi test", booster_interval_days=21)
        rabies = VaccinationType.objects.create(name="Rabies test")
        plan = VaccinationPlan.objects.create(name="Puppy course", species=self.pet.species)
        PlanDose.objects.create(plan=plan, vaccine=dhpp, label="1st", days_after_start=0)
        PlanDose.objects.create(plan=plan, vaccine=dhpp, label="2nd", days_after_start=21)
        PlanDose.objects.create(plan=plan, vaccine=rabies, days_after_start=90)
        start = timezone.localdate()
        self.client.force_login(self.reception)
        self.client.post(reverse("dashboard:pet_plan", args=[self.pet.pk]), {"plan": plan.pk, "start": start.isoformat()})
        planned = list(PlannedVaccination.objects.filter(pet=self.pet))
        self.assertEqual([p.due_date for p in planned], [start, start + datetime.timedelta(days=21), start + datetime.timedelta(days=90)])

        visit = Appointment.objects.create(client=self.owner, pet=self.pet, reason="Vaccination")
        VaccinationRecord.objects.create(appointment=visit, vaccine=dhpp, given_on=start)
        statuses = list(PlannedVaccination.objects.filter(pet=self.pet).values_list("label", "status"))
        self.assertEqual(statuses, [("1st", "given"), ("2nd", "due"), ("", "due")])

        second = planned[1]
        self.client.post(reverse("dashboard:pet_plan", args=[self.pet.pk]), {"dose": second.pk})
        second.refresh_from_db()
        self.assertEqual(second.status, PlannedVaccination.SKIPPED)
        record = self.client.get(reverse("dashboard:pet_record", args=[self.pet.pk]))
        self.assertContains(record, "Puppy course")
