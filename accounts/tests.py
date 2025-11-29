from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import CustomUser


class DarkModeToggleTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_toggle_dark_mode_unauthenticated(self):
        """Test that unauthenticated users cannot toggle dark mode"""
        response = self.client.post(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 302)

    def test_toggle_dark_mode_authenticated(self):
        """Test that authenticated users can toggle dark mode"""
        self.client.force_login(self.user)

        self.assertFalse(self.user.dark_mode)

        response = self.client.post(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.dark_mode)

        response = self.client.post(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertFalse(self.user.dark_mode)

    def test_toggle_dark_mode_get_not_allowed(self):
        """Test that GET requests are not allowed"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('toggle_dark_mode'))
        self.assertEqual(response.status_code, 405)

    def test_dark_mode_default_value(self):
        """Test that dark_mode defaults to False"""
        user = CustomUser.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='testpass123'
        )
        self.assertFalse(user.dark_mode)
