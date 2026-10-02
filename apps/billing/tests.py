from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import ADMINISTRATOR, RECEPTIONIST, VETERINARIAN
from apps.appointments.models import Appointment
from apps.clients.models import Client, Pet
from apps.clinic_setup.models import Species
from apps.core.models import SiteSettings
from apps.shop.models import Product, ProductCategory, StockMovement, change_stock

from .models import Invoice, InvoiceItem

User = get_user_model()


def make_user(username, role):
    user = User.objects.create_user(username, password="pw-Test-12345", is_staff=True, first_name=username.title())
    group = Group.objects.get(name=role)
    user.groups.add(group)
    user.staff_profile.role = group
    user.staff_profile.save()
    return user


class ShopTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.food = ProductCategory.objects.get(name="Food & treats")
        cls.services = ProductCategory.objects.get(name="Clinic services")
        cls.kibble = Product.objects.create(category=cls.food, name="Puppy kibble 3 kg", unit="bag", price=Decimal("2450"))
        change_stock(cls.kibble, 10, StockMovement.OPENING)
        cls.consultation = Product.objects.create(
            category=cls.services, name="Consultation", price=Decimal("500"), track_stock=False
        )
        cls.client_a = Client.objects.create(full_name="Ram Shrestha", phone="9801234567")
        cls.pet = Pet.objects.create(client=cls.client_a, name="Bruno", species=Species.objects.get(name="Dog"))
        cls.admin = make_user("manager", ADMINISTRATOR)
        cls.vet = make_user("vet", VETERINARIAN)
        cls.reception = make_user("reception", RECEPTIONIST)

    def invoice(self, **fields):
        return Invoice.objects.create(**fields)

    def add(self, invoice, product=None, quantity=1, price=None, description=""):
        return InvoiceItem.objects.create(
            invoice=invoice, product=product, quantity=Decimal(quantity),
            unit_price=price if price is not None else product.price, description=description or product.name,
        )


class InvoiceRuleTests(ShopTestCase):
    def test_totals_with_discount_and_vat(self):
        invoice = self.invoice(discount=Decimal("450"), vat_percent=Decimal("13"))
        self.add(invoice, self.kibble, 2)
        self.add(invoice, self.consultation)
        invoice.recalculate()
        self.assertEqual(invoice.subtotal, Decimal("5400.00"))
        self.assertEqual(invoice.vat_amount, Decimal("643.50"))
        self.assertEqual(invoice.total, Decimal("5593.50"))

    def test_issuing_takes_stock_and_numbers_the_invoice(self):
        invoice = self.invoice()
        self.add(invoice, self.kibble, 3)
        self.add(invoice, self.consultation)
        self.assertEqual(invoice.display_number, f"Draft #{invoice.pk}")
        invoice.issue(self.reception)
        self.kibble.refresh_from_db()
        self.assertEqual(self.kibble.stock_quantity, Decimal("7"))
        self.assertTrue(invoice.number.startswith("INV-") and invoice.number.endswith("-00001"))
        sale = self.kibble.stock_movements.get(reason=StockMovement.SALE)
        self.assertEqual((sale.quantity, sale.invoice), (Decimal("-3"), invoice))

    def test_not_enough_stock_stops_the_whole_invoice(self):
        invoice = self.invoice()
        self.add(invoice, self.kibble, 11)
        with self.assertRaises(ValidationError):
            invoice.issue(self.reception)
        invoice.refresh_from_db()
        self.kibble.refresh_from_db()
        self.assertEqual((invoice.status, invoice.number), (Invoice.DRAFT, ""))
        self.assertEqual(self.kibble.stock_quantity, Decimal("10"))

    def test_payments_mark_it_paid(self):
        invoice = self.invoice()
        self.add(invoice, self.consultation)
        invoice.issue(self.reception)
        invoice.add_payment(Decimal("200"), "cash", self.reception)
        self.assertEqual((invoice.payment_label, invoice.balance), ("Partly paid", Decimal("300")))
        with self.assertRaises(ValidationError):
            invoice.add_payment(Decimal("400"), "cash", self.reception)
        invoice.add_payment(Decimal("300"), "esewa", self.reception, "TX123")
        self.assertEqual(invoice.status, Invoice.PAID)
        with self.assertRaises(ValidationError):
            invoice.add_payment(Decimal("1"), "cash", self.reception)

    def test_cancelling_returns_stock(self):
        invoice = self.invoice()
        self.add(invoice, self.kibble, 4)
        invoice.issue(self.reception)
        invoice.cancel(self.admin, "Wrong item")
        self.kibble.refresh_from_db()
        self.assertEqual(self.kibble.stock_quantity, Decimal("10"))
        self.assertEqual(invoice.status, Invoice.CANCELLED)

    def test_numbers_only_go_to_issued_invoices(self):
        first, draft, second = self.invoice(), self.invoice(), self.invoice()
        for invoice in (first, draft, second):
            self.add(invoice, self.consultation)
        first.issue(self.reception)
        second.issue(self.reception)
        self.assertEqual(int(second.number[-5:]) - int(first.number[-5:]), 1)
        self.assertEqual(draft.number, "")


class SalePageTests(ShopTestCase):
    def items_data(self, rows, prefix="items"):
        data = {
            f"{prefix}-TOTAL_FORMS": str(len(rows)), f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000",
            "invoice-discount": "0", "invoice-vat_percent": "0", "invoice-notes": "",
            "invoice-customer_name": "", "invoice-customer_phone": "",
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"{prefix}-{index}-{key}"] = value
        return data

    def test_counter_sale_without_client_or_visit(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={"default_vat_percent": Decimal("13")})
        self.client.force_login(self.reception)
        response = self.client.post(reverse("dashboard:add", args=["billing", "invoice"]), {"customer_name": "Walk-in buyer"})
        invoice = Invoice.objects.get()
        self.assertRedirects(response, invoice.get_absolute_url())
        self.assertEqual((invoice.customer_display, invoice.vat_percent), ("Walk-in buyer", Decimal("13")))

        data = self.items_data([
            {"product": self.kibble.pk, "description": "", "quantity": "2", "unit_price": ""},
            {"product": "", "description": "Gift wrapping", "quantity": "1", "unit_price": "50"},
        ])
        data["invoice-customer_name"] = "Walk-in buyer"
        data["invoice-vat_percent"] = "0"
        data["_issue"] = "1"
        response = self.client.post(invoice.get_absolute_url(), data)
        self.assertRedirects(response, invoice.get_absolute_url())
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.ISSUED)
        self.assertEqual(invoice.total, Decimal("4950.00"))
        self.assertEqual(invoice.items.get(product=self.kibble).description, "Puppy kibble 3 kg")

        response = self.client.post(reverse("dashboard:invoice_pay", args=[invoice.pk]), {
            "payment-amount": "4950", "payment-method": "cash", "payment-reference": "",
        })
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.PAID)
        print_page = self.client.get(reverse("dashboard:invoice_print", args=[invoice.pk]))
        self.assertContains(print_page, invoice.number)
        self.assertContains(print_page, "Rs. 4,950.00")

    def test_item_without_product_needs_description_and_price(self):
        invoice = self.invoice()
        self.client.force_login(self.reception)
        response = self.client.post(invoice.get_absolute_url(), self.items_data([
            {"product": "", "description": "", "quantity": "2", "unit_price": ""},
        ]))
        self.assertContains(response, "Choose a product or describe the item.")
        self.assertContains(response, "Enter the price.")

    def test_insufficient_stock_is_explained(self):
        invoice = self.invoice()
        self.client.force_login(self.reception)
        data = self.items_data([{"product": self.kibble.pk, "description": "", "quantity": "50", "unit_price": ""}])
        data["_issue"] = "1"
        response = self.client.post(invoice.get_absolute_url(), data)
        self.assertContains(response, "in stock")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.DRAFT)

    def test_visit_bill_is_created_once_for_the_owner(self):
        visit = Appointment.objects.create(client=self.client_a, pet=self.pet, reason="Check-up")
        self.client.force_login(self.vet)
        url = reverse("dashboard:invoice_for_visit", args=[visit.pk])
        first = self.client.post(url)
        invoice = Invoice.objects.get()
        self.assertRedirects(first, invoice.get_absolute_url())
        self.assertEqual((invoice.client, invoice.appointment), (self.client_a, visit))
        self.client.post(url)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertContains(self.client.get(visit.get_absolute_url()), invoice.display_number)

    def test_issued_invoices_cannot_be_deleted_or_edited(self):
        invoice = self.invoice()
        self.add(invoice, self.consultation)
        invoice.issue(self.reception)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("dashboard:delete", args=["billing", "invoice", invoice.pk])).status_code, 403)
        self.assertEqual(self.client.post(invoice.get_absolute_url(), self.items_data([])).status_code, 403)

    def test_reception_cannot_cancel_or_adjust_stock(self):
        invoice = self.invoice()
        self.add(invoice, self.consultation)
        invoice.issue(self.reception)
        self.client.force_login(self.reception)
        self.assertEqual(self.client.post(reverse("dashboard:invoice_cancel", args=[invoice.pk])).status_code, 403)
        stock_url = reverse("dashboard:product_stock", args=[self.kibble.pk])
        self.assertEqual(self.client.get(stock_url).status_code, 200)
        self.assertEqual(self.client.post(stock_url, {"reason": "purchase", "quantity": "5"}).status_code, 403)

    def test_pages_open_for_each_role(self):
        invoice = self.invoice(client=self.client_a)
        pages = [
            reverse("dashboard:home"),
            reverse("dashboard:list", args=["billing", "invoice"]) + "?period=today&status=draft&q=9801",
            reverse("dashboard:add", args=["billing", "invoice"]),
            invoice.get_absolute_url(),
            reverse("dashboard:list", args=["shop", "product"]),
            reverse("dashboard:product_stock", args=[self.kibble.pk]),
            reverse("dashboard:client_record", args=[self.client_a.pk]),
            reverse("dashboard:appointment_queue"),
        ]
        for user in (self.admin, self.vet, self.reception):
            self.client.force_login(user)
            for url in pages:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.admin)
        for url in (reverse("dashboard:list", args=["shop", "stockmovement"]), reverse("dashboard:add", args=["shop", "product"])):
            self.assertEqual(self.client.get(url).status_code, 200)


class ShopPageTests(ShopTestCase):
    def test_admin_adds_product_with_opening_stock_and_records_delivery(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("dashboard:add", args=["shop", "product"]), {
            "category": self.food.pk, "name": "Cat food 1 kg", "brand": "Whiskas", "sku": "", "unit": "bag",
            "price": "950", "cost_price": "700", "track_stock": "on", "opening_stock": "12", "low_stock_level": "3",
            "show_online": "on", "description": "", "is_active": "on",
            "inline0-TOTAL_FORMS": "0", "inline0-INITIAL_FORMS": "0",
        })
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name="Cat food 1 kg")
        self.assertEqual(product.stock_quantity, Decimal("12"))
        self.assertEqual(product.slug, "cat-food-1-kg")
        stock_url = reverse("dashboard:product_stock", args=[product.pk])
        self.client.post(stock_url, {"reason": "purchase", "quantity": "6", "note": "Bill 55"})
        self.client.post(stock_url, {"reason": "adjustment", "quantity": "17", "note": "Counted"})
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, Decimal("17"))
        self.assertEqual(
            list(product.stock_movements.order_by("id").values_list("reason", "quantity")),
            [("opening", Decimal("12")), ("purchase", Decimal("6")), ("adjustment", Decimal("-1"))],
        )

    def test_public_shop_lists_only_online_products(self):
        hidden = Product.objects.create(category=self.food, name="Staff-only item", price=Decimal("10"), show_online=False)
        response = self.client.get(reverse("shop:list"))
        self.assertContains(response, "Puppy kibble 3 kg")
        self.assertNotContains(response, hidden.name)
        self.assertNotContains(response, "Consultation")
        self.assertEqual(self.client.get(reverse("shop:product", args=[self.consultation.slug])).status_code, 404)
        SiteSettings.objects.update_or_create(pk=1, defaults={"whatsapp": "+977 976-5960063"})
        detail = self.client.get(self.kibble.get_absolute_url())
        self.assertContains(detail, "Rs. 2,450")
        self.assertContains(detail, "Order on WhatsApp")
        sorted_page = self.client.get(reverse("shop:list"), {"sort": "-price"})
        names = [p.name for p in sorted_page.context["products"]]
        self.assertEqual(names[0], "Puppy kibble 3 kg")
        self.kibble.stock_quantity = 0
        self.kibble.save()
        in_stock = self.client.get(reverse("shop:list"), {"stock": "1"})
        self.assertNotContains(in_stock, "Puppy kibble 3 kg")
        self.assertEqual(self.client.get(reverse("shop:category", args=[self.food.slug])).status_code, 200)
        self.assertContains(self.client.get(reverse("shop:list"), {"q": "kibble"}), "Puppy kibble")

    def test_product_search_returns_price_for_invoices(self):
        self.client.force_login(self.reception)
        results = self.client.get(reverse("dashboard:autocomplete", args=["shop", "product"]), {"q": "kibble"}).json()["results"]
        self.assertEqual(results[0]["price"], "2450.00")
        self.assertEqual(results[0]["stock"], "10.00")


class TreatmentBillingTests(ShopTestCase):
    """Treatment given in a visit becomes its bill; shop items can be added on top."""

    def setUp(self):
        self.doxy = Product.objects.create(
            category=ProductCategory.objects.get(name="Medicines"), name="Doxycycline 100 mg", unit="tablet",
            price=Decimal("25"), treatment_kind=Product.MEDICINE, default_dose="10 mg/kg", default_route="Oral",
            default_frequency="Once a day", default_duration="21 days",
        )
        change_stock(self.doxy, 100, StockMovement.OPENING)
        self.consultation.treatment_kind = Product.PROCEDURE
        self.consultation.save()
        self.advice = Product.objects.create(
            category=self.services, name="Diet advice", price=Decimal("0"), track_stock=False,
            treatment_kind=Product.ADVICE,
        )
        self.visit = Appointment.objects.create(client=self.client_a, pet=self.pet, reason="Tick fever")

    def consultation_data(self, rows, **extra):
        from apps.clinic_setup.models import ExaminationType, HistoryOption, VaccinationType

        data = {
            "visit-reason": self.visit.reason, "visit-attended_by": "", "visit-weight_kg": "",
            "clinical-clinical_notes": "", "clinical-diagnosis": "Ehrlichiosis", "clinical-outcome": "",
            "clinical-result_notes": "", "clinical-follow_up_date": "",
            "treatment-TOTAL_FORMS": str(len(rows)), "treatment-INITIAL_FORMS": "0",
            "treatment-MIN_NUM_FORMS": "0", "treatment-MAX_NUM_FORMS": "1000",
        }
        for model, prefix in ((HistoryOption, "history"), (ExaminationType, "exam")):
            for field in model.objects.filter(is_active=True):
                data[f"{prefix}-{field.pk}-value"] = ""
        for vaccine in VaccinationType.objects.filter(is_active=True):
            for name in ("given_on", "next_due_date", "batch_number", "notes"):
                data[f"vaccine-{vaccine.pk}-{name}"] = ""
        for index, row in enumerate(rows):
            base = {"item": "", "kind": "medication", "name": "", "dose": "", "route": "", "frequency": "",
                    "duration": "", "quantity": "1", "unit_price": "", "notes": ""}
            base.update(row)
            for key, value in base.items():
                data[f"treatment-{index}-{key}"] = value
        data.update(extra)
        return data

    def test_catalogue_item_fills_the_treatment_and_generates_the_bill(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={"visit_fee_item": self.consultation})
        self.client.force_login(self.vet)
        response = self.client.post(self.visit.get_absolute_url(), self.consultation_data([
            {"item": str(self.doxy.pk), "quantity": "21"},
            {"item": str(self.advice.pk), "kind": "advice"},
            {"name": "Tick removal", "kind": "procedure", "unit_price": "150"},
        ], _bill="1"))
        invoice = Invoice.objects.get()
        self.assertRedirects(response, invoice.get_absolute_url())

        doxy = self.visit.treatments.get(item=self.doxy)
        self.assertEqual((doxy.name, doxy.unit_price, doxy.amount), ("Doxycycline 100 mg", Decimal("25.00"), Decimal("525.00")))
        self.assertIsNone(self.visit.treatments.get(item=self.advice).unit_price)

        lines = {item.description: (item.source, item.line_total) for item in invoice.items.all()}
        self.assertEqual(lines["Consultation"], ("visit_fee", Decimal("500.00")))
        self.assertEqual(lines["Tick removal"], ("treatment", Decimal("150.00")))
        self.assertEqual(len(lines), 3)
        self.assertEqual(invoice.total, Decimal("1175.00"))
        self.assertEqual((invoice.client, invoice.appointment), (self.client_a, self.visit))

    def test_regenerating_keeps_shop_items_and_follows_the_treatment(self):
        self.client.force_login(self.vet)
        self.client.post(self.visit.get_absolute_url(), self.consultation_data(
            [{"item": str(self.doxy.pk), "quantity": "10"}], _bill="1"))
        invoice = Invoice.objects.get()
        self.add(invoice, self.kibble)  # bought at the counter as well
        treatment = self.visit.treatments.get()
        treatment.quantity = Decimal("14")
        treatment.save()

        self.client.post(reverse("dashboard:invoice_for_visit", args=[self.visit.pk]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.items.count(), 2)
        self.assertEqual(invoice.items.get(source="treatment").quantity, Decimal("14"))
        self.assertEqual(invoice.total, Decimal("2800.00"))  # 14 x 25 + 2450

        page = self.client.get(invoice.get_absolute_url())
        self.assertContains(page, "From the visit")
        self.assertContains(page, "Other items")
        self.assertEqual(page.context["formset"].queryset.count(), 1)

    def test_completing_bills_automatically_only_when_something_is_charged(self):
        self.client.force_login(self.vet)
        self.client.post(self.visit.get_absolute_url(), self.consultation_data(
            [{"item": str(self.advice.pk), "kind": "advice"}], _complete="1"))
        self.assertFalse(Invoice.objects.exists())

        other = Appointment.objects.create(client=self.client_a, pet=self.pet, reason="Check-up")
        self.visit = other
        self.client.post(other.get_absolute_url(), self.consultation_data(
            [{"item": str(self.doxy.pk), "quantity": "5"}], _complete="1"))
        self.assertEqual(Invoice.objects.get().appointment, other)

    def test_issued_bill_is_not_rebuilt(self):
        self.client.force_login(self.vet)
        self.client.post(self.visit.get_absolute_url(), self.consultation_data(
            [{"item": str(self.doxy.pk), "quantity": "5"}], _bill="1"))
        invoice = Invoice.objects.get()
        invoice.issue(self.reception)
        self.visit.treatments.update(quantity=Decimal("50"))
        response = self.client.post(reverse("dashboard:invoice_for_visit", args=[self.visit.pk]))
        self.assertRedirects(response, invoice.get_absolute_url())
        invoice.refresh_from_db()
        self.assertEqual(invoice.total, Decimal("125.00"))

    def test_issue_and_take_full_payment_in_one_step(self):
        invoice = self.invoice(customer_name="Walk-in")
        self.client.force_login(self.reception)
        data = SalePageTests.items_data(self, [{"product": str(self.kibble.pk), "description": "", "quantity": "1", "unit_price": ""}])
        data.update({"invoice-customer_name": "Walk-in", "_issue": "1", "paid_by": "esewa"})
        self.client.post(invoice.get_absolute_url(), data)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.PAID)
        self.assertEqual(invoice.payments.get().method, "esewa")

    def test_treatment_catalogue_module(self):
        self.client.force_login(self.admin)
        list_url = reverse("dashboard:list", args=["shop", "treatmentitem"])
        page = self.client.get(list_url)
        self.assertContains(page, "Doxycycline 100 mg")
        self.assertNotContains(page, "Puppy kibble")  # shop-only items stay out of the catalogue
        response = self.client.post(reverse("dashboard:add", args=["shop", "treatmentitem"]), {
            "treatment_kind": "procedure", "name": "Ear flushing", "brand": "", "unit": "procedure", "price": "400",
            "cost_price": "", "default_dose": "", "default_route": "", "default_frequency": "", "default_duration": "",
            "low_stock_level": "0", "category": "", "description": "", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        item = Product.objects.get(name="Ear flushing")
        self.assertEqual((item.category.name, item.track_stock, item.show_online), ("Clinic services", False, False))

        self.client.force_login(self.vet)
        results = self.client.get(reverse("dashboard:autocomplete", args=["shop", "treatmentitem"]), {"q": "doxy"}).json()["results"]
        self.assertEqual(results[0]["dose"], "10 mg/kg")
        self.assertEqual(results[0]["kind"], "medication")

