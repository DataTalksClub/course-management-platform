import logging

from django.urls import reverse
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
)


logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


class ProjectViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() - timedelta(hours=1),
            peer_review_due_date=timezone.now() + timedelta(hours=1),
        )

    def test_project_detail_unauthenticated_no_submission(self):
        """
        Test the project details view for unauthenticated users with no submissions.
        """
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context
        submission = context["submission"]

        self.assertIsNone(submission)

        self.assertFalse(context["is_authenticated"])
        self.assertFalse(context["disabled"])
        self.assertTrue(context["accepting_submissions"])

        self.assertEqual(context["project"], self.project)
        self.assertEqual(context["course"], self.course)

    # def test_project_detail_authenticated_with_submission(self):
    #     self.client.login(
    #         username=credentials["username"],
    #         password=credentials["password"],
    #     )
    #     url = reverse(
    #         "project", args=[self.course.slug, self.project.slug]
    #     )
    #     response = self.client.get(url)
    #     self.assertEqual(response.status_code, 200)
    #     self.assertIn("submission", response.context)

    #     context = response.context
    #     submission = context["submission"]

    #     self.assertIsNotNone(submission)
        # More assertions here for the submission details...

    def test_project_detail_authenticated_certificate_name_is_used(self):
        self.enrollment.display_name = "Display Name"
        self.enrollment.certificate_name = "Certificate Name"
        self.enrollment.save()

        self.client.login(
            username=credentials["username"],
            password=credentials["password"],
        )
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context
        ceritificate_name = context["ceritificate_name"]

        self.assertEqual(ceritificate_name, "Certificate Name")

    def test_project_detail_authenticated_without_submission(self):
        self.client.login(
            username=credentials["username"],
            password=credentials["password"],
        )
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context

        submission = context["submission"]
        self.assertIsNone(submission)

        self.assertTrue(context["is_authenticated"])

    def test_project_detail_when_peer_reviewing(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertEqual(context["project"], self.project)
        self.assertTrue(context["disabled"])

    def test_project_detail_with_scored_project(self):
        """
        Test the project details view with a project that has been scored.
        """
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("project", response.context)
        # Check if the context has 'disabled' as True
        self.assertTrue(response.context["disabled"])

    def test_project_submission_post_no_submissions(self):
        """
        Test posting a project submission when there are no existing submissions.
        """
        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )

        data = {
            "github_link": "https://httpbin.org/status/200",
            "commit_id": "1234567",
            "time_spent": "2",
            "problems_comments": "Encountered an issue with...",
            "faq_contribution": "Added a solution to FAQ.",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)

        submissions = ProjectSubmission.objects.filter(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        )

        self.assertEqual(submissions.count(), 1)

        submission = submissions.first()

        self.assertEqual(submission.github_link, data["github_link"])
        self.assertEqual(submission.commit_id, data["commit_id"])
        self.assertEqual(submission.time_spent, int(data["time_spent"]))
        self.assertEqual(
            submission.problems_comments, data["problems_comments"]
        )
        self.assertEqual(
            submission.faq_contribution, data["faq_contribution"]
        )

    def test_project_submission_post_creates_enrollment(self):
        self.enrollment.delete()

        enrollments = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        )

        self.assertEqual(enrollments.count(), 0)

        self.client.login(**credentials)

        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )

        data = {
            "github_link": "https://httpbin.org/status/200",
            "commit_id": "1234567",
            "time_spent": "2",
            "problems_comments": "Encountered an issue with...",
            "faq_contribution": "Added a solution to FAQ.",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        self.assertEqual(enrollments.count(), 1)

    def test_project_submission_post_with_submissions(self):
        """
        Test posting a project submission when there are existing submissions.
        """
        self.client.login(**credentials)

        # Create an initial submission
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id="123456a",
        )

        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )

        data = {
            "github_link": "https://httpbin.org/status/200",
            "commit_id": "123456e",
            "time_spent": "3",
            "problems_comments": "No issues encountered.",
            "faq_contribution": "Helped a peer with their problem.",
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # no duplicate submissions
        count_sumissions = ProjectSubmission.objects.filter(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        ).count()

        self.assertEqual(count_sumissions, 1)

        submission = fetch_fresh(submission)
        self.assertEqual(submission.github_link, data["github_link"])
        self.assertEqual(submission.commit_id, data["commit_id"])
        self.assertEqual(submission.time_spent, int(data["time_spent"]))
        self.assertEqual(
            submission.problems_comments, data["problems_comments"]
        )
        self.assertEqual(
            submission.faq_contribution, data["faq_contribution"]
        )

    # this test requires a redesing of the project view
    # skipping for now
    # def test_submission_exist_post_with_error(self):
    #     """
    #     Test posting a project submission when there are existing submissions.
    #     """
    #     self.client.login(**credentials)

    #     # Create an initial submission
    #     db_submission = ProjectSubmission.objects.create(
    #         project=self.project,
    #         student=self.user,
    #         enrollment=self.enrollment,
    #         github_link="https://github.com/alexeygrigorev/llm-rag-workshop",
    #         commit_id="123456a",
    #         learning_in_public_links=[
    #             "https://httpbin.org/status/200?link1",
    #             "https://httpbin.org/status/200?link2",
    #         ]
    #     )

    #     url = reverse(
    #         "project", args=[self.course.slug, self.project.slug]
    #     )

    #     # accidentally replaces the working link
    #     # updates commit_id and learning in public links
    #     data = {
    #         "github_link": "https://github.com/alexeygrigorev/404",
    #         "commit_id": "123456f",
    #         "time_spent": "3",
    #         "learning_in_public_links": [
    #             "https://httpbin.org/status/200?link1",
    #             "https://httpbin.org/status/200?link2",
    #             "https://httpbin.org/status/200?link3",
    #         ]
    #     }

    #     response = self.client.post(url, data)
    #     self.assertEqual(response.status_code, 302)

    #     context = response.context
    #     submission = context["submission"]

    #     # context is updated
    #     self.assertEquals(submission.github_link, data["github_link"])
    #     self.assertEquals(submission.commit_id, data["commit_id"])
    #     self.assertEquals(submission.learning_in_public_links, data["learning_in_public_links"])

    #     # the original submission is not
    #     self.assertNotEqual(db_submission.github_link, data["github_link"])
    #     self.assertNotEqual(db_submission.commit_id, data["commit_id"])

    def test_project_submission_not_accepting_responses(self):
        """
        Test posting a project submission when there are no existing submissions.
        """

        self.client.login(**credentials)

        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )

        data = {
            "github_link": "https://httpbin.org/status/200",
            "commit_id": "1234567",
            "time_spent": "2",
            "problems_comments": "Encountered an issue with...",
            "faq_contribution": "Added a solution to FAQ.",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)

        submissions = ProjectSubmission.objects.filter(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        )

        self.assertEqual(submissions.count(), 0)

    def test_project_submission_post_invalid_link_no_submission(self):
        """
        When the link is invalid and there's no submission yet,
        no submission is created
        """
        self.client.login(**credentials)
        url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )

        data = {
            "github_link": "https://github.com/alexeygrigorev/404",
            "commit_id": "1234567"
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)

        submission = ProjectSubmission.objects.filter(
            student=self.user,
            project=self.project,
            enrollment=self.enrollment,
        )

        self.assertFalse(submission.exists())