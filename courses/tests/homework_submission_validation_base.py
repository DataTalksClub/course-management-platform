from dataclasses import dataclass
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    AnswerTypes,
    Course,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    Submission,
    User,
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
class AnswerPostData:
    question2_answer: str = "Some text"
    question3_answers: list[str] | None = None
    question4_answers: list[str] | None = None
    question6_answers: list[str] | None = None


class HomeworkSubmissionValidationBase(TestCase):
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

    def answer_post_data(self, data=None, **extra_fields):
        if data is None:
            data = AnswerPostData()
        question3_answers = data.question3_answers or ["1", "2"]
        question4_answers = data.question4_answers or ["1"]
        question6_answers = data.question6_answers or ["1", "2", "3"]
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": [data.question2_answer],
            f"answer_{self.question3.id}": question3_answers,
            f"answer_{self.question4.id}": question4_answers,
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": question6_answers,
        }
        post_data.update(extra_fields)
        return post_data

    def updated_answer_post_data(self, **extra_fields):
        data = AnswerPostData(
            question2_answer="Some other text",
            question3_answers=["1", "2", "4"],
            question4_answers=["3"],
            question6_answers=["1", "2"],
        )
        post_data = self.answer_post_data(data, **extra_fields)
        return post_data

    def post_homework(self, post_data, follow=False):
        self.client.login(**credentials)
        homework_url = self.homework_url()
        return self.client.post(homework_url, post_data, follow=follow)

    def get_saved_submission(self):
        return Submission.objects.get(
            homework=self.homework, student=self.user
        )

    def assert_no_submission(self):
        submission_exists = Submission.objects.filter(
            student=self.user, homework=self.homework
        ).exists()
        self.assertFalse(submission_exists)

    def mock_failed_url_checks(self, mock_get, mock_head, status_code=404):
        mock_response = mock.Mock()
        mock_response.status_code = status_code
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

    def enable_homework_url_field(self):
        self.homework.homework_url_field = True
        self.homework.save()

    def enable_faq_contribution_field(self):
        self.homework.faq_contribution_field = True
        self.homework.save()

    def close_homework(self):
        self.homework.state = HomeworkState.CLOSED.value
        self.homework.save(update_fields=["state"])

    def disable_homework_url_field(self):
        self.homework.homework_url_field = False
        self.homework.save()
