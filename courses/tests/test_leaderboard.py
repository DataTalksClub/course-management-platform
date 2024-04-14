import logging

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    Course,
    Homework,
    Submission,
    User,
    Enrollment,
    Project,
    ProjectSubmission,
)


logger = logging.getLogger(__name__)


from courses.scoring import update_leaderboard


class LeaderboardTestCase(TestCase):
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

    def setUp(self):
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def test_leaderboard(self):
        homework1 = self.create_homework(1)
        homework2 = self.create_homework(2)
        homework3 = self.create_homework(3)
        homework4 = self.create_homework(4)

        homeworks = [homework1, homework2, homework3, homework4]

        project1 = self.create_project(1)
        project2 = self.create_project(2)

        projects = [project1, project2]

        enrollment1 = self.create_student("s1")
        enrollment2 = self.create_student("s2")
        enrollment3 = self.create_student("s3")
        enrollment4 = self.create_student("s4")
        enrollment5 = self.create_student("s5")

        enrollments = [
            enrollment1,
            enrollment2,
            enrollment3,
            enrollment4,
            enrollment5,
        ]

        for homework in homeworks:
            score = 10
            for enrollment in enrollments:
                self.submit_homework(homework, enrollment, score=score)
                score = score + 10

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

        update_leaderboard(self.course)

        expected_scores = [
            (5, 240),
            (4, 260),
            (3, 280),
            (2, 300),
            (1, 320),
        ]

        for (rank, score), enrollment in zip(
            expected_scores, enrollments
        ):
            enrollment.refresh_from_db()
            self.assertEqual(enrollment.position_on_leaderboard, rank)

            self.assertEqual(enrollment.total_score, score)
