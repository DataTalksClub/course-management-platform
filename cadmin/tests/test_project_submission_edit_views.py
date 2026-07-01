from cadmin.tests.project_view_base import ProjectCadminViewTestBase


class ProjectSubmissionEditViewTests(ProjectCadminViewTestBase):
    def test_project_submission_edit_get(self):
        submission = self.create_project_submission(
            project_score=6,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,
        )
        self.create_project_evaluation_scores(submission)
        url = self.project_submission_edit_url(submission)

        self.login_admin()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Project Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "Problem Description")
        self.assertContains(response, "Code Quality")
        self.assertContains(response, 'value="6"')
        self.assertContains(response, 'value="23"')

    def test_project_submission_edit_post_calculates_total(self):
        submission = self.create_project_submission()
        url = self.project_submission_edit_url(submission)
        payload = self.project_score_payload()

        self.login_admin()
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assert_project_scores(submission)
        self.assert_project_evaluation_scores(submission)

    def test_project_submission_edit_post_with_checkboxes(self):
        submission = self.create_project_submission(
            project_score=6,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,
            reviewed_enough_peers=False,
            passed=False,
        )
        url = self.project_submission_edit_url(submission)
        payload = self.project_score_payload(
            reviewed_enough_peers="on",
            passed="on",
        )

        self.login_admin()
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        submission.refresh_from_db()
        self.assertTrue(submission.reviewed_enough_peers)
        self.assertTrue(submission.passed)
