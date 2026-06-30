from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectEvaluationScore,
    ProjectState,
    ProjectSubmission,
    ReviewCriteria,
    ReviewCriteriaTypes,
    User,
)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)

admin_credentials = dict(
    username="admin@test.com",
    password="admin123",
)


class ProjectCadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        User.objects.create_user(
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
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        self.create_review_criteria()

    def create_review_criteria(self):
        self.criteria1 = ReviewCriteria.objects.create(
            course=self.course,
            description="Problem Description",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )
        self.criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 4},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

    def login_admin(self):
        self.client.login(**admin_credentials)

    def create_enrollment(self, student=None):
        return Enrollment.objects.create(
            student=student or self.user,
            course=self.course,
        )

    def create_project_submission(self, enrollment=None, **overrides):
        defaults = {
            "project": self.project,
            "student": self.user,
            "enrollment": enrollment or self.create_enrollment(),
            "github_link": "https://github.com/test/repo",
            "commit_id": "abc123",
            "project_score": 0,
            "project_faq_score": 0,
            "project_learning_in_public_score": 0,
            "peer_review_score": 0,
            "peer_review_learning_in_public_score": 0,
            "total_score": 0,
        }
        defaults.update(overrides)
        return ProjectSubmission.objects.create(**defaults)

    def create_project_page_submission(self, index):
        user = User.objects.create_user(
            username=f"project-page-student-{index:02d}",
            email=f"project-page-student-{index:02d}@example.com",
            password="test",
        )
        enrollment = self.create_enrollment(student=user)
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            total_score=index,
        )

    def create_project_page_submissions(self, count):
        for index in range(count):
            self.create_project_page_submission(index)

    def create_project_evaluation_scores(self, submission):
        ProjectEvaluationScore.objects.create(
            submission=submission,
            review_criteria=self.criteria1,
            score=2,
        )
        ProjectEvaluationScore.objects.create(
            submission=submission,
            review_criteria=self.criteria2,
            score=4,
        )

    def project_score_payload(self, **overrides):
        payload = {
            f"criteria_score_{self.criteria1.id}": 2,
            f"criteria_score_{self.criteria2.id}": 4,
            "project_faq_score": 5,
            "project_learning_in_public_score": 3,
            "peer_review_score": 7,
            "peer_review_learning_in_public_score": 2,
        }
        payload.update(overrides)
        return payload

    def assert_project_submission_actions(self, response):
        project_url = reverse(
            "project",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        django_admin_url = (
            f"/admin/courses/project/{self.project.id}/change/"
        )
        assign_reviews_url = reverse(
            "cadmin_project_assign_reviews",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.assertContains(response, project_url)
        self.assertContains(response, django_admin_url)
        self.assertContains(response, "Assign peer reviews")
        self.assertContains(response, assign_reviews_url)

    def assert_project_scoring_action(self, response):
        score_url = reverse(
            "cadmin_project_score",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.assertContains(response, "Score projects")
        self.assertContains(response, score_url)

    def assert_first_project_submissions_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["submissions"]), 50)
        self.assertContains(response, 'href="?page=2"')
        self.assertContains(response, 'aria-label="Next page"')
        self.assertNotContains(response, "First")
        self.assertNotContains(response, "Last")

    def assert_second_project_submissions_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["submissions"]), 5)
        self.assertContains(response, 'href="?page=1"')
        self.assertContains(response, 'aria-label="Previous page"')

    def assert_project_scores(self, submission):
        self.assertEqual(submission.project_score, 6)
        self.assertEqual(submission.project_faq_score, 5)
        self.assertEqual(submission.project_learning_in_public_score, 3)
        self.assertEqual(submission.peer_review_score, 7)
        self.assertEqual(
            submission.peer_review_learning_in_public_score, 2
        )
        self.assertEqual(submission.total_score, 23)

    def assert_project_evaluation_scores(self, submission):
        eval_scores = ProjectEvaluationScore.objects.filter(
            submission=submission
        )
        self.assertEqual(eval_scores.count(), 2)
        criteria1_score = ProjectEvaluationScore.objects.get(
            submission=submission, review_criteria=self.criteria1
        )
        criteria2_score = ProjectEvaluationScore.objects.get(
            submission=submission, review_criteria=self.criteria2
        )
        self.assertEqual(criteria1_score.score, 2)
        self.assertEqual(criteria2_score.score, 4)

    def test_project_submissions_redirect_from_courses(self):
        """Test that project submissions view redirects to cadmin"""
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_cadmin_project_submissions_staff_allowed(self):
        """Test that staff users can view project submissions in cadmin"""
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.title)

    def test_cadmin_project_submissions_shows_project_actions(self):
        """Project submissions page exposes project actions."""
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.login_admin()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_project_submission_actions(response)

        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save(update_fields=["state"])

        response = self.client.get(url)

        self.assert_project_scoring_action(response)

    def test_project_submission_email_links_to_leaderboard_record(self):
        """Project submission email links to the student's leaderboard record."""
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Test Student",
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            total_score=10,
        )
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        leaderboard_url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": enrollment.id,
            },
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, leaderboard_url)

    def test_project_submission_search_finds_records_beyond_first_page(
        self,
    ):
        """Project submission search is server-side across all submissions."""
        for index in range(30):
            user = User.objects.create_user(
                username=f"project-student-{index:02d}",
                email=f"project-student-{index:02d}@example.com",
                password="test",
            )
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            ProjectSubmission.objects.create(
                project=self.project,
                student=user,
                enrollment=enrollment,
                total_score=index,
            )
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url, {"q": "project-student-29"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "project-student-29@example.com")
        self.assertNotContains(
            response, "project-student-00@example.com"
        )

    def test_project_submissions_paginated_by_50(self):
        self.create_project_page_submissions(55)
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.login_admin()
        response = self.client.get(url)
        self.assert_first_project_submissions_page(response)

        response = self.client.get(url, {"page": 2})
        self.assert_second_project_submissions_page(response)

    def test_project_submission_edit_get(self):
        """Test that staff users can access the project submission edit page"""
        submission = self.create_project_submission(
            project_score=6,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,
        )
        self.create_project_evaluation_scores(submission)
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            },
        )

        self.login_admin()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Project Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "Problem Description")
        self.assertContains(response, "Code Quality")
        self.assertContains(response, 'value="6"')
        self.assertContains(response, 'value="23"')

    def test_project_submission_edit_post_calculates_total(self):
        """Test that editing individual criteria scores automatically calculates the total"""
        submission = self.create_project_submission()
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            },
        )
        payload = self.project_score_payload()

        self.login_admin()
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assert_project_scores(submission)
        self.assert_project_evaluation_scores(submission)

    def test_project_submission_edit_post_with_checkboxes(self):
        """Test that editing submission with checkboxes works correctly"""
        submission = self.create_project_submission(
            project_score=6,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,
            reviewed_enough_peers=False,
            passed=False,
        )
        url = reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            },
        )
        payload = self.project_score_payload(
            reviewed_enough_peers="on",
            passed="on",
        )

        self.login_admin()
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        submission.refresh_from_db()
        self.assertTrue(submission.reviewed_enough_peers)
        self.assertTrue(submission.passed)

    @patch("cadmin.views.projects.send_project_score_notification")
    @patch("cadmin.views.projects.score_project")
    def test_project_score_shows_message(
        self,
        score_project_mock,
        send_score_notification,
    ):
        """Test that scoring project shows a message on the course admin page"""
        from courses.project_assignment import ProjectActionStatus

        score_project_mock.return_value = (
            ProjectActionStatus.OK,
            "Project scored",
        )
        url = reverse(
            "cadmin_project_score",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        course_admin_url = reverse(
            "cadmin_course",
            kwargs={"course_slug": self.course.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, course_admin_url)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        send_score_notification.assert_called_once_with(self.project)

    @patch("cadmin.views.projects.send_project_score_notification")
    @patch("cadmin.views.projects.score_project")
    def test_project_score_can_redirect_back_to_project_submissions(
        self,
        score_project_mock,
        send_score_notification,
    ):
        """Scoring from project submissions returns to that page."""
        from courses.project_assignment import ProjectActionStatus

        score_project_mock.return_value = (
            ProjectActionStatus.OK,
            "Project scored",
        )
        next_url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        url = reverse(
            "cadmin_project_score",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.client.login(**admin_credentials)
        response = self.client.post(
            url, {"next": next_url}, follow=True
        )

        self.assertRedirects(response, next_url)
        send_score_notification.assert_called_once_with(self.project)

    @patch("cadmin.views.projects.send_project_score_notification")
    def test_project_assign_reviews_shows_message(
        self,
        send_score_notification,
    ):
        """Test that assigning peer reviews shows a message on the course admin page"""
        url = reverse(
            "cadmin_project_assign_reviews",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        course_admin_url = reverse(
            "cadmin_course",
            kwargs={"course_slug": self.course.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, course_admin_url)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        send_score_notification.assert_not_called()

    @patch(
        "cadmin.views.projects.send_peer_review_assignment_notification"
    )
    def test_project_assign_reviews_can_redirect_back_to_project_submissions(
        self,
        send_assignment_notification,
    ):
        """Assigning reviews from project submissions returns to that page."""
        next_url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        url = reverse(
            "cadmin_project_assign_reviews",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        self.client.login(**admin_credentials)
        response = self.client.post(
            url, {"next": next_url}, follow=True
        )

        self.assertRedirects(response, next_url)
        send_assignment_notification.assert_not_called()
