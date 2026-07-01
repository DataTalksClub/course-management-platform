from .homework_scoring_view_base import HomeworkScoringViewBase


class HomeworkScoringViewWarningTests(HomeworkScoringViewBase):
    def test_homework_detail_unauthenticated_scored_no_answer_warning(self):
        answers_by_question = {
            self.question1: "1",
            self.question4: "3",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response()
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("Correct answers are available below", content)
        self.assertIn("Log in to view my results", content)
        self.assertIn("Correct answers", content)
        self.assertIn("Review the expected answers", content)
        self.assertIn('type="radio"', content)
        self.assertIn('type="checkbox"', content)
        self.assertIn('type="text"', content)
        self.assertIn("disabled", content)
        self.assertNotIn("Log in to submit this homework", content)
        self.assertNotIn("You can preview the questions", content)
        self.assertNotIn("Submission details", content)
        self.assertNotIn("Status: Not submitted", content)
        self.assertNotIn("No answer was submitted for this question", content)

    def test_homework_detail_authenticated_scored_with_answer_warning(self):
        answers_by_question = {
            self.question1: "1",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("No answer was submitted for this question", content)
