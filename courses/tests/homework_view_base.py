from dataclasses import dataclass

from django.test import Client, TestCase
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


class HomeworkDetailViewTestBase(TestCase):
    def create_course(self):
        return Course.objects.create(
            title="Test Course", slug="test-course"
        )

    def create_homework(self):
        due_date = timezone.now() + timezone.timedelta(days=7)
        return Homework.objects.create(
            course=self.course,
            title="Test Homework",
            description="Test Homework Description",
            due_date=due_date,
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

    def create_initial_questions(self):
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

    def create_remaining_questions(self):
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

    def create_questions(self):
        self.create_initial_questions()
        self.create_remaining_questions()
        self.questions = [
            self.question1,
            self.question2,
            self.question3,
            self.question4,
            self.question5,
            self.question6,
        ]

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
        url = self.homework_url()
        return self.client.get(url)

    def enable_all_optional_submission_fields(self):
        self.homework.homework_url_field = True
        self.homework.learning_in_public_cap = 2
        self.homework.time_spent_lectures_field = True
        self.homework.time_spent_homework_field = True
        self.homework.faq_contribution_field = True
        self.homework.save()
        self.course.homework_problems_comments_field = True
        self.course.save()

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

    def assert_unauthenticated_submission_preview(self, response):
        self.assertContains(response, "Log in to submit this homework")
        self.assertContains(response, "Log in to submit", count=2)
        self.assertContains(response, "You can preview the questions")
        self.assertNotContains(
            response, "Log in</a> to see the status of your submission."
        )

    def assert_submission_fields_hidden(self, response):
        self.assertNotContains(response, "Submission details")
        self.assertNotContains(response, "Homework URL")
        self.assertNotContains(response, "Learning in public links")
        self.assertNotContains(response, "No learning in public links submitted")
        self.assertNotContains(response, "Time spent on lectures")
        self.assertNotContains(response, "Time spent on homework")
        self.assertNotContains(response, "Problems or comments")
        self.assertNotContains(response, "FAQ contribution")

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
        answers_by_question = {
            self.question1: "3",
            self.question2: "Some text",
            self.question3: question3_answer,
            self.question4: "1",
            self.question5: "3.141516",
            self.question6: "1,2,3",
        }
        self.create_answers(answers_by_question)

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
        url = self.homework_url()
        return self.client.post(url, post_data)


    def assert_redirects_to_homework(self, response):
        self.assertEqual(response.status_code, 302)
        url = self.homework_url()
        self.assertEqual(response.url, url)

    def assert_no_enrollment_or_submission(self):
        enrollment_exists = Enrollment.objects.filter(
            student=self.user, course=self.course
        ).exists()
        self.assertFalse(enrollment_exists)
        submission_exists = Submission.objects.filter(
            student=self.user, homework=self.homework
        ).exists()
        self.assertFalse(submission_exists)

    def get_saved_submission(self):
        return Submission.objects.get(
            homework=self.homework, student=self.user
        )

    def assert_enrollment_and_submission_exist(self):
        enrollment_exists = Enrollment.objects.filter(
            student=self.user, course=self.course
        ).exists()
        self.assertTrue(enrollment_exists)
        submission_exists = Submission.objects.filter(
            student=self.user, homework=self.homework
        ).exists()
        self.assertTrue(submission_exists)

    def assert_submission_answers(self, submission, expected_answers):
        answers = Answer.objects.filter(submission=submission)
        answer_count = len(answers)
        expected_answer_count = len(expected_answers)
        self.assertEqual(answer_count, expected_answer_count)
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
        question_answer_count = len(question_answers)
        self.assertEqual(question_answer_count, 6)
        self.assertEqual(question_answers[0][0], self.question1)
        question1_options = self.unselected_options(
            ["Paris", "London", "Berlin"]
        )
        self.assertEqual(
            question_answers[0][1]["options"],
            question1_options,
        )
        self.assertEqual(question_answers[1], (self.question2, {"text": ""}))
        self.assertEqual(question_answers[2][0], self.question3)
        question3_options = self.unselected_options(["2", "3", "4", "5"])
        self.assertEqual(
            question_answers[2][1]["options"],
            question3_options,
        )
        self.assertEqual(question_answers[3][0], self.question4)
        question4_options = self.unselected_options(["5", "6", "7"])
        self.assertEqual(
            question_answers[3][1]["options"],
            question4_options,
        )
        self.assertEqual(question_answers[4], (self.question5, {"text": ""}))
        self.assertEqual(question_answers[5][0], self.question6)
        question6_options = self.unselected_options(
            ["Blue", "White", "Red", "Green"]
        )
        self.assertEqual(
            question_answers[5][1]["options"],
            question6_options,
        )

    def assert_saved_question_answers(self, question_answers):
        question_answer_count = len(question_answers)
        self.assertEqual(question_answer_count, 6)
        self.assertEqual(question_answers[0][0], self.question1)
        question1_options = self.selected_options(
            ["Paris", "London", "Berlin"], {3}
        )
        self.assertEqual(
            question_answers[0][1]["options"],
            question1_options,
        )
        self.assertEqual(question_answers[1][0], self.question2)
        self.assertEqual(question_answers[1][1]["text"], "Some text")
        self.assertEqual(question_answers[2][0], self.question3)
        question3_options = self.selected_options(
            ["2", "3", "4", "5"], {1, 2}
        )
        self.assertEqual(
            question_answers[2][1]["options"],
            question3_options,
        )
        self.assertEqual(question_answers[3][0], self.question4)
        question4_options = self.selected_options(["5", "6", "7"], {1})
        self.assertEqual(
            question_answers[3][1]["options"],
            question4_options,
        )
        self.assertEqual(question_answers[4][0], self.question5)
        self.assertEqual(question_answers[4][1]["text"], "3.141516")
        self.assertEqual(question_answers[5][0], self.question6)
        question6_options = self.selected_options(
            ["Blue", "White", "Red", "Green"], {1, 2, 3}
        )
        self.assertEqual(
            question_answers[5][1]["options"],
            question6_options,
        )

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.create_questions()
