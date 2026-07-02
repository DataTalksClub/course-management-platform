from courses.tests.homework_submission_validation_base import (
    HomeworkSubmissionValidationBase,
)


class HomeworkSubmissionLearningPublicValidationTests(
    HomeworkSubmissionValidationBase
):
    def test_submit_homework_learning_in_public_empty_and_duplicates(
        self,
    ):
        self.homework.learning_in_public_cap = 7
        self.homework.save()
        learning_links = [
            "https://test.org/totally-existing-url/1",
            "https://test.org/totally-existing-url/1",
            "https://test.org/totally-existing-url/2",
            "https://test.org/totally-existing-url/3",
        ]
        extra_fields = {"learning_in_public_links[]": learning_links}
        post_data = self.updated_answer_post_data(**extra_fields)

        self.post_homework(post_data)

        submission = self.get_saved_submission()
        expected_learning_in_public_links = [
            "https://test.org/totally-existing-url/1",
            "https://test.org/totally-existing-url/2",
            "https://test.org/totally-existing-url/3",
        ]
        self.assertEqual(
            submission.learning_in_public_links,
            expected_learning_in_public_links,
        )

    def test_submit_homework_learning_in_public_rejects_non_http_url(
        self,
    ):
        self.homework.learning_in_public_cap = 7
        self.homework.save()
        learning_links = ["javascript:alert('payment')"]
        extra_fields = {"learning_in_public_links[]": learning_links}
        post_data = self.updated_answer_post_data(**extra_fields)

        response = self.post_homework(post_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Learning in public links must be valid HTTP or HTTPS URLs.",
        )
        self.assert_no_submission()
