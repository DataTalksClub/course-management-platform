from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    Project,
    ProjectSubmission,
    Submission,
    User,
)


class LeaderboardTestBase(TestCase):
    def setUp(self):
        cache.clear()

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_student(self, name):
        student = User.objects.create_user(username=name)
        enrollment = Enrollment.objects.create(
            course=self.course,
            student=student,
        )
        return enrollment

    def create_homework(self, i):
        homework = Homework.objects.create(
            course=self.course,
            slug=f"test-homework-{i}",
            title=f"Test Homework {i}",
            due_date=timezone.now() - timedelta(hours=i),
        )
        return homework

    def create_project(self, i):
        project = Project.objects.create(
            course=self.course,
            slug=f"test-project-{i}",
            title=f"Test Project {i}",
            submission_due_date=timezone.now() - timedelta(hours=i),
            peer_review_due_date=timezone.now() - timedelta(hours=i),
        )
        return project

    def submit_homework(self, homework, enrollment, score):
        return Submission.objects.create(
            homework=homework,
            student=enrollment.student,
            enrollment=enrollment,
            total_score=score,
        )

    def create_homeworks(self, count):
        homeworks = []
        for index in range(1, count + 1):
            homework = self.create_homework(index)
            homeworks.append(homework)
        return homeworks

    def create_projects(self, count):
        projects = []
        for index in range(1, count + 1):
            project = self.create_project(index)
            projects.append(project)
        return projects

    def create_students(self, count):
        students = []
        for index in range(1, count + 1):
            student = self.create_student(f"s{index}")
            students.append(student)
        return students

    def create_homework_submissions(self, homeworks, enrollments):
        for homework in homeworks:
            score = 10
            for enrollment in enrollments:
                self.submit_homework(homework, enrollment, score=score)
                score = score + 10

    def create_project_submissions(self, projects, enrollments):
        for project in projects:
            score = 100
            for enrollment in enrollments:
                ProjectSubmission.objects.create(
                    project=project,
                    student=enrollment.student,
                    enrollment=enrollment,
                    total_score=score,
                )
                score = score - 10

    def create_leaderboard_fixture(self):
        homeworks = self.create_homeworks(4)
        projects = self.create_projects(2)
        enrollments = self.create_students(5)
        self.create_homework_submissions(homeworks, enrollments)
        self.create_project_submissions(projects, enrollments)
        return enrollments

    def assert_leaderboard_scores(self, enrollments):
        expected_scores = [
            (5, 240),
            (4, 260),
            (3, 280),
            (2, 300),
            (1, 320),
        ]
        for expected_score, enrollment in zip(expected_scores, enrollments):
            rank = expected_score[0]
            score = expected_score[1]
            enrollment.refresh_from_db()
            self.assertEqual(enrollment.position_on_leaderboard, rank)
            self.assertEqual(enrollment.total_score, score)

    def create_paginated_leaderboard(self, count):
        for i in range(1, count + 1):
            student = User.objects.create_user(username=f"student-{i:03d}")
            Enrollment.objects.create(
                course=self.course,
                student=student,
                display_name=f"Student {i:03d}",
                position_on_leaderboard=i,
                total_score=1000 - i,
            )

    def leaderboard_url(self):
        return reverse("leaderboard", kwargs={"course_slug": self.course.slug})

    def assert_first_leaderboard_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["enrollments"]), 100)
        self.assertContains(response, "Student 001")
        self.assertNotContains(response, "Student 101")
        self.assertNotContains(response, "Showing 1-100 of 105")
        self.assertContains(response, 'href="?page=2"')
        self.assertContains(response, 'aria-label="Next page"')
        self.assertNotContains(response, "First")
        self.assertNotContains(response, "Last")
        self.assertContains(response, "Leaderboard data (YAML)")

    def assert_second_leaderboard_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["enrollments"]), 5)
        self.assertContains(response, "Student 101")
        self.assertNotContains(response, "Student 001")
        self.assertNotContains(response, "Showing 101-105 of 105")
        self.assertNotContains(response, 'href="?page=3"')

    def create_leaderboard_with_target_student(self, target_index, count):
        target_user = None
        target_enrollment = None

        for i in range(1, count + 1):
            student = User.objects.create_user(username=f"student-{i:03d}")
            enrollment = Enrollment.objects.create(
                course=self.course,
                student=student,
                display_name=f"Student {i:03d}",
                position_on_leaderboard=i,
                total_score=1000 - i,
            )
            if i == target_index:
                target_user = student
                target_enrollment = enrollment

        return target_user, target_enrollment

    def assert_current_student_page_link(self, response, target_enrollment):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_student_page_number"], 2)
        self.assertContains(
            response,
            f'?page=2#record-{target_enrollment.id}',
        )

    def score_breakdown_url(self, enrollment):
        return reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": enrollment.id,
            },
        )

    def admin_enrollment_edit_url(self, enrollment):
        return reverse(
            "cadmin_enrollment_edit",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": enrollment.id,
            },
        )
