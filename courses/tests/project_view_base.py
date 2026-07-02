from datetime import timedelta
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectViewTestBase(TestCase):
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_enrollment(self):
        return Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

    def create_project(self):
        submission_due_date = timezone.now() - timedelta(hours=1)
        peer_review_due_date = timezone.now() + timedelta(hours=1)
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )

    def project_url(self):
        return reverse("project", args=[self.course.slug, self.project.slug])

    def mock_url_check_status(self, mock_get, mock_head, status_code):
        mock_response = mock.Mock()
        mock_response.status_code = status_code
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

    def project_submission_data(self, **extra_fields):
        data = {
            "github_link": "https://github.com/test/project",
            "commit_id": "1234567",
        }
        data.update(extra_fields)
        return data

    def project_confirmation_data(self):
        learning_links = {
            "learning_in_public_links[]": [
                "https://example.com/project-notes"
            ],
        }
        return self.project_submission_data(
            **learning_links,
            time_spent="2",
            problems_comments="No blockers.",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/pull/266"
            ),
        )

    def project_delete_submission_data(self):
        return self.project_submission_data(
            github_link="https://github.com/existing/repo",
            commit_id="123456e",
            time_spent="3",
            problems_comments="No issues encountered.",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/issues/266"
            ),
            action="delete",
        )

    def closed_project_submission_data(self):
        return self.project_submission_data(
            github_link="https://github.com/existing/repo",
            commit_id="1234567",
            time_spent="2",
            problems_comments="Encountered an issue with...",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/pull/266"
            ),
        )

    def close_project_submissions(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

    def post_project(self, data, execute_callbacks=False):
        self.client.login(**credentials)
        project_url = self.project_url()
        if not execute_callbacks:
            return self.client.post(project_url, data)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                project_url, data, HTTP_HOST="localhost"
            )

    def authenticated_project_response(self):
        self.client.login(**credentials)
        project_url = self.project_url()
        response = self.client.get(project_url)
        return response

    def get_project_submission(self):
        return ProjectSubmission.objects.get(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        )

    def project_submission_count(self):
        return ProjectSubmission.objects.filter(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        ).count()

    def create_existing_project_submission(self, **extra_fields):
        data = {
            "github_link": "https://github.com/existing/repo",
            "commit_id": "123456a",
        }
        data.update(extra_fields)
        return ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            **data,
        )

    def assert_project_submission_matches(self, submission, data):
        self.assertEqual(submission.github_link, data["github_link"])
        self.assertEqual(submission.commit_id, data["commit_id"])
        if "time_spent" in data:
            self.assertEqual(submission.time_spent, int(data["time_spent"]))
        if "problems_comments" in data:
            self.assertEqual(
                submission.problems_comments,
                data["problems_comments"],
            )
        if "faq_contribution_url" in data:
            self.assertEqual(
                submission.faq_contribution_url,
                data["faq_contribution_url"],
            )

    def assert_submission_form_values(self, submission, data, links):
        self.assertEqual(submission.github_link, data["github_link"])
        self.assertEqual(submission.commit_id, data["commit_id"])
        self.assertEqual(submission.learning_in_public_links, links)

    def assert_db_submission_unchanged(self, submission, data, links):
        submission.refresh_from_db()
        self.assertNotEqual(submission.github_link, data["github_link"])
        self.assertNotEqual(submission.commit_id, data["commit_id"])
        self.assertNotEqual(submission.learning_in_public_links, links)

    def assert_project_confirmation_payload(self, payload, submission):
        self.assertEqual(payload["email"], "test@test.com")
        self.assertEqual(
            payload["template_key"],
            "project-submission-confirmation",
        )
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertEqual(
            payload["idempotency_key"],
            (
                f"project-submission:{submission.id}:"
                f"{submission.submitted_at.isoformat()}"
            ),
        )
        self.assertEqual(
            payload["metadata"]["event"],
            "project_submission",
        )

    def assert_project_confirmation_context(self, payload, submission):
        context = payload["context"]
        self.assertEqual(context["submission_id"], submission.id)
        self.assertEqual(context["course_slug"], "test-course")
        self.assertEqual(context["project_slug"], "test-project")
        self.assertEqual(
            context["update_url"],
            "http://localhost/test-course/project/test-project",
        )
        self.assertEqual(
            context["profile_url"],
            "http://localhost/accounts/settings/",
        )
        self.assertEqual(
            context["notification_category"],
            "homework and project submissions",
        )
        self.assertIn(
            "homework and project submission emails",
            context["notification_footer_text"],
        )
        self.assertEqual(
            context["intro_text"],
            (
                "Your project submission for Test Project in "
                "Test Course was saved."
            ),
        )


    def expected_project_repository_fields(self):
        fields = []
        github_field = {
            "key": "github_link",
            "label": "GitHub repository",
            "value": "https://github.com/test/project",
        }
        fields.append(github_field)
        commit_field = {
            "key": "commit_id",
            "label": "Commit ID",
            "value": "1234567",
        }
        fields.append(commit_field)
        return fields

    def expected_project_detail_fields(self):
        fields = []
        learning_links_field = {
            "key": "learning_in_public_links",
            "label": "Learning in public links",
            "value": "https://example.com/project-notes",
            "values": ["https://example.com/project-notes"],
        }
        fields.append(learning_links_field)
        time_spent_field = {
            "key": "time_spent",
            "label": "Time spent on project",
            "value": "2 hours",
        }
        fields.append(time_spent_field)
        problems_field = {
            "key": "problems_comments",
            "label": "Problems, comments, or feedback",
            "value": "No blockers.",
        }
        fields.append(problems_field)
        faq_field = {
            "key": "faq_contribution_url",
            "label": "FAQ contribution URL",
            "value": "https://github.com/DataTalksClub/faq/pull/266",
        }
        fields.append(faq_field)
        return fields

    def expected_project_submission_fields(self):
        fields = []
        for field in self.expected_project_repository_fields():
            fields.append(field)
        for field in self.expected_project_detail_fields():
            fields.append(field)
        return fields

    def assert_project_submission_fields(self, payload):
        expected_fields = self.expected_project_submission_fields()
        actual_fields = payload["context"]["submission_fields"]
        self.assertEqual(actual_fields, expected_fields)

    def assert_save_submission_copy(self, response):
        self.assertContains(
            response,
            (
                "You can save your project now and keep working on it. "
                "Update the commit ID before the deadline when you have "
                "a newer version."
            ),
        )

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.enrollment = self.create_enrollment()
        self.project = self.create_project()
