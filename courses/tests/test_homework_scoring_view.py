from .homework_scoring_view_base import HomeworkScoringViewBase


class HomeworkScoringViewTests(HomeworkScoringViewBase):
    def test_homework_detail_with_scored_homework(self):
        answers_by_question = self.full_submission_answers()
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(response)
        self.assertEqual(context["submission"], self.submission)
        self.assertTrue(context["homework"].is_scored)

        self.assert_scored_question_answers(context["question_answers"])

    def test_homework_detail_scored_with_unanswered_questions(self):
        answers_by_question = {
            self.question1: "1",
            self.question2: "Some explanation",
            self.question5: "3.14",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        question_answers = response.context["question_answers"]
        self.assertEqual(len(question_answers), 6)
        self.assert_answer_present(question_answers[0], self.question1)
        answer2 = self.assert_answer_present(
            question_answers[1], self.question2
        )
        self.assertEqual(answer2["text"], "Some explanation")
        self.assert_no_answer_submitted(question_answers[2], self.question3)
        self.assert_no_answer_submitted(question_answers[3], self.question4)
        self.assert_answer_present(question_answers[4], self.question5)
        self.assert_no_answer_submitted(question_answers[5], self.question6)

    def test_homework_detail_scored_with_empty_free_form_answer(self):
        answers_by_question = {
            self.question2: "   ",
        }
        self.create_scored_submission_with_answers(answers_by_question)

        response = self.get_homework_response(login=True)
        self.assertEqual(response.status_code, 200)

        question_answers = response.context["question_answers"]
        self.assert_no_answer_submitted(
            question_answers[1],
            self.question2,
        )
