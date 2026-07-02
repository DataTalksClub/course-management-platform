from unittest import TestCase

from courses.homework_answer_checks import is_free_form_answer_correct
from courses.models import Answer, AnswerTypes, Question, QuestionTypes


class HomeworkFreeFormNumericScoringTestCase(TestCase):
    def test_scoring_free_form_float_correct(self):
        question = Question(
            text="What is the value of Pi up to two decimal places?",
            correct_answer="3.14",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.FLOAT.value,
        )
        answer = Answer(question=question, answer_text="3.1415")

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_free_form_integer_correct(self):
        question = Question(
            text="How many continents are there on Earth?",
            correct_answer="7",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
        )
        answer = Answer(question=question, answer_text="7")

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)
