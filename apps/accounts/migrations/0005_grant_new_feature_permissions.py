"""Give the existing staff roles access to the new features.

Documents in pet records, treatment templates, vaccination plans, messages to owners
and reports. Administrators already receive every permission.
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

CLINICAL = [
    ("clients", "view_petdocument"), ("clients", "add_petdocument"),
    ("clinic_setup", "view_treatmenttemplate"), ("clinic_setup", "view_vaccinationplan"),
    ("messaging", "view_outboundmessage"), ("messaging", "add_outboundmessage"), ("messaging", "view_messagetemplate"),
]
GRANTS = {
    "Veterinarian": CLINICAL + [("clients", "delete_petdocument"), ("reports", "view_report")],
    "Receptionist": CLINICAL,
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
        ("accounts", "0004_staffprofile_branches_staffprofile_default_branch"),
        ("clients", "0002_pet_documents"),
        ("clinic_setup", "0005_treatmenttemplate_treatmenttemplateline_and_more"),
        ("messaging", "0002_default_templates"),
        ("reports", "0001_initial"),
        ("activity", "0001_initial"),
        ("shop", "0007_product_is_package_packageitem"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
