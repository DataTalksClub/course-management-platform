from courses.tests.homework_submission_validation_base import (
    HomeworkSubmissionValidationBase,
)


class HomeworkSubmissionClosedTests(HomeworkSubmissionValidationBase):
    def assert_closed_homework_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This homework is not open for submissions yet.",
        )
        self.assertContains(response, "Status:")
        self.assertContains(response, "Closed")
        self.assertNotContains(response, "Not submitted")
        self.assertNotContains(response, 'name="answer_')
        self.assertNotContains(response, "Submission details")
        self.assertNotContains(response, "Save submission")

    def test_closed_homework_without_submission_hides_form(self):
        self.close_homework()
        self.client.login(
            username="test@test.com",
            password="12345",
        )

        homework_url = self.homework_url()
        response = self.client.get(homework_url)

        self.assert_closed_homework_response(response)

    def test_closed_homework_post_does_not_create_submission(self):
        self.close_homework()
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some text"],
        }

        response = self.post_homework(post_data, follow=True)

        homework_url = self.homework_url()
        self.assertRedirects(response, homework_url)
        self.assertContains(
            response, "This homework is not open for submissions."
        )
        self.assert_no_submission()
