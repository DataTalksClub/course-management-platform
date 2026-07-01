from datetime import datetime
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from courses.models import Submission
from courses.tests.homework_view_base import (
    HomeworkDetailViewTestBase,
    credentials,
)
from .util import join_possible_answers


class HomeworkSubmissionViewTests(HomeworkDetailViewTestBase):
    def test_homework_detail_submission_post_no_submissions(self):
        self.assert_no_enrollment_or_submission()

        response = self.post_homework(self.answer_post_data())

        self.assert_redirects_to_homework(response)
        self.assert_enrollment_and_submission_exist()
        self.assert_submission_answers(
            self.get_saved_submission(),
            {
                self.question1: "1",
                self.question2: "Some text",
                self.question3: "1,2",
                self.question4: "1",
                self.question5: "3.141516",
                self.question6: "1,2,3",
            },
        )

    @mock.patch("django.utils.timezone.now")
    def test_homework_detail_submission_post_with_submissions(
        self, mock_now
    ):
        update_time_now = timezone.make_aware(datetime(2020, 1, 1))
        mock_now.return_value = update_time_now
        self.create_submission_with_answers(question3_answer="1,2,3")

        response = self.post_homework(self.updated_answer_post_data())

        self.assert_redirects_to_homework(response)
        submission = Submission.objects.get(id=self.submission.id)
        self.assertEqual(submission.submitted_at, update_time_now)
        self.assert_submission_answers(
            submission,
            {
                self.question1: "1",
                self.question2: "Some other text",
                self.question3: "1,2,4",
                self.question4: "3",
                self.question5: "3.141516",
                self.question6: "1,2",
            },
        )

    def test_submit_homework_submission_artifacts(self):
        self.post_homework(self.artifact_post_data())

        self.assert_submission_answers(
            self.get_saved_submission(),
            {
                self.question1: "1",
                self.question2: "Some text",
                self.question3: "1,2",
                self.question4: "1",
                self.question5: "3.141516",
                self.question6: "1,2,3",
            },
        )

    def test_submit_homework_submission_artifacts_dispayed_correctly(
        self,
    ):
        self.post_homework(self.artifact_post_data(question1_answer="3\r\n"))

        response = self.client.get(self.homework_url())

        self.assert_saved_question_answers(response.context["question_answers"])

    def test_submit_homework_submission_artifacts_in_possible_answers(
        self,
    ):
        self.question1.possible_answers = join_possible_answers(
            ["Paris\r", "London\r", "Berlin"]
        )
        self.question1.save()
        self.client.login(**credentials)
        post_data = {f"answer_{self.question1.id}": ["1\r\n"]}
        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.post(url, post_data)
        response = self.client.get(url)
        context = response.context
        question_answers = context["question_answers"]

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": True, "index": 1},
            {"value": "London", "is_selected": False, "index": 2},
            {"value": "Berlin", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer1["options"], expected_options1)
