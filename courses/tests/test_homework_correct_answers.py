from courses.homework_correct_answers import fill_correct_answers

from .scoring_base import HomeworkScoringBase, fetch_fresh


class HomeworkCorrectAnswerTests(HomeworkScoringBase):
    def most_common_answer_rows(self):
        return [
            (self.enrollment1, "1"),
            (self.enrollment2, "1"),
            (self.enrollment3, "2"),
            (self.enrollment4, "1"),
            (self.enrollment5, "2"),
        ]

    def create_most_common_answers(self, question):
        answers = self.most_common_answer_rows()
        for enrollment, answer_text in answers:
            self.create_answer_for_question(
                enrollment, question, answer_text
            )

    def test_fill_most_common_answer_as_correct(self):
        question = self.questions[3]
        question.correct_answer = ""
        question.save()

        self.create_most_common_answers(question)

        fill_correct_answers(self.homework)

        question = fetch_fresh(question)

        self.assertEqual(question.correct_answer, "1")

    def test_fill_most_common_answer_as_correct_not_updated_when_set(self):
        question = self.questions[3]
        self.assertEqual(question.correct_answer, "2")

        self.create_most_common_answers(question)

        fill_correct_answers(self.homework)

        question = fetch_fresh(question)

        self.assertEqual(question.correct_answer, "2")

    def test_fill_most_common_answer_as_correct_updates_zero_based_answer(self):
        question = self.questions[3]
        question.correct_answer = "0"
        question.save()

        self.create_most_common_answers(question)

        fill_correct_answers(self.homework)

        question = fetch_fresh(question)

        self.assertEqual(question.correct_answer, "1")
