from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Sum

from courses.models.homework import Homework, Submission
from courses.views.dashboard_metrics import (
    quartile_fields,
    safe_quartiles,
    submission_values,
)


@dataclass(frozen=True)
class HomeworkScoreRatio:
    questions_score_median: object
    max_questions_score: object
    score_ratio: object


def dashboard_homeworks(course):
    homeworks = Homework.objects.filter(course=course)
    homeworks = homeworks.order_by("id")
    max_questions_score = Sum("question__scores_for_correct_answer")
    return homeworks.annotate(
        max_questions_score=max_questions_score,
    )


def dashboard_homework_submissions(course):
    submission_fields = (
        "homework_id",
        "time_spent_lectures",
        "time_spent_homework",
        "questions_score",
        "total_score",
    )
    return (
        Submission.objects
        .filter(homework__course=course)
        .select_related("homework")
        .values(*submission_fields)
    )


def dashboard_homework_stats(
    homeworks, all_hw_submissions, total_enrollments
):
    hw_submissions_by_homework = dashboard_homework_submissions_by_homework(
        all_hw_submissions
    )
    homework_stats = dashboard_homework_stat_rows(
        homeworks,
        hw_submissions_by_homework,
        total_enrollments,
    )
    difficulty_stats = dashboard_homework_difficulty_stats(homework_stats)
    return homework_stats, difficulty_stats


def dashboard_homework_submissions_by_homework(all_hw_submissions):
    hw_submissions_by_homework = defaultdict(list)
    for submission in all_hw_submissions:
        homework_id = submission["homework_id"]
        hw_submissions_by_homework[homework_id].append(submission)
    return hw_submissions_by_homework


def dashboard_homework_stat_rows(
    homeworks,
    hw_submissions_by_homework,
    total_enrollments,
):
    stat_rows = []
    for homework in homeworks:
        submissions = hw_submissions_by_homework.get(homework.id, [])
        stat_row = dashboard_homework_stat(
            homework,
            submissions,
            total_enrollments,
        )
        stat_rows.append(stat_row)
    return stat_rows


def dashboard_homework_stat(homework, hw_submissions, total_enrollments):
    time_stats = dashboard_homework_time_stats(hw_submissions)
    score_stats = dashboard_homework_score_stats(homework, hw_submissions)
    submissions_count = len(hw_submissions)
    completion_rate = dashboard_completion_rate(
        submissions_count,
        total_enrollments,
    )

    return {
        "homework": homework,
        "submissions_count": submissions_count,
        "completion_rate": completion_rate,
        **time_stats,
        **score_stats,
    }


def dashboard_completion_rate(submissions_count, total_enrollments):
    if total_enrollments <= 0:
        return 0.0
    return round(submissions_count / total_enrollments * 100, 1)


def dashboard_homework_time_stats(hw_submissions):
    stats = {}
    lecture_times = submission_values(
        hw_submissions,
        "time_spent_lectures",
    )
    lecture_time_stats = quartile_fields("time_lecture", lecture_times)
    stats.update(lecture_time_stats)

    homework_times = submission_values(
        hw_submissions,
        "time_spent_homework",
    )
    homework_time_stats = quartile_fields("time_homework", homework_times)
    stats.update(homework_time_stats)

    total_times = dashboard_total_homework_times(hw_submissions)
    total_time_stats = quartile_fields("time_total", total_times)
    stats.update(total_time_stats)
    return stats


def dashboard_total_homework_times(hw_submissions):
    total_times = []
    for submission in hw_submissions:
        lectures_time = submission["time_spent_lectures"]
        homework_time = submission["time_spent_homework"]
        if lectures_time is None or homework_time is None:
            continue
        total_time = lectures_time + homework_time
        total_times.append(total_time)
    return total_times


def dashboard_homework_score_stats(homework, hw_submissions):
    total_scores = submission_values(hw_submissions, "total_score")
    score_quartiles = safe_quartiles(total_scores)
    score_ratio_data = dashboard_homework_score_ratio(
        homework,
        hw_submissions,
    )
    score_ratio_pct = None
    if score_ratio_data.score_ratio is not None:
        score_ratio_pct = round(score_ratio_data.score_ratio * 100, 1)

    return {
        "score_q25": score_quartiles.q25,
        "score_median": score_quartiles.median,
        "score_q75": score_quartiles.q75,
        "questions_score_median": score_ratio_data.questions_score_median,
        "max_questions_score": score_ratio_data.max_questions_score,
        "score_ratio": score_ratio_data.score_ratio,
        "score_ratio_pct": score_ratio_pct,
    }


def dashboard_homework_score_ratio(homework, hw_submissions):
    questions_scores = submission_values(hw_submissions, "questions_score")
    questions_score_quartiles = safe_quartiles(questions_scores)
    max_questions_score = homework.max_questions_score
    if questions_score_quartiles.median is not None and max_questions_score:
        score_ratio = questions_score_quartiles.median / max_questions_score
    else:
        score_ratio = None
    return HomeworkScoreRatio(
        questions_score_median=questions_score_quartiles.median,
        max_questions_score=max_questions_score,
        score_ratio=score_ratio,
    )


def dashboard_homework_difficulty_stats(homework_stats):
    difficulty_stats = []
    for hw_stat in homework_stats:
        if hw_stat["score_ratio"] is not None:
            difficulty_stats.append(hw_stat)
    difficulty_stats.sort(
        key=lambda hw_stat: (
            hw_stat["score_ratio"],
            -hw_stat["submissions_count"],
            hw_stat["homework"].title,
        )
    )
    for rank, hw_stat in enumerate(difficulty_stats, start=1):
        hw_stat["difficulty_rank"] = rank

    return difficulty_stats
