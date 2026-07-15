from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from courses.models import (
    HomeworkState,
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
    def test_homework_score_shows_message_without_notifying(
        self, send_score_notification
    ):
        """Scoring shows a message but does not email students.

        Notifications are a separate action so a slow Datamailer send
        cannot take the scoring request down with it.
        """
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
        send_score_notification.assert_not_called()

    @patch("cadmin.views.homework.send_homework_score_notification")
    def test_homework_notify_scores_sends_notification(
        self, send_score_notification
    ):
        """The notify action emails students for a scored homework."""
        self.homework.state = HomeworkState.SCORED.value
        self.homework.save(update_fields=["state"])
        self.login_admin()
        url = reverse(
            "cadmin_homework_notify_scores",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(url, follow=True)

        self.assertRedirects(response, self.cadmin_course_url())
        send_score_notification.assert_called_once_with(self.homework)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    @patch("cadmin.views.homework.send_homework_score_notification")
    def test_homework_notify_scores_requires_scored_homework(
        self, send_score_notification
    ):
        """Notifying an unscored homework warns and sends nothing."""
        self.homework.state = HomeworkState.OPEN.value
        self.homework.save(update_fields=["state"])
        self.login_admin()
        url = reverse(
            "cadmin_homework_notify_scores",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(url, follow=True)

        self.assertRedirects(response, self.cadmin_course_url())
        send_score_notification.assert_not_called()
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

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


class HomeworkCadminRescoreTests(HomeworkCadminViewTestBase):
    def setUp(self):
        super().setUp()
        self.homework.due_date = timezone.now() - timedelta(hours=1)
        self.homework.state = HomeworkState.SCORED.value
        self.homework.save()
        self.create_free_form_question()

    def test_course_admin_shows_rescore_for_scored_homework(self):
        response = self.cadmin_course_response()
        self.assertEqual(response.status_code, 200)
        rescore_url = self.homework_action_url("cadmin_homework_rescore")
        self.assertContains(response, rescore_url)
        self.assertContains(response, "rescore")

    def test_course_admin_hides_rescore_for_unscored_homework(self):
        self.homework.state = HomeworkState.OPEN.value
        self.homework.save()

        response = self.cadmin_course_response()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Rescore")

    def test_course_admin_shows_edit_answers_link(self):
        response = self.cadmin_course_response()
        self.assertEqual(response.status_code, 200)
        answers_url = self.homework_action_url("cadmin_homework_answers")
        self.assertContains(response, answers_url)
        self.assertContains(response, "Edit answers")

    def test_rescore_reruns_scoring(self):
        self.login_admin()
        url = reverse(
            "cadmin_homework_rescore",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.post(url, follow=True)

        course_url = self.cadmin_course_url()
        self.assertRedirects(response, course_url)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("scored", messages[0].message.lower())

    def test_rescore_warns_for_unscored_homework(self):
        self.homework.state = HomeworkState.OPEN.value
        self.homework.save()
        self.login_admin()
        url = reverse(
            "cadmin_homework_rescore",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.post(url, follow=True)

        course_url = self.cadmin_course_url()
        self.assertRedirects(response, course_url)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("not scored", messages[0].message.lower())


class HomeworkCadminAnswersTests(HomeworkCadminViewTestBase):
    def setUp(self):
        super().setUp()
        self.question1 = self.create_free_form_question()
        self.question2 = self.create_multiple_choice_question()

    def test_answers_page_renders(self):
        self.login_admin()
        url = reverse(
            "cadmin_homework_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Answers: Test Homework")
        self.assertContains(response, self.question1.text)
        self.assertContains(response, self.question2.text)
        self.assertContains(response, "Correct answer")
        self.assertContains(response, "Answer type")

    def test_answers_page_shows_rescore_button_for_scored_homework(self):
        self.homework.state = HomeworkState.SCORED.value
        self.homework.save()
        self.login_admin()
        url = reverse(
            "cadmin_homework_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)
        self.assertContains(response, "rescore")

    def test_answers_page_hides_rescore_button_for_unscored_homework(self):
        self.login_admin()
        url = reverse(
            "cadmin_homework_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)
        self.assertNotContains(response, "Rescore")

    def test_answers_page_shows_empty_state(self):
        Question.objects.filter(homework=self.homework).delete()
        self.login_admin()
        url = reverse(
            "cadmin_homework_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)
        self.assertContains(response, "No questions found")

    def test_answers_update_saves_correct_answers(self):
        self.login_admin()
        url = reverse(
            "cadmin_homework_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.post(url, {
            f"correct_answer_{self.question1.id}": "99",
            f"answer_type_{self.question1.id}": "INT",
            f"correct_answer_{self.question2.id}": "3",
            f"answer_type_{self.question2.id}": "",
        }, follow=True)

        course_url = self.cadmin_course_url()
        self.assertRedirects(response, course_url)
        self.question1.refresh_from_db()
        self.question2.refresh_from_db()
        self.assertEqual(self.question1.correct_answer, "99")
        self.assertEqual(self.question1.answer_type, "INT")
        self.assertEqual(self.question2.correct_answer, "3")
        self.assertIsNone(self.question2.answer_type)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("updated", messages[0].message.lower())
