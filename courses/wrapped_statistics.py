import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from operator import attrgetter
from time import time

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import (
    Enrollment,
    PeerReview,
    ProjectSubmission,
    Submission,
    UserWrappedStatistics,
    WrappedStatistics,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserWrappedStatData:
    stats: WrappedStatistics
    student: object
    homework_submissions: list
    project_submissions: list
    enrollments: list
    peer_reviews_count: int
    leaderboard_data: list


@dataclass(frozen=True)
class UserWrappedMetrics:
    total_points: int
    total_hours: float
    learning_in_public_count: int
    faq_contributions_count: int
    certificates_earned: int
    courses: list
    rank: int | None
    display_name: str


@dataclass
class WrappedLeaderboardUserScore:
    student: object
    display_name: str
    total_score: int = 0


@dataclass(frozen=True)
class WrappedActiveEnrollmentData:
    students_with_activity: set
    enrollments: object
    courses: set


@dataclass(frozen=True)
class WrappedActivityByStudent:
    homework_by_student: dict
    project_by_student: dict
    enrollment_by_student: dict


@dataclass(frozen=True)
class WrappedActivity:
    year_start: datetime
    year_end: datetime
    homework_submissions: object
    project_submissions: object
    students_with_activity: set
    enrollments: object
    courses: set


@dataclass(frozen=True)
class UserWrappedStatsBuildData:
    stats: WrappedStatistics
    students_with_activity: set
    homework_by_student: dict
    project_by_student: dict
    enrollment_by_student: dict
    peer_review_counts: dict
    leaderboard_data: list


def _wrapped_course_stats(enrollments, courses):
    """Per-course enrollment counts, sorted most-popular first."""
    course_stats_list = []
    for course in courses:
        enrollment_count = enrollments.filter(course=course).count()
        course_stats = {
            "title": course.title,
            "slug": course.slug,
            "enrollment_count": enrollment_count,
        }
        course_stats_list.append(course_stats)
    course_stats_list.sort(
        key=lambda x: x["enrollment_count"], reverse=True
    )
    return course_stats_list


def _wrapped_leaderboard(enrollments):
    """Top-100 leaderboard, summing each student's score across courses."""
    user_scores = _wrapped_leaderboard_scores(enrollments)
    top_scores = _top_wrapped_leaderboard_scores(user_scores)
    return _wrapped_leaderboard_entries(top_scores)


def _wrapped_leaderboard_scores(enrollments):
    user_scores_by_student_id = {}
    for enrollment in enrollments:
        user_score = user_scores_by_student_id.get(enrollment.student_id)
        if user_score is None:
            user_score = WrappedLeaderboardUserScore(
                student=enrollment.student,
                display_name=enrollment.display_name,
            )
            user_scores_by_student_id[enrollment.student_id] = user_score

        user_score.total_score += enrollment.total_score or 0

    return user_scores_by_student_id


def _top_wrapped_leaderboard_scores(user_scores):
    user_score_values = user_scores.values()
    total_score_key = attrgetter("total_score")
    sorted_scores = sorted(
        user_score_values,
        key=total_score_key,
        reverse=True,
    )
    return sorted_scores[:100]


def _wrapped_leaderboard_entries(user_scores):
    leaderboard = []
    for rank, user_score in enumerate(user_scores, start=1):
        leaderboard_entry = {
            "rank": rank,
            "display_name": user_score.display_name,
            "total_score": user_score.total_score,
            "student_id": user_score.student.id,
        }
        leaderboard.append(leaderboard_entry)
    return leaderboard


def _has_faq_contribution(submission):
    if not submission.faq_contribution_url:
        return False
    stripped_url = submission.faq_contribution_url.strip()
    if stripped_url:
        return True
    return False


def _wrapped_courses(enrollments):
    courses = []
    for enrollment in enrollments:
        course_record = {
            "title": enrollment.course.title,
            "score": enrollment.total_score,
            "slug": enrollment.course.slug,
            "enrollment_id": enrollment.id,
        }
        courses.append(course_record)
    return courses


def _wrapped_certificates_count(enrollments):
    count = 0
    for enrollment in enrollments:
        if enrollment.certificate_url and enrollment.certificate_url.strip():
            count += 1
    return count


def _capped_hours(value):
    if value:
        hours = value
    else:
        hours = 0
    capped_hours = min(hours, 100.0)
    return capped_hours


def _wrapped_homework_hours(submission):
    return _capped_hours(submission.time_spent_lectures) + _capped_hours(
        submission.time_spent_homework
    )


def _wrapped_project_hours(submission):
    return _capped_hours(submission.time_spent)


def _wrapped_total_hours(homework_submissions, project_submissions):
    homework_hours = 0
    for submission in homework_submissions:
        homework_hours += _wrapped_homework_hours(submission)

    project_hours = 0
    for submission in project_submissions:
        project_hours += _wrapped_project_hours(submission)

    return round(homework_hours + project_hours, 1)


def _wrapped_learning_in_public_count(
    homework_submissions,
    project_submissions,
):
    homework_links = 0
    for homework_submission in homework_submissions:
        if homework_submission.learning_in_public_links:
            homework_links += len(homework_submission.learning_in_public_links)

    project_links = 0
    for project_submission in project_submissions:
        if project_submission.learning_in_public_links:
            project_links += len(project_submission.learning_in_public_links)

    return homework_links + project_links


def _wrapped_faq_count(homework_submissions, project_submissions):
    count = 0
    for submission in homework_submissions:
        if _has_faq_contribution(submission):
            count += 1
    for submission in project_submissions:
        if _has_faq_contribution(submission):
            count += 1
    return count


def _wrapped_rank(student, leaderboard_data):
    for entry in leaderboard_data:
        if entry["student_id"] == student.id:
            return entry["rank"]
    return None


def _wrapped_total_points(enrollments):
    total_points = 0
    for enrollment in enrollments:
        total_points += enrollment.total_score or 0
    return total_points


def _wrapped_display_name(student, enrollments):
    if enrollments:
        return enrollments[0].display_name
    return student.username


def _user_wrapped_metrics(data):
    total_points = _wrapped_total_points(data.enrollments)
    total_hours = _wrapped_total_hours(
        data.homework_submissions,
        data.project_submissions,
    )
    learning_in_public_count = _wrapped_learning_in_public_count(
        data.homework_submissions,
        data.project_submissions,
    )
    faq_contributions_count = _wrapped_faq_count(
        data.homework_submissions,
        data.project_submissions,
    )
    certificates_earned = _wrapped_certificates_count(data.enrollments)
    courses = _wrapped_courses(data.enrollments)
    rank = _wrapped_rank(data.student, data.leaderboard_data)
    display_name = _wrapped_display_name(data.student, data.enrollments)

    return UserWrappedMetrics(
        total_points=total_points,
        total_hours=total_hours,
        learning_in_public_count=learning_in_public_count,
        faq_contributions_count=faq_contributions_count,
        certificates_earned=certificates_earned,
        courses=courses,
        rank=rank,
        display_name=display_name,
    )


def _build_user_wrapped_stat(data):
    """Build an (unsaved) UserWrappedStatistics row for one student."""
    metrics = _user_wrapped_metrics(data)
    homework_count = len(data.homework_submissions)
    project_count = len(data.project_submissions)

    return UserWrappedStatistics(
        wrapped=data.stats,
        user=data.student,
        total_points=metrics.total_points,
        total_hours=metrics.total_hours,
        homework_count=homework_count,
        project_count=project_count,
        peer_reviews_given=data.peer_reviews_count,
        learning_in_public_count=metrics.learning_in_public_count,
        faq_contributions_count=metrics.faq_contributions_count,
        certificates_earned=metrics.certificates_earned,
        courses=metrics.courses,
        rank=metrics.rank,
        display_name=metrics.display_name,
    )


def _wrapped_year_window(year):
    first_year_second = datetime(year, 1, 1)
    year_start = timezone.make_aware(first_year_second)
    next_year_start = datetime(year + 1, 1, 1)
    last_year_second = next_year_start - timedelta(seconds=1)
    year_end = timezone.make_aware(last_year_second)
    return year_start, year_end


def _wrapped_activity_querysets(year_start, year_end):
    homework_submissions = Submission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).select_related(
        "homework", "homework__course", "enrollment", "student"
    )
    project_submissions = ProjectSubmission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).select_related(
        "project", "project__course", "enrollment", "student"
    )
    return homework_submissions, project_submissions


def _wrapped_students_with_activity(homework_submissions, project_submissions):
    students_from_homeworks = set()
    for homework_submission in homework_submissions:
        students_from_homeworks.add(homework_submission.student)

    students_from_projects = set()
    for project_submission in project_submissions:
        students_from_projects.add(project_submission.student)

    return students_from_homeworks | students_from_projects


def _wrapped_enrollment_ids(homework_submissions, project_submissions):
    enrollment_ids_from_homeworks = set()
    for homework_submission in homework_submissions:
        if homework_submission.enrollment_id:
            enrollment_ids_from_homeworks.add(homework_submission.enrollment_id)

    enrollment_ids_from_projects = set()
    for project_submission in project_submissions:
        if project_submission.enrollment_id:
            enrollment_ids_from_projects.add(project_submission.enrollment_id)

    return enrollment_ids_from_homeworks | enrollment_ids_from_projects


def _wrapped_enrollments(enrollment_ids):
    enrollments = Enrollment.objects.filter(id__in=enrollment_ids)
    enrollments_with_related = enrollments.select_related(
        "course",
        "student",
    )
    return enrollments_with_related


def _wrapped_active_students_and_enrollments(
    homework_submissions, project_submissions
):
    students_with_activity = _wrapped_students_with_activity(
        homework_submissions,
        project_submissions,
    )
    enrollment_ids = _wrapped_enrollment_ids(
        homework_submissions,
        project_submissions,
    )
    enrollments = _wrapped_enrollments(enrollment_ids)
    courses = set()
    for enrollment in enrollments:
        courses.add(enrollment.course)
    return WrappedActiveEnrollmentData(
        students_with_activity=students_with_activity,
        enrollments=enrollments,
        courses=courses,
    )


def _persist_wrapped_platform_statistics(stats, activity):
    stats.total_participants = len(activity.students_with_activity)
    stats.total_enrollments = activity.enrollments.count()
    stats.total_hours = _wrapped_total_hours(
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
    stats.course_stats = _wrapped_course_stats(
        activity.enrollments,
        activity.courses,
    )

    leaderboard_data = _wrapped_leaderboard(activity.enrollments)
    stats.leaderboard = leaderboard_data
    stats.save()
    return leaderboard_data


def _group_wrapped_activity_by_student(
    homework_submissions, project_submissions, enrollments
):
    homework_by_student = defaultdict(list)
    for homework_submission in homework_submissions:
        student = homework_submission.student
        homework_by_student[student].append(homework_submission)

    project_by_student = defaultdict(list)
    for project_submission in project_submissions:
        student = project_submission.student
        project_by_student[student].append(project_submission)

    enrollment_by_student = defaultdict(list)
    for enrollment in enrollments:
        student = enrollment.student
        enrollment_by_student[student].append(enrollment)

    return WrappedActivityByStudent(
        homework_by_student=homework_by_student,
        project_by_student=project_by_student,
        enrollment_by_student=enrollment_by_student,
    )


def _wrapped_peer_review_counts(students_with_activity, year_start, year_end):
    peer_review_counts = {}
    review_count_annotation = Count("id")
    peer_reviews = (
        PeerReview.objects.filter(
            reviewer__student__in=students_with_activity,
            submitted_at__gte=year_start,
            submitted_at__lte=year_end,
        )
        .values("reviewer__student")
        .annotate(count=review_count_annotation)
    )
    for peer_review in peer_reviews:
        peer_review_counts[peer_review["reviewer__student"]] = peer_review[
            "count"
        ]
    return peer_review_counts


def _build_user_wrapped_stats(data):
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
        user_stat = _build_user_wrapped_stat(stat_data)
        user_stats.append(user_stat)
    return user_stats


def _replace_user_wrapped_statistics(stats, user_stats_objects):
    UserWrappedStatistics.objects.filter(wrapped=stats).delete()
    UserWrappedStatistics.objects.bulk_create(
        user_stats_objects, batch_size=500
    )


def _wrapped_statistics_to_calculate(year, force):
    stats, created = WrappedStatistics.objects.get_or_create(year=year)
    if not force and not created:
        logger.info(
            f"Wrapped statistics for {year} already exist. Use force=True to recalculate."
        )
        return stats, False
    return stats, True


def _wrapped_activity_context(year):
    year_start, year_end = _wrapped_year_window(year)
    homework_submissions, project_submissions = (
        _wrapped_activity_querysets(year_start, year_end)
    )
    enrollment_data = _wrapped_active_students_and_enrollments(
        homework_submissions,
        project_submissions,
    )
    return WrappedActivity(
        year_start=year_start,
        year_end=year_end,
        homework_submissions=homework_submissions,
        project_submissions=project_submissions,
        students_with_activity=enrollment_data.students_with_activity,
        enrollments=enrollment_data.enrollments,
        courses=enrollment_data.courses,
    )


def _persist_wrapped_user_statistics(stats, activity, leaderboard_data):
    grouped_activity = _group_wrapped_activity_by_student(
        activity.homework_submissions,
        activity.project_submissions,
        activity.enrollments,
    )
    peer_review_counts = _wrapped_peer_review_counts(
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
    user_stats_objects = _build_user_wrapped_stats(build_data)
    _replace_user_wrapped_statistics(stats, user_stats_objects)
    return user_stats_objects


def _calculate_wrapped_statistics(stats, year):
    logger.info(f"Calculating wrapped statistics for {year}...")
    start_time = time()

    activity = _wrapped_activity_context(year)
    leaderboard_data = _persist_wrapped_platform_statistics(
        stats,
        activity,
    )

    logger.info(
        "Platform statistics calculated. Now calculating individual user statistics..."
    )
    user_stats_objects = _persist_wrapped_user_statistics(
        stats,
        activity,
        leaderboard_data,
    )

    _log_wrapped_statistics_calculated(
        year,
        start_time,
        user_stats_objects,
    )


def _log_wrapped_statistics_calculated(
    year,
    start_time,
    user_stats_objects,
):
    elapsed_time = time() - start_time
    logger.info(
        f"Wrapped statistics for {year} calculated successfully in {elapsed_time:.2f} seconds. "
        f"Processed {len(user_stats_objects)} users."
    )


def calculate_wrapped_statistics(year=2025, force=False):
    """
    Calculate and save wrapped statistics for a given year.
    This function pre-calculates all the statistics that would be needed
    for the wrapped page to avoid slow queries on page load.

    Args:
        year: The year to calculate statistics for (default: 2025)
        force: If True, recalculate even if statistics already exist

    Returns:
        WrappedStatistics object
    """
    stats, should_calculate = _wrapped_statistics_to_calculate(year, force)
    if not should_calculate:
        return stats

    _calculate_wrapped_statistics(stats, year)
    return stats
