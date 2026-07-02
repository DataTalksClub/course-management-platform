from courses.tests.homework_submission_validation_base import (
    HomeworkSubmissionValidationBase,
)


class HomeworkSubmissionTimeFieldTests(HomeworkSubmissionValidationBase):
    def test_submit_homework_time_spent_comma_decimal(self):
        self.disable_homework_url_field()
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            "time_spent_lectures": "2,5",
            "time_spent_homework": "1,25",
        }

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 302)
        submission = self.get_saved_submission()
        self.assertEqual(submission.time_spent_lectures, 2.5)
        self.assertEqual(submission.time_spent_homework, 1.25)

    def test_submit_homework_time_spent_invalid_text_shows_error(self):
        self.disable_homework_url_field()
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            "time_spent_lectures": "2 hrs",
        }

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid number of hours")
        self.assert_no_submission()
