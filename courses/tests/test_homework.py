import logging

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

from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
)

from .util import join_possible_answers

logger = logging.getLogger(__name__)

credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


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

    def create_question(
        self,
        text,
        question_type,
        possible_answers=None,
        correct_answer=None,
        answer_type=None,
    ):
        return Question.objects.create(
            homework=self.homework,
            text=text,
            question_type=question_type,
            possible_answers=possible_answers,
            correct_answer=correct_answer,
            answer_type=answer_type,
        )

    def create_multiple_choice_question(self, text, answers, correct_answer):
        return self.create_question(
            text,
            QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=join_possible_answers(answers),
            correct_answer=correct_answer,
        )

    def create_checkboxes_question(self, text, answers, correct_answer):
        return self.create_question(
            text,
            QuestionTypes.CHECKBOXES.value,
            possible_answers=join_possible_answers(answers),
            correct_answer=correct_answer,
        )

    def create_free_form_question(
        self,
        text,
        answer_type,
        correct_answer=None,
    ):
        return self.create_question(
            text,
            QuestionTypes.FREE_FORM.value,
            answer_type=answer_type,
            correct_answer=correct_answer,
        )

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

    def scored_option(
        self, value, index, is_selected, is_correct, selected_class
    ):
        option = self.option(value, index, is_selected)
        option.update(
            {
                "is_correct": is_correct,
                "correctly_selected_class": selected_class,
            }
        )
        return option

    def unselected_options(self, values):
        return [
            self.option(value, index)
            for index, value in enumerate(values, start=1)
        ]

    def selected_options(self, values, selected_indexes):
        return [
            self.option(value, index, index in selected_indexes)
            for index, value in enumerate(values, start=1)
        ]

    def scored_options(self, rows):
        return [
            self.scored_option(value, index, selected, correct, css_class)
            for index, value, selected, correct, css_class in rows
        ]

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

    def answer_post_data(
        self,
        question2_answer="Some text",
        question3_answers=None,
        question4_answers=None,
        question6_answers=None,
        **extra_fields,
    ):
        data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": [question2_answer],
            f"answer_{self.question3.id}": question3_answers or ["1", "2"],
            f"answer_{self.question4.id}": question4_answers or ["1"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": question6_answers or ["1", "2", "3"],
        }
        data.update(extra_fields)
        return data

    def updated_answer_post_data(self, **extra_fields):
        return self.answer_post_data(
            question2_answer="Some other text",
            question3_answers=["1", "2", "4"],
            question4_answers=["3"],
            question6_answers=["1", "2"],
            **extra_fields,
        )

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

    def assert_no_submission(self):
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

    def mock_successful_url_checks(self, mock_get, mock_head):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

    def mock_failed_url_checks(self, mock_get, mock_head, status_code=404):
        mock_response = mock.Mock()
        mock_response.status_code = status_code
        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

    def enable_homework_url_field(self):
        self.homework.homework_url_field = True
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
        return self.updated_answer_post_data(
            homework_url="https://httpbin.org/status/200",
            **{
                "learning_in_public_links[]": [
                    "https://httpbin.org/status/200",
                    "https://github.com/DataTalksClub",
                    "",
                ]
            },
            time_spent_lectures="5",
            time_spent_homework="3",
            problems_comments="Some problems and comments",
            faq_contribution_url=(
                "https://github.com/DataTalksClub/faq/pull/266"
            ),
        )

    def empty_optional_post_data(self):
        return self.updated_answer_post_data(
            homework_url="https://github.com/existing/repo",
            **{"learning_in_public_links[]": [""]},
            time_spent_lectures="",
            time_spent_homework="",
            problems_comments="",
            faq_contribution_url="",
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
        self.assertEqual(
            submission.time_spent_lectures,
            float(post_data["time_spent_lectures"]),
        )
        self.assertEqual(
            submission.time_spent_homework,
            float(post_data["time_spent_homework"]),
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

    def score_homework(self):
        self.homework.due_date = timezone.now() - timezone.timedelta(days=1)
        self.homework.save()

        status, _ = score_homework_submissions(self.homework.id)
        self.assertEqual(status, HomeworkScoringStatus.OK)

        self.homework = Homework.objects.get(id=self.homework.id)
        self.assertEqual(self.homework.state, HomeworkState.SCORED.value)
        self.assertTrue(self.homework.is_scored())

    def assert_scored_text_answer(self, answer, text):
        self.assertEqual(answer["text"], text)
        self.assertEqual(
            answer["correctly_selected_class"],
            "option-answer-correct",
        )

    def assert_first_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question1)
        self.assertEqual(
            answer["options"],
            self.scored_options(
                [
                    (1, "Paris", False, True, "option-answer-correct"),
                    (2, "London", False, False, "option-answer-none"),
                    (3, "Berlin", True, False, "option-answer-incorrect"),
                ]
            ),
        )

    def assert_third_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question3)
        self.assertEqual(
            answer["options"],
            self.scored_options(
                [
                    (1, "2", True, True, "option-answer-correct"),
                    (2, "3", True, True, "option-answer-correct"),
                    (3, "4", True, False, "option-answer-incorrect"),
                    (4, "5", False, True, "option-answer-correct"),
                ]
            ),
        )

    def assert_fourth_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question4)
        self.assertEqual(
            answer["options"],
            self.scored_options(
                [
                    (1, "5", True, False, "option-answer-incorrect"),
                    (2, "6", False, False, "option-answer-none"),
                    (3, "7", False, True, "option-answer-correct"),
                ]
            ),
        )

    def assert_sixth_scored_answer(self, question_answer):
        question, answer = question_answer
        self.assertEqual(question, self.question6)
        self.assertEqual(
            answer["options"],
            self.scored_options(
                [
                    (1, "Blue", True, True, "option-answer-correct"),
                    (2, "White", True, True, "option-answer-correct"),
                    (3, "Red", True, True, "option-answer-correct"),
                    (4, "Green", False, False, "option-answer-none"),
                ]
            ),
        )

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

    def create_scored_submission_with_answers(self, answers_by_question):
        self.create_enrollment()
        self.create_submission()
        self.create_answers(answers_by_question)
        self.score_homework()

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

    def test_homework_detail_with_scored_homework(self):
        self.create_submission_with_answers(question3_answer="1,2,3")
        self.score_homework()

        response = self.get_homework_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(
            response, is_authenticated=True
        )
        self.assertEqual(context["submission"], self.submission)
        self.assertTrue(context["homework"].is_scored)

        self.assert_scored_question_answers(context["question_answers"])

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

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_submit_homework_with_all_fields(self, mock_get, mock_head):
        self.mock_successful_url_checks(mock_get, mock_head)
        self.enable_full_submission_fields()
        post_data = self.full_optional_post_data()

        self.client.login(**credentials)
        self.assert_submission_help_links(
            self.client.get(self.homework_url())
        )

        self.client.post(self.homework_url(), post_data)
        self.assert_full_optional_submission(
            self.get_saved_submission(), post_data
        )

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_submit_homework_with_all_fields_optional_empty(
        self, mock_get, mock_head
    ):
        self.mock_successful_url_checks(mock_get, mock_head)
        self.enable_empty_optional_submission_fields()
        post_data = self.empty_optional_post_data()

        self.client.login(**credentials)
        self.client.post(self.homework_url(), post_data)

        self.assert_empty_optional_submission(
            self.get_saved_submission(), post_data
        )

    def test_submit_homework_rejects_non_faq_contribution_url(self):
        self.homework.faq_contribution_field = True
        self.homework.save()

        post_data = self.updated_answer_post_data(
            faq_contribution_url=(
                "https://gist.github.com/Sanjomwa/"
                "2dcb7a95baa01c07c10048fbac1a8461"
            ),
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
        self.assertFalse(
            Submission.objects.filter(
                homework=self.homework, student=self.user
            ).exists()
        )

    def test_submit_homework_accepts_faq_issue_url(self):
        self.homework.faq_contribution_field = True
        self.homework.save()

        self.client.login(**credentials)

        faq_url = "https://github.com/DataTalksClub/faq/issues/281"
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["1", "2", "4"],
            f"answer_{self.question4.id}": ["3"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1", "2"],
            "faq_contribution_url": faq_url,
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(url, post_data)

        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(
            homework=self.homework, student=self.user
        )
        self.assertEqual(submission.faq_contribution_url, faq_url)

    @mock.patch("requests.head")
    @mock.patch("requests.get")
    def test_submit_homework_url_validation_404_error(
        self, mock_get, mock_head
    ):
        self.mock_failed_url_checks(mock_get, mock_head)
        self.enable_homework_url_field()
        homework_url = "https://github.com/nonexistent/repo"

        response = self.post_homework(
            self.updated_answer_post_data(homework_url=homework_url)
        )

        self.assert_invalid_homework_url_response(response, homework_url)

    def test_closed_homework_without_submission_hides_form(self):
        self.homework.state = HomeworkState.CLOSED.value
        self.homework.save(update_fields=["state"])

        self.client.login(**credentials)
        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.get(url)

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

    def test_closed_homework_post_does_not_create_submission(self):
        self.homework.state = HomeworkState.CLOSED.value
        self.homework.save(update_fields=["state"])

        self.client.login(**credentials)
        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some text"],
        }

        response = self.client.post(url, post_data, follow=True)

        self.assertRedirects(response, url)
        self.assertContains(
            response, "This homework is not open for submissions."
        )
        self.assertFalse(
            Submission.objects.filter(
                homework=self.homework,
                student=self.user,
            ).exists()
        )

    def test_submit_homework_time_spent_comma_decimal(self):
        # Mobile and EU-locale keyboards commonly submit "2,5" for the
        # time-spent fields. This must be accepted, not crash with a 500.
        self.homework.homework_url_field = False
        self.homework.save()

        self.client.login(**credentials)

        post_data = {
            f"answer_{self.question1.id}": ["1"],
            "time_spent_lectures": "2,5",
            "time_spent_homework": "1,25",
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(url, post_data)

        self.assertEqual(response.status_code, 302)

        submission = Submission.objects.get(
            homework=self.homework, student=self.user
        )
        self.assertEqual(submission.time_spent_lectures, 2.5)
        self.assertEqual(submission.time_spent_homework, 1.25)

    def test_submit_homework_time_spent_invalid_text_shows_error(self):
        # Non-numeric input must surface a friendly form error instead of
        # raising an uncaught ValueError (which previously caused a 500).
        self.homework.homework_url_field = False
        self.homework.save()

        self.client.login(**credentials)

        post_data = {
            f"answer_{self.question1.id}": ["1"],
            "time_spent_lectures": "2 hrs",
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(url, post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid number of hours")
        # The transaction rolls back, so no partial submission is saved.
        self.assertFalse(
            Submission.objects.filter(
                homework=self.homework, student=self.user
            ).exists()
        )

    def test_submit_homework_learning_in_public_empty_and_duplicates(
        self,
    ):
        self.homework.learning_in_public_cap = 7
        self.homework.save()

        post_data = self.updated_answer_post_data(
            **{
                "learning_in_public_links[]": [
                    "https://test.org/totally-existing-url/1",
                    "https://test.org/totally-existing-url/1",
                    "https://test.org/totally-existing-url/2",
                    "https://test.org/totally-existing-url/3",
                ],
            }
        )

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

        self.client.login(**credentials)

        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["1", "2", "4"],
            f"answer_{self.question4.id}": ["3"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1", "2"],
            "learning_in_public_links[]": [
                "javascript:alert('payment')",
            ],
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(url, post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Learning in public links must be valid HTTP or HTTPS URLs.",
        )
        self.assertFalse(
            Submission.objects.filter(
                homework=self.homework, student=self.user
            ).exists()
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

    def test_homework_detail_scored_with_unanswered_questions(self):
        """Test that unanswered questions in scored homework show appropriate indicators"""
        self.create_scored_submission_with_answers(
            {
                self.question1: "1",
                self.question2: "Some explanation",
                self.question5: "3.14",
            }
        )

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
        """Test that empty free form answers in scored homework show appropriate indicators"""
        self.create_scored_submission_with_answers(
            {
                self.question2: "   ",
            }
        )

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        self.assert_no_answer_submitted(
            response.context["question_answers"][1],
            self.question2,
        )

    def test_homework_detail_unauthenticated_scored_no_answer_warning(self):
        """
        Test that unauthenticated users viewing a scored homework
        don't see 'no answer submitted' warnings in the rendered HTML.
        """
        self.create_scored_submission_with_answers(
            {
                self.question1: "1",
                self.question4: "3",
            }
        )

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
        """
        Test that authenticated users viewing a scored homework with incomplete
        answers DO see 'no answer submitted' warnings for questions they didn't answer.
        """
        self.create_scored_submission_with_answers(
            {
                self.question1: "1",
            }
        )

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("No answer was submitted for this question", content)


class HomeworkSubmissionsViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create regular user
        self.user = User.objects.create_user(**credentials)

        # Create admin user
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
            is_superuser=True,
        )

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.homework = Homework.objects.create(
            course=self.course,
            title="Test Homework",
            description="Test Homework Description",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.OPEN.value,
            slug="test-homework",
        )

        # Create an enrollment and submission for the regular user
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
            questions_score=10,
            faq_score=2,
            learning_in_public_score=3,
            total_score=15,
        )

    def login_admin(self):
        self.client.login(username="admin@test.com", password="admin123")

    def submissions_url(self):
        return reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def cadmin_submission_edit_url(self):
        return reverse(
            "cadmin_homework_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "submission_id": self.submission.id,
            },
        )

    def create_answered_free_form_question(
        self, text, answer_type, correct_answer, answer_text
    ):
        question = Question.objects.create(
            homework=self.homework,
            text=text,
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=answer_type,
            correct_answer=correct_answer,
        )
        Answer.objects.create(
            submission=self.submission,
            question=question,
            answer_text=answer_text,
        )
        return question

    def assert_compact_submission_context(self, response):
        self.assertNotIn("questions", response.context)
        submissions_data = response.context["submissions_data"]
        self.assertEqual(len(submissions_data), 1)
        item = submissions_data[0]
        self.assertEqual(item["submission"], self.submission)
        self.assertNotIn("answers", item)

    def test_submissions_view_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected"""
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        # Should redirect to homework view with error message
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse(
                "homework",
                kwargs={
                    "course_slug": self.course.slug,
                    "homework_slug": self.homework.slug,
                },
            ),
        )

    def test_submissions_view_regular_user_denied(self):
        """Test that regular users cannot access submissions view"""
        self.client.login(**credentials)
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        # Should redirect to homework view with error message
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse(
                "homework",
                kwargs={
                    "course_slug": self.course.slug,
                    "homework_slug": self.homework.slug,
                },
            ),
        )

    def test_submissions_view_admin_can_access(self):
        """Test that admin users can access submissions view"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "cadmin/homework_submissions.html")

        context = response.context
        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["homework"], self.homework)

        submissions_data = context["submissions_data"]
        self.assertEqual(len(submissions_data), 1)
        self.assertEqual(submissions_data[0]["submission"], self.submission)

    def test_submissions_view_displays_all_submissions(self):
        """Test that all submissions are displayed"""
        # Create another user and submission
        user2 = User.objects.create_user(
            username="user2@test.com",
            email="user2@test.com",
            password="12345",
        )
        enrollment2 = Enrollment.objects.create(
            student=user2,
            course=self.course,
        )
        Submission.objects.create(
            homework=self.homework,
            student=user2,
            enrollment=enrollment2,
            questions_score=8,
            faq_score=1,
            learning_in_public_score=2,
            total_score=11,
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        submissions_data = response.context["submissions_data"]
        self.assertEqual(len(submissions_data), 2)

    def test_admin_link_visible_to_staff(self):
        """Test that the admin link is visible to staff users"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Manage homework in cadmin", content)
        self.assertIn(
            reverse(
                "cadmin_homework_submissions",
                kwargs={
                    "course_slug": self.course.slug,
                    "homework_slug": self.homework.slug,
                },
            ),
            content,
        )

    def test_admin_link_not_visible_to_regular_users(self):
        """Test that the admin link is not visible to regular users"""
        self.client.login(**credentials)
        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("Manage homework in cadmin", content)

    def test_submissions_view_hides_answers_and_links_to_edit_page(self):
        """Test that submissions view keeps answers out of the compact list."""
        self.create_answered_free_form_question(
            text="What is 2+2?",
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="4",
            answer_text="4",
        )
        self.create_answered_free_form_question(
            text="What is the capital of France?",
            answer_type=AnswerTypes.EXACT_STRING.value,
            correct_answer="Paris",
            answer_text="Paris",
        )

        self.login_admin()
        response = self.client.get(self.submissions_url(), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assert_compact_submission_context(response)

        content = response.content.decode("utf-8")
        self.assertIn(self.user.email, content)
        self.assertIn("Score", content)
        self.assertIn("Open", content)
        self.assertIn(self.cadmin_submission_edit_url(), content)
        self.assertNotIn("What is 2+2?", content)
        self.assertNotIn("What is the capital of France?", content)
        self.assertNotIn("Paris", content)

    def test_submissions_view_short_answers_are_hidden(self):
        """Test that short answers are hidden from the compact submissions list."""
        q1 = Question.objects.create(
            homework=self.homework,
            text="Short answer question",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
        )
        
        short_answer = "This is a short answer with less than 1000 characters."
        Answer.objects.create(
            submission=self.submission,
            question=q1,
            answer_text=short_answer,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertNotIn(short_answer, content)
        self.assertNotIn('class="btn btn-sm btn-outline-primary mt-1 toggle-answer"', content)

    def test_submissions_view_long_answers_are_hidden(self):
        """Test that long answers are hidden from the compact submissions list."""
        q1 = Question.objects.create(
            homework=self.homework,
            text="Long answer question",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
        )

        long_answer = "This is a very long answer. " * 100  # Should be over 1000 chars
        Answer.objects.create(
            submission=self.submission,
            question=q1,
            answer_text=long_answer,
        )

        self.client.login(username="admin@test.com", password="admin123")
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertNotIn(long_answer, content)
        self.assertNotIn('title="' + long_answer, content)
        self.assertNotIn("…", content)
