from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Answer,
    AnswerTypes,
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    Submission,
)

User = get_user_model()


class DashboardQuestionDifficultyTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            first_homework_scored=True,
        )
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.SCORED.value,
        )
        self.graded_question = Question.objects.create(
            homework=self.homework,
            text="What is 2 + 2?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            answer_type=AnswerTypes.INTEGER.value,
            scores_for_correct_answer=1,
        )
        self.participation_question = Question.objects.create(
            homework=self.homework,
            text="Any feedback?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
            scores_for_correct_answer=1,
        )

    def create_answers(self, correctness):
        for index, is_correct in enumerate(correctness):
            user = User.objects.create_user(
                username=f"student{index}@test.com",
                email=f"student{index}@test.com",
                password="12345",
            )
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            submission = Submission.objects.create(
                homework=self.homework,
                student=user,
                enrollment=enrollment,
            )
            Answer.objects.create(
                submission=submission,
                question=self.graded_question,
                answer_text="4",
                is_correct=is_correct,
            )
            Answer.objects.create(
                submission=submission,
                question=self.participation_question,
                answer_text="great",
                is_correct=True,
            )

    def dashboard_url(self):
        return reverse("dashboard", args=[self.course.slug])

    def test_question_difficulty_pct_correct(self):
        self.create_answers([True, True, False])

        response = self.client.get(self.dashboard_url())

        groups = response.context["question_difficulty"]
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group["homework_title"], "Homework 1")

        # Only the graded question is included; the ANY question is excluded.
        self.assertEqual(len(group["questions"]), 1)
        question = group["questions"][0]
        self.assertEqual(question["text"], "What is 2 + 2?")
        self.assertEqual(question["total"], 3)
        self.assertEqual(question["correct"], 2)
        self.assertEqual(question["pct_correct"], 66.7)

    def test_question_difficulty_rendered(self):
        self.create_answers([True, False])

        response = self.client.get(self.dashboard_url())

        self.assertContains(response, "Question difficulty")
        self.assertContains(response, "What is 2 + 2?")
        self.assertNotContains(response, "Any feedback?")

    def test_question_difficulty_empty_without_answers(self):
        response = self.client.get(self.dashboard_url())

        self.assertEqual(response.context["question_difficulty"], [])
        self.assertNotContains(response, "Question difficulty")

    def test_question_difficulty_excludes_unscored_homework(self):
        self.create_answers([True, False])

        unscored = Homework.objects.create(
            course=self.course,
            slug="hw2",
            title="Homework 2",
            due_date=timezone.now() + timedelta(days=14),
            state=HomeworkState.OPEN.value,
        )
        unscored_question = Question.objects.create(
            homework=unscored,
            text="Unscored question?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            answer_type=AnswerTypes.INTEGER.value,
            scores_for_correct_answer=1,
        )
        user = User.objects.create_user(
            username="unscored_student@test.com",
            email="unscored_student@test.com",
            password="12345",
        )
        enrollment = Enrollment.objects.create(
            student=user, course=self.course
        )
        submission = Submission.objects.create(
            homework=unscored,
            student=user,
            enrollment=enrollment,
        )
        Answer.objects.create(
            submission=submission,
            question=unscored_question,
            answer_text="1",
            is_correct=False,
        )

        response = self.client.get(self.dashboard_url())

        groups = response.context["question_difficulty"]
        homework_titles = [g["homework_title"] for g in groups]
        self.assertIn("Homework 1", homework_titles)
        self.assertNotIn("Homework 2", homework_titles)
