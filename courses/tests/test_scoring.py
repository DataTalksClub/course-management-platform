import logging

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    Course,
    Homework,
    Question,
    Submission,
    Answer,
    User,
    QuestionTypes,
    AnswerTypes,
)

from courses.scoring import HomeworkScoringStatus, score_homework_submissions


logger = logging.getLogger(__name__)


class HomeworkScoringTestCase(TestCase):
    def create_answers_for_student(self, submission, answers):
        for question, answer_text in zip(self.questions, answers):
            Answer.objects.create(
                submission=submission,
                question=question,
                student=submission.student,
                answer_text=answer_text,
            )

    def setUp(self):
        # Set up the data for the test

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() - timedelta(hours=1),
        )

        # Create questions
        self.questions = [
            Question.objects.create(
                homework=self.homework,
                text="What is the capital of France?",
                correct_answer="paris",
                question_type=QuestionTypes.FREE_FORM.value,
                answer_type=AnswerTypes.EXACT_STRING.value,
                scores_for_correct_answer=2,
            ),
            Question.objects.create(
                homework=self.homework,
                text="What is 5 multiplied by 3?",
                correct_answer="15",
                question_type=QuestionTypes.FREE_FORM.value,
                answer_type=AnswerTypes.INTEGER.value,
                scores_for_correct_answer=1,
            ),
            Question.objects.create(
                homework=self.homework,
                text="Which gas is most abundant in Earth's atmosphere?",
                correct_answer="nitrogen",
                question_type=QuestionTypes.FREE_FORM.value,
                answer_type=AnswerTypes.EXACT_STRING.value,
                scores_for_correct_answer=2,
            ),
            Question.objects.create(
                homework=self.homework,
                text="Is the Earth flat? (yes/no)",
                correct_answer="no",
                question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                answer_type=AnswerTypes.EXACT_STRING.value,
                scores_for_correct_answer=3,
            ),
            Question.objects.create(
                homework=self.homework,
                text="Water boils at 100 degrees Celsius. (true/false)",
                correct_answer="true",
                question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                answer_type=AnswerTypes.EXACT_STRING.value,
                scores_for_correct_answer=1,
            ),
            Question.objects.create(
                homework=self.homework,
                text="Select the prime numbers: 2, 4, 5, 7, 8",
                correct_answer="2,5,7",
                question_type=QuestionTypes.CHECKBOXES.value,
                answer_type=AnswerTypes.EXACT_STRING.value,
                scores_for_correct_answer=2,
            ),
        ]

        self.student1 = User.objects.create_user(username="student1")
        self.student2 = User.objects.create_user(username="student2")
        self.submission1 = Submission.objects.create(
            homework=self.homework, student=self.student1
        )
        self.submission2 = Submission.objects.create(
            homework=self.homework, student=self.student2
        )

        answers_student1 = [
            "paris",  # Correct
            "15",  # Correct
            "oxygen",  # Incorrect
            "no",  # Correct
            "false",  # Incorrect
            "2,5",  # Partially correct
        ]

        # Answers for student 2 (different mix of correct and incorrect)
        answers_student2 = [
            "london",  # Incorrect
            "20",  # Incorrect
            "nitrogen",  # Correct
            "yes",  # Incorrect
            "true",  # Correct
            "2,5,7",  # Correct
        ]

        self.create_answers_for_student(self.submission1, answers_student1)
        self.create_answers_for_student(self.submission2, answers_student2)

    def test_homework_scoring(self):
        status, message = score_homework_submissions(self.homework.id)
        logger.info(f"test_homework_scoring: status={status}, message={message}")

        self.homework = Homework.objects.get(pk=self.homework.id)
        self.submission1 = Submission.objects.get(pk=self.submission1.id)
        self.submission2 = Submission.objects.get(pk=self.submission2.id)

        self.assertEqual(status, HomeworkScoringStatus.OK)
        self.assertEqual(self.homework.is_scored, True)
        self.assertEqual(self.submission1.total_score, 2 + 1 + 3)
        self.assertEqual(self.submission2.total_score, 2 + 1 + 2)
