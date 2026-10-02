"""Create the main branch from the hospital's details and give every staff member access to it.

Administrators and superusers get "all branches", so new branches are open to them at once.
"""
from django.db import migrations


def create_main_branch(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    SiteSettings = apps.get_model("core", "SiteSettings")
    StaffProfile = apps.get_model("accounts", "StaffProfile")

    if Branch.objects.exists():
        return
    site = SiteSettings.objects.filter(pk=1).first()
    main = Branch.objects.create(
        name="Main branch",
        code="MAIN",
        address=(site.address if site else ""),
        phone=(site.phone if site else ""),
        whatsapp=(site.whatsapp if site else ""),
        email=(site.email if site else ""),
        opening_hours=(site.opening_hours if site else ""),
        map_embed_url=(site.map_embed_url if site else ""),
        is_main=True,
    )
    for profile in StaffProfile.objects.select_related("user", "role"):
        profile.branches.add(main)
        profile.default_branch = main
        if profile.user.is_superuser or (profile.role and profile.role.name == "Administrator"):
            profile.all_branches = True
        profile.save()


class Migration(migrations.Migration):
    dependencies = [
        ("branches", "0001_initial"),
        ("accounts", "0004_staffprofile_branches_staffprofile_default_branch"),
        ("core", "0004_sitesettings_visit_fee_item"),
    ]

    operations = [migrations.RunPython(create_main_branch, migrations.RunPython.noop)]
