from unittest import TestCase

from courses.homework_answer_checks import is_multiple_choice_answer_correct
from courses.models import Answer, Question, QuestionTypes
from courses.tests.util import join_possible_answers


class HomeworkMultipleChoiceScoringTestCase(TestCase):
    def test_scoring_multiple_choice_correct(self):
        possible_answers = join_possible_answers(
            [
                "George Washington",
                "Thomas Jefferson",
                "Abraham Lincoln",
            ]
        )
        question = Question(
            text="Who is the first President of the United States?",
            possible_answers=possible_answers,
            correct_answer="1",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
        )
        answer = Answer(question=question, answer_text="1")

        result = is_multiple_choice_answer_correct(question, answer)

        self.assertTrue(result)

    def test_scoring_multiple_choice_incorrect(self):
        possible_answers = join_possible_answers(
            [
                "George Washington",
                "Thomas Jefferson",
                "Abraham Lincoln",
            ]
        )
        question = Question(
            text="Who is the first President of the United States?",
            possible_answers=possible_answers,
            correct_answer="1",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
        )
        answer = Answer(question=question, answer_text="2")

        result = is_multiple_choice_answer_correct(question, answer)

        self.assertFalse(result)
