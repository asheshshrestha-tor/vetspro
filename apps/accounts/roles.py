"""The default staff roles, created after migrations.

Roles are Django groups, so permission checks work the usual way. A role is only
filled with permissions when it is first created; after that, administrators edit
it in the dashboard and their changes are kept. The Administrator role is the one
exception: it always receives any new permission, so new modules appear for it.
"""
from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission

ADMINISTRATOR = "Administrator"
VETERINARIAN = "Veterinarian"
RECEPTIONIST = "Receptionist"

MANAGED_APPS = [
    "core", "services", "team", "pricing", "faq", "gallery", "testimonials", "contact",
    "clinic_setup", "clients", "appointments", "accounts", "shop", "billing",
]

VIEW = ["view"]
EDIT = ["view", "add", "change"]

# Selling at the counter and billing visits; stock itself is managed by administrators.
SALES_MODELS = {
    ("billing", "invoice"): EDIT,
    ("shop", "product"): VIEW,
    ("shop", "productcategory"): VIEW,
}
SALES_EXTRA = [("billing", "issue_invoice")]

# (app label, model name) -> actions, plus extra codenames per role.
ROLE_PERMISSIONS = {
    VETERINARIAN: {
        "models": {
            ("clients", "client"): EDIT,
            ("clients", "pet"): EDIT,
            ("appointments", "appointment"): EDIT,
            ("clinic_setup", "species"): VIEW,
            ("clinic_setup", "historyoption"): VIEW,
            ("clinic_setup", "vaccinationtype"): VIEW,
            ("clinic_setup", "examinationtype"): VIEW,
            **SALES_MODELS,
        },
        "extra": [
            ("appointments", "view_clinical"),
            ("appointments", "record_clinical"),
            ("appointments", "change_completed_appointment"),
        ] + SALES_EXTRA,
    },
    RECEPTIONIST: {
        "models": {
            ("clients", "client"): EDIT,
            ("clients", "pet"): EDIT,
            ("appointments", "appointment"): EDIT,
            ("clinic_setup", "species"): VIEW,
            **SALES_MODELS,
        },
        "extra": SALES_EXTRA + [("billing", "record_payment")],
    },
}


def administrator_permissions():
    return Permission.objects.filter(content_type__app_label__in=MANAGED_APPS + ["auth"]).exclude(
        content_type__model="permission"
    )


def role_permissions(spec):
    perms = []
    for (app_label, model), actions in spec["models"].items():
        codenames = [f"{action}_{model}" for action in actions]
        perms += list(Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames))
    for app_label, codename in spec["extra"]:
        perms += list(Permission.objects.filter(content_type__app_label=app_label, codename=codename))
    return perms


def setup_default_roles(sender=None, using="default", **kwargs):
    # Permissions for every app must exist first; this runs once per migrate, after all apps.
    if sender is None or sender.name != "apps.accounts":
        return
    for app_config in global_apps.get_app_configs():
        create_permissions(app_config, verbosity=0, using=using)

    admin, _ = Group.objects.using(using).get_or_create(name=ADMINISTRATOR)
    admin.permissions.add(*administrator_permissions())

    for name, spec in ROLE_PERMISSIONS.items():
        group, created = Group.objects.using(using).get_or_create(name=name)
        if created:
            group.permissions.set(role_permissions(spec))
