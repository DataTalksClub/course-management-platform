from dataclasses import dataclass
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectStatistics,
    Enrollment,
    ProjectState,
)

from courses.assignment_statistics import (
    calculate_raw_project_statistics,
    calculate_project_statistics,
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


class ProjectStatisticsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.project = self.create_completed_project()
        self.users = []
        self.enrollments = []
        self.create_student_enrollments()

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

    def create_project_submission(self, user, enrollment, scores=None):
        """Helper to create a project submission with optional scores"""
        if scores is None:
            scores = {
                "project_score": 10,
                "project_learning_in_public_score": 5,
                "peer_review_score": 3,
                "peer_review_learning_in_public_score": 2,
                "total_score": 20,
                "time_spent": 10.5,
            }

        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            **scores,
        )
        return submission

    def create_bulk_submissions(self, submissions_data):
        """Bulk create submissions for better performance"""
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

    def create_basic_raw_statistics_submissions(self):
        self.create_bulk_submissions(
            [
                {"project_score": 8, "total_score": 15, "time_spent": 8.0},
                {"project_score": 12, "total_score": 20, "time_spent": 12.0},
                {"project_score": 10, "total_score": 18, "time_spent": 10.0},
            ]
        )

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

    def test_calculate_raw_project_statistics_basic(self):
        """Test basic raw statistics calculation"""
        self.create_basic_raw_statistics_submissions()

        stats = calculate_raw_project_statistics(self.project)

        self.assertEqual(stats["total_submissions"], 3)
        self.assert_basic_project_score_stats(stats)
        self.assert_basic_total_score_stats(stats)
        self.assert_basic_time_spent_stats(stats)

    def test_calculate_raw_project_statistics_insufficient_data(self):
        """Test statistics calculation with insufficient data (< 3 submissions)"""
        # Create only 2 submissions
        for i in range(2):
            self.create_project_submission(
                self.users[i], self.enrollments[i]
            )

        stats = calculate_raw_project_statistics(self.project)

        # Should have total_submissions but null stats for insufficient data
        self.assertEqual(stats["total_submissions"], 2)

        # All score fields should have None values
        score_fields = ["project_score", "total_score", "time_spent"]
        for field in score_fields:
            self.assertIsNone(stats[field]["min"])
            self.assertIsNone(stats[field]["max"])
            self.assertIsNone(stats[field]["avg"])
            self.assertIsNone(stats[field]["q1"])
            self.assertIsNone(stats[field]["median"])
            self.assertIsNone(stats[field]["q3"])

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

    def assert_non_null_time_spent_stats(self, stats):
        self.assertEqual(stats["time_spent"]["min"], 8.0)
        self.assertEqual(stats["time_spent"]["max"], 12.0)
        self.assertEqual(stats["time_spent"]["avg"], 10.0)

    def assert_project_score_includes_null_time_rows(self, stats):
        self.assertEqual(stats["project_score"]["min"], 8)
        self.assertEqual(stats["project_score"]["max"], 12)

    def test_calculate_raw_project_statistics_with_nulls(self):
        """Test statistics calculation with some null values"""
        self.create_null_time_spent_submissions()

        stats = calculate_raw_project_statistics(self.project)

        self.assert_non_null_time_spent_stats(stats)
        self.assert_project_score_includes_null_time_rows(stats)

    def test_calculate_project_statistics_model_creation(self):
        """Test that calculate_project_statistics creates a ProjectStatistics object"""
        self.create_model_method_submissions()
        statistics_exists = self.project_statistics_exists()
        self.assertFalse(statistics_exists)

        stats = calculate_project_statistics(self.project)

        self.assert_created_project_statistics(stats)

    def test_calculate_project_statistics_force_update(self):
        """Test that force=True updates existing statistics"""
        submissions_data = self.force_update_submission_data()
        self.create_bulk_submissions(submissions_data)
        stats1 = calculate_project_statistics(self.project)
        initial_count = stats1.total_submissions

        self.create_project_submission(
            self.users[3], self.enrollments[3]
        )

        stats2 = calculate_project_statistics(self.project, force=False)
        self.assertEqual(stats2.total_submissions, initial_count)

        stats3 = calculate_project_statistics(self.project, force=True)
        self.assertEqual(stats3.total_submissions, initial_count + 1)

    def test_calculate_project_statistics_uncompleted_project(self):
        """Test that statistics calculation fails for uncompleted projects"""
        # Create a project that's not completed
        incomplete_project = Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        with self.assertRaises(ValueError) as context:
            calculate_project_statistics(incomplete_project)

        self.assertIn(
            "Cannot calculate statistics for uncompleted project",
            str(context.exception),
        )

    def test_project_statistics_model_methods(self):
        """Test ProjectStatistics model methods"""
        self.create_model_method_submissions()
        stats = calculate_project_statistics(self.project)

        self.assert_statistics_values(stats)
        self.assert_stat_fields_shape(stats)
        self.assert_statistics_string_includes_project(stats)
