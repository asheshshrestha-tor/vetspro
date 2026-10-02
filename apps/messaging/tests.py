import datetime
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import RECEPTIONIST
from apps.appointments.models import Appointment, VaccinationRecord
from apps.billing.models import Invoice, InvoiceItem
from apps.billing.tests import make_user
from apps.clients.models import Client, Pet
from apps.clinic_setup.models import Species, VaccinationType

from . import providers
from .models import MessageTemplate, OutboundMessage, render_text


class MessagingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = Client.objects.create(full_name="Ram Shrestha", phone="980-1234567", email="ram@example.com")
        cls.pet = Pet.objects.create(client=cls.owner, name="Bruno", species=Species.objects.get(name="Dog"))
        cls.reception = make_user("reception", RECEPTIONIST)
        cls.url = reverse("dashboard:add", args=["messaging", "outboundmessage"])

    def setUp(self):
        self.client.force_login(self.reception)

    def test_placeholders_fill_and_unknown_ones_stay(self):
        self.assertEqual(render_text("Hi {client}, {oops}", {"client": "Ram"}), "Hi Ram, {oops}")

    def test_phone_numbers_get_the_country_code(self):
        self.assertEqual(providers.international("980-1234567"), "9779801234567")
        self.assertEqual(providers.international("+977 9801234567"), "9779801234567")

    def test_vaccination_reminder_is_prefilled_and_opens_whatsapp(self):
        vaccine = VaccinationType.objects.create(name="Rabies test", booster_interval_days=365)
        visit = Appointment.objects.create(client=self.owner, pet=self.pet, reason="Vaccination")
        due = timezone.localdate() + datetime.timedelta(days=5)
        record = VaccinationRecord.objects.create(appointment=visit, vaccine=vaccine, given_on=timezone.localdate(), next_due_date=due)
        page = self.client.get(self.url, {"vaccination": record.pk})
        self.assertContains(page, "Bruno&#x27;s Rabies test vaccination is due on")
        body = page.context["form"].initial["body"]
        response = self.client.post(self.url, {
            "vaccination": record.pk, "purpose": "vaccination_due", "channel": "whatsapp", "to": self.owner.phone, "body": body,
        })
        self.assertContains(response, "https://wa.me/9779801234567?text=")
        message = OutboundMessage.objects.get()
        self.assertEqual((message.status, message.client, message.pet), (OutboundMessage.OPENED, self.owner, self.pet))
        record.refresh_from_db()
        self.assertIsNotNone(record.reminded_at)
        reminders = self.client.get(reverse("dashboard:message_reminders"))
        self.assertContains(reminders, "Bruno")

    def test_sms_without_a_provider_is_logged_only(self):
        response = self.client.post(self.url, {"client": self.owner.pk, "channel": "sms", "to": self.owner.phone, "body": "Hello"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OutboundMessage.objects.get().status, OutboundMessage.LOGGED)

    def test_sparrow_sms_is_posted(self):
        with mock.patch.dict("os.environ", {"SMS_PROVIDER": "sparrow", "SPARROW_SMS_TOKEN": "t", "SPARROW_SMS_FROM": "BMB"}), \
                mock.patch.object(providers, "_post", return_value=(200, '{"count": 1}')) as post:
            self.client.post(self.url, {"client": self.owner.pk, "channel": "sms", "to": self.owner.phone, "body": "Hello"})
        self.assertEqual(post.call_args.args[1]["to"], "9801234567")
        self.assertEqual(OutboundMessage.objects.get().status, OutboundMessage.SENT)

    def test_bill_by_email(self):
        invoice = Invoice.objects.create(client=self.owner)
        InvoiceItem.objects.create(invoice=invoice, description="Check-up", quantity=1, unit_price=Decimal("500"))
        invoice.recalculate()
        page = self.client.get(self.url, {"invoice": invoice.pk})
        self.assertIn("Rs. 500.00", page.context["form"].initial["body"])
        self.client.post(self.url, {
            "invoice": invoice.pk, "channel": "email", "to": self.owner.email, "subject": "Your bill", "body": "Total Rs. 500",
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(OutboundMessage.objects.get().invoice, invoice)

    def test_templates_are_seeded(self):
        self.assertTrue(MessageTemplate.objects.filter(purpose=MessageTemplate.VACCINATION_DUE).exists())
