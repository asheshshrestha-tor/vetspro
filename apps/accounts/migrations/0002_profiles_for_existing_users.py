from django.conf import settings
from django.db import migrations


def create_profiles(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    StaffProfile = apps.get_model("accounts", "StaffProfile")
    for user in User.objects.filter(staff_profile__isnull=True):
        StaffProfile.objects.create(user=user)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.RunPython(create_profiles, migrations.RunPython.noop)]
