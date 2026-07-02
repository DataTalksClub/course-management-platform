"""
Tests for homework-related data API views.

Tests for homework_data_view.
The old HomeworkContentAPITestCase has been
replaced by tests in api/tests/ for the new /api/ endpoints.
"""

from courses.models import Answer

from .homework_base import HomeworkDataAPITestBase


class HomeworkDataAPITestCase(HomeworkDataAPITestBase):
    """Tests for homework_data_view endpoint."""

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
