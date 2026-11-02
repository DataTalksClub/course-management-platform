from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Sum

from courses.models.homework import Homework, HomeworkState, Submission
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


def dashboard_all_homeworks(course):
    homeworks = Homework.objects.filter(course=course).order_by("id")
    max_questions_score = Sum("question__scores_for_correct_answer")
    return list(
        homeworks.annotate(
            max_questions_score=max_questions_score,
        )
    )


def dashboard_homeworks(course):
    homeworks = Homework.objects.filter(course=course)
    homeworks = homeworks.filter(state=HomeworkState.SCORED.value)
    homeworks = homeworks.order_by("id")
    max_questions_score = Sum("question__scores_for_correct_answer")
    return homeworks.annotate(
        max_questions_score=max_questions_score,
    )


def dashboard_homework_submissions(course, homework_ids=None):
    # Slim tuple rows (values_list) covered by sub_hw_dashboard_idx:
    # avoids joining courses_homework and parsing duplicate due_date
    # timestamps on every submission row.
    submission_fields = (
        "homework_id",
        "time_spent_lectures",
        "time_spent_homework",
        "questions_score",
        "total_score",
        "submitted_at",
    )
    if homework_ids is not None:
        if not homework_ids:
            return ()
        queryset = Submission.objects.filter(
            homework_id__in=homework_ids
        )
    else:
        queryset = Submission.objects.filter(homework__course=course)
    return queryset.values_list(*submission_fields)


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
        homework_id = (
            submission[0]
            if isinstance(submission, tuple)
            else submission["homework_id"]
        )
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


def _collect_homework_submission_series(hw_submissions):
    lecture_times = []
    homework_times = []
    total_times = []
    questions_scores = []
    total_scores = []
    for submission in hw_submissions:
        if isinstance(submission, tuple):
            _, lectures_time, homework_time, questions_score, total_score, _ = (
                submission
            )
        else:
            lectures_time = submission["time_spent_lectures"]
            homework_time = submission["time_spent_homework"]
            questions_score = submission["questions_score"]
            total_score = submission["total_score"]
        if lectures_time is not None:
            lecture_times.append(lectures_time)
        if homework_time is not None:
            homework_times.append(homework_time)
            if lectures_time is not None:
                total_times.append(lectures_time + homework_time)
        if questions_score is not None:
            questions_scores.append(questions_score)
        if total_score is not None:
            total_scores.append(total_score)
    return (
        lecture_times,
        homework_times,
        total_times,
        questions_scores,
        total_scores,
    )


def dashboard_homework_stat(homework, hw_submissions, total_enrollments):
    (
        lecture_times,
        homework_times,
        total_times,
        questions_scores,
        total_scores,
    ) = _collect_homework_submission_series(hw_submissions)
    time_stats = {
        **quartile_fields("time_lecture", lecture_times),
        **quartile_fields("time_homework", homework_times),
        **quartile_fields("time_total", total_times),
    }
    score_quartiles = safe_quartiles(total_scores)
    questions_score_quartiles = safe_quartiles(questions_scores)
    max_questions_score = homework.max_questions_score
    if questions_score_quartiles.median is not None and max_questions_score:
        score_ratio = questions_score_quartiles.median / max_questions_score
        score_ratio_pct = round(score_ratio * 100, 1)
    else:
        score_ratio = None
        score_ratio_pct = None
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
        "score_q25": score_quartiles.q25,
        "score_median": score_quartiles.median,
        "score_q75": score_quartiles.q75,
        "questions_score_median": questions_score_quartiles.median,
        "max_questions_score": max_questions_score,
        "score_ratio": score_ratio,
        "score_ratio_pct": score_ratio_pct,
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


def _homework_difficulty_sort_key(hw_stat):
    score_ratio = hw_stat["score_ratio"]
    submissions_count = hw_stat["submissions_count"]
    homework_title = hw_stat["homework"].title
    return score_ratio, -submissions_count, homework_title


def dashboard_homework_difficulty_stats(homework_stats):
    difficulty_stats = []
    for hw_stat in homework_stats:
        homework = hw_stat["homework"]
        if (
            hw_stat["score_ratio"] is not None
            and homework.state == HomeworkState.SCORED.value
        ):
            difficulty_stats.append(hw_stat)
    difficulty_stats.sort(key=_homework_difficulty_sort_key)
    for rank, hw_stat in enumerate(difficulty_stats, start=1):
        hw_stat["difficulty_rank"] = rank

    return difficulty_stats
