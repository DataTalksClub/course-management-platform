import statistics

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import (
    Course,
    Enrollment,
)
from courses.models.homework import (
    Homework,
    Submission,
)
from courses.models.project import ProjectSubmission


@dataclass(frozen=True)
class QuartileValues:
    q25: object
    median: object
    q75: object


@dataclass(frozen=True)
class HomeworkScoreRatio:
    questions_score_median: object
    max_questions_score: object
    score_ratio: object


def _safe_quartiles(data):
    """Return quartiles, or empty quartiles if there is too little data."""
    if len(data) < 3:
        return QuartileValues(None, None, None)
    try:
        quartiles = statistics.quantiles(data, n=4)
        return QuartileValues(
            quartiles[0],
            quartiles[1],
            quartiles[2],
        )
    except statistics.StatisticsError:
        return QuartileValues(None, None, None)


def _format_median(value):
    """Format a median: whole numbers without decimals, else one decimal."""
    if not value:
        return None
    if value % 1 == 0:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _dashboard_project_stats(course, total_enrollments):
    """Project-submission aggregates for the course dashboard."""
    project_submissions = _dashboard_project_submission_rows(course)
    completion_rate = _project_completion_rate(
        project_submissions,
        total_enrollments,
    )
    time_spent = _project_submission_values(
        project_submissions,
        "time_spent",
    )
    scores = _project_submission_values(project_submissions, "total_score")
    pass_count, fail_count = _project_pass_fail_counts(project_submissions)
    time_quartiles = _safe_quartiles(time_spent)
    score_quartiles = _safe_quartiles(scores)
    rounded_completion_rate = round(completion_rate, 1)

    return {
        "project_completion_rate": rounded_completion_rate,
        "project_time_q25": time_quartiles.q25,
        "project_time_median": time_quartiles.median,
        "project_time_q75": time_quartiles.q75,
        "project_score_q25": score_quartiles.q25,
        "project_score_median": score_quartiles.median,
        "project_score_q75": score_quartiles.q75,
        "project_pass_count": pass_count,
        "project_fail_count": fail_count,
        "project_total_submissions": pass_count + fail_count,
    }


def _dashboard_project_submission_rows(course):
    submission_rows = (
        ProjectSubmission.objects.filter(project__course=course)
        .select_related("project", "enrollment")
        .values("enrollment_id", "time_spent", "total_score", "passed")
    )
    return list(submission_rows)


def _project_completion_rate(project_submissions, total_enrollments):
    if total_enrollments <= 0:
        return 0

    enrollment_ids = _project_submission_enrollment_ids(project_submissions)
    completed_enrollments_count = len(enrollment_ids)
    return completed_enrollments_count / total_enrollments * 100


def _project_submission_enrollment_ids(project_submissions):
    enrollment_ids = set()
    for submission in project_submissions:
        enrollment_ids.add(submission["enrollment_id"])
    return enrollment_ids


def _project_submission_values(project_submissions, field_name):
    values = []
    for submission in project_submissions:
        value = submission[field_name]
        if value is not None:
            values.append(value)
    return values


def _project_pass_fail_counts(project_submissions):
    pass_count = 0
    for submission in project_submissions:
        if submission["passed"]:
            pass_count += 1
    fail_count = len(project_submissions) - pass_count
    return pass_count, fail_count


def _submission_values(submissions, field_name):
    values = []
    for submission in submissions:
        value = submission[field_name]
        if value is not None:
            values.append(value)
    return values


def _dashboard_completion_rate(submissions_count, total_enrollments):
    if total_enrollments <= 0:
        return 0.0
    return round(submissions_count / total_enrollments * 100, 1)


def _dashboard_total_homework_times(hw_submissions):
    total_times = []
    for submission in hw_submissions:
        lectures_time = submission["time_spent_lectures"]
        homework_time = submission["time_spent_homework"]
        if lectures_time is None or homework_time is None:
            continue
        total_time = lectures_time + homework_time
        total_times.append(total_time)
    return total_times


def _quartile_fields(prefix, values):
    quartiles = _safe_quartiles(values)
    formatted_median = _format_median(quartiles.median)
    return {
        f"{prefix}_q25": quartiles.q25,
        f"{prefix}_median": quartiles.median,
        f"{prefix}_q75": quartiles.q75,
        f"{prefix}_median_formatted": formatted_median,
    }


def _dashboard_homework_time_stats(hw_submissions):
    stats = {}
    lecture_times = _submission_values(
        hw_submissions,
        "time_spent_lectures",
    )
    lecture_time_stats = _quartile_fields("time_lecture", lecture_times)
    stats.update(lecture_time_stats)

    homework_times = _submission_values(
        hw_submissions,
        "time_spent_homework",
    )
    homework_time_stats = _quartile_fields("time_homework", homework_times)
    stats.update(homework_time_stats)

    total_times = _dashboard_total_homework_times(hw_submissions)
    total_time_stats = _quartile_fields("time_total", total_times)
    stats.update(total_time_stats)
    return stats


def _dashboard_homework_score_ratio(homework, hw_submissions):
    questions_scores = _submission_values(hw_submissions, "questions_score")
    questions_score_quartiles = _safe_quartiles(questions_scores)
    max_questions_score = homework.max_questions_score
    score_ratio = (
        questions_score_quartiles.median / max_questions_score
        if questions_score_quartiles.median is not None
        and max_questions_score
        else None
    )
    return HomeworkScoreRatio(
        questions_score_median=questions_score_quartiles.median,
        max_questions_score=max_questions_score,
        score_ratio=score_ratio,
    )


def _dashboard_homework_score_stats(homework, hw_submissions):
    total_scores = _submission_values(hw_submissions, "total_score")
    score_quartiles = _safe_quartiles(total_scores)
    score_ratio_data = _dashboard_homework_score_ratio(
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


def _dashboard_homework_stat(homework, hw_submissions, total_enrollments):
    """Per-homework statistics row for the dashboard."""
    time_stats = _dashboard_homework_time_stats(hw_submissions)
    score_stats = _dashboard_homework_score_stats(homework, hw_submissions)
    submissions_count = len(hw_submissions)
    completion_rate = _dashboard_completion_rate(
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


def _dashboard_homework_submissions_by_homework(all_hw_submissions):
    hw_submissions_by_homework = defaultdict(list)
    for submission in all_hw_submissions:
        hw_submissions_by_homework[submission["homework_id"]].append(
            submission
        )
    return hw_submissions_by_homework


def _dashboard_homework_stat_rows(
    homeworks,
    hw_submissions_by_homework,
    total_enrollments,
):
    stat_rows = []
    for homework in homeworks:
        submissions = hw_submissions_by_homework.get(homework.id, [])
        stat_row = _dashboard_homework_stat(
            homework,
            submissions,
            total_enrollments,
        )
        stat_rows.append(stat_row)
    return stat_rows


def _dashboard_homework_difficulty_stats(homework_stats):
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


def _dashboard_homework_stats(homeworks, all_hw_submissions, total_enrollments):
    """Build per-homework stats plus the difficulty-ranked subset."""
    hw_submissions_by_homework = _dashboard_homework_submissions_by_homework(
        all_hw_submissions
    )
    homework_stats = _dashboard_homework_stat_rows(
        homeworks,
        hw_submissions_by_homework,
        total_enrollments,
    )
    difficulty_stats = _dashboard_homework_difficulty_stats(homework_stats)
    return homework_stats, difficulty_stats


def _dashboard_avg_total_score(course):
    enrollments_with_scores = Enrollment.objects.filter(
        course=course, total_score__isnull=False
    ).values_list("total_score", flat=True)
    return (
        statistics.mean(enrollments_with_scores)
        if enrollments_with_scores
        else 0
    )


def _dashboard_homeworks(course):
    homeworks = Homework.objects.filter(course=course)
    homeworks = homeworks.order_by("id")
    max_questions_score = Sum("question__scores_for_correct_answer")
    return homeworks.annotate(
        max_questions_score=max_questions_score,
    )


def _dashboard_homework_submissions(course):
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


def _dashboard_graduates_count(course):
    return (
        Enrollment.objects
        .filter(
            course=course, certificate_url__isnull=False
        )
        .exclude(certificate_url="")
        .count()
    )


def _dashboard_context(course):
    total_enrollments = Enrollment.objects.filter(course=course).count()
    homeworks = _dashboard_homeworks(course)
    homework_submissions = _dashboard_homework_submissions(course)
    homework_stats, homework_difficulty_stats = _dashboard_homework_stats(
        homeworks,
        homework_submissions,
        total_enrollments,
    )
    raw_avg_total_score = _dashboard_avg_total_score(course)
    avg_total_score = round(raw_avg_total_score, 1)
    graduates_count = _dashboard_graduates_count(course)
    project_stats = _dashboard_project_stats(course, total_enrollments)

    return {
        "course": course,
        "total_enrollments": total_enrollments,
        "avg_total_score": avg_total_score,
        "project_passing_score": course.project_passing_score,
        "graduates_count": graduates_count,
        "homework_stats": homework_stats,
        "homework_difficulty_stats": homework_difficulty_stats,
        **project_stats,
    }


def dashboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    if not course.first_homework_scored:
        response = redirect("course", course_slug=course.slug)
        return response

    context = _dashboard_context(course)
    response = render(
        request,
        "courses/dashboard.html",
        context,
    )
    return response
