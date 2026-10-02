from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import ADMINISTRATOR, RECEPTIONIST
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem
from apps.billing.services import build_visit_bill
from apps.billing.tests import make_user
from apps.clients.models import Client, Pet
from apps.clinic_setup.models import Species
from apps.shop.models import (
    BranchPrice,
    BranchStock,
    PackageItem,
    Product,
    ProductCategory,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    change_stock,
)

from .context import SESSION_KEY
from .models import Branch


class BranchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.main = Branch.main()
        cls.north = Branch.objects.create(name="North", code="nth-1", phone="01-5550000", vat_percent=Decimal("0"))
        cls.food = ProductCategory.objects.get(name="Food & treats")
        cls.kibble = Product.objects.create(category=cls.food, name="Kibble", unit="bag", price=Decimal("1000"))
        change_stock(cls.kibble, 10, StockMovement.OPENING, branch=cls.main)
        cls.owner = Client.objects.create(full_name="Ram Shrestha", phone="9801234567")
        cls.pet = Pet.objects.create(client=cls.owner, name="Bruno", species=Species.objects.get(name="Dog"))
        cls.admin = make_user("manager", ADMINISTRATOR)
        cls.admin.staff_profile.all_branches = True
        cls.admin.staff_profile.save()
        # Receptionist working only at the North branch.
        cls.north_desk = make_user("northdesk", RECEPTIONIST)
        profile = cls.north_desk.staff_profile
        profile.branches.set([cls.north])
        profile.default_branch = cls.north
        profile.save()

    def use_branch(self, branch):
        session = self.client.session
        session[SESSION_KEY] = str(branch.pk) if branch != "all" else "all"
        session.save()


class BranchModelTests(BranchTestCase):
    def test_code_is_cleaned_and_one_main_branch(self):
        self.assertEqual(self.north.code, "NTH1")
        self.north.is_main = True
        self.north.save()
        self.main.refresh_from_db()
        self.assertFalse(self.main.is_main)

    def test_branch_values_fall_back_to_the_hospital(self):
        self.assertEqual(self.north.effective_vat_percent, Decimal("0"))
        self.assertEqual(self.north.effective_phone, "01-5550000")
        self.assertEqual(self.north.effective_address, self.main._site().address)


class ScopingTests(BranchTestCase):
    def test_staff_see_only_their_branch(self):
        here = Appointment.objects.create(branch=self.north, client=self.owner, pet=self.pet, reason="North visit")
        there = Appointment.objects.create(branch=self.main, client=self.owner, pet=self.pet, reason="Main visit")
        self.client.force_login(self.north_desk)
        queue = self.client.get(reverse("dashboard:appointment_queue"))
        self.assertContains(queue, "North visit")
        self.assertNotContains(queue, "Main visit")
        self.assertEqual(self.client.get(here.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(there.get_absolute_url()).status_code, 404)

    def test_tokens_are_counted_per_branch(self):
        a = Appointment.objects.create(branch=self.north, client=self.owner, pet=self.pet, reason="x")
        b = Appointment.objects.create(branch=self.main, client=self.owner, pet=self.pet, reason="y")
        self.assertEqual((a.token, b.token), (1, 1))

    def test_all_branches_mode_needs_a_branch_to_add(self):
        self.client.force_login(self.admin)
        self.use_branch("all")
        response = self.client.get(reverse("dashboard:add", args=["appointments", "appointment"]))
        self.assertContains(response, "Choose a branch")
        self.use_branch(self.north)
        self.assertEqual(self.client.get(reverse("dashboard:add", args=["appointments", "appointment"])).status_code, 200)

    def test_switching_to_a_branch_you_do_not_work_at_is_refused(self):
        self.client.force_login(self.north_desk)
        self.client.post(reverse("dashboard:branch_switch"), {"branch": self.main.pk})
        self.assertNotEqual(self.client.session.get(SESSION_KEY), str(self.main.pk))


class BranchStockTests(BranchTestCase):
    def test_stock_is_kept_per_branch(self):
        self.assertEqual(self.kibble.stock_at(self.main), Decimal("10"))
        self.assertEqual(self.kibble.stock_at(self.north), Decimal("0"))
        with self.assertRaises(ValidationError):
            change_stock(self.kibble, -1, StockMovement.SALE, branch=self.north)
        self.kibble.refresh_from_db()
        self.assertEqual(self.kibble.stock_quantity, Decimal("10"))

    def test_transfer_moves_stock_when_sent_and_received(self):
        transfer = StockTransfer.objects.create(from_branch=self.main, to_branch=self.north)
        StockTransferItem.objects.create(transfer=transfer, product=self.kibble, quantity=4)
        transfer.send(self.admin)
        self.assertEqual(self.kibble.stock_at(self.main), Decimal("6"))
        self.assertEqual(self.kibble.stock_at(self.north), Decimal("0"))
        transfer.receive(self.admin)
        self.assertEqual(self.kibble.stock_at(self.north), Decimal("4"))
        self.kibble.refresh_from_db()
        self.assertEqual(self.kibble.stock_quantity, Decimal("10"))
        with self.assertRaises(ValidationError):
            transfer.cancel(self.admin)

    def test_cancelling_a_sent_transfer_returns_the_stock(self):
        transfer = StockTransfer.objects.create(from_branch=self.main, to_branch=self.north)
        StockTransferItem.objects.create(transfer=transfer, product=self.kibble, quantity=3)
        transfer.send(self.admin)
        transfer.cancel(self.admin)
        self.assertEqual(self.kibble.stock_at(self.main), Decimal("10"))
        self.assertEqual(transfer.status, StockTransfer.CANCELLED)

    def test_only_the_receiving_branch_can_receive(self):
        transfer = StockTransfer.objects.create(from_branch=self.main, to_branch=self.north)
        StockTransferItem.objects.create(transfer=transfer, product=self.kibble, quantity=1)
        transfer.send(self.admin)
        self.north_desk.user_permissions.add(*self._perms("view_stocktransfer", "receive_stocktransfer"))
        self.client.force_login(self.north_desk)
        url = reverse("dashboard:stocktransfer_action", args=[transfer.pk, "receive"])
        self.client.post(url)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, StockTransfer.RECEIVED)

    def _perms(self, *codenames):
        from django.contrib.auth.models import Permission

        return Permission.objects.filter(content_type__app_label="shop", codename__in=codenames)

    def test_low_stock_is_per_branch(self):
        change_stock(self.kibble, 1, StockMovement.OPENING, branch=self.north)
        self.assertEqual(list(Product.objects.low_stock([self.north.pk])), [self.kibble])
        self.assertEqual(list(Product.objects.low_stock([self.main.pk])), [])


class BranchBillingTests(BranchTestCase):
    def test_each_branch_numbers_its_bills_and_uses_its_stock(self):
        change_stock(self.kibble, 5, StockMovement.OPENING, branch=self.north)
        invoice = Invoice.objects.create(branch=self.north)
        InvoiceItem.objects.create(invoice=invoice, product=self.kibble, description="Kibble", quantity=2, unit_price=1000)
        invoice.issue(self.admin)
        self.assertEqual(invoice.number, f"INV-NTH1-{timezone.localdate().year}-00001")
        self.assertEqual(self.kibble.stock_at(self.north), Decimal("3"))
        self.assertEqual(self.kibble.stock_at(self.main), Decimal("10"))

    def test_branch_price_and_vat_on_visit_bills(self):
        fee = Product.objects.create(category=self.food, name="Visit fee", price=Decimal("500"), track_stock=False)
        self.north.visit_fee_item = fee
        self.north.save()
        BranchPrice.objects.create(product=fee, branch=self.north, price=Decimal("300"))
        visit = Appointment.objects.create(branch=self.north, client=self.owner, pet=self.pet, reason="x")
        invoice, _ = build_visit_bill(visit, self.admin)
        self.assertEqual(invoice.branch, self.north)
        self.assertEqual(invoice.vat_percent, Decimal("0"))
        self.assertEqual(invoice.items.get().unit_price, Decimal("300"))
        self.assertEqual(fee.price_at(self.main), Decimal("500"))

    def test_line_discount(self):
        invoice = Invoice.objects.create(branch=self.main)
        item = InvoiceItem.objects.create(
            invoice=invoice, description="Kibble", quantity=2, unit_price=Decimal("1000"), discount_percent=Decimal("10")
        )
        self.assertEqual(item.line_total, Decimal("1800.00"))
        self.assertEqual(item.discount_amount, Decimal("200.00"))

    def test_package_takes_its_contents_from_stock(self):
        package = Product.objects.create(
            category=self.food, name="Puppy pack", price=Decimal("2500"), is_package=True, track_stock=False
        )
        PackageItem.objects.create(package=package, component=self.kibble, quantity=2)
        invoice = Invoice.objects.create(branch=self.main)
        InvoiceItem.objects.create(invoice=invoice, product=package, description="Puppy pack", quantity=1, unit_price=2500)
        invoice.issue(self.admin)
        self.assertEqual(self.kibble.stock_at(self.main), Decimal("8"))
        invoice.cancel(self.admin)
        self.assertEqual(self.kibble.stock_at(self.main), Decimal("10"))

    def test_receipt_prints_for_a_payment(self):
        invoice = Invoice.objects.create(branch=self.main)
        InvoiceItem.objects.create(invoice=invoice, description="Check", quantity=1, unit_price=Decimal("400"))
        invoice.issue(self.admin)
        payment = invoice.add_payment(Decimal("150"), "cash", self.admin)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:invoice_receipt", args=[invoice.pk, payment.pk]))
        self.assertContains(response, payment.receipt_number)
        self.assertContains(response, "Rs. 250.00")

    def test_other_branch_bills_are_hidden(self):
        invoice = Invoice.objects.create(branch=self.main)
        self.client.force_login(self.north_desk)
        self.assertEqual(self.client.get(invoice.get_absolute_url()).status_code, 404)


class BranchStockPageTests(BranchTestCase):
    def test_price_sync_copies_and_resets(self):
        BranchPrice.objects.create(product=self.kibble, branch=self.main, price=Decimal("900"))
        self.client.force_login(self.admin)
        url = reverse("dashboard:branchprice_sync")
        self.client.post(url, {"action": "copy", "branch": self.north.pk, "source": self.main.pk})
        self.assertEqual(self.kibble.price_at(self.north), Decimal("900"))
        self.client.post(url, {"action": "reset", "branch": self.north.pk})
        self.assertEqual(self.kibble.price_at(self.north), Decimal("1000"))
        self.client.post(url, {"action": "promote", "branch": self.main.pk})
        self.kibble.refresh_from_db()
        self.assertEqual(self.kibble.price, Decimal("900"))
        self.assertFalse(BranchPrice.objects.exists())

    def test_stock_page_changes_the_current_branch(self):
        self.client.force_login(self.admin)
        self.use_branch(self.north)
        url = reverse("dashboard:product_stock", args=[self.kibble.pk])
        self.client.post(url, {"reason": "purchase", "quantity": "7", "note": ""})
        self.assertEqual(self.kibble.stock_at(self.north), Decimal("7"))
        self.assertEqual(BranchStock.objects.get(product=self.kibble, branch=self.main).quantity, Decimal("10"))

    def test_low_stock_filter_follows_the_branch(self):
        treats = Product.objects.create(category=self.food, name="Treats", unit="pack", price=Decimal("200"))
        change_stock(treats, 50, StockMovement.OPENING, branch=self.north)
        change_stock(self.kibble, 1, StockMovement.OPENING, branch=self.north)
        change_stock(self.kibble, -1, StockMovement.SALE, branch=self.north)
        self.client.force_login(self.admin)
        url = reverse("dashboard:list", args=["shop", "product"])

        self.use_branch(self.north)
        low = self.client.get(url, {"stock_level": "low"})
        self.assertContains(low, "Kibble")
        self.assertNotContains(low, "Treats")
        self.assertContains(self.client.get(url, {"stock_level": "out"}), "Kibble")

        self.use_branch(self.main)
        self.assertNotContains(self.client.get(url, {"stock_level": "low"}), "Kibble")


class WebsiteTests(TestCase):
    def test_branches_page_only_with_more_than_one_branch(self):
        url = reverse("branches:list")
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("core:home")), url)
        Branch.objects.create(name="Lalitpur", code="LTP", address="Jhamsikhel")
        page = self.client.get(url)
        self.assertContains(page, "Lalitpur")
        self.assertContains(page, "Jhamsikhel")
        self.assertContains(self.client.get(reverse("core:home")), url)

    def test_contact_form_offers_branches(self):
        from apps.contact.models import ContactMessage

        lalitpur = Branch.objects.create(name="Lalitpur", code="LTP")
        page = self.client.get(reverse("contact:contact") + f"?branch={lalitpur.pk}")
        self.assertContains(page, "Any branch")
        self.client.post(reverse("contact:contact"), {
            "name": "Sita", "email": "sita@example.com", "phone": "", "branch": lalitpur.pk, "message": "Hello",
        })
        self.assertEqual(ContactMessage.objects.get().branch, lalitpur)
