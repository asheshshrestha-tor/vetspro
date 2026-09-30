from django.apps import AppConfig
from django.db.models.signals import post_migrate, post_save


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = "Staff"

    def ready(self):
        from django.contrib.auth import get_user_model

        from .roles import setup_default_roles
        from .signals import create_staff_profile

        post_save.connect(create_staff_profile, sender=get_user_model(), dispatch_uid="accounts_create_staff_profile")
        post_migrate.connect(setup_default_roles, dispatch_uid="accounts_setup_default_roles")
