from dataclasses import dataclass

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
    User,
)
from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
)

from .homework_scoring_view_expectations import (
    FIRST_QUESTION_EXPECTATIONS,
    FOURTH_QUESTION_EXPECTATIONS,
    SIXTH_QUESTION_EXPECTATIONS,
    THIRD_QUESTION_EXPECTATIONS,
    scored_options,
)
from .util import join_possible_answers

credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


@dataclass(frozen=True)
class QuestionData:
    text: str
    question_type: str
    possible_answers: str | None = None
    correct_answer: str | None = None
    answer_type: str | None = None


class HomeworkScoringCourseFixtureMixin:
    def create_course(self):
        return Course.objects.create(
            title="Test Course", slug="test-course"
        )

    def create_homework(self):
        now = timezone.now()
        due_date = now + timezone.timedelta(days=7)
        return Homework.objects.create(
            course=self.course,
            title="Test Homework",
            description="Test Homework Description",
            due_date=due_date,
            state=HomeworkState.OPEN.value,
            slug="test-homework",
        )


class HomeworkScoringQuestionFixtureMixin:
    def create_question(self, data):
        return Question.objects.create(
            homework=self.homework,
            text=data.text,
            question_type=data.question_type,
            possible_answers=data.possible_answers,
            correct_answer=data.correct_answer,
            answer_type=data.answer_type,
        )

    def create_multiple_choice_question(self, text, answers, correct_answer):
        possible_answers = join_possible_answers(answers)
        question = QuestionData(
            text=text,
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=possible_answers,
            correct_answer=correct_answer,
        )
        return self.create_question(question)

    def create_checkboxes_question(self, text, answers, correct_answer):
        possible_answers = join_possible_answers(answers)
        question = QuestionData(
            text=text,
            question_type=QuestionTypes.CHECKBOXES.value,
            possible_answers=possible_answers,
            correct_answer=correct_answer,
        )
        return self.create_question(question)

    def create_free_form_question(
        self,
        text,
        answer_type,
        correct_answer=None,
    ):
        question = QuestionData(
            text=text,
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=answer_type,
            correct_answer=correct_answer,
        )
        return self.create_question(question)

    def create_questions(self):
        self.question1 = self.create_multiple_choice_question(
            "What is the capital of France?",
            ["Paris", "London", "Berlin"],
            "1",
        )
        self.question2 = self.create_free_form_question(
            "Explain the theory of relativity.",
            AnswerTypes.ANY.value,
        )
        self.question3 = self.create_checkboxes_question(
            "Select prime numbers.",
            ["2", "3", "4", "5"],
            "1,2,4",
        )
        self.question4 = self.create_multiple_choice_question(
            "How many continents are there on Earth?",
            ["5", "6", "7"],
            "3",
        )
        self.question5 = self.create_free_form_question(
            "What is the value of Pi (up to 2 decimal places)?",
            AnswerTypes.FLOAT.value,
            "3.14",
        )
        self.question6 = self.create_checkboxes_question(
            "Select the colors in the French flag.",
            ["Blue", "White", "Red", "Green"],
            "1,2,3",
        )


class HomeworkScoringRequestMixin:
    def homework_url(self):
        kwargs = {
            "course_slug": self.course.slug,
            "homework_slug": self.homework.slug,
        }
        return reverse("homework", kwargs=kwargs)

    def get_homework_response(self, login=False):
        if login:
            self.client.login(**credentials)
        url = self.homework_url()
        return self.client.get(url)

    def assert_homework_context(self, response):
        context = response.context
        self.assertEqual(context["homework"], self.homework)
        self.assertEqual(context["course"], self.course)
        self.assertTrue(context["is_authenticated"])
        return context


class HomeworkScoringSubmissionFixtureMixin:
    def create_enrollment(self):
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        return self.enrollment

    def create_submission(self):
        self.submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
        )
        return self.submission

    def create_answers(self, answers_by_question):
        for question, answer_text in answers_by_question.items():
            Answer.objects.create(
                submission=self.submission,
                question=question,
                answer_text=answer_text,
            )

    def score_homework(self):
        now = timezone.now()
        self.homework.due_date = now - timezone.timedelta(days=1)
        self.homework.save()

        status, _ = score_homework_submissions(self.homework.id)
        self.assertEqual(status, HomeworkScoringStatus.OK)

        self.homework = Homework.objects.get(id=self.homework.id)
        self.assertEqual(self.homework.state, HomeworkState.SCORED.value)
        homework_is_scored = self.homework.is_scored()
        self.assertTrue(homework_is_scored)

    def create_scored_submission_with_answers(self, answers_by_question):
        self.create_enrollment()
        self.create_submission()
        self.create_answers(answers_by_question)
        self.score_homework()


class HomeworkScoringAnswerAssertionsMixin:
    def assert_scored_text_answer(self, answer, text):
        self.assertEqual(answer["text"], text)
        self.assertEqual(
            answer["correctly_selected_class"],
            "option-answer-correct",
        )

    def assert_first_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question1)
        expectations = FIRST_QUESTION_EXPECTATIONS
        expected_options = scored_options(expectations)
        self.assertEqual(answer["options"], expected_options)

    def assert_third_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question3)
        expectations = THIRD_QUESTION_EXPECTATIONS
        expected_options = scored_options(expectations)
        self.assertEqual(answer["options"], expected_options)

    def assert_fourth_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question4)
        expectations = FOURTH_QUESTION_EXPECTATIONS
        expected_options = scored_options(expectations)
        self.assertEqual(answer["options"], expected_options)

    def assert_sixth_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question6)
        expectations = SIXTH_QUESTION_EXPECTATIONS
        expected_options = scored_options(expectations)
        self.assertEqual(answer["options"], expected_options)

    def assert_scored_question_answers(self, question_answers):
        self.assertEqual(len(question_answers), 6)
        self.assert_first_scored_answer(question_answers[0])
        self.assertEqual(question_answers[1][0], self.question2)
        self.assert_scored_text_answer(question_answers[1][1], "Some text")
        self.assert_third_scored_answer(question_answers[2])
        self.assert_fourth_scored_answer(question_answers[3])
        self.assertEqual(question_answers[4][0], self.question5)
        self.assert_scored_text_answer(question_answers[4][1], "3.141516")
        self.assert_sixth_scored_answer(question_answers[5])

    def assert_answer_present(self, question_answer, expected_question):
        question, answer = question_answer
        self.assertEqual(question, expected_question)
        self.assertNotIn("no_answer_submitted", answer)
        return answer

    def assert_no_answer_submitted(self, question_answer, expected_question):
        question, answer = question_answer
        self.assertEqual(question, expected_question)
        no_answer_submitted = answer.get("no_answer_submitted", False)
        self.assertTrue(no_answer_submitted)
        return answer

    def full_submission_answers(self):
        answers_by_question = {
            self.question1: "3",
            self.question2: "Some text",
            self.question3: "1,2,3",
            self.question4: "1",
            self.question5: "3.141516",
            self.question6: "1,2,3",
        }
        return answers_by_question


class HomeworkScoringViewBase(
    HomeworkScoringCourseFixtureMixin,
    HomeworkScoringQuestionFixtureMixin,
    HomeworkScoringRequestMixin,
    HomeworkScoringSubmissionFixtureMixin,
    HomeworkScoringAnswerAssertionsMixin,
    TestCase,
):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.create_questions()
