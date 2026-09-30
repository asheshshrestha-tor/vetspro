from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .roles import ADMINISTRATOR, RECEPTIONIST, VETERINARIAN

User = get_user_model()
PASSWORD = "pw-Test-12345"


class RoleSetupTests(TestCase):
    def test_default_roles_exist(self):
        names = set(Group.objects.values_list("name", flat=True))
        self.assertTrue({ADMINISTRATOR, VETERINARIAN, RECEPTIONIST} <= names)
        vet = Group.objects.get(name=VETERINARIAN)
        self.assertTrue(vet.permissions.filter(codename="record_clinical").exists())
        reception = Group.objects.get(name=RECEPTIONIST)
        self.assertFalse(reception.permissions.filter(codename="record_clinical").exists())

    def test_every_user_gets_a_profile(self):
        user = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.assertTrue(user.staff_profile.can_attend)


class StaffUserTests(TestCase):
    add_url = reverse("dashboard:add", args=["auth", "user"])

    def setUp(self):
        self.admin_role = Group.objects.get(name=ADMINISTRATOR)
        self.manager = User.objects.create_user("manager", password=PASSWORD, is_staff=True)
        self.manager.groups.add(self.admin_role)
        self.client.force_login(self.manager)

    def test_create_staff_user_with_role(self):
        vet_role = Group.objects.get(name=VETERINARIAN)
        response = self.client.post(self.add_url, {
            "username": "dr.sharma", "first_name": "Asha", "last_name": "Sharma", "email": "",
            "is_active": "on", "role": vet_role.pk, "designation": "Veterinarian", "phone": "",
            "licence_number": "NVC-123", "can_attend": "on",
            "password1": "Clinic-pass-2026", "password2": "Clinic-pass-2026",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="dr.sharma")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("Clinic-pass-2026"))
        self.assertEqual(list(user.groups.all()), [vet_role])
        self.assertEqual(user.staff_profile.role, vet_role)
        self.assertEqual(user.staff_profile.licence_number, "NVC-123")
        self.assertTrue(user.has_perm("appointments.record_clinical"))

    def test_cannot_deactivate_own_account(self):
        url = reverse("dashboard:edit", args=["auth", "user", self.manager.pk])
        response = self.client.post(url, {
            "username": "manager", "first_name": "Manager", "role": self.admin_role.pk,
        })
        self.assertContains(response, "You cannot deactivate your own account.")
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_superuser_accounts_are_read_only_for_others(self):
        root = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        url = reverse("dashboard:edit", args=["auth", "user", root.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="password1"')
        response = self.client.post(url, {"username": "hijacked", "first_name": "x", "role": self.admin_role.pk})
        self.assertEqual(response.status_code, 403)

    def test_role_permissions_are_editable(self):
        role = Group.objects.get(name=RECEPTIONIST)
        url = reverse("dashboard:edit", args=["auth", "group", role.pk])
        response = self.client.get(url)
        self.assertContains(response, "Record clinical details")
        keep = list(role.permissions.values_list("pk", flat=True))[:2]
        self.client.post(url, {"name": RECEPTIONIST, "permissions": keep})
        self.assertEqual(sorted(role.permissions.values_list("pk", flat=True)), sorted(keep))

    def test_my_profile(self):
        response = self.client.post(reverse("dashboard:my_profile"), {"first_name": "Mina", "phone": "9800000000"})
        self.assertEqual(response.status_code, 302)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.first_name, "Mina")
        self.assertEqual(self.manager.staff_profile.phone, "9800000000")
