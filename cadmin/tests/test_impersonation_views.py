from courses.models import Enrollment, User

from .impersonation_base import (
    ImpersonationCadminViewTestBase,
    admin_credentials,
)


class LoginAsUserCadminViewTests(ImpersonationCadminViewTestBase):
    def test_log_as_user_requires_post_request(self):
        url = self.login_as_user_url()

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)

    def test_log_as_user_with_post_request(self):
        Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        url = self.login_as_user_url()

        self.client.login(**admin_credentials)
        self.assertEqual(
            self.client.session["_auth_user_id"],
            str(self.admin_user.id),
        )
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

    def test_staff_cannot_impersonate_other_staff(self):
        other_staff = User.objects.create_user(
            username="staff2@test.com",
            email="staff2@test.com",
            password="staff123",
            is_staff=True,
        )
        url = self.login_as_user_url(other_staff)

        self.client.login(**admin_credentials)
        response = self.client.post(url, follow=True)

        self.assertEqual(
            response.wsgi_request.user.username, "admin@test.com"
        )
