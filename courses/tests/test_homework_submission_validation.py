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


class HomeworkSubmissionValidationTests(TestCase):
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
        return self.client.post(self.homework_url(), post_data, follow=follow)

    def get_saved_submission(self):
        return Submission.objects.get(
            homework=self.homework, student=self.user
        )

    def assert_no_submission(self):
        self.assertFalse(
            Submission.objects.filter(
                student=self.user, homework=self.homework
            ).exists()
        )

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

    def assert_invalid_homework_url_response(self, response, homework_url):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The submitted GitHub link")
        self.assertContains(response, "does not exist")
        self.assertContains(response, f'value="{homework_url}"')
        self.assertContains(
            response,
            'class="form-control mt-2 is-invalid"',
        )
        self.assertContains(
            response,
            "Check that the repository exists and is public.",
        )
        self.assertContains(
            response,
            f'id="radio-{self.question1.id}-1"',
        )
        self.assertContains(response, "checked")
        self.assertContains(
            response,
            'value="Some other text"',
        )
        self.assertContains(
            response,
            'value="3.141516"',
        )
        self.assert_no_submission()

    def assert_closed_homework_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This homework is not open for submissions yet.",
        )
        self.assertContains(response, "Status:")
        self.assertContains(response, "Closed")
        self.assertNotContains(response, "Not submitted")
        self.assertNotContains(response, 'name="answer_')
        self.assertNotContains(response, "Submission details")
        self.assertNotContains(response, "Save submission")

    def test_submit_homework_rejects_non_faq_contribution_url(self):
        self.enable_faq_contribution_field()
        faq_url = (
            "https://gist.github.com/Sanjomwa/"
            "2dcb7a95baa01c07c10048fbac1a8461"
        )
        post_data = self.updated_answer_post_data(
            faq_contribution_url=faq_url,
        )

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "FAQ contribution must be a DataTalksClub/faq issue "
            "or pull request URL",
        )
        self.assertContains(
            response,
            'value="https://gist.github.com/Sanjomwa/'
            '2dcb7a95baa01c07c10048fbac1a8461"',
        )
        self.assertContains(
            response,
            'class="form-control mt-2 is-invalid"',
        )
        self.assert_no_submission()

    def test_submit_homework_accepts_faq_issue_url(self):
        self.enable_faq_contribution_field()
        self.client.login(**credentials)

        faq_url = "https://github.com/DataTalksClub/faq/issues/281"
        post_data = self.updated_answer_post_data(
            faq_contribution_url=faq_url,
        )

        response = self.client.post(self.homework_url(), post_data)

        self.assertEqual(response.status_code, 302)
        submission = self.get_saved_submission()
        self.assertEqual(submission.faq_contribution_url, faq_url)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_submit_homework_url_validation_404_error(
        self, mock_get, mock_head
    ):
        self.mock_failed_url_checks(mock_get, mock_head)
        self.enable_homework_url_field()
        homework_url = "https://github.com/nonexistent/repo"
        post_data = self.updated_answer_post_data(homework_url=homework_url)

        response = self.post_homework(post_data)

        self.assert_invalid_homework_url_response(response, homework_url)

    def test_closed_homework_without_submission_hides_form(self):
        self.close_homework()
        self.client.login(**credentials)

        response = self.client.get(self.homework_url())

        self.assert_closed_homework_response(response)

    def test_closed_homework_post_does_not_create_submission(self):
        self.close_homework()
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some text"],
        }

        response = self.post_homework(post_data, follow=True)

        self.assertRedirects(response, self.homework_url())
        self.assertContains(
            response, "This homework is not open for submissions."
        )
        self.assert_no_submission()

    def test_submit_homework_time_spent_comma_decimal(self):
        self.disable_homework_url_field()
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            "time_spent_lectures": "2,5",
            "time_spent_homework": "1,25",
        }

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 302)
        submission = self.get_saved_submission()
        self.assertEqual(submission.time_spent_lectures, 2.5)
        self.assertEqual(submission.time_spent_homework, 1.25)

    def test_submit_homework_time_spent_invalid_text_shows_error(self):
        self.disable_homework_url_field()
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            "time_spent_lectures": "2 hrs",
        }

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid number of hours")
        self.assert_no_submission()

    def test_submit_homework_learning_in_public_empty_and_duplicates(
        self,
    ):
        self.homework.learning_in_public_cap = 7
        self.homework.save()
        learning_links = [
            "https://test.org/totally-existing-url/1",
            "https://test.org/totally-existing-url/1",
            "https://test.org/totally-existing-url/2",
            "https://test.org/totally-existing-url/3",
        ]
        extra_fields = {"learning_in_public_links[]": learning_links}
        post_data = self.updated_answer_post_data(**extra_fields)

        self.post_homework(post_data)

        submission = self.get_saved_submission()
        expected_learning_in_public_links = [
            "https://test.org/totally-existing-url/1",
            "https://test.org/totally-existing-url/2",
            "https://test.org/totally-existing-url/3",
        ]
        self.assertEqual(
            submission.learning_in_public_links,
            expected_learning_in_public_links,
        )

    def test_submit_homework_learning_in_public_rejects_non_http_url(
        self,
    ):
        self.homework.learning_in_public_cap = 7
        self.homework.save()
        learning_links = ["javascript:alert('payment')"]
        extra_fields = {"learning_in_public_links[]": learning_links}
        post_data = self.updated_answer_post_data(**extra_fields)

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Learning in public links must be valid HTTP or HTTPS URLs.",
        )
        self.assert_no_submission()
