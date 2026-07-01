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


@dataclass(frozen=True)
class ScoredOptionExpectation:
    index: int
    value: str
    is_selected: bool
    is_correct: bool
    selected_class: str


class HomeworkScoringViewTests(TestCase):
    def create_course(self):
        return Course.objects.create(
            title="Test Course", slug="test-course"
        )

    def create_homework(self):
        return Homework.objects.create(
            course=self.course,
            title="Test Homework",
            description="Test Homework Description",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.OPEN.value,
            slug="test-homework",
        )

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

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.create_questions()

    def homework_url(self):
        return reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def get_homework_response(self, login=False):
        if login:
            self.client.login(**credentials)
        return self.client.get(self.homework_url())

    def assert_homework_context(self, response):
        context = response.context
        self.assertEqual(context["homework"], self.homework)
        self.assertEqual(context["course"], self.course)
        self.assertTrue(context["is_authenticated"])
        return context

    def option(self, expectation):
        option = {
            "value": expectation.value,
            "is_selected": expectation.is_selected,
            "index": expectation.index,
        }
        option["is_correct"] = expectation.is_correct
        option["correctly_selected_class"] = expectation.selected_class
        return option

    def scored_options(self, expectations):
        options = []
        for expectation in expectations:
            option = self.option(expectation)
            options.append(option)
        return options

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
        self.homework.due_date = timezone.now() - timezone.timedelta(days=1)
        self.homework.save()

        status, _ = score_homework_submissions(self.homework.id)
        self.assertEqual(status, HomeworkScoringStatus.OK)

        self.homework = Homework.objects.get(id=self.homework.id)
        self.assertEqual(self.homework.state, HomeworkState.SCORED.value)
        self.assertTrue(self.homework.is_scored())

    def create_scored_submission_with_answers(self, answers_by_question):
        self.create_enrollment()
        self.create_submission()
        self.create_answers(answers_by_question)
        self.score_homework()

    def assert_scored_text_answer(self, answer, text):
        self.assertEqual(answer["text"], text)
        self.assertEqual(
            answer["correctly_selected_class"],
            "option-answer-correct",
        )

    def first_question_expectations(self):
        expectations = []
        expectation = ScoredOptionExpectation(
            index=1,
            value="Paris",
            is_selected=False,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=2,
            value="London",
            is_selected=False,
            is_correct=False,
            selected_class="option-answer-none",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=3,
            value="Berlin",
            is_selected=True,
            is_correct=False,
            selected_class="option-answer-incorrect",
        )
        expectations.append(expectation)
        return expectations

    def third_question_expectations(self):
        expectations = []
        expectation = ScoredOptionExpectation(
            index=1,
            value="2",
            is_selected=True,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=2,
            value="3",
            is_selected=True,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=3,
            value="4",
            is_selected=True,
            is_correct=False,
            selected_class="option-answer-incorrect",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=4,
            value="5",
            is_selected=False,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        return expectations

    def fourth_question_expectations(self):
        expectations = []
        expectation = ScoredOptionExpectation(
            index=1,
            value="5",
            is_selected=True,
            is_correct=False,
            selected_class="option-answer-incorrect",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=2,
            value="6",
            is_selected=False,
            is_correct=False,
            selected_class="option-answer-none",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=3,
            value="7",
            is_selected=False,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        return expectations

    def sixth_question_expectations(self):
        expectations = []
        expectation = ScoredOptionExpectation(
            index=1,
            value="Blue",
            is_selected=True,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=2,
            value="White",
            is_selected=True,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=3,
            value="Red",
            is_selected=True,
            is_correct=True,
            selected_class="option-answer-correct",
        )
        expectations.append(expectation)
        expectation = ScoredOptionExpectation(
            index=4,
            value="Green",
            is_selected=False,
            is_correct=False,
            selected_class="option-answer-none",
        )
        expectations.append(expectation)
        return expectations

    def assert_first_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question1)
        expectations = self.first_question_expectations()
        expected_options = self.scored_options(expectations)
        self.assertEqual(answer["options"], expected_options)

    def assert_third_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question3)
        expectations = self.third_question_expectations()
        expected_options = self.scored_options(expectations)
        self.assertEqual(answer["options"], expected_options)

    def assert_fourth_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question4)
        expectations = self.fourth_question_expectations()
        expected_options = self.scored_options(expectations)
        self.assertEqual(answer["options"], expected_options)

    def assert_sixth_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question6)
        expectations = self.sixth_question_expectations()
        expected_options = self.scored_options(expectations)
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
        self.assertTrue(answer.get("no_answer_submitted", False))
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

    def test_homework_detail_with_scored_homework(self):
        answers_by_question = self.full_submission_answers()
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(response)
        self.assertEqual(context["submission"], self.submission)
        self.assertTrue(context["homework"].is_scored)

        self.assert_scored_question_answers(context["question_answers"])

    def test_homework_detail_scored_with_unanswered_questions(self):
        answers_by_question = {
            self.question1: "1",
            self.question2: "Some explanation",
            self.question5: "3.14",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        question_answers = response.context["question_answers"]
        self.assertEqual(len(question_answers), 6)
        self.assert_answer_present(question_answers[0], self.question1)
        answer2 = self.assert_answer_present(
            question_answers[1], self.question2
        )
        self.assertEqual(answer2["text"], "Some explanation")
        self.assert_no_answer_submitted(question_answers[2], self.question3)
        self.assert_no_answer_submitted(question_answers[3], self.question4)
        self.assert_answer_present(question_answers[4], self.question5)
        self.assert_no_answer_submitted(question_answers[5], self.question6)

    def test_homework_detail_scored_with_empty_free_form_answer(self):
        answers_by_question = {
            self.question2: "   ",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        question_answers = response.context["question_answers"]
        self.assert_no_answer_submitted(
            question_answers[1],
            self.question2,
        )

    def test_homework_detail_unauthenticated_scored_no_answer_warning(self):
        answers_by_question = {
            self.question1: "1",
            self.question4: "3",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response()
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("Correct answers are available below", content)
        self.assertIn("Log in to view my results", content)
        self.assertIn("Correct answers", content)
        self.assertIn("Review the expected answers", content)
        self.assertIn('type="radio"', content)
        self.assertIn('type="checkbox"', content)
        self.assertIn('type="text"', content)
        self.assertIn("disabled", content)
        self.assertNotIn("Log in to submit this homework", content)
        self.assertNotIn("You can preview the questions", content)
        self.assertNotIn("Submission details", content)
        self.assertNotIn("Status: Not submitted", content)
        self.assertNotIn("No answer was submitted for this question", content)

    def test_homework_detail_authenticated_scored_with_answer_warning(self):
        answers_by_question = {
            self.question1: "1",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("No answer was submitted for this question", content)
