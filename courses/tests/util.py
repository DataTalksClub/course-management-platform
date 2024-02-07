
from courses.models import QUESTION_ANSWER_DELIMITER

def join_possible_answers(possible_answers: list) -> str:
    return QUESTION_ANSWER_DELIMITER.join(possible_answers)