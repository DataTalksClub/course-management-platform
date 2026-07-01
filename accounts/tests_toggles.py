from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser


class DarkModeToggleTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_toggle_dark_mode_unauthenticated(self):
        """Test that unauthenticated users cannot toggle dark mode"""
        url = reverse("toggle_dark_mode")

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    def test_toggle_dark_mode_authenticated(self):
        """Test that authenticated users can toggle dark mode"""
        self.client.force_login(self.user)
        url = reverse("toggle_dark_mode")

        self.assertFalse(self.user.dark_mode)

        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.dark_mode)

        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertFalse(self.user.dark_mode)

    def test_toggle_dark_mode_get_not_allowed(self):
        """Test that GET requests are not allowed"""
        self.client.force_login(self.user)
        url = reverse("toggle_dark_mode")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)

    def test_update_account_toggle_sets_explicit_dark_mode_value(self):
        self.client.force_login(self.user)
        url = reverse("update_account_toggle")
        enable_payload = {"field": "dark_mode", "value": "true"}

        response = self.client.post(url, enable_payload)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(
            response_data,
            {
                "field": "dark_mode",
                "value": True,
                "dark_mode": True,
            },
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.dark_mode)

        disable_payload = {"field": "dark_mode", "value": "false"}
        response = self.client.post(url, disable_payload)

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.dark_mode)

    def test_update_account_toggle_rejects_unknown_field(self):
        self.client.force_login(self.user)
        url = reverse("update_account_toggle")
        payload = {"field": "is_staff", "value": "true"}

        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 400)

    def test_dark_mode_default_value(self):
        """Test that dark_mode defaults to False"""
        user = CustomUser.objects.create_user(
            username="newuser",
            email="new@example.com",
            password="testpass123",
        )
        self.assertFalse(user.dark_mode)
