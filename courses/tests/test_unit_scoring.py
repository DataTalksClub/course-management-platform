import logging

from unittest import TestCase

from courses.models import (
    Question,
    Answer,
    QuestionTypes,
    AnswerTypes,
)

from courses.scoring import (
    is_checkbox_answer_correct,
    is_multiple_choice_answer_correct,
    is_free_form_answer_correct,
    is_answer_correct,
)


from .util import join_possible_answers

logger = logging.getLogger(__name__)


class HomeworkScoringTestCase(TestCase):
    def test_scoring_checkbox_correct(self):
        question = Question(
            text="Select the prime numbers: 2, 4, 5, 7, 8",
            possible_answers=join_possible_answers(
                ["2", "4", "5", "7", "8"]
            ),
            correct_answer="1,3,4",
            question_type=QuestionTypes.CHECKBOXES.value,
            scores_for_correct_answer=100000,
        )

        answer = Answer(
            question=question,
            answer_text="1,3,4",
        )

        result = is_checkbox_answer_correct(question, answer)
        self.assertTrue(result)


    def test_scoring_checkbox_partially_correct(self):
        question = Question(
            text="Select the prime numbers: 2, 4, 5, 7, 8",
            possible_answers=join_possible_answers(
                ["2", "4", "5", "7", "8"]
            ),
            correct_answer="1,3,4",
            question_type=QuestionTypes.CHECKBOXES.value,
            scores_for_correct_answer=100000,
        )

        answer = Answer(
            question=question,
            answer_text="1,3",
        )

        result = is_checkbox_answer_correct(question, answer)
        self.assertFalse(result)

    def test_scoring_checkbox_incorrect(self):
        question = Question(
            text="Select the prime numbers: 2, 4, 5, 7, 8",
            possible_answers=join_possible_answers(
                ["2", "4", "5", "7", "8"]
            ),
            correct_answer="1,3,4",
            question_type=QuestionTypes.CHECKBOXES.value,
            scores_for_correct_answer=100000,
        )

        answer = Answer(
            question=question,
            answer_text="1,2,5",
        )

        result = is_checkbox_answer_correct(question, answer)
        self.assertFalse(result)

    def test_scoring_multiple_choice_correct(self):
        question = Question(
            text="Who is the first President of the United States?",
            possible_answers=join_possible_answers(
                [
                    "George Washington",
                    "Thomas Jefferson",
                    "Abraham Lincoln",
                ]
            ),
            correct_answer="1",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
        )

        answer = Answer(
            question=question,
            answer_text="1",
        )

        result = is_multiple_choice_answer_correct(question, answer)
        self.assertTrue(result)

    def test_scoring_multiple_choice_incorrect(self):
        question = Question(
            text="Who is the first President of the United States?",
            possible_answers=join_possible_answers(
                [
                    "George Washington",
                    "Thomas Jefferson",
                    "Abraham Lincoln",
                ]
            ),
            correct_answer="1",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
        )

        answer = Answer(
            question=question,
            answer_text="2",
        )

        result = is_multiple_choice_answer_correct(question, answer)
        self.assertFalse(result)

    # Free Form: Exact String
    def test_scoring_free_form_exact_string_correct(self):
        question = Question(
            text="What is the capital of France?",
            correct_answer="Paris",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.EXACT_STRING.value,
        )

        answer = Answer(
            question=question,
            answer_text=" paris ",
        )

        result = is_free_form_answer_correct(question, answer)
        self.assertTrue(result)

    def test_scoring_free_form_exact_string_incorrect(self):
        question = Question(
            text="What is the capital of France?",
            correct_answer="Paris",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.EXACT_STRING.value,
        )

        answer = Answer(
            question=question,
            answer_text="Lyon",
        )

        result = is_free_form_answer_correct(question, answer)
        self.assertFalse(result)

    # Free Form: Contains String
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

    # Free Form: Float
    def test_scoring_free_form_float_correct(self):
        question = Question(
            text="What is the value of Pi up to two decimal places?",
            correct_answer="3.14",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.FLOAT.value,
        )

        answer = Answer(
            question=question,
            answer_text="3.1415",
        )

        result = is_free_form_answer_correct(question, answer)
        self.assertTrue(result)

    # Free Form: Integer
    def test_scoring_free_form_integer_correct(self):
        question = Question(
            text="How many continents are there on Earth?",
            correct_answer="7",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
        )

        answer = Answer(
            question=question,
            answer_text="7",
        )

        result = is_free_form_answer_correct(question, answer)
        self.assertTrue(result)
