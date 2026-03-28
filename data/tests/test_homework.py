"""
Tests for homework-related data API views.

Tests for homework_data_view.
The old HomeworkContentAPITestCase (for /data/<slug>/homework/<hw>/content) has been
replaced by tests in api/tests/ for the new /api/ endpoints.
"""

import json

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Homework,
    Submission,
    Enrollment,
    Question,
    QuestionTypes,
    HomeworkState,
    Answer,
)

from accounts.models import CustomUser, Token

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

    def test_homework_data_view(self):
        self.homework = Homework.objects.create(
            course=self.course,
            title="Test Homework",
            description="Test Homework Description",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.OPEN.value,
            slug="test-homework",
        )

        self.submission = Submission(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
            homework_link="https://github.com/DataTalksClub",
        )

        self.submission.save()

        self.question = Question.objects.create(
            homework=self.homework,
            text="What is the capital of France?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=join_possible_answers(
                ["Paris", "London", "Berlin"]
            ),
            correct_answer="1",
        )
        self.question.save()

        self.answer = Answer.objects.create(
            submission=self.submission,
            question=self.question,
            answer_text="1",
            is_correct=True,
        )

        url = reverse(
            "data_homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        actual_result = response.json()

        # Test course fields
        self.assertEqual(actual_result["course"]["id"], self.course.id)
        self.assertEqual(
            actual_result["course"]["slug"], self.course.slug
        )
        self.assertEqual(
            actual_result["course"]["title"], self.course.title
        )
        self.assertEqual(
            actual_result["course"]["description"],
            self.course.description,
        )
        self.assertEqual(
            actual_result["course"]["social_media_hashtag"],
            self.course.social_media_hashtag,
        )
        self.assertEqual(
            actual_result["course"]["faq_document_url"],
            self.course.faq_document_url,
        )

        # Test homework fields
        self.assertEqual(
            actual_result["homework"]["id"], self.homework.id
        )
        self.assertEqual(
            actual_result["homework"]["slug"], self.homework.slug
        )
        self.assertEqual(
            actual_result["homework"]["course"], self.course.id
        )
        self.assertEqual(
            actual_result["homework"]["title"], self.homework.title
        )
        self.assertEqual(
            actual_result["homework"]["description"],
            self.homework.description,
        )
        self.assertEqual(
            actual_result["homework"]["learning_in_public_cap"],
            self.homework.learning_in_public_cap,
        )
        self.assertEqual(
            actual_result["homework"]["homework_url_field"],
            self.homework.homework_url_field,
        )
        self.assertEqual(
            actual_result["homework"]["time_spent_lectures_field"],
            self.homework.time_spent_lectures_field,
        )
        self.assertEqual(
            actual_result["homework"]["time_spent_homework_field"],
            self.homework.time_spent_homework_field,
        )
        self.assertEqual(
            actual_result["homework"]["faq_contribution_field"],
            self.homework.faq_contribution_field,
        )
        self.assertEqual(
            actual_result["homework"]["state"], self.homework.state
        )

        # Test submissions fields
        self.assertEqual(len(actual_result["submissions"]), 1)
        submission = actual_result["submissions"][0]
        self.assertEqual(submission["student_id"], self.user.id)
        self.assertEqual(
            submission["homework_link"], self.submission.homework_link
        )
        self.assertEqual(
            submission["learning_in_public_links"],
            self.submission.learning_in_public_links,
        )
        self.assertEqual(
            submission["time_spent_lectures"],
            self.submission.time_spent_lectures,
        )
        self.assertEqual(
            submission["time_spent_homework"],
            self.submission.time_spent_homework,
        )
        self.assertEqual(
            submission["problems_comments"],
            self.submission.problems_comments,
        )
        self.assertEqual(
            submission["faq_contribution"],
            self.submission.faq_contribution,
        )
        self.assertEqual(
            submission["questions_score"],
            self.submission.questions_score,
        )
        self.assertEqual(
            submission["faq_score"], self.submission.faq_score
        )
        self.assertEqual(
            submission["learning_in_public_score"],
            self.submission.learning_in_public_score,
        )
        self.assertEqual(
            submission["total_score"], self.submission.total_score
        )

        # Test answers fields
        self.assertEqual(len(submission["answers"]), 1)

        answer = submission["answers"][0]
        self.assertEqual(answer["question_id"], self.question.id)
        self.assertEqual(answer["answer_text"], self.answer.answer_text)
        self.assertEqual(answer["is_correct"], True)
