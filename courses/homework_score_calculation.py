import logging

from courses.homework_answer_checks import is_answer_correct
from courses.models.homework import Answer, Submission


logger = logging.getLogger(__name__)


def update_learning_in_public_score(submission: Submission) -> int:
    learning_in_public_score = 0

    if submission.enrollment.disable_learning_in_public:
        submission.learning_in_public_score = 0
        return 0

    if submission.learning_in_public_links:
        learning_in_public_score = len(
            submission.learning_in_public_links
        )
        submission.learning_in_public_score = learning_in_public_score

    return learning_in_public_score


def update_faq_score(submission: Submission) -> int:
    faq_score = 0

    if (
        submission.faq_contribution_url
        and len(submission.faq_contribution_url) >= 5
    ):
        faq_score = 1
        submission.faq_score = faq_score

    return faq_score


def score_answer(answer: Answer, save: bool) -> int:
    is_correct = is_answer_correct(answer.question, answer)
    answer.is_correct = is_correct
    if save:
        answer.save()

    if is_correct:
        return answer.question.scores_for_correct_answer
    return 0


def questions_score(answers: list[Answer], save: bool) -> int:
    score = 0
    for answer in answers:
        answer_score = score_answer(answer, save)
        score += answer_score
    return score


def submission_total_score(
    submission: Submission, questions_score_value: int
):
    lip_score = update_learning_in_public_score(submission)
    faq_score = update_faq_score(submission)
    return questions_score_value + lip_score + faq_score


def update_score(
    submission: Submission, answers: list[Answer], save: bool = True
) -> None:
    logger.info(f"Scoring submission {submission.id}")
    score = questions_score(answers, save)
    submission.questions_score = score
    submission.total_score = submission_total_score(
        submission,
        score,
    )

    if save:
        submission.save()
