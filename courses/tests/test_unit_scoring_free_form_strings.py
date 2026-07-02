from unittest import TestCase

from courses.homework_answer_checks import is_free_form_answer_correct
from courses.models import Answer, AnswerTypes, Question, QuestionTypes


class HomeworkFreeFormStringScoringTestCase(TestCase):
    def test_scoring_free_form_exact_string_correct(self):
        question = Question(
            text="What is the capital of France?",
            correct_answer="Paris",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.EXACT_STRING.value,
        )
        answer = Answer(question=question, answer_text=" paris ")

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_free_form_exact_string_incorrect(self):
        question = Question(
            text="What is the capital of France?",
            correct_answer="Paris",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.EXACT_STRING.value,
        )
        answer = Answer(question=question, answer_text="Lyon")

        result = is_free_form_answer_correct(question, answer)

        self.assertFalse(result)

    def test_scoring_free_form_contains_string_correct(self):
        question = Question(
            text="Name a programming language that's widely used for web development.",
            correct_answer="Python",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.CONTAINS_STRING.value,
        )
        answer = Answer(
            question=question,
            answer_text="I think Python is one",
        )

        result = is_free_form_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_free_form_contains_string_incorrect(self):
        question = Question(
            text="Name a programming language that's widely used for web development.",
            correct_answer="Python",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.CONTAINS_STRING.value,
        )
        answer = Answer(
            question=question,
            answer_text="I prefer using only JavaScript",
        )

        result = is_free_form_answer_correct(question, answer)

        self.assertFalse(result)
