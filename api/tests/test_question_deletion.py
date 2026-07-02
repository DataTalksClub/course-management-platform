from courses.models import Question
from api.tests.question_api_base import QuestionAPITestBase


class QuestionDeletionAPITestCase(QuestionAPITestBase):
    def test_delete_question(self):
        question = self.create_question(text="To delete", question_type="FF")
        url = self.question_url(question.id)

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        question_exists = Question.objects.filter(id=question.id).exists()
        self.assertFalse(question_exists)

    def test_delete_question_with_answers_is_blocked(self):
        question, answer = self.create_answered_question()
        url = self.question_url(question.id)

        response = self.client.delete(url)

        self.assert_question_delete_blocked_response(response)
        self.assert_answered_question_exists(question, answer)
