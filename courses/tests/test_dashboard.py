from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    Submission,
)

User = get_user_model()

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


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
        self.course = self.create_dashboard_course()
        self.homework = self.create_dashboard_homework()
        self.users = []
        self.enrollments = []
        self.create_dashboard_enrollments(5)

    def create_dashboard_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            first_homework_scored=True,
        )

    def create_dashboard_homework(self):
        return Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

    def create_dashboard_enrollments(self, count):
        for i in range(count):
            user = self.create_dashboard_stat_user(i)
            enrollment = self.create_dashboard_stat_enrollment(user)
            self.users.append(user)
            self.enrollments.append(enrollment)

    def create_dashboard_stat_user(self, index):
        user_creds = {
            "username": f"user{index}@test.com",
            "email": f"user{index}@test.com",
            "password": "12345",
        }
        return User.objects.create_user(**user_creds)

    def create_dashboard_stat_enrollment(self, user):
        return Enrollment.objects.create(
            student=user,
            course=self.course,
        )

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

    def create_formatted_time_submissions(self):
        scores = {
            "time_spent_lectures": 3.0,
            "time_spent_homework": 4.0,
            "total_score": 85,
        }
        self.create_homework_submission(
            self.users[0],
            self.enrollments[0],
            scores,
        )

        for index in range(1, 4):
            scores = {
                "time_spent_lectures": 3.0 + index,
                "time_spent_homework": 4.0 + index,
                "total_score": 85 + index,
            }
            self.create_homework_submission(
                self.users[index],
                self.enrollments[index],
                scores,
            )

    def assert_formatted_time_fields(self, hw_stat):
        self.assertIn("time_lecture_median_formatted", hw_stat)
        self.assertIn("time_homework_median_formatted", hw_stat)
        self.assertIn("time_total_median_formatted", hw_stat)

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
        self.create_formatted_time_submissions()

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        hw_stats = response.context["homework_stats"]
        hw_stat = hw_stats[0]

        self.assert_formatted_time_fields(hw_stat)
