import statistics

from courses.models.course import Enrollment
from courses.models.homework import HomeworkState
from courses.views.dashboard_homeworks import (
    dashboard_all_homeworks,
    dashboard_homework_stats,
    dashboard_homework_submissions,
)
from courses.views.dashboard_metrics import quartile_fields
from courses.views.dashboard_projects import dashboard_project_stats
from courses.views.dashboard_engagement import dashboard_engagement_trend
from courses.views.dashboard_questions import dashboard_question_difficulty
from courses.views.dashboard_timing import dashboard_submission_timing


def dashboard_context(course):
    # Single index-only scan on enroll_course_score_idx for count, mean,
    # and quartiles (Enrollment.total_score is NOT NULL).
    total_scores = list(
        Enrollment.objects.filter(
            course=course, total_score__isnull=False
        ).values_list("total_score", flat=True)
    )
    total_enrollments = len(total_scores)
    all_homeworks = dashboard_all_homeworks(course)
    homeworks = [
        hw
        for hw in all_homeworks
        if hw.state == HomeworkState.SCORED.value
    ]
    due_dates_by_homework_id = {
        hw.id: hw.due_date for hw in all_homeworks
    }
    homework_submissions = list(
        dashboard_homework_submissions(
            course, homework_ids=due_dates_by_homework_id
        )
    )
    homework_stats, homework_difficulty_stats = dashboard_homework_stats(
        homeworks,
        homework_submissions,
        total_enrollments,
    )
    raw_avg_total_score = (
        statistics.mean(total_scores) if total_scores else 0
    )
    avg_total_score = round(raw_avg_total_score, 1)
    overall_completion_rate = dashboard_overall_completion_rate(homework_stats)
    total_score_distribution = quartile_fields("total_score", total_scores)
    question_difficulty = dashboard_question_difficulty(
        course, scored_homeworks=homeworks
    )
    submission_timing = dashboard_submission_timing(
        homework_submissions,
        due_dates_by_homework_id=due_dates_by_homework_id,
    )
    engagement_trend = dashboard_engagement_trend(homework_submissions)
    graduates_count = dashboard_graduates_count(course)
    project_stats = dashboard_project_stats(course, total_enrollments)

    return {
        "course": course,
        "total_enrollments": total_enrollments,
        "avg_total_score": avg_total_score,
        "overall_completion_rate": overall_completion_rate,
        "project_passing_score": course.project_passing_score,
        "graduates_count": graduates_count,
        "homework_stats": homework_stats,
        "homework_difficulty_stats": homework_difficulty_stats,
        "question_difficulty": question_difficulty,
        "submission_timing": submission_timing,
        "engagement_trend": engagement_trend,
        **total_score_distribution,
        **project_stats,
    }


def dashboard_overall_completion_rate(homework_stats):
    completion_rates = [
        hw_stat["completion_rate"] for hw_stat in homework_stats
    ]
    if not completion_rates:
        return None
    return round(statistics.mean(completion_rates), 1)


def dashboard_total_score_distribution(course):
    total_scores = list(
        Enrollment.objects.filter(
            course=course, total_score__isnull=False
        ).values_list("total_score", flat=True)
    )
    return quartile_fields("total_score", total_scores)


def dashboard_avg_total_score(course):
    enrollments_with_scores = Enrollment.objects.filter(
        course=course, total_score__isnull=False
    ).values_list("total_score", flat=True)
    if enrollments_with_scores:
        return statistics.mean(enrollments_with_scores)
    return 0


def dashboard_graduates_count(course):
    return (
        Enrollment.objects
        .filter(
            course=course, certificate_url__isnull=False
        )
        .exclude(certificate_url="")
        .count()
    )
