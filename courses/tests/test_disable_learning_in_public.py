import logging
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Submission,
    User,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
)

from courses.homework_score_calculation import (
    update_learning_in_public_score,
)
from courses.services.enrollment_flags import (
    set_learning_in_public_disabled,
)

logger = logging.getLogger(__name__)


class DisableLearningInPublicTestCase(TestCase):
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_student(self):
        return User.objects.create_user(
            username="student1",
            email="student1@test.com",
            password="testpass123",
        )

    def create_enrollment(self):
        return Enrollment.objects.create(
            student=self.student1,
            course=self.course,
        )

    def create_homework(self):
        return Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
            learning_in_public_cap=3,
        )

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Test Project Description",
            submission_due_date=timezone.now() + timedelta(days=14),
            peer_review_due_date=timezone.now() + timedelta(days=21),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            learning_in_public_cap_project=14,
            learning_in_public_cap_review=2,
        )

    def create_scored_homework_submission(self):
        return Submission.objects.create(
            homework=self.homework,
            student=self.student1,
            enrollment=self.enrollment1,
            learning_in_public_links=[
                "http://link1.com",
                "http://link2.com",
            ],
            learning_in_public_score=2,
            questions_score=5,
            faq_score=1,
            total_score=8,
        )

    def create_scored_project_submission(self):
        return ProjectSubmission.objects.create(
            project=self.project,
            student=self.student1,
            enrollment=self.enrollment1,
            learning_in_public_links=["http://link1.com"],
            project_learning_in_public_score=1,
            peer_review_learning_in_public_score=2,
            project_score=10,
            total_score=13,
        )

    def assert_homework_learning_in_public_zeroed(self, submission):
        submission.refresh_from_db()
        self.assertEqual(submission.learning_in_public_score, 0)
        self.assertEqual(submission.total_score, 6)

    def assert_project_learning_in_public_zeroed(self, submission):
        submission.refresh_from_db()
        self.assertEqual(submission.project_learning_in_public_score, 0)
        self.assertEqual(submission.peer_review_learning_in_public_score, 0)
        self.assertEqual(submission.total_score, 10)

    def setUp(self):
        self.course = self.create_course()
        self.student1 = self.create_student()
        self.enrollment1 = self.create_enrollment()
        self.homework = self.create_homework()
        self.project = self.create_project()

    def test_enrollment_has_disable_field(self):
        """Test that enrollment has disable_learning_in_public field"""
        self.assertFalse(self.enrollment1.disable_learning_in_public)
        self.enrollment1.disable_learning_in_public = True
        self.enrollment1.save()
        
        # Refresh from DB
        enrollment = Enrollment.objects.get(id=self.enrollment1.id)
        self.assertTrue(enrollment.disable_learning_in_public)

    def test_homework_scoring_respects_disable_flag(self):
        """Test that homework scoring sets learning in public score to 0 when disabled"""
        # Create submission with learning in public links
        submission1 = Submission.objects.create(
            homework=self.homework,
            student=self.student1,
            enrollment=self.enrollment1,
            learning_in_public_links=[
                "http://link1.com",
                "http://link2.com",
                "http://link3.com",
            ],
        )
        
        # Score normally - should get 3 points
        score = update_learning_in_public_score(submission1)
        self.assertEqual(score, 3)
        self.assertEqual(submission1.learning_in_public_score, 3)
        
        # Disable learning in public for enrollment
        self.enrollment1.disable_learning_in_public = True
        self.enrollment1.save()
        
        # Re-score - should get 0 points
        score = update_learning_in_public_score(submission1)
        self.assertEqual(score, 0)
        self.assertEqual(submission1.learning_in_public_score, 0)

    def test_zeroing_scores_when_disabling(self):
        """Test that disabling learning in public zeros out all scores"""
        submission = self.create_scored_homework_submission()
        project_submission = self.create_scored_project_submission()

        set_learning_in_public_disabled(self.enrollment1, True)

        self.assert_homework_learning_in_public_zeroed(submission)
        self.assert_project_learning_in_public_zeroed(project_submission)

    def test_reenabling_does_not_recreate_scores(self):
        submission = Submission.objects.create(
            homework=self.homework,
            student=self.student1,
            enrollment=self.enrollment1,
            learning_in_public_links=["http://link1.com"],
            learning_in_public_score=1,
            questions_score=5,
            faq_score=1,
            total_score=7,
        )

        set_learning_in_public_disabled(self.enrollment1, True)
        set_learning_in_public_disabled(self.enrollment1, False)

        self.enrollment1.refresh_from_db()
        submission.refresh_from_db()
        self.assertFalse(self.enrollment1.disable_learning_in_public)
        self.assertEqual(submission.learning_in_public_score, 0)
        self.assertEqual(submission.total_score, 6)
