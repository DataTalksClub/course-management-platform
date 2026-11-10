from django.test import SimpleTestCase

from api.tests.homework_api_base import HomeworkAPITestBase
from api.tests.project_api_base import ProjectAPITestBase
from api.urls import urlpatterns


STAFF_TOKEN_VIEWS = {
    "api_homework_submissions_export",
    "api_project_submissions_export",
}

# Other token routes have intentionally public or method-specific policies;
# their handlers retain those checks. A new token route must be classified.
EXPLICIT_TOKEN_POLICY_ALLOWLIST = {
    "api_openapi_json",
    "api_course_graduates",
    "api_course_certificates",
    "api_course_certificate_notify",
    "api_datamailer_send_audits",
    "api_datamailer_send_audit_detail",
    "api_courses_list",
    "api_course_detail",
    "api_registration_campaigns",
    "api_registration_campaign_detail",
    "api_registration_campaign_registrations",
    "api_registration_campaign_approve_batch",
    "api_registration_campaign_registration_detail",
    "api_registration_campaign_emails",
    "api_homeworks",
    "api_homework_detail",
    "api_homework_score",
    "api_homework_detail_by_slug",
    "api_homework_score_by_slug",
    "api_projects",
    "api_project_detail",
    "api_project_assign_reviews",
    "api_project_score",
    "api_project_detail_by_slug",
    "api_project_assign_reviews_by_slug",
    "api_project_notify_peer_reviews_by_slug",
    "api_project_notify_scores_by_slug",
    "api_project_score_by_slug",
    "api_project_system_evaluations",
    "api_review_criteria",
    "api_review_criteria_detail",
    "api_questions",
    "api_question_detail",
}


class ExportTokenAuthTests(SimpleTestCase):
    def test_every_token_route_has_an_explicit_access_policy(self):
        token_routes = {
            pattern.name: pattern.callback
            for pattern in urlpatterns
            if getattr(pattern.callback, "requires_token_auth", False)
        }

        self.assertEqual(
            set(token_routes),
            STAFF_TOKEN_VIEWS | EXPLICIT_TOKEN_POLICY_ALLOWLIST,
        )
        for route_name in STAFF_TOKEN_VIEWS:
            with self.subTest(route=route_name):
                self.assertTrue(
                    getattr(token_routes[route_name], "requires_staff_token", False)
                )


class HomeworkExportAuthTests(HomeworkAPITestBase):
    def test_submission_export_rejects_non_staff_token(self):
        homework = self._create_homework(slug="staff-export")
        student = self._non_staff_client("homework-export-student")

        response = student.get(
            f"/api/courses/{self.course.slug}/homeworks/"
            f"{homework.slug}/submissions"
        )

        self._assert_staff_token_required(response)

    def test_submission_export_allows_staff_token(self):
        homework = self._create_homework(slug="staff-export")

        response = self.client.get(
            f"/api/courses/{self.course.slug}/homeworks/"
            f"{homework.slug}/submissions"
        )

        self.assertEqual(response.status_code, 200)


class ProjectExportAuthTests(ProjectAPITestBase):
    def test_submission_export_rejects_non_staff_token(self):
        project = self._create_project(slug="staff-export")
        student = self._non_staff_client("project-export-student")

        response = student.get(
            f"/api/courses/{self.course.slug}/projects/"
            f"{project.slug}/submissions"
        )

        self._assert_staff_token_required(response)

    def test_submission_export_allows_staff_token(self):
        project = self._create_project(slug="staff-export")

        response = self.client.get(
            f"/api/courses/{self.course.slug}/projects/"
            f"{project.slug}/submissions"
        )

        self.assertEqual(response.status_code, 200)
