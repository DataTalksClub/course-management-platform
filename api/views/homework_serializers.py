from courses.models.homework import HomeworkState

from .serializer_counts import annotated_or_count


def homework_delete_blockers(homework, submissions_count):
    blockers = []
    if homework.state != HomeworkState.CLOSED.value:
        blockers.append("not_closed")
    if submissions_count > 0:
        blockers.append("has_submissions")
    return blockers


def homework_to_dict(homework):
    submissions_count = annotated_or_count(
        homework, "submission_count", "submission_set"
    )
    questions_count = annotated_or_count(
        homework, "question_count", "question_set"
    )
    delete_blockers = homework_delete_blockers(homework, submissions_count)
    due_date = homework.due_date.isoformat()
    return {
        "id": homework.id,
        "slug": homework.slug,
        "title": homework.title,
        "description": homework.description,
        "instructions_url": homework.instructions_url,
        "due_date": due_date,
        "state": homework.state,
        "learning_in_public_cap": homework.learning_in_public_cap,
        "homework_url_field": homework.homework_url_field,
        "time_spent_lectures_field": homework.time_spent_lectures_field,
        "time_spent_homework_field": homework.time_spent_homework_field,
        "faq_contribution_field": homework.faq_contribution_field,
        "questions_count": questions_count,
        "submissions_count": submissions_count,
        "can_delete": not delete_blockers,
        "delete_blockers": delete_blockers,
    }
