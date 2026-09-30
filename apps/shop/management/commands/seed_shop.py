"""Load sample products into every shop category, so the shop and billing can be tried out.

Sample products get an SKU starting with "SAMPLE-". Running the command again only adds
what is missing. `--remove` deletes the sample products that have never been sold; ones
already on an invoice are hidden instead, so past invoices stay intact.

Prices and stock levels are made up. Replace them with your own before real use.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.shop.models import Product, ProductCategory, StockMovement, change_stock

PREFIX = "SAMPLE-"

# category: [(name, brand, unit, price, opening stock, low-stock level, prescription only, description)]
PRODUCTS = {
    "Medicines": [
        ("Doxycycline 100 mg", "", "tablet", "25", 200, 30, True, "Antibiotic, commonly used for tick fever."),
        ("Amoxicillin + clavulanate 250 mg", "", "tablet", "35", 150, 30, True, "Broad-spectrum antibiotic."),
        ("Meloxicam oral suspension 10 ml", "", "bottle", "650", 20, 5, True, "Pain and inflammation relief."),
        ("Ondansetron injection 2 mg/ml", "", "vial", "180", 3, 5, True, "Anti-vomiting injection, used in the clinic."),
        ("Ringer's lactate 500 ml", "", "bottle", "150", 40, 10, True, "IV fluid, used in the clinic."),
        ("Deworming tablet (praziquantel + pyrantel)", "", "tablet", "120", 100, 20, False,
         "Broad-spectrum dewormer for dogs. Dose by body weight."),
        ("Anti-tick spot-on, dogs 10-20 kg", "", "pipette", "850", 30, 8, False, "Monthly tick and flea protection."),
        ("Ear cleaning solution 100 ml", "", "bottle", "750", 15, 4, False, "Gentle cleaner for routine ear care."),
        ("Multivitamin syrup 200 ml", "", "bottle", "550", 20, 5, False, "Daily supplement for dogs and cats."),
        ("Probiotic paste 15 g", "", "tube", "900", 2, 4, False, "Supports digestion after illness or antibiotics."),
    ],
    "Food & treats": [
        ("Puppy dry food 3 kg", "", "bag", "2450", 14, 4, False, "Complete food for puppies up to 12 months."),
        ("Adult dog dry food 10 kg", "", "bag", "6800", 6, 2, False, "Complete food for adult dogs."),
        ("Kitten dry food 1.2 kg", "", "bag", "1350", 10, 3, False, "Complete food for kittens."),
        ("Adult cat dry food 1 kg", "", "bag", "950", 12, 3, False, "Complete food for adult cats."),
        ("Wet cat food pouch 85 g", "", "pouch", "120", 60, 15, False, "Chicken in gravy."),
        ("Dog biscuits 500 g", "", "pack", "450", 25, 6, False, "Crunchy treats for training and rewards."),
        ("Dental chew sticks (7 pack)", "", "pack", "650", 20, 5, False, "Helps keep teeth clean."),
    ],
    "Toys": [
        ("Rope chew toy", "", "piece", "350", 25, 5, False, "Tough cotton rope for chewing and tug."),
        ("Squeaky rubber ball", "", "piece", "250", 30, 6, False, "Bouncy ball with a squeaker."),
        ("Cat teaser wand", "", "piece", "300", 18, 4, False, "Feather wand for play."),
        ("Catnip mouse", "", "piece", "200", 20, 5, False, "Soft toy filled with catnip."),
    ],
    "Cages, beds & carriers": [
        ("Pet carrier, small (up to 5 kg)", "", "piece", "3200", 4, 2, False, "Airline-style carrier for cats and small dogs."),
        ("Pet carrier, medium (up to 10 kg)", "", "piece", "3800", 1, 2, False, "Airline-style carrier."),
        ("Folding dog crate, medium", "", "piece", "7500", 2, 1, False, "Metal crate with removable tray."),
        ("Cushion bed, medium", "", "piece", "2200", 5, 2, False, "Soft washable bed."),
        ("Bird cage, medium", "", "piece", "2800", 3, 1, False, "With perches and feeding cups."),
    ],
    "Collars, leashes & accessories": [
        ("Nylon collar, medium", "", "piece", "400", 20, 5, False, "Adjustable collar with buckle."),
        ("Nylon leash 1.5 m", "", "piece", "450", 0, 5, False, "Strong leash with padded handle."),
        ("Chest harness, medium", "", "piece", "1100", 10, 3, False, "Comfortable harness for walks."),
        ("Stainless steel bowl, medium", "", "piece", "500", 20, 5, False, "Non-slip base, dishwasher safe."),
    ],
    "Grooming & hygiene": [
        ("Anti-tick shampoo 200 ml", "", "bottle", "650", 12, 4, False, "Medicated shampoo for ticks and fleas."),
        ("Puppy shampoo 200 ml", "", "bottle", "550", 10, 3, False, "Mild shampoo for puppies."),
        ("Slicker brush", "", "piece", "600", 8, 2, False, "Removes loose fur and tangles."),
        ("Nail clipper", "", "piece", "500", 8, 2, False, "With safety guard."),
        ("Cat litter 5 kg", "", "bag", "900", 15, 4, False, "Clumping, low dust."),
        ("Poop bags (4 rolls)", "", "pack", "300", 25, 6, False, "Leak-proof bags."),
    ],
}

# Treatment catalogue entries for sample items: (type, usual dose, route, frequency, duration).
# Sample values only; vets must set the doses they actually use.
TREATMENT_DEFAULTS = {
    "Doxycycline 100 mg": ("medicine", "10 mg/kg", "Oral", "Once a day", "21 days"),
    "Amoxicillin + clavulanate 250 mg": ("medicine", "12.5 mg/kg", "Oral", "Twice a day", "7 days"),
    "Meloxicam oral suspension 10 ml": ("medicine", "0.1 mg/kg", "Oral", "Once a day", "5 days"),
    "Ondansetron injection 2 mg/ml": ("medicine", "0.5 mg/kg", "IV", "Twice a day", "2 days"),
    "Ringer's lactate 500 ml": ("medicine", "", "IV", "As needed", ""),
    "Deworming tablet (praziquantel + pyrantel)": ("medicine", "1 tablet per 10 kg", "Oral", "Once", ""),
    "Anti-tick spot-on, dogs 10-20 kg": ("medicine", "1 pipette", "Spot-on", "Monthly", ""),
    "Ear cleaning solution 100 ml": ("medicine", "", "Topical", "Twice a week", ""),
    "Multivitamin syrup 200 ml": ("medicine", "5 ml", "Oral", "Once a day", "30 days"),
    "Probiotic paste 15 g": ("medicine", "1 g", "Oral", "Once a day", "5 days"),
    "Consultation fee": ("procedure", "", "", "", ""),
    "Emergency consultation (night)": ("procedure", "", "", "", ""),
    "Follow-up consultation": ("procedure", "", "", "", ""),
    "Rabies vaccination": ("procedure", "1 ml", "SC", "Once", ""),
    "DHPPiL vaccination": ("procedure", "1 ml", "SC", "Once", ""),
    "Deworming (in clinic)": ("procedure", "", "Oral", "Once", ""),
    "IV fluid therapy, per day": ("procedure", "", "IV", "", ""),
    "Wound dressing": ("procedure", "", "Topical", "", ""),
    "Nail trimming": ("procedure", "", "", "", ""),
    "Grooming bath, small dog": ("procedure", "", "", "", ""),
}

# Advice given at visits; recorded in the treatment, not charged.
ADVICE = [
    ("Diet advice", "Bland diet, small frequent meals, fresh water."),
    ("Home care instructions", "Rest, keep the wound clean and dry, watch for vomiting or lethargy."),
    ("Tick and flea prevention advice", "Monthly preventive, check coat and ears after walks."),
]

# Services: not counted, and not shown in the online shop.
SERVICES = [
    ("Consultation fee", "500"),
    ("Emergency consultation (night)", "1000"),
    ("Follow-up consultation", "300"),
    ("Rabies vaccination", "800"),
    ("DHPPiL vaccination", "1500"),
    ("Deworming (in clinic)", "300"),
    ("IV fluid therapy, per day", "1500"),
    ("Wound dressing", "500"),
    ("Nail trimming", "300"),
    ("Grooming bath, small dog", "1200"),
]


class Command(BaseCommand):
    help = "Load sample shop products (SKU starting SAMPLE-), or remove them with --remove."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true", help="Remove the sample products instead.")

    def handle(self, *args, **options):
        if options["remove"]:
            self.remove()
        else:
            self.load()

    @transaction.atomic
    def load(self):
        categories = {category.name: category for category in ProductCategory.objects.all()}
        missing = [name for name in [*PRODUCTS, "Clinic services"] if name not in categories]
        if missing:
            self.stderr.write(f"Missing categories, skipped: {', '.join(missing)}")

        added = 0
        number = 0
        for category_name, rows in PRODUCTS.items():
            category = categories.get(category_name)
            for name, brand, unit, price, stock, low, prescription, description in rows:
                number += 1
                if category is None:
                    continue
                product, created = Product.objects.get_or_create(
                    sku=f"{PREFIX}{number:03d}",
                    defaults={
                        "category": category, "name": name, "brand": brand, "unit": unit, "price": Decimal(price),
                        "cost_price": (Decimal(price) * Decimal("0.7")).quantize(Decimal("1")),
                        "low_stock_level": low, "is_prescription": prescription, "description": description,
                        # Injections and IV fluids are used in the clinic, not sold online.
                        "show_online": unit not in ("vial",) and "Ringer" not in name,
                    },
                )
                if created:
                    added += 1
                    if stock:
                        change_stock(product, stock, StockMovement.OPENING, note="Sample data")

        services = categories.get("Clinic services")
        for index, (name, price) in enumerate(SERVICES, start=1):
            if services is None:
                continue
            _, created = Product.objects.get_or_create(
                sku=f"{PREFIX}S{index:02d}",
                defaults={
                    "category": services, "name": name, "unit": "service", "price": Decimal(price),
                    "track_stock": False, "show_online": False,
                },
            )
            added += created

        for index, (name, description) in enumerate(ADVICE, start=1):
            if services is None:
                continue
            _, created = Product.objects.get_or_create(
                sku=f"{PREFIX}A{index:02d}",
                defaults={
                    "category": services, "name": name, "unit": "advice", "price": Decimal("0"),
                    "track_stock": False, "show_online": False, "treatment_kind": Product.ADVICE,
                    "description": description,
                },
            )
            added += created

        # Put sample medicines and services in the treatment catalogue, without overwriting any edits.
        for product in Product.objects.filter(sku__startswith=PREFIX, name__in=TREATMENT_DEFAULTS):
            kind, dose, route, frequency, duration = TREATMENT_DEFAULTS[product.name]
            changed = False
            for field, value in (
                ("treatment_kind", kind), ("default_dose", dose), ("default_route", route),
                ("default_frequency", frequency), ("default_duration", duration),
            ):
                if value and not getattr(product, field):
                    setattr(product, field, value)
                    changed = True
            if changed:
                product.save()

        total = Product.objects.filter(sku__startswith=PREFIX).count()
        self.stdout.write(self.style.SUCCESS(f"{added} sample product(s) added; {total} sample products in total."))

    @transaction.atomic
    def remove(self):
        samples = Product.objects.filter(sku__startswith=PREFIX)
        sold = samples.filter(invoice_items__isnull=False).distinct()
        hidden = sold.update(is_active=False, show_online=False)
        unsold = samples.exclude(pk__in=sold.values("pk"))
        StockMovement.objects.filter(product__in=unsold).delete()
        removed = unsold.count()
        unsold.delete()
        self.stdout.write(self.style.SUCCESS(
            f"{removed} sample product(s) removed; {hidden} already on invoices were hidden instead."
        ))
