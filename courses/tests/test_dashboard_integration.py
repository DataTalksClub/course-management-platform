from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Project,
    ProjectState,
    ProjectSubmission,
    Submission,
)

User = get_user_model()

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class DashboardIntegrationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=70,
            first_homework_scored=True,
        )
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

    def dashboard_url(self):
        return reverse("dashboard", args=[self.course.slug])

    def create_student_enrollments(self):
        users = []
        enrollments = []
        for index in range(4):
            user = User.objects.create_user(
                username=f"student{index}@test.com",
                email=f"student{index}@test.com",
                password="12345",
            )
            enrollment = Enrollment.objects.create(
                student=user,
                course=self.course,
                total_score=80 + index * 10,
            )
            users.append(user)
            enrollments.append(enrollment)
        return users, enrollments

    def create_homework_submissions(self, users, enrollments):
        for index, user_enrollment in enumerate(zip(users, enrollments)):
            user = user_enrollment[0]
            enrollment = user_enrollment[1]
            Submission.objects.create(
                homework=self.homework1,
                student=user,
                enrollment=enrollment,
                time_spent_lectures=2.0 + index,
                time_spent_homework=3.0 + index,
                total_score=80 + index * 5,
            )
            if index < 3:
                Submission.objects.create(
                    homework=self.homework2,
                    student=user,
                    enrollment=enrollment,
                    time_spent_lectures=1.5 + index,
                    time_spent_homework=2.5 + index,
                    total_score=75 + index * 5,
                )

    def create_project_submissions(self, users, enrollments):
        first_users = users[:3]
        first_enrollments = enrollments[:3]
        for index, user_enrollment in enumerate(
            zip(first_users, first_enrollments)
        ):
            user = user_enrollment[0]
            enrollment = user_enrollment[1]
            total_score = 70 + index * 10
            ProjectSubmission.objects.create(
                project=self.project,
                student=user,
                enrollment=enrollment,
                github_link=f"https://github.com/user{index}/project",
                total_score=total_score,
                time_spent=8.0 + index * 2,
                passed=total_score >= 70,
            )

    def create_complete_dashboard_fixture(self):
        users, enrollments = self.create_student_enrollments()
        self.create_homework_submissions(users, enrollments)
        self.create_project_submissions(users, enrollments)

    def homework_stats_by_homework(self, response):
        stats_by_homework = {}
        homework_stats = response.context["homework_stats"]
        for stat in homework_stats:
            homework = stat["homework"]
            stats_by_homework[homework] = stat
        return stats_by_homework

    def assert_complete_dashboard_counts(self, response):
        self.assertEqual(response.context["total_enrollments"], 4)
        self.assertEqual(len(response.context["homework_stats"]), 2)
        self.assertEqual(response.context["project_pass_count"], 3)
        self.assertEqual(response.context["project_fail_count"], 0)

    def assert_complete_homework_stats(self, response):
        homework_stats = self.homework_stats_by_homework(response)
        self.assertEqual(
            homework_stats[self.homework1]["submissions_count"],
            4,
        )
        self.assertEqual(
            homework_stats[self.homework2]["submissions_count"],
            3,
        )

    def assert_complete_dashboard_content(self, response):
        self.assertContains(response, "Test Course Dashboard")
        self.assertContains(response, "Homework 1")
        self.assertContains(response, "Homework 2")
        self.assertContains(response, "View Leaderboard")
        self.assertContains(response, "View All Project Submissions")

    def test_dashboard_with_complete_course_data(self):
        self.create_complete_dashboard_fixture()
        url = self.dashboard_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_complete_dashboard_counts(response)
        self.assert_complete_homework_stats(response)
        self.assert_complete_dashboard_content(response)
