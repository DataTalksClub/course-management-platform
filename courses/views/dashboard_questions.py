from django.db.models import Count, Q

from courses.models.homework import Answer, AnswerTypes


def dashboard_question_difficulty(course):
    """Per-question correctness, grouped by homework.

    Questions with answer_type ANY are excluded: they are graded on
    participation (any non-empty answer is "correct"), so their correctness
    rate is not a measure of difficulty.
    """
    rows = (
        Answer.objects
        .filter(question__homework__course=course)
        .exclude(question__answer_type=AnswerTypes.ANY.value)
        .values(
            "question_id",
            "question__text",
            "question__homework_id",
            "question__homework__title",
        )
        .annotate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
        .order_by("question__homework_id", "question_id")
    )

    groups = []
    group_by_homework = {}
    for row in rows:
        homework_id = row["question__homework_id"]
        group = group_by_homework.get(homework_id)
        if group is None:
            group = {
                "homework_id": homework_id,
                "homework_title": row["question__homework__title"],
                "questions": [],
            }
            group_by_homework[homework_id] = group
            groups.append(group)
        group["questions"].append(dashboard_question_row(row))

    return groups


def dashboard_question_row(row):
    total = row["total"]
    correct = row["correct"]
    pct_correct = round(correct / total * 100, 1) if total else None
    return {
        "text": row["question__text"],
        "total": total,
        "correct": correct,
        "pct_correct": pct_correct,
    }
