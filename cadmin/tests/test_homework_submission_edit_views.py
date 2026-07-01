from cadmin.tests.homework_view_base import (
    AnswerData,
    HomeworkCadminViewTestBase,
    HomeworkSubmissionScoreExpectation,
)


class HomeworkSubmissionEditViewTests(HomeworkCadminViewTestBase):
    def test_homework_submission_edit_get(self):
        fixture = self.create_homework_submission_edit_page_fixture()

        response = self.homework_submission_edit_response(fixture.submission)

        self.assert_homework_submission_edit_page(response, fixture)

    def test_homework_submission_edit_post_updates_answers(self):
        fixture = self.create_homework_submission_edit_fixture()

        response = self.post_homework_submission_answer_edit(fixture)

        self.assertEqual(response.status_code, 302)
        fixture.submission.refresh_from_db()
        expected_scores = HomeworkSubmissionScoreExpectation(
            submission=fixture.submission,
            questions_score=2,
            learning_in_public_score=2,
            total_score=4,
        )
        self.assert_homework_submission_scores(expected_scores)
        self.assert_answer_updated(fixture.submission, fixture.question1, "4")
        self.assert_answer_updated(fixture.submission, fixture.question2, "2")
        expected_links = [
            "https://example.com/post1",
            "https://example.com/post2",
        ]
        self.assert_learning_in_public_links(
            fixture.submission,
            expected_links,
        )

    def test_homework_submission_edit_updates_faq_entry_and_score(self):
        question = self.create_free_form_question(score=10)
        submission = self.create_homework_submission()
        answer = AnswerData(
            submission=submission,
            question=question,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(answer)

        self.login_admin()
        faq_entry = "https://gist.github.com/example/not-validated-here"
        data = {
            f"answer_{question.id}": "4",
            "learning_in_public_links": "",
            "faq_contribution_url": faq_entry,
            "faq_score": "3",
        }
        response = self.client.post(
            self.homework_submission_edit_url(submission),
            data,
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.faq_contribution_url, faq_entry)
        self.assertEqual(submission.faq_score, 3)
        self.assertEqual(submission.total_score, 13)

    def test_homework_submission_edit_triggers_leaderboard_update(self):
        enrollment = self.create_enrollment()
        question = self.create_free_form_question(score=10)
        submission = self.create_homework_submission(
            enrollment=enrollment,
        )
        answer = AnswerData(
            submission=submission,
            question=question,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(answer)

        enrollment.total_score = 0
        enrollment.position_on_leaderboard = 999
        enrollment.save()

        self.login_admin()
        data = {
            f"answer_{question.id}": "4",
            "learning_in_public_links": "",
        }
        response = self.client.post(
            self.homework_submission_edit_url(submission),
            data,
        )

        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.total_score, 10)
