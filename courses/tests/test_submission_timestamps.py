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
    def create_course(self):
        return Course.objects.create(
            slug="course",
            title="Course",
            description="Course description",
        )

    def create_homework(self, course):
        return Homework.objects.create(
            course=course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now(),
        )

    def create_question(self, homework):
        return Question.objects.create(
            homework=homework,
            text="Question",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type="ANY",
        )

    def create_submission_fixture(self, submitted_at):
        user = CustomUser.objects.create(email="student@example.com")
        course = self.create_course()
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        homework = self.create_homework(course)
        question = self.create_question(homework)
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
        return submission, answer

    def test_scoring_does_not_update_submission_timestamp(self):
        submitted_at = timezone.now() - timedelta(days=3)
        submission, answer = self.create_submission_fixture(submitted_at)
        update_score(submission, [answer], save=True)

        submission.refresh_from_db()
        self.assertEqual(submission.submitted_at, submitted_at)
