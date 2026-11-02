from collections import defaultdict

from django.db.models import Count

from courses.models.homework import (
    Answer,
    AnswerTypes,
    Homework,
    HomeworkState,
    Question,
)


def dashboard_question_difficulty(course, scored_homeworks=None):
    """Per-question correctness, grouped by homework.

    Questions with answer_type ANY are excluded: they are graded on
    participation (any non-empty answer is "correct"), so their correctness
    rate is not a measure of difficulty.

    Uses a two-step query so Answer aggregation is an index-only scan on
    (question_id, is_correct) without joining Question/Homework or grouping
    hundreds of thousands of rows by question.text.
    """
    if scored_homeworks is None:
        scored_hw_titles = dict(
            Homework.objects.filter(
                course=course,
                state=HomeworkState.SCORED.value,
            ).values_list("id", "title")
        )
    else:
        scored_hw_titles = {hw.id: hw.title for hw in scored_homeworks}

    if not scored_hw_titles:
        return []

    questions = list(
        Question.objects
        .filter(homework_id__in=scored_hw_titles)
        .exclude(answer_type=AnswerTypes.ANY.value)
        .values_list("id", "text", "homework_id")
        .order_by("homework_id", "id")
    )
    if not questions:
        return []

    question_ids = [q[0] for q in questions]
    total_by_question = defaultdict(int)
    correct_by_question = defaultdict(int)
    for question_id, is_correct, count in (
        Answer.objects
        .filter(question_id__in=question_ids)
        .values_list("question_id", "is_correct")
        .annotate(count=Count("id"))
        .order_by()
    ):
        total_by_question[question_id] += count
        if is_correct:
            correct_by_question[question_id] += count

    groups = []
    group_by_homework = {}
    for question_id, question_text, homework_id in questions:
        total = total_by_question.get(question_id, 0)
        if not total:
            continue
        correct = correct_by_question.get(question_id, 0)
        group = group_by_homework.get(homework_id)
        if group is None:
            group = {
                "homework_id": homework_id,
                "homework_title": scored_hw_titles[homework_id],
                "questions": [],
            }
            group_by_homework[homework_id] = group
            groups.append(group)
        group["questions"].append(
            dashboard_question_row({
                "question__text": question_text,
                "total": total,
                "correct": correct,
            })
        )

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
