from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.homework_question_stats import homework_question_stats
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


class HomeworkQuestionStatsTestCase(TestCase):
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
        self.choice_question = Question.objects.create(
            homework=self.homework,
            text="Pick one",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            answer_type=AnswerTypes.ANY.value,
            possible_answers="Option A\nOption B\nOption C",
            correct_answer="2",
            scores_for_correct_answer=1,
        )
        self.free_form_question = Question.objects.create(
            homework=self.homework,
            text="Type a number",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="42",
            scores_for_correct_answer=1,
        )
        self.participation_question = Question.objects.create(
            homework=self.homework,
            text="Any feedback?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
            scores_for_correct_answer=0,
        )

    def create_student_and_submission(self):
        user = User.objects.create_user(
            username=f"user-{User.objects.count()}@test.com",
            email=f"user-{User.objects.count()}@test.com",
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
        return user, submission

    def create_answers(self, choice_index, free_form_text):
        user, submission = self.create_student_and_submission()
        Answer.objects.create(
            submission=submission,
            question=self.choice_question,
            answer_text=str(choice_index),
            is_correct=choice_index == 2,
        )
        Answer.objects.create(
            submission=submission,
            question=self.free_form_question,
            answer_text=free_form_text,
            is_correct=free_form_text == "42",
        )
        Answer.objects.create(
            submission=submission,
            question=self.participation_question,
            answer_text="good",
            is_correct=True,
        )

    def test_question_stats_order_and_count(self):
        for _ in range(5):
            self.create_answers(2, "42")
        self.create_answers(1, "99")

        stats = homework_question_stats(self.homework)
        self.assertEqual(len(stats), 3)
        self.assertEqual(stats[0].question_id, self.choice_question.id)
        self.assertEqual(stats[1].question_id, self.free_form_question.id)

    def test_choice_question_distribution(self):
        for _ in range(5):
            self.create_answers(2, "42")
        self.create_answers(1, "99")
        self.create_answers(3, "7")

        stats = homework_question_stats(self.homework)
        choice_stat = stats[0]
        self.assertEqual(choice_stat.total, 7)
        self.assertEqual(choice_stat.correct, 5)
        self.assertEqual(choice_stat.pct_correct, 71.4)
        self.assertIsNotNone(choice_stat.choice_options)

        options = {o.index: o for o in choice_stat.choice_options}
        self.assertEqual(options[1].count, 1)
        self.assertEqual(options[2].count, 5)
        self.assertEqual(options[2].is_correct, True)
        self.assertEqual(options[1].is_correct, False)
        self.assertEqual(options[2].pct, 71.4)

    def test_free_form_question_distribution(self):
        for _ in range(5):
            self.create_answers(2, "42")
        self.create_answers(2, "99")

        stats = homework_question_stats(self.homework)
        ff_stat = stats[1]
        self.assertEqual(ff_stat.total, 6)
        self.assertEqual(ff_stat.correct, 5)
        self.assertEqual(ff_stat.pct_correct, 83.3)
        self.assertIsNone(ff_stat.choice_options)
        self.assertIsNotNone(ff_stat.free_form_values)

        values = dict(ff_stat.free_form_values)
        self.assertEqual(values["42"], 5)
        self.assertEqual(values["99"], 1)

    def test_question_with_no_answers(self):
        stats = homework_question_stats(self.homework)
        choice_stat = stats[0]
        self.assertEqual(choice_stat.total, 0)
        self.assertEqual(choice_stat.correct, 0)
        self.assertIsNone(choice_stat.pct_correct)
        self.assertEqual(choice_stat.choice_options[0].count, 0)
        self.assertEqual(choice_stat.choice_options[0].pct, 0.0)

    def test_stats_page_renders_question_breakdown(self):
        for _ in range(3):
            self.create_answers(2, "42")
        self.create_answers(1, "99")

        url = reverse(
            "homework_statistics",
            args=[self.course.slug, self.homework.slug],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Question breakdown")
        self.assertContains(response, "Pick one")
        self.assertContains(response, "Type a number")
        self.assertContains(response, "Option B")
        question_stats = response.context["question_stats"]
        self.assertEqual(len(question_stats), 3)
