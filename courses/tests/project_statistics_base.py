from dataclasses import dataclass
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectStatistics,
    ProjectSubmission,
    User,
)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


@dataclass(frozen=True)
class RawStatExpectation:
    stats: dict
    field: str
    minimum: float
    maximum: float
    average: float


class ProjectStatisticsFixtureMixin:
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

    def create_completed_project(self):
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Test project description",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COMPLETED.value,
        )

    def create_student_enrollments(self):
        for i in range(5):
            user = User.objects.create_user(
                username=f"student{i}@test.com",
                email=f"student{i}@test.com",
                password="password123",
            )
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            self.users.append(user)
            self.enrollments.append(enrollment)


class ProjectStatisticsSubmissionFixtureMixin:
    def create_project_submission(self, user, enrollment, scores=None):
        if scores is None:
            scores = {
                "project_score": 10,
                "project_learning_in_public_score": 5,
                "peer_review_score": 3,
                "peer_review_learning_in_public_score": 2,
                "total_score": 20,
                "time_spent": 10.5,
            }

        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            **scores,
        )

    def create_bulk_submissions(self, submissions_data):
        submissions = []
        for i, scores in enumerate(submissions_data):
            submission = ProjectSubmission(
                project=self.project,
                student=self.users[i],
                enrollment=self.enrollments[i],
                github_link=f"https://github.com/student{i}/repo",
                commit_id=f"abc12{i}",
                **scores,
            )
            submissions.append(submission)
        return ProjectSubmission.objects.bulk_create(submissions)


class ProjectStatisticsModelFixtureMixin:
    def create_model_method_submissions(self):
        for i in range(3):
            scores = {
                "project_score": 10 + i,
                "total_score": 20 + i,
                "time_spent": 10.0 + i,
            }
            self.create_project_submission(
                self.users[i], self.enrollments[i], scores
            )

    def project_statistics_exists(self):
        exists = ProjectStatistics.objects.filter(
            project=self.project
        ).exists()
        return exists

    def assert_created_project_statistics(self, stats):
        statistics_exists = self.project_statistics_exists()
        self.assertTrue(statistics_exists)
        self.assertEqual(stats.project, self.project)
        self.assertEqual(stats.total_submissions, 3)
        self.assertEqual(stats.min_project_score, 10)
        self.assertEqual(stats.max_project_score, 12)
        self.assertEqual(stats.avg_project_score, 11.0)

    def force_update_submission_data(self):
        submissions_data = []
        for _index in range(3):
            scores = {
                "project_score": 10,
                "total_score": 20,
                "time_spent": 10.5,
            }
            submissions_data.append(scores)
        return submissions_data


class ProjectStatisticsModelAssertionsMixin:
    def assert_statistics_values(self, stats):
        min_project_score = stats.get_value("project_score", "min")
        self.assertEqual(min_project_score, 10)
        max_project_score = stats.get_value("project_score", "max")
        self.assertEqual(max_project_score, 12)
        avg_total_score = stats.get_value("total_score", "avg")
        self.assertEqual(avg_total_score, 21.0)

    def assert_stat_fields_shape(self, stats):
        stat_fields = stats.get_stat_fields()
        self.assertIsInstance(stat_fields, list)
        self.assertTrue(len(stat_fields) > 0)

        first_field = stat_fields[0]
        self.assertIsInstance(first_field, tuple)
        self.assertEqual(len(first_field), 3)

        field_name = first_field[0]
        field_stats = first_field[1]
        field_icon = first_field[2]
        self.assertIsInstance(field_name, str)
        self.assertIsInstance(field_stats, list)
        self.assertIsInstance(field_icon, str)

        if field_stats:
            stat_item = field_stats[0]
            self.assertEqual(len(stat_item), 3)

    def assert_statistics_string_includes_project(self, stats):
        str_representation = str(stats)
        self.assertIn(self.project.slug, str_representation)


class ProjectStatisticsRawFixtureMixin:
    def create_basic_raw_statistics_submissions(self):
        submissions_data = [
            {"project_score": 8, "total_score": 15, "time_spent": 8.0},
            {"project_score": 12, "total_score": 20, "time_spent": 12.0},
            {"project_score": 10, "total_score": 18, "time_spent": 10.0},
        ]
        self.create_bulk_submissions(submissions_data)

    def assert_raw_stat(self, data: RawStatExpectation):
        self.assertEqual(data.stats[data.field]["min"], data.minimum)
        self.assertEqual(data.stats[data.field]["max"], data.maximum)
        self.assertEqual(data.stats[data.field]["avg"], data.average)

    def assert_basic_project_score_stats(self, stats):
        expectation = RawStatExpectation(
            stats=stats,
            field="project_score",
            minimum=8,
            maximum=12,
            average=10.0,
        )
        self.assert_raw_stat(expectation)

    def assert_basic_total_score_stats(self, stats):
        expectation = RawStatExpectation(
            stats=stats,
            field="total_score",
            minimum=15,
            maximum=20,
            average=17.666666666666668,
        )
        self.assert_raw_stat(expectation)

    def assert_basic_time_spent_stats(self, stats):
        expectation = RawStatExpectation(
            stats=stats,
            field="time_spent",
            minimum=8.0,
            maximum=12.0,
            average=10.0,
        )
        self.assert_raw_stat(expectation)

    def create_null_time_spent_submissions(self):
        submissions_data = [
            {"project_score": 8, "total_score": 15, "time_spent": None},
            {
                "project_score": 12,
                "total_score": 20,
                "time_spent": 12.0,
            },
            {
                "project_score": 10,
                "total_score": 18,
                "time_spent": 10.0,
            },
            {"project_score": 9, "total_score": 16, "time_spent": 8.0},
        ]

        for i, scores in enumerate(submissions_data):
            self.create_project_submission(
                self.users[i], self.enrollments[i], scores
            )


class ProjectStatisticsRawAssertionsMixin:
    def assert_non_null_time_spent_stats(self, stats):
        self.assertEqual(stats["time_spent"]["min"], 8.0)
        self.assertEqual(stats["time_spent"]["max"], 12.0)
        self.assertEqual(stats["time_spent"]["avg"], 10.0)

    def assert_project_score_includes_null_time_rows(self, stats):
        self.assertEqual(stats["project_score"]["min"], 8)
        self.assertEqual(stats["project_score"]["max"], 12)


class ProjectStatisticsIncompleteProjectMixin:
    def create_incomplete_project(self):
        return Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )


class ProjectStatisticsTestBase(
    ProjectStatisticsFixtureMixin,
    ProjectStatisticsSubmissionFixtureMixin,
    ProjectStatisticsModelFixtureMixin,
    ProjectStatisticsModelAssertionsMixin,
    ProjectStatisticsRawFixtureMixin,
    ProjectStatisticsRawAssertionsMixin,
    ProjectStatisticsIncompleteProjectMixin,
    TestCase,
):
    def setUp(self):
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.project = self.create_completed_project()
        self.users = []
        self.enrollments = []
        self.create_student_enrollments()
