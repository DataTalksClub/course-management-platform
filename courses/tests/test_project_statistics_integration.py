from dataclasses import dataclass
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.assignment_statistics import calculate_project_statistics
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
    User,
)

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


@dataclass(frozen=True)
class WorkflowSubmissionScores:
    project_score: int
    project_learning_in_public_score: int
    peer_review_score: int
    peer_review_learning_in_public_score: int
    total_score: int
    time_spent: float


class ProjectStatisticsIntegrationTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.create_primary_user()
        cls.course = cls.create_course()
        cls.project = cls.create_project()
        cls.users = cls.create_bulk_users()
        cls.enrollments = cls.create_bulk_enrollments(cls.users)

    @classmethod
    def create_primary_user(cls):
        return User.objects.create_user(**credentials)

    @classmethod
    def create_course(cls):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

    @classmethod
    def create_project(cls):
        return Project.objects.create(
            course=cls.course,
            slug="test-project",
            title="Test Project",
            description="Test project description",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COMPLETED.value,
        )

    @classmethod
    def create_bulk_users(cls):
        users = []
        for i in range(10):
            user = User(
                username=f"student{i}@test.com",
                email=f"student{i}@test.com",
                password="password123",
            )
            users.append(user)
        return User.objects.bulk_create(users)

    @classmethod
    def create_bulk_enrollments(cls, users):
        enrollments = []
        for user in users:
            enrollment = Enrollment(student=user, course=cls.course)
            enrollments.append(enrollment)
        return Enrollment.objects.bulk_create(enrollments)

    def setUp(self):
        self.client = Client()
        self.shared_enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )
        self.shared_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.shared_enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=10,
            total_score=20,
            time_spent=10.0,
        )

    def lower_workflow_submission_score_rows(self):
        rows = []
        row = WorkflowSubmissionScores(
            project_score=5,
            project_learning_in_public_score=2,
            peer_review_score=1,
            peer_review_learning_in_public_score=0,
            total_score=8,
            time_spent=5.0,
        )
        rows.append(row)
        row = WorkflowSubmissionScores(
            project_score=8,
            project_learning_in_public_score=4,
            peer_review_score=2,
            peer_review_learning_in_public_score=1,
            total_score=15,
            time_spent=8.0,
        )
        rows.append(row)
        return rows

    def higher_workflow_submission_score_rows(self):
        rows = []
        row = WorkflowSubmissionScores(
            project_score=12,
            project_learning_in_public_score=6,
            peer_review_score=3,
            peer_review_learning_in_public_score=2,
            total_score=23,
            time_spent=12.0,
        )
        rows.append(row)
        row = WorkflowSubmissionScores(
            project_score=10,
            project_learning_in_public_score=5,
            peer_review_score=3,
            peer_review_learning_in_public_score=1,
            total_score=19,
            time_spent=10.0,
        )
        rows.append(row)
        row = WorkflowSubmissionScores(
            project_score=15,
            project_learning_in_public_score=8,
            peer_review_score=3,
            peer_review_learning_in_public_score=2,
            total_score=28,
            time_spent=15.0,
        )
        rows.append(row)
        return rows

    def workflow_submission_score_rows(self):
        rows = []
        for row in self.lower_workflow_submission_score_rows():
            rows.append(row)
        for row in self.higher_workflow_submission_score_rows():
            rows.append(row)
        return rows

    def workflow_submission_scores(self, row):
        return {
            "project_score": row.project_score,
            "project_learning_in_public_score": (
                row.project_learning_in_public_score
            ),
            "peer_review_score": row.peer_review_score,
            "peer_review_learning_in_public_score": (
                row.peer_review_learning_in_public_score
            ),
            "total_score": row.total_score,
            "time_spent": row.time_spent,
        }

    def workflow_submission_data(self):
        submission_data = []
        score_rows = self.workflow_submission_score_rows()
        for row in score_rows:
            scores = self.workflow_submission_scores(row)
            submission_data.append(scores)
        return submission_data

    def create_workflow_submissions(self):
        ProjectSubmission.objects.filter(project=self.project).delete()
        submissions = []
        submission_data = self.workflow_submission_data()
        for index, scores in enumerate(submission_data):
            submission = ProjectSubmission(
                project=self.project,
                student=self.users[index],
                enrollment=self.enrollments[index],
                github_link=f"https://github.com/student{index}/repo",
                commit_id=f"abc12{index}",
                **scores,
            )
            submissions.append(submission)
        return ProjectSubmission.objects.bulk_create(submissions)

    def assert_workflow_statistics(self, stats):
        self.assertIsNotNone(stats)
        self.assertEqual(stats.total_submissions, 5)
        self.assertEqual(stats.min_project_score, 5)
        self.assertEqual(stats.max_project_score, 15)
        self.assertEqual(stats.avg_project_score, 10.0)

    def project_statistics_url(self):
        return reverse(
            "project_statistics",
            args=[self.course.slug, self.project.slug],
        )

    def assert_statistics_view_content(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "5")
        self.assertContains(response, "Project score")
        self.assertContains(response, "Total score")
        self.assertContains(response, "Time spent on project")

    def test_full_statistics_workflow(self):
        """Test the complete statistics workflow from submission to view"""
        self.create_workflow_submissions()

        stats = calculate_project_statistics(self.project)
        self.assert_workflow_statistics(stats)

        response = self.client.get(self.project_statistics_url())
        self.assert_statistics_view_content(response)

        project_url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        project_response = self.client.get(project_url)
        self.assertContains(project_response, "Project statistics")
        self.assertContains(project_response, self.project_statistics_url())

    def test_statistics_links_in_navigation(self):
        """Test that statistics links appear in appropriate navigation areas"""
        stats_url = reverse(
            "project_statistics",
            args=[self.course.slug, self.project.slug],
        )

        results_url = reverse(
            "project_results",
            args=[self.course.slug, self.project.slug],
        )
        results_response = self.client.get(results_url)
        self.assertContains(results_response, "Project statistics")
        self.assertContains(results_response, stats_url)

        list_url = reverse(
            "project_list", args=[self.course.slug, self.project.slug]
        )
        list_response = self.client.get(list_url)
        self.assertContains(list_response, "Project statistics")
        self.assertContains(list_response, stats_url)

    def test_statistics_links_only_for_completed_projects(self):
        """Test that statistics links only appear for completed projects"""
        incomplete_project = Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        stats_url = reverse(
            "project_statistics",
            args=[self.course.slug, incomplete_project.slug],
        )

        project_url = reverse(
            "project", args=[self.course.slug, incomplete_project.slug]
        )
        project_response = self.client.get(project_url)
        self.assertNotContains(project_response, "Project statistics")
        self.assertNotContains(project_response, stats_url)

        list_url = reverse(
            "project_list",
            args=[self.course.slug, incomplete_project.slug],
        )
        list_response = self.client.get(list_url)
        self.assertNotContains(list_response, "Project statistics")
        self.assertNotContains(list_response, stats_url)
