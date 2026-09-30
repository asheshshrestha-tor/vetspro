"""Put existing medicines and clinic services into the treatment catalogue, and let vets use it."""
from django.contrib.auth.management import create_permissions
from django.db import migrations


def fill_catalogue(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    Product.objects.filter(category__name="Medicines", treatment_kind="").update(treatment_kind="medicine")
    Product.objects.filter(category__name="Clinic services", treatment_kind="").update(treatment_kind="procedure")

    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    view = Permission.objects.filter(content_type__app_label="shop", codename="view_treatmentitem").first()
    vet = Group.objects.filter(name="Veterinarian").first()
    if view and vet:
        vet.permissions.add(view)


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0003_treatmentitem_product_default_dose_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(fill_catalogue, migrations.RunPython.noop)]
