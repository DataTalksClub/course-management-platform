from unittest import TestCase

from courses.homework_answer_checks import is_free_form_answer_correct
from courses.models import Answer, AnswerTypes, Question, QuestionTypes


class HomeworkFreeFormLongScoringTestCase(TestCase):
    def test_scoring_free_form_long_any_with_answer(self):
        question = Question(
            text="Explain something in detail",
            correct_answer="",
            question_type=QuestionTypes.FREE_FORM_LONG.value,
            answer_type=AnswerTypes.ANY.value,
        )
        answer = Answer(
            question=question,
            answer_text="This is a long explanation\nwith multiple lines\nof text",
        )

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_free_form_long_exact_string(self):
        question = Question(
            text="What is the capital of France?",
            correct_answer="Paris",
            question_type=QuestionTypes.FREE_FORM_LONG.value,
            answer_type=AnswerTypes.EXACT_STRING.value,
        )
        answer = Answer(question=question, answer_text="Paris")

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_free_form_long_contains_string(self):
        question = Question(
            text="Describe Python",
            correct_answer="programming language",
            question_type=QuestionTypes.FREE_FORM_LONG.value,
            answer_type=AnswerTypes.CONTAINS_STRING.value,
        )
        answer = Answer(
            question=question,
            answer_text=(
                "Python is a high-level programming language that is widely "
                "used\nfor web development, data science, and automation"
            ),
        )

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)
