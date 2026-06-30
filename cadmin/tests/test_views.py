from dataclasses import dataclass
from datetime import timedelta
import logging
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    AnswerTypes,
    QuestionTypes,
    Submission,
    Answer,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnswerData:
    submission: Submission
    question: Question
    answer_text: str
    is_correct: bool


@dataclass(frozen=True)
class HomeworkSubmissionEditFixture:
    submission: Submission
    question1: Question
    question2: Question


@dataclass(frozen=True)
class HomeworkSubmissionEditPageFixture:
    enrollment: Enrollment
    submission: Submission
    question1: Question
    question2: Question


@dataclass(frozen=True)
class HomeworkSubmissionScoreExpectation:
    submission: Submission
    questions_score: int
    learning_in_public_score: int
    total_score: int


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class CadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.create_test_users()
        self.create_course_work_items()

    def create_test_users(self):
        self.user = User.objects.create_user(**credentials)
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )

    def create_course_work_items(self):
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

    def login_admin(self):
        self.client.login(username="admin@test.com", password="admin123")

    def create_enrollment(self, student=None):
        return Enrollment.objects.create(
            student=student or self.user,
            course=self.course,
        )

    def create_homework_submission(self, enrollment=None, **overrides):
        defaults = {
            "homework": self.homework,
            "student": self.user,
            "enrollment": enrollment or self.create_enrollment(),
            "questions_score": 0,
            "faq_score": 0,
            "learning_in_public_score": 0,
            "total_score": 0,
        }
        defaults.update(overrides)
        return Submission.objects.create(**defaults)

    def create_free_form_question(self, score=1):
        return Question.objects.create(
            homework=self.homework,
            text="What is 2+2?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="4",
            scores_for_correct_answer=score,
        )

    def create_multiple_choice_question(self, **overrides):
        defaults = {
            "homework": self.homework,
            "text": "What is the capital of France?",
            "question_type": QuestionTypes.MULTIPLE_CHOICE.value,
            "possible_answers": "London\nParis\nBerlin",
            "correct_answer": "2",
            "scores_for_correct_answer": 1,
        }
        defaults.update(overrides)
        return Question.objects.create(**defaults)

    def create_homework_answer_submission(
        self,
        question,
        answer_text,
        student_index,
    ):
        user = User.objects.create_user(
            username=f"student{student_index}@test.com",
            email=f"student{student_index}@test.com",
            password="12345",
        )
        enrollment = self.create_enrollment(student=user)
        submission = Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
        )
        return Answer.objects.create(
            submission=submission,
            question=question,
            answer_text=answer_text,
        )

    def create_homework_answer_frequency(self, question, answer_texts):
        for index, answer_text in enumerate(answer_texts, start=1):
            self.create_homework_answer_submission(
                question,
                answer_text,
                index,
            )

    def create_answer(self, data):
        return Answer.objects.create(
            submission=data.submission,
            question=data.question,
            answer_text=data.answer_text,
            is_correct=data.is_correct,
        )

    def create_submission_with_answer_preview(self, answer_text):
        question = Question.objects.create(
            homework=self.homework,
            text="Explain your answer",
            question_type=QuestionTypes.FREE_FORM.value,
        )
        submission = self.create_homework_submission(total_score=1)
        Answer.objects.create(
            submission=submission,
            question=question,
            answer_text=answer_text,
        )
        return submission

    def homework_submission_edit_url(self, submission):
        return reverse(
            "cadmin_homework_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "submission_id": submission.id,
            },
        )

    def assert_answer_updated(self, submission, question, answer_text):
        answer = Answer.objects.get(submission=submission, question=question)
        self.assertEqual(answer.answer_text, answer_text)
        self.assertTrue(answer.is_correct)

    def create_homework_submission_edit_page_fixture(self):
        enrollment = self.create_enrollment()
        question1 = self.create_free_form_question()
        question2 = self.create_multiple_choice_question()
        submission = self.create_homework_submission(
            enrollment=enrollment,
            learning_in_public_links=["https://example.com/post1"],
            questions_score=2,
            learning_in_public_score=1,
            total_score=3,
        )
        first_answer = AnswerData(
            submission=submission,
            question=question1,
            answer_text="4",
            is_correct=True,
        )
        self.create_answer(first_answer)
        second_answer = AnswerData(
            submission=submission,
            question=question2,
            answer_text="2",
            is_correct=True,
        )
        self.create_answer(second_answer)
        return HomeworkSubmissionEditPageFixture(
            enrollment=enrollment,
            submission=submission,
            question1=question1,
            question2=question2,
        )

    def create_homework_submission_edit_fixture(self):
        enrollment = self.create_enrollment()
        question1 = self.create_free_form_question()
        question2 = self.create_multiple_choice_question()
        submission = self.create_homework_submission(
            enrollment=enrollment,
            learning_in_public_links=["https://example.com/post1"],
            learning_in_public_score=1,
            total_score=1,
        )
        first_answer = AnswerData(
            submission=submission,
            question=question1,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(first_answer)
        second_answer = AnswerData(
            submission=submission,
            question=question2,
            answer_text="1",
            is_correct=False,
        )
        self.create_answer(second_answer)
        return HomeworkSubmissionEditFixture(
            submission=submission,
            question1=question1,
            question2=question2,
        )

    def post_homework_submission_answer_edit(self, fixture):
        self.login_admin()
        return self.client.post(
            self.homework_submission_edit_url(fixture.submission),
            {
                f"answer_{fixture.question1.id}": "4",
                f"answer_{fixture.question2.id}": "2",
                "learning_in_public_links": (
                    "https://example.com/post1\n"
                    "https://example.com/post2"
                ),
            },
        )

    def homework_submission_edit_response(self, submission):
        self.login_admin()
        url = self.homework_submission_edit_url(submission)
        response = self.client.get(url)
        return response

    def assert_homework_submission_edit_page(self, response, fixture):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Homework Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, fixture.question1.text)
        self.assertContains(response, fixture.question2.text)
        self.assertContains(response, 'value="3"')
        self.assertContains(response, "Manage enrollment")
        enrollment_url = reverse(
            "cadmin_enrollment_edit",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": fixture.enrollment.id,
            },
        )
        self.assertContains(response, enrollment_url)

    def assert_homework_submission_scores(self, expectation):
        self.assertEqual(
            expectation.submission.questions_score,
            expectation.questions_score,
        )
        self.assertEqual(
            expectation.submission.learning_in_public_score,
            expectation.learning_in_public_score,
        )
        self.assertEqual(
            expectation.submission.total_score,
            expectation.total_score,
        )

    def assert_learning_in_public_links(self, submission, expected_links):
        self.assertEqual(
            len(submission.learning_in_public_links),
            len(expected_links),
        )
        for expected_link in expected_links:
            self.assertIn(expected_link, submission.learning_in_public_links)

    def cadmin_homework_submissions_url(self):
        return reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def homework_action_url(self, name):
        return reverse(
            name,
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def post_homework_action_to_submissions(self, action_name):
        return self.client.post(
            self.homework_action_url(action_name),
            {"next": self.cadmin_homework_submissions_url()},
        )

    def cadmin_course_url(self):
        return reverse(
            "cadmin_course",
            kwargs={"course_slug": self.course.slug},
        )

    def cadmin_course_response(self):
        self.login_admin()
        return self.client.get(self.cadmin_course_url())

    def assert_homework_submission_actions(self, response):
        self.assertContains(response, self.homework_url())
        self.assertContains(
            response,
            f"/admin/courses/homework/{self.homework.id}/change/",
        )
        self.assertContains(
            response,
            self.homework_action_url("cadmin_homework_set_correct_answers"),
        )
        self.assertContains(
            response,
            self.homework_action_url("cadmin_homework_clear_correct_answers"),
        )
        self.assertContains(
            response,
            self.homework_action_url("cadmin_homework_score"),
        )
        self.assertContains(response, "Select most frequent answer")
        self.assertContains(response, "Clear correct answers")
        self.assertContains(response, "Score submissions")

    def homework_url(self):
        return reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def test_homework_submissions_redirect_from_courses(self):
        """Test that homework submissions view redirects to cadmin"""
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
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_cadmin_homework_submissions_staff_allowed(self):
        """Test that staff users can view homework submissions in cadmin"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.homework.title)

    def test_cadmin_homework_submissions_hides_answer_previews(self):
        """Submission lists stay compact and link to the edit page."""
        answer_text = (
            "This long answer should only be visible after opening the submission."
        )
        submission = self.create_submission_with_answer_preview(answer_text)

        self.login_admin()

        response = self.client.get(self.cadmin_homework_submissions_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "This long answer should only")
        self.assertContains(response, "Open")
        self.assertContains(
            response,
            self.homework_submission_edit_url(submission),
        )

    def test_cadmin_homework_submissions_shows_course_actions(self):
        """Homework submissions page exposes the same homework actions as course admin."""
        self.login_admin()

        response = self.client.get(self.cadmin_homework_submissions_url())

        self.assertEqual(response.status_code, 200)
        self.assert_homework_submission_actions(response)

    def test_homework_actions_can_redirect_back_to_homework_submissions(
        self,
    ):
        self.login_admin()
        submissions_url = self.cadmin_homework_submissions_url()

        response = self.post_homework_action_to_submissions(
            "cadmin_homework_set_correct_answers"
        )
        self.assertRedirects(response, submissions_url)

        response = self.post_homework_action_to_submissions(
            "cadmin_homework_clear_correct_answers"
        )
        self.assertRedirects(response, submissions_url)

    def test_homework_actions_ignore_unsafe_next_redirects(self):
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        action_url = reverse(
            "cadmin_homework_set_correct_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(
            action_url, {"next": "https://example.com/"}
        )

        self.assertRedirects(
            response,
            reverse(
                "cadmin_course",
                kwargs={"course_slug": self.course.slug},
            ),
        )

    def test_enrollments_search_finds_records_beyond_first_page(self):
        """Enrollment search is server-side, not limited to the visible page."""
        for index in range(30):
            user = User.objects.create_user(
                username=f"student-{index:02d}",
                email=f"student-{index:02d}@example.com",
                password="test",
            )
            Enrollment.objects.create(
                student=user,
                course=self.course,
                display_name=f"Student {index:02d}",
            )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse(
                "cadmin_enrollments",
                kwargs={"course_slug": self.course.slug},
            ),
            {"q": "student-29"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student-29@example.com")
        self.assertNotContains(response, "student-00@example.com")

    def test_homework_submission_search_finds_records_beyond_first_page(
        self,
    ):
        """Homework submission search is server-side across all submissions."""
        from courses.models import Submission

        for index in range(30):
            user = User.objects.create_user(
                username=f"hw-student-{index:02d}",
                email=f"hw-student-{index:02d}@example.com",
                password="test",
            )
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            Submission.objects.create(
                homework=self.homework,
                student=user,
                enrollment=enrollment,
                total_score=index,
            )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse(
                "cadmin_homework_submissions",
                kwargs={
                    "course_slug": self.course.slug,
                    "homework_slug": self.homework.slug,
                },
            ),
            {"q": "hw-student-29"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hw-student-29@example.com")
        self.assertNotContains(response, "hw-student-00@example.com")

    @patch("cadmin.views.homework.send_homework_score_notification")
    def test_homework_score_shows_message(
        self, send_score_notification
    ):
        """Test that scoring homework shows a message on the course admin page"""
        self.homework.due_date = timezone.now() - timedelta(hours=1)
        self.homework.save(update_fields=["due_date"])
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_homework_score",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.post(url, follow=True)

        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse(
                "cadmin_course",
                kwargs={"course_slug": self.course.slug},
            ),
        )

        # Check that a message was added
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        send_score_notification.assert_called_once_with(self.homework)

    def test_course_admin_shows_most_frequent_answer_action(self):
        self.create_homework_submission()

        response = self.cadmin_course_response()

        self.assertEqual(response.status_code, 200)
        self.assert_homework_submission_actions(response)

    def test_homework_set_correct_answers_uses_most_frequent_answer(
        self,
    ):
        question = self.create_multiple_choice_question(
            text="Pick one",
            possible_answers="A\nB\nC",
            correct_answer="",
        )
        self.create_homework_answer_frequency(question, ["2", "2", "1"])

        self.login_admin()
        response = self.client.post(
            self.homework_action_url(
                "cadmin_homework_set_correct_answers"
            ),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        question.refresh_from_db()
        self.assertEqual(question.correct_answer, "2")
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    def test_homework_clear_correct_answers_removes_all_correct_answers(
        self,
    ):
        first_question = self.create_multiple_choice_question(
            text="Pick one",
            possible_answers="A\nB\nC",
            correct_answer="2",
        )
        second_question = Question.objects.create(
            homework=self.homework,
            text="Explain",
            question_type=QuestionTypes.FREE_FORM.value,
            correct_answer="expected answer",
        )

        self.login_admin()
        response = self.client.post(
            self.homework_action_url(
                "cadmin_homework_clear_correct_answers"
            ),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        first_question.refresh_from_db()
        second_question.refresh_from_db()
        self.assertEqual(first_question.correct_answer, "")
        self.assertEqual(second_question.correct_answer, "")
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    def test_homework_submission_edit_get(self):
        """Test that staff users can access the homework submission edit page"""
        fixture = self.create_homework_submission_edit_page_fixture()

        response = self.homework_submission_edit_response(fixture.submission)

        self.assert_homework_submission_edit_page(response, fixture)

    def test_homework_submission_edit_post_updates_answers(self):
        """Test that editing homework answers updates the submission correctly"""
        fixture = self.create_homework_submission_edit_fixture()

        response = self.post_homework_submission_answer_edit(fixture)

        self.assertEqual(response.status_code, 302)
        fixture.submission.refresh_from_db()
        expected_scores = HomeworkSubmissionScoreExpectation(
            submission=fixture.submission,
            questions_score=2,
            learning_in_public_score=2,
            total_score=4,
        )
        self.assert_homework_submission_scores(expected_scores)
        self.assert_answer_updated(fixture.submission, fixture.question1, "4")
        self.assert_answer_updated(fixture.submission, fixture.question2, "2")
        self.assert_learning_in_public_links(
            fixture.submission,
            [
                "https://example.com/post1",
                "https://example.com/post2",
            ],
        )

    def test_homework_submission_edit_updates_faq_entry_and_score(self):
        """Test that staff can edit FAQ contribution fields."""
        question = self.create_free_form_question(score=10)
        submission = self.create_homework_submission()
        answer = AnswerData(
            submission=submission,
            question=question,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(answer)

        self.login_admin()
        faq_entry = "https://gist.github.com/example/not-validated-here"

        response = self.client.post(
            self.homework_submission_edit_url(submission),
            {
                f"answer_{question.id}": "4",
                "learning_in_public_links": "",
                "faq_contribution_url": faq_entry,
                "faq_score": "3",
            },
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.faq_contribution_url, faq_entry)
        self.assertEqual(submission.faq_score, 3)
        self.assertEqual(submission.total_score, 13)

    def test_homework_submission_edit_triggers_leaderboard_update(self):
        """Test that editing homework submission triggers leaderboard recalculation if score changes"""
        enrollment = self.create_enrollment()
        question = self.create_free_form_question(score=10)
        submission = self.create_homework_submission(
            enrollment=enrollment,
        )
        answer = AnswerData(
            submission=submission,
            question=question,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(answer)

        enrollment.total_score = 0
        enrollment.position_on_leaderboard = 999
        enrollment.save()

        self.login_admin()
        response = self.client.post(
            self.homework_submission_edit_url(submission),
            {
                f"answer_{question.id}": "4",
                "learning_in_public_links": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.total_score, 10)
