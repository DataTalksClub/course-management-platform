import json

from api.tests.question_api_base import QuestionAPITestBase


class QuestionUpdateAPITestCase(QuestionAPITestBase):
    def test_patch_question(self):
        question = self.create_question(text="Old text", question_type="FF")
        url = self.question_url(question.id)
        patch_payload = {"text": "New text", "scores_for_correct_answer": 3}
        request_body = json.dumps(patch_payload)

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(question.text, "New text")
        self.assertEqual(question.scores_for_correct_answer, 3)

    def test_patch_question_possible_answers_as_list(self):
        question = self.create_question(text="Q?", question_type="MC")
        url = self.question_url(question.id)
        patch_payload = {"possible_answers": ["A", "B", "C"]}
        request_body = json.dumps(patch_payload)

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        question.refresh_from_db()
        possible_answers = question.get_possible_answers()
        self.assertEqual(possible_answers, ["A", "B", "C"])

    def test_patch_question_invalid_field(self):
        question = self.create_question(text="Q?", question_type="FF")
        url = self.question_url(question.id)
        patch_payload = {"id": 999}
        request_body = json.dumps(patch_payload)

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_field")
