"""
Tests for enrollment-related graduate data API views.
"""

from courses.models import Enrollment

from .enrollment_base import (
    EnrollmentDataAPIBase,
    PassedProjectSubmissionData,
)


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
        first_submission = PassedProjectSubmissionData(
            project=project1,
            student=self.user,
            enrollment=self.enrollment,
            commit_id="1111",
        )
        self.create_passed_project_submission(first_submission)
        second_submission = PassedProjectSubmissionData(
            project=project2,
            student=self.user,
            enrollment=self.enrollment,
            commit_id="2222",
        )
        self.create_passed_project_submission(second_submission)

    def create_graduate_view_scenario(self):
        self.require_two_projects_to_pass()
        self.configure_certificate_user()
        other_user, other_enrollment = self.create_other_graduate_candidate()
        project1 = self.create_saved_project("project1", "Project 1")
        project2 = self.create_saved_project("project2", "Project 2")
        self.create_primary_graduate_submissions(project1, project2)
        other_submission = PassedProjectSubmissionData(
            project=project1,
            student=other_user,
            enrollment=other_enrollment,
            commit_id="3333",
        )
        self.create_passed_project_submission(other_submission)

    def test_graduate_data_view(self):
        self.create_graduate_view_scenario()
        url = self.graduates_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        graduates = response_json["graduates"]
        graduates_count = len(graduates)

        self.assertEqual(graduates_count, 1)

        first_graduate = graduates[0]
        self.assertEqual(first_graduate["email"], self.user.email)
        self.assertEqual(
            first_graduate["name"], self.user.certificate_name
        )
