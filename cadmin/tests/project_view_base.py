from datetime import timedelta

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


class ProjectCadminFixtureMixin:
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


class ProjectCadminSubmissionFixtureMixin:
    def create_enrollment(self, student=None):
        return Enrollment.objects.create(
            student=student or self.user,
            course=self.course,
        )

    def create_project_submission(self, enrollment=None, **overrides):
        submission_enrollment = enrollment
        if submission_enrollment is None:
            submission_enrollment = self.create_enrollment()
        defaults = {
            "project": self.project,
            "student": self.user,
            "enrollment": submission_enrollment,
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


class ProjectCadminSubmissionListFixtureMixin:
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

    def create_project_search_submission(self, index):
        user = User.objects.create_user(
            username=f"project-student-{index:02d}",
            email=f"project-student-{index:02d}@example.com",
            password="test",
        )
        enrollment = self.create_enrollment(student=user)
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            total_score=index,
        )

    def create_project_search_submissions(self, count):
        for index in range(count):
            self.create_project_search_submission(index)


class ProjectCadminSubmissionEditFixtureMixin:
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


class ProjectCadminUrlMixin:
    def cadmin_project_submissions_url(self):
        kwargs = {
            "course_slug": self.course.slug,
            "project_slug": self.project.slug,
        }
        return reverse("cadmin_project_submissions", kwargs=kwargs)

    def project_submissions_url(self):
        kwargs = {
            "course_slug": self.course.slug,
            "project_slug": self.project.slug,
        }
        return reverse("project_submissions", kwargs=kwargs)

    def project_url(self):
        kwargs = {
            "course_slug": self.course.slug,
            "project_slug": self.project.slug,
        }
        return reverse("project", kwargs=kwargs)

    def leaderboard_score_breakdown_url(self, enrollment):
        kwargs = {
            "course_slug": self.course.slug,
            "enrollment_id": enrollment.id,
        }
        return reverse("leaderboard_score_breakdown", kwargs=kwargs)

    def project_submission_edit_url(self, submission):
        kwargs = {
            "course_slug": self.course.slug,
            "project_slug": self.project.slug,
            "submission_id": submission.id,
        }
        return reverse("cadmin_project_submission_edit", kwargs=kwargs)

    def cadmin_project_score_url(self):
        kwargs = {
            "course_slug": self.course.slug,
            "project_slug": self.project.slug,
        }
        return reverse("cadmin_project_score", kwargs=kwargs)

    def cadmin_project_assign_reviews_url(self):
        kwargs = {
            "course_slug": self.course.slug,
            "project_slug": self.project.slug,
        }
        return reverse("cadmin_project_assign_reviews", kwargs=kwargs)

    def cadmin_course_url(self):
        kwargs = {"course_slug": self.course.slug}
        return reverse("cadmin_course", kwargs=kwargs)


class ProjectCadminSubmissionAssertionsMixin:
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
        eval_score_count = eval_scores.count()
        self.assertEqual(eval_score_count, 2)
        criteria1_score = ProjectEvaluationScore.objects.get(
            submission=submission, review_criteria=self.criteria1
        )
        criteria2_score = ProjectEvaluationScore.objects.get(
            submission=submission, review_criteria=self.criteria2
        )
        self.assertEqual(criteria1_score.score, 2)
        self.assertEqual(criteria2_score.score, 4)


class ProjectCadminViewTestBase(
    ProjectCadminFixtureMixin,
    ProjectCadminSubmissionFixtureMixin,
    ProjectCadminSubmissionListFixtureMixin,
    ProjectCadminSubmissionEditFixtureMixin,
    ProjectCadminUrlMixin,
    ProjectCadminSubmissionAssertionsMixin,
    TestCase,
):
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
        submission_due_date = timezone.now() + timedelta(days=7)
        peer_review_due_date = timezone.now() + timedelta(days=14)
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        self.create_review_criteria()
