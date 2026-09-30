from django.db import migrations
from django.utils.text import slugify

CATEGORIES = [
    ("Medicines", True),
    ("Food & treats", True),
    ("Toys", True),
    ("Cages, beds & carriers", True),
    ("Collars, leashes & accessories", True),
    ("Grooming & hygiene", True),
    ("Clinic services", False),
]


def add_categories(apps, schema_editor):
    ProductCategory = apps.get_model("shop", "ProductCategory")
    for order, (name, online) in enumerate(CATEGORIES):
        ProductCategory.objects.get_or_create(
            name=name, defaults={"slug": slugify(name), "order": order, "show_online": online}
        )


class Migration(migrations.Migration):
    dependencies = [("shop", "0001_initial")]

    operations = [migrations.RunPython(add_categories, migrations.RunPython.noop)]
