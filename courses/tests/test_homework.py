import logging

from dataclasses import dataclass
from datetime import datetime
from unittest import mock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Homework,
    HomeworkState,
    Question,
    Submission,
    Answer,
    Enrollment,
    QuestionTypes,
    AnswerTypes,
)

from .util import join_possible_answers

logger = logging.getLogger(__name__)

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


class HomeworkDetailViewTests(TestCase):
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
        question = QuestionData(
            text=text,
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=join_possible_answers(answers),
            correct_answer=correct_answer,
        )
        return self.create_question(question)

    def create_checkboxes_question(self, text, answers, correct_answer):
        question = QuestionData(
            text=text,
            question_type=QuestionTypes.CHECKBOXES.value,
            possible_answers=join_possible_answers(answers),
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
        self.quesions = [
            self.question1,
            self.question2,
            self.question3,
            self.question4,
            self.question5,
            self.question6,
        ]

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

    def option(self, value, index, is_selected=False):
        return {
            "value": value,
            "is_selected": is_selected,
            "index": index,
        }

    def unselected_options(self, values):
        options = []
        for index, value in enumerate(values, start=1):
            option = self.option(value, index)
            options.append(option)
        return options

    def selected_options(self, values, selected_indexes):
        options = []
        for index, value in enumerate(values, start=1):
            is_selected = index in selected_indexes
            option = self.option(value, index, is_selected)
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

    def create_submission_with_answers(self, question3_answer="1,2"):
        self.create_enrollment()
        self.create_submission()
        self.create_answers(
            {
                self.question1: "3",
                self.question2: "Some text",
                self.question3: question3_answer,
                self.question4: "1",
                self.question5: "3.141516",
                self.question6: "1,2,3",
            }
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
        return self.answer_post_data(data, **extra_fields)

    def artifact_post_data(self, question1_answer="1\r\n"):
        return {
            f"answer_{self.question1.id}": [question1_answer],
            f"answer_{self.question2.id}": ["Some text"],
            f"answer_{self.question3.id}": ["1\r\n", "2"],
            f"answer_{self.question4.id}": ["1"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1\r\n", "2\r\n", "3"],
        }

    def post_homework(self, post_data):
        self.client.login(**credentials)
        return self.client.post(self.homework_url(), post_data)

    def assert_redirects_to_homework(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.homework_url())

    def assert_no_enrollment_or_submission(self):
        self.assertFalse(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )
        self.assertFalse(
            Submission.objects.filter(
                student=self.user, homework=self.homework
            ).exists()
        )

    def get_saved_submission(self):
        return Submission.objects.get(
            homework=self.homework, student=self.user
        )

    def assert_enrollment_and_submission_exist(self):
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.user, course=self.course
            ).exists()
        )
        self.assertTrue(
            Submission.objects.filter(
                student=self.user, homework=self.homework
            ).exists()
        )

    def assert_submission_answers(self, submission, expected_answers):
        answers = Answer.objects.filter(submission=submission)
        self.assertEqual(len(answers), len(expected_answers))
        for question, expected_answer in expected_answers.items():
            answer = answers.get(question=question)
            self.assertEqual(answer.answer_text, expected_answer)

    def assert_homework_context(self, response, is_authenticated):
        context = response.context
        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["homework"], self.homework)
        self.assertEqual(context["is_authenticated"], is_authenticated)
        return context

    def assert_empty_question_answers(self, question_answers):
        self.assertEqual(len(question_answers), 6)
        self.assertEqual(question_answers[0][0], self.question1)
        self.assertEqual(
            question_answers[0][1]["options"],
            self.unselected_options(["Paris", "London", "Berlin"]),
        )
        self.assertEqual(question_answers[1], (self.question2, {"text": ""}))
        self.assertEqual(question_answers[2][0], self.question3)
        self.assertEqual(
            question_answers[2][1]["options"],
            self.unselected_options(["2", "3", "4", "5"]),
        )
        self.assertEqual(question_answers[3][0], self.question4)
        self.assertEqual(
            question_answers[3][1]["options"],
            self.unselected_options(["5", "6", "7"]),
        )
        self.assertEqual(question_answers[4], (self.question5, {"text": ""}))
        self.assertEqual(question_answers[5][0], self.question6)
        self.assertEqual(
            question_answers[5][1]["options"],
            self.unselected_options(["Blue", "White", "Red", "Green"]),
        )

    def assert_saved_question_answers(self, question_answers):
        self.assertEqual(len(question_answers), 6)
        self.assertEqual(question_answers[0][0], self.question1)
        self.assertEqual(
            question_answers[0][1]["options"],
            self.selected_options(["Paris", "London", "Berlin"], {3}),
        )
        self.assertEqual(question_answers[1][0], self.question2)
        self.assertEqual(question_answers[1][1]["text"], "Some text")
        self.assertEqual(question_answers[2][0], self.question3)
        self.assertEqual(
            question_answers[2][1]["options"],
            self.selected_options(["2", "3", "4", "5"], {1, 2}),
        )
        self.assertEqual(question_answers[3][0], self.question4)
        self.assertEqual(
            question_answers[3][1]["options"],
            self.selected_options(["5", "6", "7"], {1}),
        )
        self.assertEqual(question_answers[4][0], self.question5)
        self.assertEqual(question_answers[4][1]["text"], "3.141516")
        self.assertEqual(question_answers[5][0], self.question6)
        self.assertEqual(
            question_answers[5][1]["options"],
            self.selected_options(
                ["Blue", "White", "Red", "Green"], {1, 2, 3}
            ),
        )

    def test_homework_detail_unauthenticated(self):
        response = self.get_homework_response()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(
            response, is_authenticated=False
        )
        self.assert_empty_question_answers(context["question_answers"])

        self.assertContains(response, "Shown in your timezone.")
        self.assertNotContains(response, "account timezone")

    def test_homework_detail_unauthenticated_hides_submission_fields(self):
        self.homework.homework_url_field = True
        self.homework.learning_in_public_cap = 2
        self.homework.time_spent_lectures_field = True
        self.homework.time_spent_homework_field = True
        self.homework.faq_contribution_field = True
        self.homework.save()
        self.course.homework_problems_comments_field = True
        self.course.save()

        response = self.client.get(
            reverse(
                "homework",
                kwargs={
                    "course_slug": self.course.slug,
                    "homework_slug": self.homework.slug,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in to submit this homework")
        self.assertContains(response, "Log in to submit", count=2)
        self.assertContains(response, "You can preview the questions")
        self.assertNotContains(
            response, "Log in</a> to see the status of your submission."
        )
        self.assertNotContains(response, "Submission details")
        self.assertNotContains(response, "Homework URL")
        self.assertNotContains(response, "Learning in public links")
        self.assertNotContains(response, "No learning in public links submitted")
        self.assertNotContains(response, "Time spent on lectures")
        self.assertNotContains(response, "Time spent on homework")
        self.assertNotContains(response, "Problems or comments")
        self.assertNotContains(response, "FAQ contribution")

    def test_homework_detail_displays_optional_instructions_url(self):
        self.homework.instructions_url = (
            "https://github.com/DataTalksClub/course-management-platform/"
            "blob/main/README.md"
        )
        self.homework.save()

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instructions")
        self.assertContains(response, self.homework.instructions_url)
        self.assertContains(response, "fab fa-github")

    def test_homework_detail_hides_missing_instructions_url(self):
        self.homework.instructions_url = ""
        self.homework.save()

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Instructions")

    def test_homework_detail_authenticated_no_submission(self):
        response = self.get_homework_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(
            response, is_authenticated=True
        )
        self.assertContains(response, "account timezone")
        self.assertContains(
            response,
            f'{reverse("account_settings")}#display-preferences-section',
        )

        self.assert_empty_question_answers(context["question_answers"])
        self.assertContains(response, "Status: Not saved yet")
        self.assertContains(response, "Save submission")
        self.assertContains(
            response,
            (
                "You can save partial answers and update them until the "
                "deadline. Your latest saved version will be scored."
            ),
        )

    def test_homework_detail_authenticated_with_submission(self):
        self.create_submission_with_answers()

        logger.info(f"url={self.homework_url()}")
        response = self.get_homework_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(
            response, is_authenticated=True
        )
        self.assertEqual(context["submission"], self.submission)

        self.assert_saved_question_answers(context["question_answers"])
        self.assertContains(response, "Status: Last saved at")
        self.assertContains(response, "Update submission")
        self.assertContains(
            response,
            (
                "You can save partial answers and update them until the "
                "deadline. Your latest saved version will be scored."
            ),
        )

    def test_homework_detail_submission_post_no_submissions(self):
        self.assert_no_enrollment_or_submission()

        response = self.post_homework(self.answer_post_data())

        self.assert_redirects_to_homework(response)
        self.assert_enrollment_and_submission_exist()
        self.assert_submission_answers(
            self.get_saved_submission(),
            {
                self.question1: "1",
                self.question2: "Some text",
                self.question3: "1,2",
                self.question4: "1",
                self.question5: "3.141516",
                self.question6: "1,2,3",
            },
        )

    @mock.patch("django.utils.timezone.now")
    def test_homework_detail_submission_post_with_submissions(
        self, mock_now
    ):
        update_time_now = timezone.make_aware(datetime(2020, 1, 1))
        mock_now.return_value = update_time_now

        self.create_submission_with_answers(question3_answer="1,2,3")

        response = self.post_homework(self.updated_answer_post_data())

        self.assert_redirects_to_homework(response)

        submission = Submission.objects.get(id=self.submission.id)
        self.assertEqual(submission.submitted_at, update_time_now)
        self.assert_submission_answers(
            submission,
            {
                self.question1: "1",
                self.question2: "Some other text",
                self.question3: "1,2,4",
                self.question4: "3",
                self.question5: "3.141516",
                self.question6: "1,2",
            },
        )

    def test_submit_homework_submission_artifacts(self):
        self.post_homework(self.artifact_post_data())

        self.assert_submission_answers(
            self.get_saved_submission(),
            {
                self.question1: "1",
                self.question2: "Some text",
                self.question3: "1,2",
                self.question4: "1",
                self.question5: "3.141516",
                self.question6: "1,2,3",
            },
        )

    def test_submit_homework_submission_artifacts_dispayed_correctly(
        self,
    ):
        self.post_homework(self.artifact_post_data(question1_answer="3\r\n"))

        response = self.client.get(self.homework_url())
        self.assert_saved_question_answers(response.context["question_answers"])

    def test_submit_homework_submission_artifacts_in_possible_answers(
        self,
    ):
        self.question1.possible_answers = join_possible_answers(
            ["Paris\r", "London\r", "Berlin"]
        )
        self.question1.save()

        self.client.login(**credentials)

        post_data = {f"answer_{self.question1.id}": ["1\r\n"]}

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.post(url, post_data)

        response = self.client.get(url)
        context = response.context

        question_answers = context["question_answers"]

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": True, "index": 1},
            {"value": "London", "is_selected": False, "index": 2},
            {"value": "Berlin", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer1["options"], expected_options1)
