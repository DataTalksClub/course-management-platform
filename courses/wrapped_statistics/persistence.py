from django.db.models import Q, Sum

from courses.models import UserWrappedStatistics

from .activity import (
    group_wrapped_activity_by_student,
    wrapped_peer_review_counts,
)
from .metrics import (
    build_user_wrapped_stat,
    wrapped_course_stats,
    wrapped_leaderboard,
    wrapped_total_hours,
)
from .types import UserWrappedStatData, UserWrappedStatsBuildData


def persist_wrapped_platform_statistics(stats, activity):
    stats.total_participants = len(activity.students_with_activity)
    stats.total_enrollments = activity.enrollments.count()
    stats.total_hours = wrapped_total_hours(
        activity.homework_submissions,
        activity.project_submissions,
    )
    missing_certificate_url = Q(certificate_url__isnull=True)
    empty_certificate_url = Q(certificate_url="")
    no_certificate_url = missing_certificate_url | empty_certificate_url
    stats.total_certificates = activity.enrollments.exclude(
        no_certificate_url
    ).count()
    total_score_annotation = Sum("total_score")
    score_totals = activity.enrollments.aggregate(
        total_score=total_score_annotation
    )
    stats.total_points = score_totals["total_score"] or 0
    stats.course_stats = wrapped_course_stats(
        activity.enrollments,
        activity.courses,
    )

    leaderboard_data = wrapped_leaderboard(activity.enrollments)
    stats.leaderboard = leaderboard_data
    stats.save()
    return leaderboard_data


def build_user_wrapped_stats(data: UserWrappedStatsBuildData):
    user_stats = []
    for student in data.students_with_activity:
        homework_submissions = data.homework_by_student.get(student, [])
        project_submissions = data.project_by_student.get(student, [])
        enrollments = data.enrollment_by_student.get(student, [])
        peer_reviews_count = data.peer_review_counts.get(student.id, 0)
        stat_data = UserWrappedStatData(
            stats=data.stats,
            student=student,
            homework_submissions=homework_submissions,
            project_submissions=project_submissions,
            enrollments=enrollments,
            peer_reviews_count=peer_reviews_count,
            leaderboard_data=data.leaderboard_data,
        )
        user_stat = build_user_wrapped_stat(stat_data)
        user_stats.append(user_stat)
    return user_stats


def replace_user_wrapped_statistics(stats, user_stats_objects):
    UserWrappedStatistics.objects.filter(wrapped=stats).delete()
    UserWrappedStatistics.objects.bulk_create(
        user_stats_objects, batch_size=500
    )


def persist_wrapped_user_statistics(stats, activity, leaderboard_data):
    grouped_activity = group_wrapped_activity_by_student(
        activity.homework_submissions,
        activity.project_submissions,
        activity.enrollments,
    )
    peer_review_counts = wrapped_peer_review_counts(
        activity.students_with_activity,
        activity.year_start,
        activity.year_end,
    )
    build_data = UserWrappedStatsBuildData(
        stats=stats,
        students_with_activity=activity.students_with_activity,
        homework_by_student=grouped_activity.homework_by_student,
        project_by_student=grouped_activity.project_by_student,
        enrollment_by_student=grouped_activity.enrollment_by_student,
        peer_review_counts=peer_review_counts,
        leaderboard_data=leaderboard_data,
    )
    user_stats_objects = build_user_wrapped_stats(build_data)
    replace_user_wrapped_statistics(stats, user_stats_objects)
    return user_stats_objects
