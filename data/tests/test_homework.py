"""
Tests for homework-related data API views.

Tests for homework_data_view and homework_content_view.
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


class HomeworkContentAPITestCase(TestCase):
    """Tests for the homework_content_view endpoint."""

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

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            description="Test Description",
            due_date="2025-03-15T23:59:59Z",
            state="CL",
        )

        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

        self.url = reverse(
            "data_homework_content",
            kwargs={"course_slug": self.course.slug, "homework_slug": self.homework.slug}
        )

    def test_get_homework_content_returns_homework_and_questions(self):
        """Test GET returns homework details and questions."""
        # Create some questions
        Question.objects.create(
            homework=self.homework,
            text="What is 2+2?",
            question_type="MC",
            answer_type="INT",
            possible_answers="3\n4\n5",
            correct_answer="2",
            scores_for_correct_answer=1,
        )
        Question.objects.create(
            homework=self.homework,
            text="Explain your answer",
            question_type="FF",
            answer_type="CTS",
            correct_answer="4",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(result["course"], "test-course")
        self.assertEqual(result["homework"]["slug"], "test-homework")
        self.assertEqual(result["homework"]["title"], "Test Homework")
        self.assertEqual(result["homework"]["description"], "Test Description")
        self.assertEqual(result["homework"]["state"], "CL")
        self.assertEqual(result["homework"]["learning_in_public_cap"], 7)
        self.assertTrue(result["homework"]["homework_url_field"])
        self.assertTrue(result["homework"]["time_spent_lectures_field"])
        self.assertTrue(result["homework"]["time_spent_homework_field"])
        self.assertTrue(result["homework"]["faq_contribution_field"])

        # Check questions
        self.assertEqual(len(result["questions"]), 2)
        self.assertEqual(result["questions"][0]["text"], "What is 2+2?")
        self.assertEqual(result["questions"][0]["question_type"], "MC")
        self.assertEqual(result["questions"][0]["possible_answers"], ["3", "4", "5"])
        self.assertEqual(result["questions"][1]["text"], "Explain your answer")

    def test_get_homework_content_empty_questions(self):
        """Test GET returns empty questions list when no questions exist."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["questions"]), 0)

    def test_post_creates_questions(self):
        """Test POST creates questions for homework."""
        data = {
            "questions": [
                {
                    "text": "What is the capital of France?",
                    "question_type": "MC",
                    "answer_type": "EXS",
                    "possible_answers": ["London", "Paris", "Berlin"],
                    "correct_answer": "2",
                    "scores_for_correct_answer": 2,
                },
                {
                    "text": "Describe Paris",
                    "question_type": "FL",
                    "answer_type": "ANY",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["created_questions"]), 2)
        self.assertEqual(result["created_questions"][0]["text"], "What is the capital of France?")
        self.assertEqual(len(result["errors"]), 0)

        # Verify questions were created in DB
        self.assertEqual(Question.objects.count(), 2)

    def test_post_empty_questions_list(self):
        """Test POST with empty questions list."""
        data = {"questions": []}

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_questions"]), 0)

    def test_post_no_questions_key(self):
        """Test POST without questions key (defaults to empty list)."""
        data = {}

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_questions"]), 0)

    def test_post_all_question_types(self):
        """Test POST with all question types."""
        data = {
            "questions": [
                {
                    "text": "Multiple Choice",
                    "question_type": "MC",
                    "answer_type": "INT",
                    "possible_answers": ["1", "2", "3"],
                    "correct_answer": "1",
                },
                {
                    "text": "Free Form",
                    "question_type": "FF",
                    "answer_type": "CTS",
                    "correct_answer": "answer",
                },
                {
                    "text": "Free Form Long",
                    "question_type": "FL",
                    "answer_type": "ANY",
                },
                {
                    "text": "Checkboxes",
                    "question_type": "CB",
                    "answer_type": "INT",
                    "possible_answers": ["A", "B", "C"],
                    "correct_answer": "1,2",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_questions"]), 4)

        # Verify in DB
        mc_question = Question.objects.get(text="Multiple Choice")
        self.assertEqual(mc_question.question_type, "MC")

        ff_question = Question.objects.get(text="Free Form")
        self.assertEqual(ff_question.question_type, "FF")

        fl_question = Question.objects.get(text="Free Form Long")
        self.assertEqual(fl_question.question_type, "FL")

        cb_question = Question.objects.get(text="Checkboxes")
        self.assertEqual(cb_question.question_type, "CB")

    def test_post_all_answer_types(self):
        """Test POST with all answer types."""
        data = {
            "questions": [
                {"text": "ANY", "question_type": "FF", "answer_type": "ANY"},
                {"text": "FLT", "question_type": "FF", "answer_type": "FLT"},
                {"text": "INT", "question_type": "FF", "answer_type": "INT"},
                {"text": "EXS", "question_type": "FF", "answer_type": "EXS"},
                {"text": "CTS", "question_type": "FF", "answer_type": "CTS"},
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["created_questions"]), 5)

    def test_post_default_values(self):
        """Test POST uses default values for optional fields."""
        data = {
            "questions": [
                {
                    "text": "Minimal question",
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        question = Question.objects.first()
        self.assertEqual(question.text, "Minimal question")
        self.assertEqual(question.question_type, "FF")  # default
        self.assertIsNone(question.answer_type)
        self.assertEqual(question.possible_answers, "")
        self.assertEqual(question.correct_answer, "")
        self.assertEqual(question.scores_for_correct_answer, 1)  # default

    def test_nonexistent_course(self):
        """Test with non-existent course."""
        url = reverse(
            "data_homework_content",
            kwargs={"course_slug": "nonexistent", "homework_slug": "hw"}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertEqual(result["error"], "Course or homework not found")

    def test_nonexistent_homework(self):
        """Test with non-existent homework."""
        url = reverse(
            "data_homework_content",
            kwargs={"course_slug": self.course.slug, "homework_slug": "nonexistent"}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertEqual(result["error"], "Course or homework not found")

    def test_wrong_http_method(self):
        """Test with wrong HTTP method."""
        response = self.client.put(self.url)
        self.assertEqual(response.status_code, 405)

    def test_invalid_json(self):
        """Test POST with invalid JSON."""
        response = self.client.post(
            self.url, "invalid json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertEqual(result["error"], "Invalid JSON")

    def test_no_authentication(self):
        """Test without authentication token."""
        unauth_client = Client()
        response = unauth_client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_post_partial_success(self):
        """Test POST continues even if some questions fail."""
        data = {
            "questions": [
                {
                    "text": "Valid question",
                    "question_type": "FF",
                },
                {
                    "text": "Another valid question",
                    "question_type": "FL",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Both should succeed since they're valid
        self.assertEqual(len(result["created_questions"]), 2)
        self.assertEqual(len(result["errors"]), 0)

    def test_post_update_state_from_closed_to_open(self):
        """Test POST updates homework state from closed to open."""
        self.assertEqual(self.homework.state, "CL")

        data = {
            "questions": [
                {"text": "New question", "question_type": "FF"}
            ],
            "state": "OP"
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertIn("homework_state", result)
        self.assertEqual(result["homework_state"]["old"], "CL")
        self.assertEqual(result["homework_state"]["new"], "OP")

        # Verify state was updated in DB
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "OP")

    def test_post_update_state_only(self):
        """Test POST can update state without adding questions."""
        self.assertEqual(self.homework.state, "CL")

        data = {"state": "OP"}

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(result["homework_state"]["old"], "CL")
        self.assertEqual(result["homework_state"]["new"], "OP")
        self.assertEqual(len(result["created_questions"]), 0)

        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "OP")

    def test_post_update_state_invalid(self):
        """Test POST with invalid state returns error."""
        data = {
            "questions": [{"text": "Question", "question_type": "FF"}],
            "state": "INVALID"
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertIn("Invalid state", result["error"])

    def test_post_update_all_states(self):
        """Test POST can update to all valid states."""
        # CL -> OP
        data = {"state": "OP"}
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "OP")

        # OP -> SC
        data = {"state": "SC"}
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "SC")

        # SC -> CL
        data = {"state": "CL"}
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "CL")
