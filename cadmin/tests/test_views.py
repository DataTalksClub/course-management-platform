import logging

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
    Homework,
    HomeworkState,
)


logger = logging.getLogger(__name__)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class CadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        # Create admin user
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def test_course_list_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected from course list"""
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_course_list_non_staff_denied(self):
        """Test that non-staff users cannot access course list"""
        self.client.login(username="test@test.com", password="12345")
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_course_list_staff_allowed(self):
        """Test that staff users can access course list"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse("cadmin_course_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course Administration")

    def test_course_admin_staff_allowed(self):
        """Test that staff users can access course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course.title)
        self.assertContains(response, "Admin Panel")

    def test_homework_submissions_redirect_from_courses(self):
        """Test that homework submissions view redirects to cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_project_submissions_redirect_from_courses(self):
        """Test that project submissions view redirects to cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_cadmin_homework_submissions_staff_allowed(self):
        """Test that staff users can view homework submissions in cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.homework.title)

    def test_cadmin_project_submissions_staff_allowed(self):
        """Test that staff users can view project submissions in cadmin"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.title)

    def test_project_submission_edit_get(self):
        """Test that staff users can access the project submission edit page"""
        # Create a project submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=10,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=27,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            }
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Project Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, 'value="10"')  # project_score
        self.assertContains(response, 'value="27"')  # total_score

    def test_project_submission_edit_post_calculates_total(self):
        """Test that editing individual scores automatically calculates the total"""
        # Create a project submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=0,
            project_faq_score=0,
            project_learning_in_public_score=0,
            peer_review_score=0,
            peer_review_learning_in_public_score=0,
            total_score=0,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            }
        )

        # Post new scores
        response = self.client.post(url, {
            "project_score": 10,
            "project_faq_score": 5,
            "project_learning_in_public_score": 3,
            "peer_review_score": 7,
            "peer_review_learning_in_public_score": 2,
        })

        # Should redirect back to submissions list
        self.assertEqual(response.status_code, 302)

        # Refresh submission from database
        submission.refresh_from_db()

        # Check that total was calculated correctly
        self.assertEqual(submission.project_score, 10)
        self.assertEqual(submission.project_faq_score, 5)
        self.assertEqual(submission.project_learning_in_public_score, 3)
        self.assertEqual(submission.peer_review_score, 7)
        self.assertEqual(submission.peer_review_learning_in_public_score, 2)
        self.assertEqual(submission.total_score, 27)  # Sum of all scores

    def test_project_submission_edit_post_with_checkboxes(self):
        """Test that editing submission with checkboxes works correctly"""
        # Create a project submission
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=10,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=27,
            reviewed_enough_peers=False,
            passed=False,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            }
        )

        # Post with checkboxes checked
        response = self.client.post(url, {
            "project_score": 10,
            "project_faq_score": 5,
            "project_learning_in_public_score": 3,
            "peer_review_score": 7,
            "peer_review_learning_in_public_score": 2,
            "reviewed_enough_peers": "on",
            "passed": "on",
        })

        # Refresh submission from database
        submission.refresh_from_db()

        # Check that checkboxes were saved correctly
        self.assertTrue(submission.reviewed_enough_peers)
        self.assertTrue(submission.passed)

    def test_homework_score_shows_message(self):
        """Test that scoring homework shows a message on the course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_homework_score",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            }
        )
        response = self.client.post(url, follow=True)
        
        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        )
        
        # Check that a message was added
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)

    def test_project_score_shows_message(self):
        """Test that scoring project shows a message on the course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_score",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.post(url, follow=True)
        
        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        )
        
        # Check that a message was added
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)

    def test_project_assign_reviews_shows_message(self):
        """Test that assigning peer reviews shows a message on the course admin page"""
        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "cadmin_project_assign_reviews",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            }
        )
        response = self.client.post(url, follow=True)
        
        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse("cadmin_course", kwargs={"course_slug": self.course.slug})
        )
        
        # Check that a message was added
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
