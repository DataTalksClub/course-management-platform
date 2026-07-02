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


class HomeworkOptionalFieldsBase(TestCase):
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

    def mock_successful_url_checks(self, mock_get, mock_head):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

    def enable_full_submission_fields(self):
        self.course.homework_problems_comments_field = True
        self.course.save()

        self.homework.homework_url_field = True
        self.homework.learning_in_public_cap = 7
        self.homework.time_spent_lectures_field = True
        self.homework.time_spent_homework_field = True
        self.homework.faq_contribution_field = True
        self.homework.save()

    def enable_empty_optional_submission_fields(self):
        self.homework.homework_url_field = True
        self.homework.learning_in_public_cap = 7
        self.homework.time_spent_lectures_field = True
        self.homework.time_spent_homework_field = True
        self.homework.problems_comments_field = True
        self.homework.faq_contribution_field = True
        self.homework.save()

    def full_optional_post_data(self):
        learning_links = [
            "https://httpbin.org/status/200",
            "https://github.com/DataTalksClub",
            "",
        ]
        extra_fields = {"learning_in_public_links[]": learning_links}
        post_data = self.updated_answer_post_data(
            homework_url="https://httpbin.org/status/200",
            **extra_fields,
            time_spent_lectures="5",
            time_spent_homework="3",
            problems_comments="Some problems and comments",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/pull/266"
            ),
        )
        return post_data

    def empty_optional_post_data(self):
        extra_fields = {"learning_in_public_links[]": [""]}
        post_data = self.updated_answer_post_data(
            homework_url="https://github.com/existing/repo",
            **extra_fields,
            time_spent_lectures="",
            time_spent_homework="",
            problems_comments="",
            faq_contribution_url="",
        )
        return post_data

    def get_saved_submission(self):
        return Submission.objects.get(
            student=self.user,
            homework=self.homework,
        )

    def assert_submission_help_links(self, response):
        self.assertContains(
            response,
            "https://datatalks.club/docs/courses/"
            "course-management-platform/learning-in-public/",
        )
        self.assertContains(
            response,
            "https://datatalks.club/docs/courses/faq/",
        )

    def assert_full_optional_submission(self, submission, post_data):
        self.assertEqual(submission.homework_link, post_data["homework_url"])
        self.assertEqual(
            submission.learning_in_public_links,
            [
                "https://httpbin.org/status/200",
                "https://github.com/DataTalksClub",
            ],
        )
        time_spent_lectures = float(post_data["time_spent_lectures"])
        self.assertEqual(
            submission.time_spent_lectures,
            time_spent_lectures,
        )
        time_spent_homework = float(post_data["time_spent_homework"])
        self.assertEqual(
            submission.time_spent_homework,
            time_spent_homework,
        )
        self.assertEqual(
            submission.problems_comments,
            post_data["problems_comments"],
        )
        self.assertEqual(
            submission.faq_contribution_url,
            post_data["faq_contribution_url"],
        )

    def assert_empty_optional_submission(self, submission, post_data):
        self.assertEqual(submission.homework_link, post_data["homework_url"])
        self.assertEqual(submission.learning_in_public_links, [])
        self.assertEqual(submission.time_spent_lectures, None)
        self.assertEqual(submission.time_spent_homework, None)
        self.assertEqual(submission.problems_comments, "")
        self.assertEqual(submission.faq_contribution_url, "")

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.create_questions()


class HomeworkOptionalFullFieldsTests(HomeworkOptionalFieldsBase):
    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_submit_homework_with_all_fields(self, mock_get, mock_head):
        self.mock_successful_url_checks(mock_get, mock_head)
        self.enable_full_submission_fields()
        post_data = self.full_optional_post_data()

        self.client.login(**credentials)
        homework_url = self.homework_url()
        response = self.client.get(homework_url)
        self.assert_submission_help_links(response)

        self.client.post(homework_url, post_data)
        submission = self.get_saved_submission()
        self.assert_full_optional_submission(submission, post_data)


class HomeworkOptionalEmptyFieldsTests(HomeworkOptionalFieldsBase):
    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_submit_homework_with_all_fields_optional_empty(
        self, mock_get, mock_head
    ):
        self.mock_successful_url_checks(mock_get, mock_head)
        self.enable_empty_optional_submission_fields()
        post_data = self.empty_optional_post_data()

        self.client.login(**credentials)
        homework_url = self.homework_url()
        self.client.post(homework_url, post_data)

        submission = self.get_saved_submission()
        self.assert_empty_optional_submission(submission, post_data)
