"""
Tests for homework-related data API views.

Tests for homework_data_view.
The old HomeworkContentAPITestCase has been
replaced by tests in api/tests/ for the new /api/ endpoints.
"""

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import Answer
from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    Submission,
)
from courses.tests.util import join_possible_answers


class HomeworkDataAPITestCase(TestCase):
    """Tests for homework_data_view endpoint."""

    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="testuser@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)
        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
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

    def create_submission(self, homework):
        return Submission.objects.create(
            homework=homework,
            student=self.user,
            enrollment=self.enrollment,
            homework_link="https://github.com/DataTalksClub",
            faq_contribution_url="https://github.com/DataTalksClub/faq/pull/266",
        )

    def create_question(self, homework):
        possible_answer_options = ["Paris", "London", "Berlin"]
        possible_answers = join_possible_answers(possible_answer_options)
        return Question.objects.create(
            homework=homework,
            text="What is the capital of France?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=possible_answers,
            correct_answer="1",
        )

    def homework_export_url(self, homework):
        return reverse(
            "api_homework_submissions_export",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": homework.slug,
            },
        )

    def expected_course_data(self):
        return {
            "id": self.course.id,
            "slug": self.course.slug,
            "title": self.course.title,
            "description": self.course.description,
            "social_media_hashtag": self.course.social_media_hashtag,
            "faq_document_url": self.course.faq_document_url,
        }

    def expected_homework_data(self, homework):
        return {
            "id": homework.id,
            "slug": homework.slug,
            "course": self.course.id,
            "title": homework.title,
            "description": homework.description,
            "learning_in_public_cap": homework.learning_in_public_cap,
            "homework_url_field": homework.homework_url_field,
            "time_spent_lectures_field": (
                homework.time_spent_lectures_field
            ),
            "time_spent_homework_field": (
                homework.time_spent_homework_field
            ),
            "faq_contribution_field": homework.faq_contribution_field,
            "state": homework.state,
        }

    def expected_submission_data(self, submission):
        return {
            "student_id": self.user.id,
            "homework_link": submission.homework_link,
            "learning_in_public_links": (
                submission.learning_in_public_links
            ),
            "time_spent_lectures": submission.time_spent_lectures,
            "time_spent_homework": submission.time_spent_homework,
            "problems_comments": submission.problems_comments,
            "faq_contribution_url": submission.faq_contribution_url,
            "questions_score": submission.questions_score,
            "faq_score": submission.faq_score,
            "learning_in_public_score": (
                submission.learning_in_public_score
            ),
            "total_score": submission.total_score,
        }

    def expected_answer_data(self, question, answer):
        return {
            "question_id": question.id,
            "answer_text": answer.answer_text,
            "is_correct": True,
        }

    def assert_fields(self, actual, expected):
        for field, expected_value in expected.items():
            self.assertEqual(actual[field], expected_value)

    def assert_course_data(self, actual_result):
        expected_course = self.expected_course_data()
        self.assert_fields(actual_result["course"], expected_course)

    def assert_homework_data(self, actual_result, homework):
        expected_homework = self.expected_homework_data(homework)
        self.assert_fields(
            actual_result["homework"], expected_homework
        )

    def assert_submission_data(self, actual_result, submission):
        submission_count = len(actual_result["submissions"])
        self.assertEqual(submission_count, 1)
        actual_submission = actual_result["submissions"][0]
        expected_submission = self.expected_submission_data(submission)
        self.assert_fields(actual_submission, expected_submission)
        return actual_submission

    def assert_answer_data(self, actual_submission, question, answer):
        answer_count = len(actual_submission["answers"])
        self.assertEqual(answer_count, 1)
        expected_answer = self.expected_answer_data(question, answer)
        self.assert_fields(
            actual_submission["answers"][0],
            expected_answer,
        )

    def test_homework_data_view(self):
        homework = self.create_homework()
        submission = self.create_submission(homework)
        question = self.create_question(homework)
        answer = Answer.objects.create(
            submission=submission,
            question=question,
            answer_text="1",
            is_correct=True,
        )

        export_url = self.homework_export_url(homework)
        response = self.client.get(export_url)

        self.assertEqual(response.status_code, 200)
        actual_result = response.json()
        self.assert_course_data(actual_result)
        self.assert_homework_data(actual_result, homework)
        actual_submission = self.assert_submission_data(
            actual_result,
            submission,
        )
        self.assert_answer_data(actual_submission, question, answer)
