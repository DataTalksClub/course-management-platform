from courses.models.homework import HomeworkState


def homework_delete_blockers(homework):
    blockers = []
    submissions_count = homework.submission_set.count()
    if homework.state != HomeworkState.CLOSED.value:
        blockers.append("not_closed")
    if submissions_count > 0:
        blockers.append("has_submissions")
    return blockers


def homework_to_dict(homework):
    submissions_count = homework.submission_set.count()
    delete_blockers = homework_delete_blockers(homework)
    return {
        "id": homework.id,
        "slug": homework.slug,
        "title": homework.title,
        "description": homework.description,
        "instructions_url": homework.instructions_url,
        "due_date": homework.due_date.isoformat(),
        "state": homework.state,
        "learning_in_public_cap": homework.learning_in_public_cap,
        "homework_url_field": homework.homework_url_field,
        "time_spent_lectures_field": homework.time_spent_lectures_field,
        "time_spent_homework_field": homework.time_spent_homework_field,
        "faq_contribution_field": homework.faq_contribution_field,
        "questions_count": homework.question_set.count(),
        "submissions_count": submissions_count,
        "can_delete": not delete_blockers,
        "delete_blockers": delete_blockers,
    }
