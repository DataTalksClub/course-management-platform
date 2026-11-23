"""Regression tests for the cadmin "Correct answers" panel.

Reported bug (2026-11-23): ticking correct answers on the homework submissions
page and clicking "Save answers" showed a success banner, but afterwards every
checkbox was cleared. The panel posts a hidden empty ``correct_answer_<id>``
input next to the checkboxes, so the browser payload for a choice question is
``["", "1", "3"]``.
"""

import json
import re

from django.urls import reverse

from cadmin.tests.homework_view_base import HomeworkCadminViewTestBase
from courses.models import Question, QuestionTypes


class CorrectAnswersPanelTestBase(HomeworkCadminViewTestBase):
    def setUp(self):
        super().setUp()
        self.free_form = self.create_free_form_question()
        self.checkboxes = Question.objects.create(
            homework=self.homework,
            text="Select all that apply",
            question_type=QuestionTypes.CHECKBOXES.value,
            possible_answers="Alpha\nBeta\nGamma",
            correct_answer="",
            scores_for_correct_answer=1,
        )
        self.multiple_choice = self.create_multiple_choice_question(
            correct_answer="",
        )

    def submissions_url(self):
        return reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def checked_options(self, html, question):
        pattern = re.compile(
            r'<input type="checkbox"[^>]*?id="correct_answer_'
            + str(question.id)
            + r'_(\d+)"[^>]*?>',
            re.S,
        )
        checked = set()
        for match in pattern.finditer(html):
            if re.search(r"\schecked[\s>]", match.group(0)):
                checked.add(int(match.group(1)))
        return checked


class SaveAnswersFormRegressionTests(CorrectAnswersPanelTestBase):
    def save_url(self):
        return reverse(
            "cadmin_homework_save_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def test_browser_payload_with_hidden_empty_input_persists_selection(self):
        self.login_admin()
        self.client.post(
            self.save_url(),
            {
                f"correct_answer_{self.free_form.id}": "4",
                f"answer_type_{self.free_form.id}": "INT",
                # Exactly what the browser sends: hidden "" + checked boxes.
                f"correct_answer_{self.checkboxes.id}": ["", "1", "3"],
                f"correct_answer_{self.multiple_choice.id}": ["", "2"],
            },
        )

        self.checkboxes.refresh_from_db()
        self.multiple_choice.refresh_from_db()
        self.assertEqual(self.checkboxes.correct_answer, "1,3")
        self.assertEqual(self.multiple_choice.correct_answer, "2")

        html = self.client.get(self.submissions_url()).content.decode()
        self.assertEqual(self.checked_options(html, self.checkboxes), {1, 3})
        self.assertEqual(
            self.checked_options(html, self.multiple_choice), {2}
        )

    def test_legacy_value_with_empty_segment_still_renders_checked(self):
        """Rows already saved by the buggy form (",1,3") must not look empty."""
        self.checkboxes.correct_answer = ",1,3"
        self.checkboxes.save()
        self.assertEqual(self.checkboxes.get_correct_answer_indices(), {1, 3})
        self.assertEqual(
            self.checkboxes.get_choice_correct_answer(), {"Alpha", "Gamma"}
        )

        self.login_admin()
        html = self.client.get(self.submissions_url()).content.decode()
        self.assertEqual(self.checked_options(html, self.checkboxes), {1, 3})


    def test_single_mc_selection_is_stored_without_leading_comma(self):
        """hw4 symptom: MC answers were stored as ",1" instead of "1"."""
        self.login_admin()
        self.client.post(
            self.save_url(),
            {
                f"correct_answer_{self.free_form.id}": "4",
                f"correct_answer_{self.checkboxes.id}": [""],
                f"correct_answer_{self.multiple_choice.id}": ["", "1"],
            },
        )
        self.multiple_choice.refresh_from_db()
        self.checkboxes.refresh_from_db()
        self.assertEqual(self.multiple_choice.correct_answer, "1")
        self.assertEqual(self.checkboxes.correct_answer, "")

    def test_legacy_mc_leading_comma_renders_checked(self):
        self.multiple_choice.correct_answer = ",1"
        self.multiple_choice.save()
        self.login_admin()
        html = self.client.get(self.submissions_url()).content.decode()
        self.assertEqual(
            self.checked_options(html, self.multiple_choice), {1}
        )

    def test_free_text_answer_saved_with_form(self):
        """hw4 Q5 (free-form, type ANY) must persist the typed answer."""
        self.login_admin()
        self.client.post(
            self.save_url(),
            {
                f"correct_answer_{self.free_form.id}": "No incident to fix.",
                f"answer_type_{self.free_form.id}": "ANY",
                f"correct_answer_{self.multiple_choice.id}": ["", "2"],
            },
        )
        self.free_form.refresh_from_db()
        self.assertEqual(self.free_form.correct_answer, "No incident to fix.")
        self.assertEqual(self.free_form.answer_type, "ANY")
        html = self.client.get(self.submissions_url()).content.decode()
        self.assertIn('value="No incident to fix."', html)

    def test_invalid_form_post_saves_nothing_and_shows_error(self):
        self.login_admin()
        response = self.client.post(
            self.save_url(),
            {
                f"correct_answer_{self.free_form.id}": "100",
                f"correct_answer_{self.multiple_choice.id}": ["9"],
            },
            follow=True,
        )
        self.free_form.refresh_from_db()
        self.assertEqual(self.free_form.correct_answer, "4")
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("NOT saved" in m for m in messages))


class AutosaveAnswerEndpointTests(CorrectAnswersPanelTestBase):
    def autosave_url(self, question):
        return reverse(
            "cadmin_homework_question_save_answer",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "question_id": question.id,
            },
        )

    def post_json(self, question, payload):
        return self.client.post(
            self.autosave_url(question),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_saves_checkbox_selection(self):
        self.login_admin()
        response = self.post_json(
            self.checkboxes, {"correct_answer": ["3", "1"]}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["correct_answer"], "1,3")
        self.checkboxes.refresh_from_db()
        self.assertEqual(self.checkboxes.correct_answer, "1,3")

        html = self.client.get(self.submissions_url()).content.decode()
        self.assertEqual(self.checked_options(html, self.checkboxes), {1, 3})

    def test_clearing_all_checkboxes_saves_empty(self):
        self.checkboxes.correct_answer = "2"
        self.checkboxes.save()
        self.login_admin()
        response = self.post_json(self.checkboxes, {"correct_answer": []})
        self.assertEqual(response.status_code, 200)
        self.checkboxes.refresh_from_db()
        self.assertEqual(self.checkboxes.correct_answer, "")

    def test_saves_free_text_and_answer_type(self):
        self.login_admin()
        response = self.post_json(
            self.free_form,
            {"correct_answer": " 42 ", "answer_type": "INT"},
        )
        self.assertEqual(response.status_code, 200)
        self.free_form.refresh_from_db()
        self.assertEqual(self.free_form.correct_answer, "42")
        self.assertEqual(self.free_form.answer_type, "INT")

    def test_free_text_without_answer_type_keeps_existing_type(self):
        self.login_admin()
        response = self.post_json(self.free_form, {"correct_answer": "5"})
        self.assertEqual(response.status_code, 200)
        self.free_form.refresh_from_db()
        self.assertEqual(self.free_form.correct_answer, "5")
        self.assertEqual(self.free_form.answer_type, "INT")

    def test_out_of_range_option_is_rejected_and_logged(self):
        self.login_admin()
        with self.assertLogs("cadmin", level="ERROR") as logs:
            response = self.post_json(
                self.checkboxes, {"correct_answer": ["1", "9"]}
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("correct_answer_save_failed", "\n".join(logs.output))
        self.checkboxes.refresh_from_db()
        self.assertEqual(self.checkboxes.correct_answer, "")

    def test_invalid_answer_type_is_rejected(self):
        self.login_admin()
        with self.assertLogs("cadmin", level="ERROR"):
            response = self.post_json(
                self.free_form, {"correct_answer": "4", "answer_type": "BAD"}
            )
        self.assertEqual(response.status_code, 400)

    def test_malformed_json_is_rejected(self):
        self.login_admin()
        with self.assertLogs("cadmin", level="ERROR"):
            response = self.client.post(
                self.autosave_url(self.free_form),
                data="not json",
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)

    def test_question_from_another_homework_is_404(self):
        other = self.create_free_form_question()
        other.homework = self.create_other_homework()
        other.save()
        self.login_admin()
        response = self.post_json(other, {"correct_answer": "1"})
        self.assertEqual(response.status_code, 404)

    def test_requires_staff(self):
        self.client.login(username="test@test.com", password="12345")
        response = self.post_json(self.free_form, {"correct_answer": "1"})
        self.assertNotEqual(response.status_code, 200)
        self.free_form.refresh_from_db()
        self.assertEqual(self.free_form.correct_answer, "4")

    def test_get_not_allowed(self):
        self.login_admin()
        response = self.client.get(self.autosave_url(self.free_form))
        self.assertEqual(response.status_code, 405)

    def create_other_homework(self):
        from courses.models import Homework

        return Homework.objects.create(
            course=self.course,
            slug="other-homework",
            title="Other Homework",
            due_date=self.homework.due_date,
            state=self.homework.state,
        )


class AutosaveClientErrorReportTests(CorrectAnswersPanelTestBase):
    def test_client_failure_report_is_logged_at_error(self):
        url = reverse(
            "cadmin_homework_correct_answers_client_error",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        self.login_admin()
        with self.assertLogs("cadmin", level="ERROR") as logs:
            response = self.client.post(
                url,
                data=json.dumps(
                    {
                        "question_id": self.checkboxes.id,
                        "reason": "timeout",
                        "detail": "x" * 5000,
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        output = "\n".join(logs.output)
        self.assertIn("correct_answer_autosave_client_failure", output)
        self.assertIn("timeout", output)
        self.assertLess(len(output), 2000)


class CorrectAnswersPanelRenderTests(CorrectAnswersPanelTestBase):
    def test_panel_wires_autosave_and_has_no_save_button(self):
        self.login_admin()
        response = self.client.get(self.submissions_url())
        self.assertContains(response, "data-correct-answers-autosave")
        self.assertContains(
            response, self.autosave_url_for(self.checkboxes)
        )
        self.assertContains(response, 'data-autosave-status')
        self.assertNotContains(response, "Save answers")
        # The hidden empty input that corrupted saves is gone.
        self.assertNotContains(
            response, f'id="hidden_correct_{self.checkboxes.id}"'
        )

    def autosave_url_for(self, question):
        return reverse(
            "cadmin_homework_question_save_answer",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "question_id": question.id,
            },
        )
