"""Let the existing vet and reception roles see the doctor schedule. Administrators already get every permission."""
from django.contrib.auth.management import create_permissions
from django.db import migrations

VIEW = [("schedules", "view_doctorshift"), ("schedules", "view_schedulechange")]
GRANTS = {"Veterinarian": VIEW, "Receptionist": VIEW}


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
        ("schedules", "0001_initial"),
        ("accounts", "0005_grant_new_feature_permissions"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
