from django.db import transaction

from courses.models.homework import Answer
from courses.models.project import ProjectEvaluationScore
from courses.leaderboard import update_leaderboard
from courses.homework_score_calculation import update_score


def update_homework_submission_from_admin(submission, cleaned_data):
    with transaction.atomic():
        old_total_score = submission.total_score

        update_homework_answers_from_admin(
            submission,
            cleaned_data["answers_by_question"],
        )
        apply_homework_submission_admin_fields(submission, cleaned_data)
        rescore_homework_submission(submission)
        apply_homework_admin_score_overrides(submission, cleaned_data)

        score_changed = submission.total_score != old_total_score
        if score_changed:
            update_leaderboard(submission.homework.course)

        return score_changed


def update_homework_answers_from_admin(submission, answers_by_question):
    for question, answer_text in answers_by_question:
        Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults={"answer_text": answer_text},
        )


def apply_homework_submission_admin_fields(submission, cleaned_data):
    submission.learning_in_public_links = cleaned_data[
        "learning_in_public_links_list"
    ]
    submission.faq_contribution_url = cleaned_data["faq_contribution_url"]


def rescore_homework_submission(submission):
    answer_records = Answer.objects.filter(
        submission=submission
    ).select_related(
        "question"
    )
    updated_answers = list(answer_records)
    update_score(submission, updated_answers, save=True)


def apply_homework_admin_score_overrides(submission, cleaned_data):
    submission.faq_score = cleaned_data["faq_score"]
    submission.total_score = (
        submission.questions_score
        + submission.learning_in_public_score
        + submission.faq_score
    )
    submission.save(
        update_fields=[
            "learning_in_public_links",
            "faq_contribution_url",
            "faq_score",
            "total_score",
        ]
    )


def update_project_submission_from_admin(submission, cleaned_data):
    with transaction.atomic():
        submission.project_score = update_project_criteria_scores_from_admin(
            submission,
            cleaned_data["criteria_scores"],
        )
        apply_project_submission_admin_scores(submission, cleaned_data)
        apply_project_submission_admin_status(submission, cleaned_data)
        submission.total_score = project_submission_admin_total_score(
            submission
        )
        submission.save()


def update_project_criteria_scores_from_admin(submission, criteria_scores):
    project_score = 0
    for criteria, score in criteria_scores:
        project_score += score
        ProjectEvaluationScore.objects.update_or_create(
            submission=submission,
            review_criteria=criteria,
            defaults={"score": score},
        )
    return project_score


def apply_project_submission_admin_scores(submission, cleaned_data):
    submission.project_faq_score = cleaned_data["project_faq_score"]
    submission.project_learning_in_public_score = cleaned_data[
        "project_learning_in_public_score"
    ]
    submission.peer_review_score = cleaned_data["peer_review_score"]
    submission.peer_review_learning_in_public_score = cleaned_data[
        "peer_review_learning_in_public_score"
    ]


def apply_project_submission_admin_status(submission, cleaned_data):
    submission.reviewed_enough_peers = cleaned_data["reviewed_enough_peers"]
    submission.passed = cleaned_data["passed"]


def project_submission_admin_total_score(submission):
    return (
        submission.project_score
        + submission.project_faq_score
        + submission.project_learning_in_public_score
        + submission.peer_review_score
        + submission.peer_review_learning_in_public_score
    )
