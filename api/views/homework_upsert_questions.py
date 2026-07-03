from api.safety import error_response
from api.views.homework_create import create_question
from api.views.homework_serializers import homework_delete_blockers
from api.views.serializer_counts import annotated_or_count


def homework_questions_replace_error(homework):
    submissions_count = annotated_or_count(
        homework, "submission_count", "submission_set"
    )
    delete_blockers = homework_delete_blockers(homework, submissions_count)
    if delete_blockers:
        return error_response(
            "Questions can only be replaced for closed homeworks with no submissions",
            "homework_questions_replace_blocked",
            details={"delete_blockers": delete_blockers},
        )

    answered_questions = homework.question_set.filter(
        answer__isnull=False
    ).distinct()
    if answered_questions.exists():
        answered_questions_count = answered_questions.count()
        return error_response(
            "Cannot replace questions with existing answers",
            "homework_questions_have_answers",
            details={
                "answered_questions_count": answered_questions_count
            },
        )

    return None


def replace_homework_questions(homework, questions_data):
    error = homework_questions_replace_error(homework)
    if error:
        return error

    homework.question_set.all().delete()
    for question_data in questions_data:
        create_question(homework, question_data)
    return None
