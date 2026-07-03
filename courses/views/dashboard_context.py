import statistics

from courses.models.course import Enrollment
from courses.views.dashboard_homeworks import (
    dashboard_homework_stats,
    dashboard_homework_submissions,
    dashboard_homeworks,
)
from courses.views.dashboard_metrics import quartile_fields
from courses.views.dashboard_projects import dashboard_project_stats
from courses.views.dashboard_engagement import dashboard_engagement_trend
from courses.views.dashboard_questions import dashboard_question_difficulty
from courses.views.dashboard_timing import dashboard_submission_timing


def dashboard_context(course):
    total_enrollments = Enrollment.objects.filter(course=course).count()
    homeworks = dashboard_homeworks(course)
    homework_submissions = dashboard_homework_submissions(course)
    homework_stats, homework_difficulty_stats = dashboard_homework_stats(
        homeworks,
        homework_submissions,
        total_enrollments,
    )
    raw_avg_total_score = dashboard_avg_total_score(course)
    avg_total_score = round(raw_avg_total_score, 1)
    overall_completion_rate = dashboard_overall_completion_rate(homework_stats)
    total_score_distribution = dashboard_total_score_distribution(course)
    question_difficulty = dashboard_question_difficulty(course)
    submission_timing = dashboard_submission_timing(course)
    engagement_trend = dashboard_engagement_trend(course)
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
