from datetime import timedelta
from dataclasses import dataclass, field

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import CustomUser
from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    Submission,
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


class DashboardViewTestCase(TestCase):
    @classmethod
    def create_dashboard_user(cls):
        cls.user = User.objects.create_user(**credentials)

    @classmethod
    def create_dashboard_course(cls):
        cls.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Description",
            project_passing_score=70,
            first_homework_scored=True,
        )

    @classmethod
    def create_statistic_users(cls):
        user_data = []
        for i in range(5):
            user = User(
                username=f"user{i}@test.com",
                email=f"user{i}@test.com",
                password="12345",
            )
            user_data.append(user)

        cls.users = User.objects.bulk_create(user_data)

    @classmethod
    def create_statistic_enrollments(cls):
        enrollment_data = []
        for i, user in enumerate(cls.users):
            enrollment = Enrollment(
                student=user,
                course=cls.course,
                total_score=100 + i * 20,
            )
            enrollment_data.append(enrollment)

        cls.enrollments = Enrollment.objects.bulk_create(
            enrollment_data
        )

    @classmethod
    def create_primary_enrollment(cls):
        cls.enrollment = Enrollment.objects.create(
            student=cls.user, course=cls.course, total_score=150
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.create_dashboard_user()
        cls.create_dashboard_course()
        cls.create_statistic_users()
        cls.create_statistic_enrollments()
        cls.create_primary_enrollment()

    def setUp(self):
        self.client = Client()

    def test_dashboard_url_exists(self):
        """Test that dashboard URL exists and is accessible"""
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_uses_correct_template(self):
        """Test that dashboard uses the correct template"""
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)
        self.assertTemplateUsed(response, "courses/dashboard.html")

    def test_dashboard_context_basic(self):
        """Test basic context variables in dashboard"""
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertIn("course", response.context)
        self.assertIn("total_enrollments", response.context)
        self.assertIn("homework_stats", response.context)
        self.assertIn("homework_difficulty_stats", response.context)
        self.assertIn("project_passing_score", response.context)

        self.assertEqual(response.context["course"], self.course)
        self.assertEqual(
            response.context["total_enrollments"], 6
        )  # 1 main user + 5 additional
        self.assertEqual(response.context["project_passing_score"], 70)

    def test_dashboard_with_invalid_course(self):
        """Test dashboard with non-existent course returns 404"""
        url = reverse("dashboard", args=["non-existent-course"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_dashboard_with_no_enrollments(self):
        """Test dashboard with course that has no enrollments"""
        # Create course with no enrollments
        empty_course = Course.objects.create(
            slug="empty-course",
            title="Empty Course",
            first_homework_scored=True,
        )

        url = reverse("dashboard", args=[empty_course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_enrollments"], 0)


class DashboardHomeworkStatsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            first_homework_scored=True,
        )

        # Create homework
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

        # Create multiple users and submissions for statistics
        self.users = []
        self.enrollments = []
        for i in range(5):
            user_creds = {
                "username": f"user{i}@test.com",
                "email": f"user{i}@test.com",
                "password": "12345",
            }
            user = User.objects.create_user(**user_creds)
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            self.users.append(user)
            self.enrollments.append(enrollment)

    def create_homework_submission(self, user, enrollment, scores=None):
        """Helper method to create homework submissions with test data"""
        if scores is None:
            scores = {
                "time_spent_lectures": 2.0,
                "time_spent_homework": 3.0,
                "total_score": 85,
            }

        return Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
            **scores,
        )

    def homework_submission_stats_data(self):
        return [
            {
                "time_spent_lectures": 1.0,
                "time_spent_homework": 2.0,
                "total_score": 80,
            },
            {
                "time_spent_lectures": 2.0,
                "time_spent_homework": 3.0,
                "total_score": 85,
            },
            {
                "time_spent_lectures": 3.0,
                "time_spent_homework": 4.0,
                "total_score": 90,
            },
            {
                "time_spent_lectures": 4.0,
                "time_spent_homework": 5.0,
                "total_score": 95,
            },
            {
                "time_spent_lectures": 5.0,
                "time_spent_homework": 6.0,
                "total_score": 100,
            },
        ]

    def create_homework_stat_submissions(self):
        submission_stats = self.homework_submission_stats_data()
        for index, data in enumerate(submission_stats):
            self.create_homework_submission(
                self.users[index],
                self.enrollments[index],
                data,
            )

    def null_time_submission_stats_data(self):
        return [
            {
                "time_spent_lectures": 2.0,
                "time_spent_homework": 3.0,
                "total_score": 85,
            },
            {
                "time_spent_lectures": None,
                "time_spent_homework": 4.0,
                "total_score": 90,
            },
            {
                "time_spent_lectures": 3.0,
                "time_spent_homework": None,
                "total_score": 80,
            },
            {
                "time_spent_lectures": 4.0,
                "time_spent_homework": 5.0,
                "total_score": 95,
            },
        ]

    def create_null_time_submissions(self):
        submission_stats = self.null_time_submission_stats_data()
        for index, data in enumerate(submission_stats):
            self.create_homework_submission(
                self.users[index],
                self.enrollments[index],
                data,
            )

    def assert_homework_stat_summary(self, hw_stat):
        self.assertEqual(hw_stat["homework"], self.homework)
        self.assertEqual(hw_stat["submissions_count"], 5)
        self.assertEqual(hw_stat["completion_rate"], 100.0)
        self.assertEqual(hw_stat["time_lecture_median"], 3.0)
        self.assertEqual(hw_stat["time_homework_median"], 4.0)
        self.assertEqual(hw_stat["time_total_median"], 7.0)
        self.assertEqual(hw_stat["score_median"], 90)

    def assert_null_time_homework_stats(self, hw_stat):
        self.assertEqual(hw_stat["submissions_count"], 4)
        self.assertIsNotNone(hw_stat["time_lecture_median"])

    def test_homework_statistics_calculation(self):
        """Test homework statistics calculation with various data"""
        self.create_homework_stat_submissions()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        hw_stats = response.context["homework_stats"]
        self.assertEqual(len(hw_stats), 1)

        self.assert_homework_stat_summary(hw_stats[0])

    def test_homework_statistics_with_insufficient_data(self):
        """Test homework statistics with insufficient data for quartiles"""
        # Create only 2 submissions (less than 3 required for quartiles)
        for i in range(2):
            self.create_homework_submission(
                self.users[i], self.enrollments[i]
            )

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        hw_stats = response.context["homework_stats"]
        hw_stat = hw_stats[0]

        # Should have None values for quartiles when insufficient data
        self.assertIsNone(hw_stat["time_lecture_q25"])
        self.assertIsNone(hw_stat["time_lecture_median"])
        self.assertIsNone(hw_stat["time_lecture_q75"])
        self.assertEqual(hw_stat["completion_rate"], 40.0)

    def _add_questions(self, homework, count):
        """Create `count` 1-point questions for a homework."""
        questions = []
        for i in range(count):
            question = Question(
                homework=homework,
                text=f"Q{i}",
                question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                scores_for_correct_answer=1,
            )
            questions.append(question)
        Question.objects.bulk_create(questions)

    def create_homework_for_difficulty(self, slug, title, days_until_due):
        homework = Homework.objects.create(
            course=self.course,
            slug=slug,
            title=title,
            due_date=timezone.now() + timedelta(days=days_until_due),
            state=HomeworkState.OPEN.value,
        )
        return homework

    def create_difficulty_submissions(self, harder_homework):
        for user, enrollment in zip(self.users, self.enrollments):
            Submission.objects.create(
                homework=self.homework,
                student=user,
                enrollment=enrollment,
                time_spent_lectures=2.0,
                time_spent_homework=3.0,
                questions_score=3,
                total_score=3,
            )
            Submission.objects.create(
                homework=harder_homework,
                student=user,
                enrollment=enrollment,
                time_spent_lectures=2.0,
                time_spent_homework=3.0,
                questions_score=5,
                total_score=12,
            )

    def assert_difficulty_ranking(self, response, harder_homework):
        difficulty_stats = response.context["homework_difficulty_stats"]
        self.assertEqual(difficulty_stats[0]["homework"], harder_homework)
        self.assertEqual(difficulty_stats[0]["difficulty_rank"], 1)
        self.assertEqual(difficulty_stats[0]["score_ratio_pct"], 50.0)
        self.assertEqual(difficulty_stats[0]["max_questions_score"], 10)
        self.assertEqual(difficulty_stats[1]["homework"], self.homework)
        self.assertEqual(difficulty_stats[1]["difficulty_rank"], 2)
        self.assertEqual(difficulty_stats[1]["score_ratio_pct"], 100.0)

    def test_homework_difficulty_ranking(self):
        """Difficulty is ranked by the question score normalized by question count.

        A short homework with a high raw median is not "harder" than a long
        homework with a lower per-question score, so ranking must use the ratio
        of the median question score to the max achievable.
        """
        self._add_questions(self.homework, 3)
        harder_homework = self.create_homework_for_difficulty(
            "hw2",
            "Homework 2",
            14,
        )
        self._add_questions(harder_homework, 10)
        self.create_difficulty_submissions(harder_homework)

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assert_difficulty_ranking(response, harder_homework)
        self.assertContains(response, "Assignment difficulty")
        self.assertContains(response, "Completion")

    def test_homework_statistics_with_null_values(self):
        """Test homework statistics with some null time values"""
        self.create_null_time_submissions()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assert_null_time_homework_stats(
            response.context["homework_stats"][0]
        )

    def test_homework_formatted_time_display(self):
        """Test that time formatting works correctly"""
        # Create submission with whole number time
        self.create_homework_submission(
            self.users[0],
            self.enrollments[0],
            {
                "time_spent_lectures": 3.0,
                "time_spent_homework": 4.0,
                "total_score": 85,
            },
        )

        # Create more submissions for quartile calculation
        for i in range(1, 4):
            self.create_homework_submission(
                self.users[i],
                self.enrollments[i],
                {
                    "time_spent_lectures": 3.0 + i,
                    "time_spent_homework": 4.0 + i,
                    "total_score": 85 + i,
                },
            )

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        hw_stats = response.context["homework_stats"]
        hw_stat = hw_stats[0]

        # Check formatted values exist
        self.assertIn("time_lecture_median_formatted", hw_stat)
        self.assertIn("time_homework_median_formatted", hw_stat)
        self.assertIn("time_total_median_formatted", hw_stat)


class DashboardProjectStatsTestCase(TestCase):
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
        cls.project = Project.objects.create(
            course=cls.course,
            slug="project1",
            title="Project 1",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COMPLETED.value,
        )

    @classmethod
    def create_project_users(cls):
        user_data = []
        for i in range(6):
            user = User(
                username=f"user{i}@test.com",
                email=f"user{i}@test.com",
                password="12345",
            )
            user_data.append(user)

        cls.users = User.objects.bulk_create(user_data)

    @classmethod
    def create_project_enrollments(cls):
        enrollment_data = []
        users = cls.users
        for user in users:
            enrollment = Enrollment(student=user, course=cls.course)
            enrollment_data.append(enrollment)

        cls.enrollments = Enrollment.objects.bulk_create(
            enrollment_data
        )

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

    def create_project_submission(self, data: ProjectSubmissionFixtureData):
        """Helper method to create project submissions"""
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
        """Helper method to create project submissions in bulk"""
        submissions = []
        for i, data in enumerate(submission_data):
            passed = data.pop("passed", True)
            submission = ProjectSubmission(
                project=self.project,
                student=self.users[i],
                enrollment=self.enrollments[i],
                github_link=f"https://github.com/user{i}/repo",
                passed=passed,
                **data,
            )
            submissions.append(submission)
        return ProjectSubmission.objects.bulk_create(submissions)

    def test_project_statistics_calculation(self):
        """Test project statistics with various scores and pass/fail"""
        # Create mix of passing and failing submissions using bulk operations
        submission_data = [
            {"total_score": 90, "time_spent": 8.0, "passed": True},
            {"total_score": 85, "time_spent": 10.0, "passed": True},
            {"total_score": 75, "time_spent": 12.0, "passed": True},
            {"total_score": 60, "time_spent": 6.0, "passed": False},
            {"total_score": 55, "time_spent": 5.0, "passed": False},
        ]

        self.create_bulk_project_submissions(submission_data)

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check pass/fail counts
        self.assertEqual(response.context["project_pass_count"], 3)
        self.assertEqual(response.context["project_fail_count"], 2)

        # Check completion rate (5 submissions out of 6 total enrollments)
        expected_completion = (5 / 6) * 100
        self.assertAlmostEqual(
            response.context["project_completion_rate"],
            expected_completion,
            places=1,
        )

        # Check quartile calculations
        self.assertIsNotNone(response.context["project_score_median"])
        self.assertIsNotNone(response.context["project_time_median"])

    def create_completed_second_project(self):
        project = Project.objects.create(
            course=self.course,
            slug="project2",
            title="Project 2",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COMPLETED.value,
        )
        return project

    def create_overlapping_project_submissions(self, project):
        for i in range(3):
            submission_data = ProjectSubmissionFixtureData(
                user=self.users[i],
                enrollment=self.enrollments[i],
            )
            self.create_project_submission(submission_data)
        for i in range(2):
            ProjectSubmission.objects.create(
                project=project,
                student=self.users[i],
                enrollment=self.enrollments[i],
                github_link="https://github.com/test/repo2",
                passed=True,
                total_score=80,
                time_spent=10.0,
            )

    def assert_distinct_student_completion_rate(self, response):
        self.assertAlmostEqual(
            response.context["project_completion_rate"],
            (3 / 6) * 100,
            places=1,
        )

    def test_completion_rate_with_multiple_projects(self):
        """Completion rate counts distinct students, not enrollments x projects."""
        project = self.create_completed_second_project()
        self.create_overlapping_project_submissions(project)

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assert_distinct_student_completion_rate(response)

    def test_project_statistics_with_no_submissions(self):
        """Test project statistics when no submissions exist"""
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.context["project_pass_count"], 0)
        self.assertEqual(response.context["project_fail_count"], 0)
        self.assertEqual(
            response.context["project_completion_rate"], 0.0
        )

        # Should have None values for quartiles
        self.assertIsNone(response.context["project_score_q25"])
        self.assertIsNone(response.context["project_time_q25"])

    def test_avg_total_score_calculation(self):
        """Test average total score calculation from enrollments"""
        # Set specific total scores for enrollments
        for i, enrollment in enumerate(self.enrollments):
            enrollment.total_score = 100 + i * 10
            enrollment.save()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        # Should calculate average of enrollment total scores
        expected_avg = (100 + 110 + 120 + 130 + 140 + 150) / 6
        self.assertAlmostEqual(
            response.context["avg_total_score"], expected_avg, places=1
        )

    def test_project_total_submissions(self):
        """Test that project_total_submissions is calculated correctly"""
        # Create mix of passing and failing submissions
        submission_data = [
            {"total_score": 90, "time_spent": 8.0, "passed": True},
            {"total_score": 85, "time_spent": 10.0, "passed": True},
            {"total_score": 75, "time_spent": 12.0, "passed": True},
            {"total_score": 60, "time_spent": 6.0, "passed": False},
            {"total_score": 55, "time_spent": 5.0, "passed": False},
        ]

        self.create_bulk_project_submissions(submission_data)

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertIn("project_total_submissions", response.context)
        self.assertIn("project_pass_count", response.context)
        self.assertIn("project_fail_count", response.context)

        # 3 passed + 2 failed = 5 total
        self.assertEqual(response.context["project_pass_count"], 3)
        self.assertEqual(response.context["project_fail_count"], 2)
        self.assertEqual(response.context["project_total_submissions"], 5)

    def test_graduates_count(self):
        """Test that graduates_count is calculated correctly"""
        # Add certificate URLs to some enrollments
        first_enrollments = self.enrollments[:3]
        for i, enrollment in enumerate(first_enrollments):
            enrollment.certificate_url = f"https://example.com/cert{i}.pdf"
            enrollment.save()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertIn("graduates_count", response.context)
        self.assertEqual(response.context["graduates_count"], 3)

    def test_graduates_count_excludes_empty_certificates(self):
        """Test that graduates_count excludes enrollments with empty certificate URLs"""
        # Add certificate URLs to some enrollments
        self.enrollments[0].certificate_url = "https://example.com/cert1.pdf"
        self.enrollments[0].save()

        # Add empty certificate URL (should not count)
        self.enrollments[1].certificate_url = ""
        self.enrollments[1].save()

        # Leave others as None (should not count)
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertIn("graduates_count", response.context)
        self.assertEqual(response.context["graduates_count"], 1)
