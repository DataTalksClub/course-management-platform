"""
Tests for project-related data API views.

Tests for project_data_view endpoint.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Project,
    ProjectSubmission,
    Enrollment,
)

from accounts.models import CustomUser, Token


class ProjectDataAPITestCase(TestCase):
    """Tests for project_data_view endpoint."""

    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="testuser@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

    def create_project_submission(self, project):
        return ProjectSubmission.objects.create(
            project=project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/DataTalksClub",
            commit_id="abcd1234",
            faq_contribution_url="https://github.com/DataTalksClub/faq/issues/266",
        )

    def project_export_url(self, project):
        return reverse(
            "api_project_submissions_export",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": project.slug,
            },
        )

    def expected_course_data(self):
        return {
            "id": self.course.id,
            "slug": self.course.slug,
            "title": self.course.title,
            "description": self.course.description,
            "social_media_hashtag": self.course.social_media_hashtag,
            "faq_document_url": self.course.faq_document_url,
        }

    def expected_project_data(self, project):
        return {
            "id": project.id,
            "course": self.course.id,
            "slug": project.slug,
            "title": project.title,
            "description": project.description,
            "learning_in_public_cap_project": (
                project.learning_in_public_cap_project
            ),
            "time_spent_project_field": project.time_spent_project_field,
            "problems_comments_field": project.problems_comments_field,
            "faq_contribution_field": project.faq_contribution_field,
            "learning_in_public_cap_review": (
                project.learning_in_public_cap_review
            ),
            "number_of_peers_to_evaluate": (
                project.number_of_peers_to_evaluate
            ),
            "points_for_peer_review": project.points_for_peer_review,
            "time_spent_evaluation_field": (
                project.time_spent_evaluation_field
            ),
            "points_to_pass": project.points_to_pass,
            "state": project.state,
        }

    def expected_submission_data(self, submission):
        return {
            "student_id": self.user.id,
            "student_email": self.user.email,
            "github_link": submission.github_link,
            "commit_id": submission.commit_id,
            "learning_in_public_links": submission.learning_in_public_links,
            "faq_contribution_url": submission.faq_contribution_url,
            "time_spent": submission.time_spent,
            "problems_comments": submission.problems_comments,
            "project_score": submission.project_score,
            "project_faq_score": submission.project_faq_score,
            "project_learning_in_public_score": (
                submission.project_learning_in_public_score
            ),
            "peer_review_score": submission.peer_review_score,
            "peer_review_learning_in_public_score": (
                submission.peer_review_learning_in_public_score
            ),
            "total_score": submission.total_score,
            "reviewed_enough_peers": submission.reviewed_enough_peers,
            "passed": submission.passed,
        }

    def assert_fields(self, actual, expected):
        for field, expected_value in expected.items():
            self.assertEqual(actual[field], expected_value)

    def test_project_data_view(self):
        project = self.create_project()
        submission = self.create_project_submission(project)

        response = self.client.get(self.project_export_url(project))

        self.assertEqual(response.status_code, 200)
        actual_result = response.json()
        self.assert_fields(actual_result["course"], self.expected_course_data())
        self.assert_fields(
            actual_result["project"], self.expected_project_data(project)
        )
        self.assertEqual(len(actual_result["submissions"]), 1)
        self.assert_fields(
            actual_result["submissions"][0],
            self.expected_submission_data(submission),
        )
