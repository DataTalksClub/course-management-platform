from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from courses.models import (
    Answer,
    Course,
    Enrollment,
    Homework,
    Question,
    QuestionTypes,
    Submission,
)
from courses.scoring import update_score


class SubmissionTimestampTest(TestCase):
    def test_scoring_does_not_update_submission_timestamp(self):
        user = CustomUser.objects.create(email="student@example.com")
        course = Course.objects.create(
            slug="course",
            title="Course",
            description="Course description",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        homework = Homework.objects.create(
            course=course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now(),
        )
        question = Question.objects.create(
            homework=homework,
            text="Question",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type="ANY",
        )
        submitted_at = timezone.now() - timedelta(days=3)
        submission = Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
            submitted_at=submitted_at,
        )
        answer = Answer.objects.create(
            submission=submission,
            question=question,
            answer_text="answer",
        )

        update_score(submission, [answer], save=True)

        submission.refresh_from_db()
        self.assertEqual(submission.submitted_at, submitted_at)
