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


class DashboardViewTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(**credentials)
        cls.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Description",
            project_passing_score=70,
        )

        # Create additional users for statistics using bulk operations
        user_data = []
        for i in range(5):
            user_data.append(
                User(
                    username=f"user{i}@test.com",
                    email=f"user{i}@test.com",
                    password="12345",
                )
            )

        cls.users = User.objects.bulk_create(user_data)

        # Create enrollments in bulk
        enrollment_data = []
        for i, user in enumerate(cls.users):
            enrollment_data.append(
                Enrollment(
                    student=user,
                    course=cls.course,
                    total_score=100 + i * 20,
                )
            )

        cls.enrollments = Enrollment.objects.bulk_create(
            enrollment_data
        )

        # Create main enrollment
        cls.enrollment = Enrollment.objects.create(
            student=cls.user, course=cls.course, total_score=150
        )

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
            slug="empty-course", title="Empty Course"
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
            slug="test-course", title="Test Course"
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

    def test_homework_statistics_calculation(self):
        """Test homework statistics calculation with various data"""
        # Create submissions with different time/score values
        submission_data = [
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

        for i, data in enumerate(submission_data):
            self.create_homework_submission(
                self.users[i], self.enrollments[i], data
            )

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        hw_stats = response.context["homework_stats"]
        self.assertEqual(len(hw_stats), 1)

        hw_stat = hw_stats[0]
        self.assertEqual(hw_stat["homework"], self.homework)
        self.assertEqual(hw_stat["submissions_count"], 5)

        # Check quartile calculations (median should be middle value)
        self.assertEqual(hw_stat["time_lecture_median"], 3.0)
        self.assertEqual(hw_stat["time_homework_median"], 4.0)
        self.assertEqual(hw_stat["time_total_median"], 7.0)  # 3.0 + 4.0
        self.assertEqual(hw_stat["score_median"], 90)

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

    def test_homework_statistics_with_null_values(self):
        """Test homework statistics with some null time values"""
        # Create submissions with mixed null/non-null values
        submission_data = [
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

        for i, data in enumerate(submission_data):
            self.create_homework_submission(
                self.users[i], self.enrollments[i], data
            )

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        hw_stats = response.context["homework_stats"]
        hw_stat = hw_stats[0]

        # Should handle null values gracefully
        self.assertEqual(hw_stat["submissions_count"], 4)
        # Only 3 non-null lecture time values, so should calculate quartiles
        self.assertIsNotNone(hw_stat["time_lecture_median"])

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
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(**credentials)
        cls.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=70,
        )

        cls.project = Project.objects.create(
            course=cls.course,
            slug="project1",
            title="Project 1",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COMPLETED.value,
        )

        # Create users for project submissions using bulk operations
        user_data = []
        for i in range(6):
            user_data.append(
                User(
                    username=f"user{i}@test.com",
                    email=f"user{i}@test.com",
                    password="12345",
                )
            )

        cls.users = User.objects.bulk_create(user_data)

        # Create enrollments in bulk
        enrollment_data = []
        for user in cls.users:
            enrollment_data.append(
                Enrollment(student=user, course=cls.course)
            )

        cls.enrollments = Enrollment.objects.bulk_create(
            enrollment_data
        )

    def setUp(self):
        self.client = Client()

    def create_project_submission(
        self, user, enrollment, scores=None, passed=True
    ):
        """Helper method to create project submissions"""
        if scores is None:
            scores = {"total_score": 80, "time_spent": 10.0}

        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            passed=passed,
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
        for i, enrollment in enumerate(self.enrollments[:3]):
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


class DashboardIntegrationTestCase(TestCase):
    """Integration tests for dashboard with complete data"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=70,
        )

        # Create multiple homeworks and projects
        self.homework1 = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.SCORED.value,
        )

        self.homework2 = Homework.objects.create(
            course=self.course,
            slug="hw2",
            title="Homework 2",
            due_date=timezone.now() + timedelta(days=14),
            state=HomeworkState.OPEN.value,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="project1",
            title="Project 1",
            submission_due_date=timezone.now() + timedelta(days=21),
            peer_review_due_date=timezone.now() + timedelta(days=28),
            state=ProjectState.COMPLETED.value,
        )

    def test_dashboard_with_complete_course_data(self):
        """Test dashboard with a complete course setup"""
        # Create users and enrollments
        users = []
        enrollments = []
        for i in range(4):
            user = User.objects.create_user(
                username=f"student{i}@test.com",
                email=f"student{i}@test.com",
                password="12345",
            )
            enrollment = Enrollment.objects.create(
                student=user,
                course=self.course,
                total_score=80 + i * 10,
            )
            users.append(user)
            enrollments.append(enrollment)

        # Create homework submissions
        for i, (user, enrollment) in enumerate(zip(users, enrollments)):
            # Homework 1 submissions
            Submission.objects.create(
                homework=self.homework1,
                student=user,
                enrollment=enrollment,
                time_spent_lectures=2.0 + i,
                time_spent_homework=3.0 + i,
                total_score=80 + i * 5,
            )

            # Some homework 2 submissions (not all students)
            if i < 3:
                Submission.objects.create(
                    homework=self.homework2,
                    student=user,
                    enrollment=enrollment,
                    time_spent_lectures=1.5 + i,
                    time_spent_homework=2.5 + i,
                    total_score=75 + i * 5,
                )

        # Create project submissions
        for i, (user, enrollment) in enumerate(
            zip(users[:3], enrollments[:3])
        ):
            ProjectSubmission.objects.create(
                project=self.project,
                student=user,
                enrollment=enrollment,
                github_link=f"https://github.com/user{i}/project",
                total_score=70 + i * 10,
                time_spent=8.0 + i * 2,
                passed=True if (70 + i * 10) >= 70 else False,
            )

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check basic counts
        self.assertEqual(response.context["total_enrollments"], 4)

        # Check homework stats
        hw_stats = response.context["homework_stats"]
        self.assertEqual(len(hw_stats), 2)  # Two homeworks created

        # Verify homework data
        hw1_stats = next(
            stat
            for stat in hw_stats
            if stat["homework"] == self.homework1
        )
        hw2_stats = next(
            stat
            for stat in hw_stats
            if stat["homework"] == self.homework2
        )

        self.assertEqual(hw1_stats["submissions_count"], 4)
        self.assertEqual(hw2_stats["submissions_count"], 3)

        # Check project stats
        self.assertEqual(response.context["project_pass_count"], 3)
        self.assertEqual(response.context["project_fail_count"], 0)

        # Verify template renders correctly
        self.assertContains(response, "Test Course Dashboard")
        self.assertContains(response, "Homework 1")
        self.assertContains(response, "Homework 2")
        self.assertContains(response, "View Leaderboard")
        self.assertContains(response, "View All Project Submissions")


class DashboardAuthenticationTestCase(TestCase):
    """Test dashboard access with different authentication states"""

    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            slug="test-course", title="Test Course"
        )

    def test_dashboard_access_without_login(self):
        """Test that dashboard is accessible without login (public access)"""
        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        # Dashboard should be accessible without authentication
        self.assertEqual(response.status_code, 200)

    def test_dashboard_access_with_login(self):
        """Test dashboard access with authenticated user"""
        user = User.objects.create_user(**credentials)
        self.client.login(**credentials)

        url = reverse("dashboard", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
