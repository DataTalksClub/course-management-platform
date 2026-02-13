import logging

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache

from django.urls import reverse

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
        # Clear cache before each test to ensure fresh state
        cache.clear()
        
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

    def test_leaderboard_cache_invalidation(self):
        """Test that leaderboard cache is invalidated when update_leaderboard is called"""
        # Create some test data
        enrollment1 = self.create_student("student1")
        enrollment2 = self.create_student("student2")

        homework = self.create_homework(1)
        self.submit_homework(homework, enrollment1, score=100)
        self.submit_homework(homework, enrollment2, score=50)

        # Update leaderboard (this should populate the cache)
        update_leaderboard(self.course)

        # Check the cache key
        cache_key = f"leaderboard:{self.course.id}"

        # Manually set a value in cache to verify it gets invalidated
        cache.set(cache_key, "test_value", 3600)
        self.assertEqual(cache.get(cache_key), "test_value")

        # Update leaderboard again (this should invalidate the cache)
        update_leaderboard(self.course)

        # Cache should be invalidated (None)
        self.assertIsNone(cache.get(cache_key))

    def test_score_breakdown_admin_button_visible_for_staff(self):
        """Test that admin edit button is visible on score breakdown page for staff users"""
        enrollment = self.create_student("student1")
        admin_user = User.objects.create_user(username="admin", is_staff=True)

        self.client.force_login(admin_user)
        url = reverse("leaderboard_score_breakdown", kwargs={
            "course_slug": self.course.slug,
            "enrollment_id": enrollment.id,
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        admin_edit_url = reverse("cadmin_enrollment_edit", kwargs={
            "course_slug": self.course.slug,
            "enrollment_id": enrollment.id,
        })
        self.assertContains(response, admin_edit_url)
        self.assertContains(response, "fa-cog")

    def test_score_breakdown_admin_button_hidden_for_regular_user(self):
        """Test that admin edit button is hidden on score breakdown page for regular users"""
        enrollment = self.create_student("student1")
        regular_user = User.objects.create_user(username="regular", is_staff=False)

        self.client.force_login(regular_user)
        url = reverse("leaderboard_score_breakdown", kwargs={
            "course_slug": self.course.slug,
            "enrollment_id": enrollment.id,
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "fa-cog")

    def test_score_breakdown_admin_button_hidden_for_anonymous(self):
        """Test that admin edit button is hidden on score breakdown page for anonymous users"""
        enrollment = self.create_student("student1")

        url = reverse("leaderboard_score_breakdown", kwargs={
            "course_slug": self.course.slug,
            "enrollment_id": enrollment.id,
        })
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "fa-cog")
