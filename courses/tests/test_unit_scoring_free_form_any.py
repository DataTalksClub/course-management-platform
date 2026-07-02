from unittest import TestCase

from courses.homework_answer_checks import is_free_form_answer_correct
from courses.models import Answer, AnswerTypes, Question, QuestionTypes


class HomeworkFreeFormAnyScoringTestCase(TestCase):
    def test_scoring_free_form_any_with_answer(self):
        question = Question(
            text="Explain something",
            correct_answer="",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
        )
        answer = Answer(question=question, answer_text="Some explanation")

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_free_form_any_with_empty_answer(self):
        question = Question(
            text="Explain something",
            correct_answer="",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
        )
        answer = Answer(question=question, answer_text="")

        result = is_free_form_answer_correct(question, answer)

        self.assertFalse(result)

    def test_scoring_free_form_any_with_whitespace_only(self):
        question = Question(
            text="Explain something",
            correct_answer="",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
        )
        answer = Answer(question=question, answer_text="   ")

        result = is_free_form_answer_correct(question, answer)

        self.assertFalse(result)
