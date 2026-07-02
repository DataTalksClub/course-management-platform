from courses.tests.homework_submissions_base import (
    HomeworkSubmissionsViewTestBase,
)


class HomeworkSubmissionsHiddenAnswersTest(
    HomeworkSubmissionsViewTestBase
):
    def test_submissions_view_hides_answers_and_links_to_edit_page(self):
        self.create_hidden_answer_questions()

        response = self.get_admin_submissions_response()

        self.assertEqual(response.status_code, 200)
        self.assert_compact_submission_context(response)

        content = response.content.decode("utf-8")
        self.assert_compact_submission_content(content)

    def test_submissions_view_short_answers_are_hidden(self):
        short_answer = "This is a short answer with less than 1000 characters."
        self.create_answer("Short answer question", short_answer)

        self.login_admin()
        url = self.submissions_url()

        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertNotIn(short_answer, content)
        self.assertNotIn(
            'class="btn btn-sm btn-outline-primary mt-1 toggle-answer"',
            content,
        )

    def test_submissions_view_long_answers_are_hidden(self):
        long_answer = "This is a very long answer. " * 100
        self.create_answer("Long answer question", long_answer)

        self.login_admin()
        url = self.submissions_url()

        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertNotIn(long_answer, content)
        self.assertNotIn(f'title="{long_answer}', content)
        self.assertNotIn("…", content)
