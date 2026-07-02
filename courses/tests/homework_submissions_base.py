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


credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


@dataclass(frozen=True)
class AnsweredFreeFormQuestionData:
    text: str
    answer_type: str
    correct_answer: str
    answer_text: str


class HomeworkSubmissionsViewTestBase(TestCase):
    def create_admin_user(self):
        return User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
            is_superuser=True,
        )

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

    def create_enrollment(self):
        return Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

    def create_submission(self):
        return Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
            questions_score=10,
            faq_score=2,
            learning_in_public_score=3,
            total_score=15,
        )

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.admin_user = self.create_admin_user()
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.enrollment = self.create_enrollment()
        self.submission = self.create_submission()

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

    def homework_url(self):
        return reverse(
            "homework",
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

    def cadmin_homework_submissions_url(self):
        return reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def create_answered_free_form_question(self, data):
        question = Question.objects.create(
            homework=self.homework,
            text=data.text,
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=data.answer_type,
            correct_answer=data.correct_answer,
        )
        Answer.objects.create(
            submission=self.submission,
            question=question,
            answer_text=data.answer_text,
        )
        return question

    def create_second_submission(self):
        user = User.objects.create_user(
            username="user2@test.com",
            email="user2@test.com",
            password="12345",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
        )
        return Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
            questions_score=8,
            faq_score=1,
            learning_in_public_score=2,
            total_score=11,
        )

    def create_answer(self, text, answer_text):
        question = Question.objects.create(
            homework=self.homework,
            text=text,
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
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

    def create_hidden_answer_questions(self):
        arithmetic_question = AnsweredFreeFormQuestionData(
            text="What is 2+2?",
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="4",
            answer_text="4",
        )
        self.create_answered_free_form_question(arithmetic_question)
        capital_question = AnsweredFreeFormQuestionData(
            text="What is the capital of France?",
            answer_type=AnswerTypes.EXACT_STRING.value,
            correct_answer="Paris",
            answer_text="Paris",
        )
        self.create_answered_free_form_question(capital_question)

    def get_admin_submissions_response(self):
        self.login_admin()

        url = self.submissions_url()
        return self.client.get(url, follow=True)

    def assert_compact_submission_content(self, content):
        self.assertIn(self.user.email, content)
        self.assertIn("Score", content)
        self.assertIn("Open", content)
        edit_url = self.cadmin_submission_edit_url()
        self.assertIn(edit_url, content)
        self.assertNotIn("What is 2+2?", content)
        self.assertNotIn("What is the capital of France?", content)
        self.assertNotIn("Paris", content)
