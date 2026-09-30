from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.billing.models import Invoice, InvoiceItem

from .models import Product


class SeedShopTests(TestCase):
    def test_load_is_repeatable_and_remove_keeps_sold_products(self):
        call_command("seed_shop")
        count = Product.objects.filter(sku__startswith="SAMPLE-").count()
        call_command("seed_shop")
        self.assertEqual(Product.objects.filter(sku__startswith="SAMPLE-").count(), count)
        kibble = Product.objects.get(name="Puppy dry food 3 kg")
        self.assertEqual(kibble.stock_quantity, Decimal("14"))
        self.assertFalse(Product.objects.get(name="Consultation fee").track_stock)

        invoice = Invoice.objects.create()
        InvoiceItem.objects.create(invoice=invoice, product=kibble, description=kibble.name, unit_price=kibble.price)
        call_command("seed_shop", "--remove")
        self.assertEqual(list(Product.objects.values_list("name", flat=True)), ["Puppy dry food 3 kg"])
        kibble.refresh_from_db()
        self.assertFalse(kibble.is_active)
