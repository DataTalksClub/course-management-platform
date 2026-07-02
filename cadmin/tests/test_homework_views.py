from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Enrollment,
    Question,
    QuestionTypes,
)
from cadmin.tests.homework_view_base import HomeworkCadminViewTestBase


class HomeworkCadminSubmissionViewTests(HomeworkCadminViewTestBase):
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

        submissions_url = self.cadmin_homework_submissions_url()
        response = self.client.get(submissions_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "This long answer should only")
        self.assertContains(response, "Open")
        edit_url = self.homework_submission_edit_url(submission)
        self.assertContains(
            response,
            edit_url,
        )

    def test_cadmin_homework_submissions_shows_course_actions(self):
        """Homework submissions page exposes the same homework actions as course admin."""
        self.login_admin()

        submissions_url = self.cadmin_homework_submissions_url()
        response = self.client.get(submissions_url)

        self.assertEqual(response.status_code, 200)
        self.assert_homework_submission_actions(response)


class HomeworkCadminActionRedirectTests(HomeworkCadminViewTestBase):
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

        course_url = self.cadmin_course_url()
        self.assertRedirects(response, course_url)


class HomeworkCadminSearchTests(HomeworkCadminViewTestBase):
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
        enrollments_url = reverse(
            "cadmin_enrollments",
            kwargs={"course_slug": self.course.slug},
        )
        response = self.client.get(
            enrollments_url,
            {"q": "student-29"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student-29@example.com")
        self.assertNotContains(response, "student-00@example.com")

    def test_homework_submission_search_finds_records_beyond_first_page(
        self,
    ):
        """Homework submission search is server-side across all submissions."""
        self.create_homework_search_submissions(30)

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        submissions_url = self.cadmin_homework_submissions_url()
        response = self.client.get(
            submissions_url,
            {"q": "hw-student-29"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hw-student-29@example.com")
        self.assertNotContains(response, "hw-student-00@example.com")


class HomeworkCadminScoringActionTests(HomeworkCadminViewTestBase):
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
        course_url = self.cadmin_course_url()
        self.assertRedirects(response, course_url)

        # Check that a message was added
        messages = list(response.context["messages"])
        messages_count = len(messages)
        self.assertEqual(messages_count, 1)
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
        action_url = self.homework_action_url(
            "cadmin_homework_set_correct_answers"
        )
        response = self.client.post(
            action_url,
            follow=True,
        )

        course_url = self.cadmin_course_url()
        self.assertRedirects(response, course_url)
        question.refresh_from_db()
        self.assertEqual(question.correct_answer, "2")
        messages = list(response.context["messages"])
        messages_count = len(messages)
        self.assertEqual(messages_count, 1)

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
        action_url = self.homework_action_url(
            "cadmin_homework_clear_correct_answers"
        )
        response = self.client.post(
            action_url,
            follow=True,
        )

        course_url = self.cadmin_course_url()
        self.assertRedirects(response, course_url)
        first_question.refresh_from_db()
        second_question.refresh_from_db()
        self.assertEqual(first_question.correct_answer, "")
        self.assertEqual(second_question.correct_answer, "")
        messages = list(response.context["messages"])
        messages_count = len(messages)
        self.assertEqual(messages_count, 1)
