from unittest import TestCase

from courses.homework_answer_checks import is_checkbox_answer_correct
from courses.models import Answer, Question, QuestionTypes
from courses.tests.util import join_possible_answers


class HomeworkCheckboxScoringTestCase(TestCase):
    def test_scoring_checkbox_correct(self):
        possible_answers = join_possible_answers(
            ["2", "4", "5", "7", "8"]
        )
        question = Question(
            text="Select the prime numbers: 2, 4, 5, 7, 8",
            possible_answers=possible_answers,
            correct_answer="1,3,4",
            question_type=QuestionTypes.CHECKBOXES.value,
            scores_for_correct_answer=100000,
        )
        answer = Answer(question=question, answer_text="1,3,4")

        result = is_checkbox_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_checkbox_partially_correct(self):
        possible_answers = join_possible_answers(
            ["2", "4", "5", "7", "8"]
        )
        question = Question(
            text="Select the prime numbers: 2, 4, 5, 7, 8",
            possible_answers=possible_answers,
            correct_answer="1,3,4",
            question_type=QuestionTypes.CHECKBOXES.value,
            scores_for_correct_answer=100000,
        )
        answer = Answer(question=question, answer_text="1,3")

        result = is_checkbox_answer_correct(question, answer)

        self.assertFalse(result)

    def test_scoring_checkbox_incorrect(self):
        possible_answers = join_possible_answers(
            ["2", "4", "5", "7", "8"]
        )
        question = Question(
            text="Select the prime numbers: 2, 4, 5, 7, 8",
            possible_answers=possible_answers,
            correct_answer="1,3,4",
            question_type=QuestionTypes.CHECKBOXES.value,
            scores_for_correct_answer=100000,
        )
        answer = Answer(question=question, answer_text="1,2,5")

        result = is_checkbox_answer_correct(question, answer)

        self.assertFalse(result)
