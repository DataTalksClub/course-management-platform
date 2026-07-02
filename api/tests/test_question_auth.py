from api.tests.question_api_base import QuestionAPITestBase


class QuestionAuthAPITestCase(QuestionAPITestBase):
    def test_question_mutations_require_staff_token(self):
        question = self.create_question(
            text="Staff only question",
            question_type="FF",
        )
        client = self.non_staff_client()

        responses = self.non_staff_mutation_responses(client, question)

        for response in responses:
            self.assert_staff_token_required(response)
        self.assert_question_unchanged_after_forbidden_mutations(question)
