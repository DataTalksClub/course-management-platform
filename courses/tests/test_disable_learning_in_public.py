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

from courses.scoring import (
    update_learning_in_public_score,
)

logger = logging.getLogger(__name__)


class DisableLearningInPublicTestCase(TestCase):
    def setUp(self):
        # Create test course
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        # Create test students
        self.student1 = User.objects.create_user(
            username="student1",
            email="student1@test.com",
            password="testpass123"
        )

        # Create enrollments
        self.enrollment1 = Enrollment.objects.create(
            student=self.student1,
            course=self.course
        )

        # Create homework
        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
            learning_in_public_cap=3
        )

        # Create project
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Test Project Description",
            submission_due_date=timezone.now() + timedelta(days=14),
            peer_review_due_date=timezone.now() + timedelta(days=21),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            learning_in_public_cap_project=14,
            learning_in_public_cap_review=2
        )

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
            learning_in_public_links=["http://link1.com", "http://link2.com", "http://link3.com"]
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
        # Create submissions with learning in public scores
        submission1 = Submission.objects.create(
            homework=self.homework,
            student=self.student1,
            enrollment=self.enrollment1,
            learning_in_public_links=["http://link1.com", "http://link2.com"],
            learning_in_public_score=2,
            questions_score=5,
            faq_score=1,
            total_score=8
        )
        
        project_submission1 = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student1,
            enrollment=self.enrollment1,
            learning_in_public_links=["http://link1.com"],
            project_learning_in_public_score=1,
            peer_review_learning_in_public_score=2,
            project_score=10,
            total_score=13
        )
        
        # Disable learning in public programmatically
        self.enrollment1.disable_learning_in_public = True
        self.enrollment1.save()
        
        # Zero out homework learning in public scores
        homework_submissions = Submission.objects.filter(enrollment=self.enrollment1)
        for submission in homework_submissions:
            if submission.learning_in_public_score > 0:
                submission.learning_in_public_score = 0
                submission.total_score = (
                    submission.questions_score + 
                    submission.faq_score + 
                    submission.learning_in_public_score
                )
        Submission.objects.bulk_update(
            homework_submissions,
            ['learning_in_public_score', 'total_score']
        )
        
        # Zero out project learning in public scores
        project_submissions = ProjectSubmission.objects.filter(enrollment=self.enrollment1)
        for submission in project_submissions:
            if submission.project_learning_in_public_score > 0 or submission.peer_review_learning_in_public_score > 0:
                submission.project_learning_in_public_score = 0
                submission.peer_review_learning_in_public_score = 0
                submission.total_score = (
                    submission.project_score +
                    submission.project_faq_score +
                    submission.project_learning_in_public_score +
                    submission.peer_review_score +
                    submission.peer_review_learning_in_public_score
                )
        ProjectSubmission.objects.bulk_update(
            project_submissions,
            ['project_learning_in_public_score', 'peer_review_learning_in_public_score', 'total_score']
        )
        
        # Verify scores are zeroed
        submission1.refresh_from_db()
        self.assertEqual(submission1.learning_in_public_score, 0)
        self.assertEqual(submission1.total_score, 6)  # 5 + 1 (questions + faq, no LiP)
        
        project_submission1.refresh_from_db()
        self.assertEqual(project_submission1.project_learning_in_public_score, 0)
        self.assertEqual(project_submission1.peer_review_learning_in_public_score, 0)
        self.assertEqual(project_submission1.total_score, 10)  # Only project score

