from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser, Token


class TokenAdminAccessTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.token_add_url = reverse("admin:accounts_token_add")
        self.student = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

    def test_non_staff_user_cannot_access_token_admin(self):
        self.client.force_login(self.student)

        response = self.client.get(self.token_add_url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Token.objects.filter(user=self.student).exists())

    def test_staff_without_token_permission_cannot_create_token(self):
        staff = CustomUser.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="password",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.post(
            self.token_add_url,
            {"key": "staff-token", "user": staff.id},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Token.objects.filter(user=staff).exists())

    def test_token_admin_rejects_non_staff_user_selection(self):
        superuser = CustomUser.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )
        self.client.force_login(superuser)

        response = self.client.post(
            self.token_add_url,
            {
                "key": "student-token",
                "user": self.student.id,
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Token.objects.filter(user=self.student).exists())
