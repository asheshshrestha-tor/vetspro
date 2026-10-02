from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import ADMINISTRATOR, RECEPTIONIST, VETERINARIAN
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem
from apps.billing.tests import make_user
from apps.clients.models import Client, Pet
from apps.clinic_setup.models import Species


class ReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("manager", ADMINISTRATOR)
        cls.vet = make_user("vet", VETERINARIAN)
        cls.reception = make_user("reception", RECEPTIONIST)
        owner = Client.objects.create(full_name="Ram Shrestha", phone="9801234567")
        pet = Pet.objects.create(client=owner, name="Bruno", species=Species.objects.get(name="Dog"))
        visit = Appointment.objects.create(client=owner, pet=pet, reason="Check", attended_by=cls.vet)
        invoice = Invoice.objects.create(client=owner, appointment=visit)
        InvoiceItem.objects.create(invoice=invoice, description="Consultation", quantity=1, unit_price=Decimal("800"))
        invoice.issue(cls.admin)
        invoice.add_payment(Decimal("500"), "esewa", cls.admin)
        cls.url = reverse("dashboard:list", args=["reports", "report"])

    def test_report_totals(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"period": "today"})
        self.assertEqual(response.status_code, 200)
        sales = response.context["sales"]
        self.assertEqual((sales["total"], sales["received"], sales["outstanding"]), (Decimal("800"), Decimal("500"), Decimal("300")))
        self.assertEqual(response.context["visits"]["count"], 1)
        self.assertEqual(response.context["providers"][0]["billed"], Decimal("800"))
        self.assertEqual(response.context["top_items"][0]["name"], "Consultation")

    def test_csv_export(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"period": "today", "export": "sales"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Consultation", self.client.get(self.url, {"export": "items"}).content.decode())
        self.assertIn("800", response.content.decode())

    def test_access_by_role(self):
        self.client.force_login(self.reception)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.vet)
        self.assertEqual(self.client.get(self.url).status_code, 200)
