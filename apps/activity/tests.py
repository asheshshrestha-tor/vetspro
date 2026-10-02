from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import ADMINISTRATOR, RECEPTIONIST
from apps.billing.tests import make_user
from apps.clients.models import Client

from .models import ActivityLog


class ActivityLogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("manager", ADMINISTRATOR)
        cls.reception = make_user("reception", RECEPTIONIST)

    def test_changes_through_the_dashboard_are_logged_with_the_fields(self):
        owner = Client.objects.create(full_name="Ram Shrestha", phone="9801234567")
        self.assertFalse(ActivityLog.objects.exists())  # not made through a request
        self.client.force_login(self.reception)
        self.client.post(reverse("dashboard:edit", args=["clients", "client", owner.pk]), {
            "full_name": "Ram Bahadur Shrestha", "phone": "9801234567", "alt_phone": "", "email": "", "address": "",
            "area": "", "notes": "", "is_active": "on",
            "inline0-TOTAL_FORMS": "0", "inline0-INITIAL_FORMS": "0",
        })
        entry = ActivityLog.objects.get(action=ActivityLog.UPDATE)
        self.assertEqual(entry.user, self.reception)
        self.assertEqual(entry.changes, {"full_name": ["Ram Shrestha", "Ram Bahadur Shrestha"]})
        self.assertEqual(entry.object_repr, str(Client.objects.get()))

    def test_sign_ins_are_logged_and_only_admins_see_the_log(self):
        self.client.post(reverse("dashboard:login"), {"username": "reception", "password": "wrong"})
        self.client.post(reverse("dashboard:login"), {"username": "reception", "password": "pw-Test-12345"})
        actions = set(ActivityLog.objects.values_list("action", flat=True))
        self.assertEqual(actions, {ActivityLog.LOGIN_FAILED, ActivityLog.LOGIN})
        url = reverse("dashboard:list", args=["activity", "activitylog"])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url), "Failed sign-in")

    def test_passwords_are_never_stored(self):
        from django.test import RequestFactory

        from .middleware import _state

        request = RequestFactory().post("/")
        request.user = self.admin
        _state.request = request
        try:
            self.reception.set_password("new-Pass-12345")
            self.reception.save()
        finally:
            _state.request = None
        entry = ActivityLog.objects.get(action=ActivityLog.UPDATE)
        self.assertEqual(entry.changes["password"], ["•••", "changed"])
        self.assertNotIn("pbkdf2", str(entry.changes))
