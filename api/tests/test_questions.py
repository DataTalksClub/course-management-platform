from api.tests.question_api_base import QuestionAPITestBase


class QuestionsAPITestCase(QuestionAPITestBase):
    def test_list_questions(self):
        self.create_question(text="Q1?", question_type="FF")
        url = self.question_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions"]), 1)
        self.assertEqual(data["questions"][0]["answers_count"], 0)
        self.assertTrue(data["questions"][0]["can_delete"])

    def test_get_question_detail(self):
        question = self.create_question(
            text="Question detail",
            question_type="FF",
        )
        url = self.question_url(question.id)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], question.id)
        self.assertEqual(data["answers_count"], 0)
        self.assertTrue(data["can_delete"])
