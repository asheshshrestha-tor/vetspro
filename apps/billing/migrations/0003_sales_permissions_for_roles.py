"""Give the existing staff roles the new sales permissions.

Roles are only filled with permissions when first created, so roles made before
the shop and billing existed need them added once. Administrators edit roles
afterwards as they like.
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

GRANTS = {
    "Veterinarian": [
        ("billing", "view_invoice"), ("billing", "add_invoice"), ("billing", "change_invoice"),
        ("billing", "issue_invoice"), ("shop", "view_product"), ("shop", "view_productcategory"),
    ],
    "Receptionist": [
        ("billing", "view_invoice"), ("billing", "add_invoice"), ("billing", "change_invoice"),
        ("billing", "issue_invoice"), ("billing", "record_payment"),
        ("shop", "view_product"), ("shop", "view_productcategory"),
    ],
}


def grant(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for role, codes in GRANTS.items():
        group = Group.objects.filter(name=role).first()
        if group is None:
            continue
        for app_label, codename in codes:
            perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
            if perm is not None:
                group.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_initial"),
        ("shop", "0002_starter_categories"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
