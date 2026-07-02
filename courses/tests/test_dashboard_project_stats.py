from dataclasses import dataclass, field
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
)

User = get_user_model()

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


@dataclass(frozen=True)
class ProjectSubmissionFixtureData:
    user: CustomUser
    enrollment: Enrollment
    scores: dict = field(default_factory=dict)
    passed: bool = True


class DashboardProjectFixtureMixin:
    @classmethod
    def create_dashboard_user(cls):
        cls.user = User.objects.create_user(**credentials)

    @classmethod
    def create_dashboard_course(cls):
        cls.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=70,
            first_homework_scored=True,
        )

    @classmethod
    def create_dashboard_project(cls):
        submission_due_date = timezone.now() + timedelta(days=7)
        peer_review_due_date = timezone.now() + timedelta(days=14)
        cls.project = Project.objects.create(
            course=cls.course,
            slug="project1",
            title="Project 1",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.COMPLETED.value,
        )

    @classmethod
    def create_project_users(cls):
        user_data = []
        for index in range(6):
            user = User(
                username=f"user{index}@test.com",
                email=f"user{index}@test.com",
                password="12345",
            )
            user_data.append(user)

        cls.users = User.objects.bulk_create(user_data)

    @classmethod
    def create_project_enrollments(cls):
        enrollment_data = []
        for user in cls.users:
            enrollment = Enrollment(student=user, course=cls.course)
            enrollment_data.append(enrollment)

        cls.enrollments = Enrollment.objects.bulk_create(
            enrollment_data
        )


class DashboardProjectSubmissionMixin:
    def create_project_submission(self, data: ProjectSubmissionFixtureData):
        scores = data.scores
        if not scores:
            scores = {"total_score": 80, "time_spent": 10.0}

        return ProjectSubmission.objects.create(
            project=self.project,
            student=data.user,
            enrollment=data.enrollment,
            github_link="https://github.com/test/repo",
            passed=data.passed,
            **scores,
        )

    def create_bulk_project_submissions(self, submission_data):
        submissions = []
        for index, data in enumerate(submission_data):
            passed = data.pop("passed", True)
            submission = ProjectSubmission(
                project=self.project,
                student=self.users[index],
                enrollment=self.enrollments[index],
                github_link=f"https://github.com/user{index}/repo",
                passed=passed,
                **data,
            )
            submissions.append(submission)
        return ProjectSubmission.objects.bulk_create(submissions)

    def create_completed_second_project(self):
        submission_due_date = timezone.now() + timedelta(days=7)
        peer_review_due_date = timezone.now() + timedelta(days=14)
        project = Project.objects.create(
            course=self.course,
            slug="project2",
            title="Project 2",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.COMPLETED.value,
        )
        return project

    def create_overlapping_project_submissions(self, project):
        for index in range(3):
            submission_data = ProjectSubmissionFixtureData(
                user=self.users[index],
                enrollment=self.enrollments[index],
            )
            self.create_project_submission(submission_data)
        for index in range(2):
            ProjectSubmission.objects.create(
                project=project,
                student=self.users[index],
                enrollment=self.enrollments[index],
                github_link="https://github.com/test/repo2",
                passed=True,
                total_score=80,
                time_spent=10.0,
            )


class DashboardProjectRequestMixin:
    def dashboard_response(self):
        url = reverse("dashboard", args=[self.course.slug])
        return self.client.get(url)


class DashboardProjectStatsAssertionsMixin:
    def assert_distinct_student_completion_rate(self, response):
        self.assertAlmostEqual(
            response.context["project_completion_rate"],
            (3 / 6) * 100,
            places=1,
        )


class DashboardProjectStatsTestCase(
    DashboardProjectFixtureMixin,
    DashboardProjectSubmissionMixin,
    DashboardProjectRequestMixin,
    DashboardProjectStatsAssertionsMixin,
    TestCase,
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.create_dashboard_user()
        cls.create_dashboard_course()
        cls.create_dashboard_project()
        cls.create_project_users()
        cls.create_project_enrollments()

    def setUp(self):
        self.client = Client()


class DashboardProjectStatisticsCalculationTest(DashboardProjectStatsTestCase):
    def test_project_statistics_calculation(self):
        submission_data = [
            {"total_score": 90, "time_spent": 8.0, "passed": True},
            {"total_score": 85, "time_spent": 10.0, "passed": True},
            {"total_score": 75, "time_spent": 12.0, "passed": True},
            {"total_score": 60, "time_spent": 6.0, "passed": False},
            {"total_score": 55, "time_spent": 5.0, "passed": False},
        ]

        self.create_bulk_project_submissions(submission_data)

        response = self.dashboard_response()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["project_pass_count"], 3)
        self.assertEqual(response.context["project_fail_count"], 2)
        expected_completion = (5 / 6) * 100
        self.assertAlmostEqual(
            response.context["project_completion_rate"],
            expected_completion,
            places=1,
        )
        self.assertIsNotNone(response.context["project_score_median"])
        self.assertIsNotNone(response.context["project_time_median"])

    def test_project_statistics_with_no_submissions(self):
        response = self.dashboard_response()

        self.assertEqual(response.context["project_pass_count"], 0)
        self.assertEqual(response.context["project_fail_count"], 0)
        self.assertEqual(
            response.context["project_completion_rate"], 0.0
        )
        self.assertIsNone(response.context["project_score_q25"])
        self.assertIsNone(response.context["project_time_q25"])

    def test_project_total_submissions(self):
        submission_data = [
            {"total_score": 90, "time_spent": 8.0, "passed": True},
            {"total_score": 85, "time_spent": 10.0, "passed": True},
            {"total_score": 75, "time_spent": 12.0, "passed": True},
            {"total_score": 60, "time_spent": 6.0, "passed": False},
            {"total_score": 55, "time_spent": 5.0, "passed": False},
        ]

        self.create_bulk_project_submissions(submission_data)

        response = self.dashboard_response()

        self.assertIn("project_total_submissions", response.context)
        self.assertIn("project_pass_count", response.context)
        self.assertIn("project_fail_count", response.context)
        self.assertEqual(response.context["project_pass_count"], 3)
        self.assertEqual(response.context["project_fail_count"], 2)
        self.assertEqual(response.context["project_total_submissions"], 5)


class DashboardProjectCompletionRateTest(DashboardProjectStatsTestCase):
    def test_completion_rate_with_multiple_projects(self):
        project = self.create_completed_second_project()
        self.create_overlapping_project_submissions(project)

        response = self.dashboard_response()

        self.assert_distinct_student_completion_rate(response)


class DashboardProjectEnrollmentScoreTest(DashboardProjectStatsTestCase):
    def test_avg_total_score_calculation(self):
        for index, enrollment in enumerate(self.enrollments):
            enrollment.total_score = 100 + index * 10
            enrollment.save()

        response = self.dashboard_response()

        expected_avg = (100 + 110 + 120 + 130 + 140 + 150) / 6
        self.assertAlmostEqual(
            response.context["avg_total_score"], expected_avg, places=1
        )


class DashboardProjectGraduateCountTest(DashboardProjectStatsTestCase):
    def test_graduates_count(self):
        first_enrollments = self.enrollments[:3]
        for index, enrollment in enumerate(first_enrollments):
            enrollment.certificate_url = f"https://example.com/cert{index}.pdf"
            enrollment.save()

        response = self.dashboard_response()

        self.assertIn("graduates_count", response.context)
        self.assertEqual(response.context["graduates_count"], 3)

    def test_graduates_count_excludes_empty_certificates(self):
        self.enrollments[0].certificate_url = "https://example.com/cert1.pdf"
        self.enrollments[0].save()
        self.enrollments[1].certificate_url = ""
        self.enrollments[1].save()

        response = self.dashboard_response()

        self.assertIn("graduates_count", response.context)
        self.assertEqual(response.context["graduates_count"], 1)
