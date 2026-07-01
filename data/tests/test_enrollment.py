"""
Tests for enrollment-related graduate data API views.
"""

from courses.models import Enrollment

from .enrollment_base import EnrollmentDataAPIBase


class EnrollmentGraduateDataAPITestCase(EnrollmentDataAPIBase):
    def create_other_graduate_candidate(self):
        other_user = self.create_certificate_user(
            username="student2",
            email="student2@example.com",
            certificate_name="Student Two",
        )
        other_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course,
        )
        return other_user, other_enrollment

    def create_primary_graduate_submissions(self, project1, project2):
        self.create_passed_submission_data(
            project1,
            self.user,
            self.enrollment,
            "1111",
        )
        self.create_passed_submission_data(
            project2,
            self.user,
            self.enrollment,
            "2222",
        )

    def create_graduate_view_scenario(self):
        self.require_two_projects_to_pass()
        self.configure_certificate_user()
        other_user, other_enrollment = self.create_other_graduate_candidate()
        project1 = self.create_saved_project("project1", "Project 1")
        project2 = self.create_saved_project("project2", "Project 2")
        self.create_primary_graduate_submissions(project1, project2)
        self.create_passed_submission_data(
            project1,
            other_user,
            other_enrollment,
            "3333",
        )

    def test_graduate_data_view(self):
        self.create_graduate_view_scenario()

        response = self.client.get(self.graduates_url())

        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        graduates = response_json["graduates"]

        self.assertEqual(len(graduates), 1)

        first_graduate = graduates[0]
        self.assertEqual(first_graduate["email"], self.user.email)
        self.assertEqual(
            first_graduate["name"], self.user.certificate_name
        )
