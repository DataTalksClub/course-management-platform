import json

from api.tests.question_api_base import QuestionAPITestBase


class QuestionCreationAPITestCase(QuestionAPITestBase):
    def test_create_question(self):
        payload = {
            "text": "What is 2+2?",
            "question_type": "MC",
            "possible_answers": ["3", "4", "5"],
            "correct_answer": "2",
        }
        url = self.question_url()
        request_body = json.dumps(payload)

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        created_count = len(data["created"])
        self.assertEqual(created_count, 1)
        self.assertEqual(data["created"][0]["text"], "What is 2+2?")

    def test_create_question_bulk(self):
        payload = [
            {"text": "Q1?", "question_type": "FF"},
            {"text": "Q2?", "question_type": "FF"},
        ]
        url = self.question_url()
        request_body = json.dumps(payload)

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        created_count = len(data["created"])
        self.assertEqual(created_count, 2)

    def test_create_question_missing_text(self):
        payload = {"question_type": "FF"}
        url = self.question_url()
        request_body = json.dumps(payload)

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
