from collections import defaultdict
from datetime import datetime, timedelta

from django.db.models import Count
from django.utils import timezone

from courses.models.course import Enrollment
from courses.models.homework import Submission
from courses.models.project import (
    PeerReview,
    ProjectSubmission,
)

from .types import (
    WrappedActiveEnrollmentData,
    WrappedActivity,
    WrappedActivityByStudent,
)


def wrapped_year_window(year):
    first_year_second = datetime(year, 1, 1)
    year_start = timezone.make_aware(first_year_second)
    next_year_start = datetime(year + 1, 1, 1)
    last_year_second = next_year_start - timedelta(seconds=1)
    year_end = timezone.make_aware(last_year_second)
    return year_start, year_end


def wrapped_activity_querysets(year_start, year_end):
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


def wrapped_students_with_activity(homework_submissions, project_submissions):
    students_from_homeworks = set()
    for homework_submission in homework_submissions:
        students_from_homeworks.add(homework_submission.student)

    students_from_projects = set()
    for project_submission in project_submissions:
        students_from_projects.add(project_submission.student)

    return students_from_homeworks | students_from_projects


def wrapped_enrollment_ids(homework_submissions, project_submissions):
    enrollment_ids_from_homeworks = set()
    for homework_submission in homework_submissions:
        if homework_submission.enrollment_id:
            enrollment_ids_from_homeworks.add(homework_submission.enrollment_id)

    enrollment_ids_from_projects = set()
    for project_submission in project_submissions:
        if project_submission.enrollment_id:
            enrollment_ids_from_projects.add(project_submission.enrollment_id)

    return enrollment_ids_from_homeworks | enrollment_ids_from_projects


def wrapped_enrollments(enrollment_ids):
    enrollments = Enrollment.objects.filter(id__in=enrollment_ids)
    enrollments_with_related = enrollments.select_related(
        "course",
        "student",
    )
    return enrollments_with_related


def wrapped_active_students_and_enrollments(
    homework_submissions, project_submissions
):
    students_with_activity = wrapped_students_with_activity(
        homework_submissions,
        project_submissions,
    )
    enrollment_ids = wrapped_enrollment_ids(
        homework_submissions,
        project_submissions,
    )
    enrollments = wrapped_enrollments(enrollment_ids)
    courses = set()
    for enrollment in enrollments:
        courses.add(enrollment.course)
    return WrappedActiveEnrollmentData(
        students_with_activity=students_with_activity,
        enrollments=enrollments,
        courses=courses,
    )


def group_wrapped_activity_by_student(
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


def wrapped_peer_review_counts(students_with_activity, year_start, year_end):
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


def wrapped_activity_context(year):
    year_start, year_end = wrapped_year_window(year)
    homework_submissions, project_submissions = wrapped_activity_querysets(
        year_start,
        year_end,
    )
    enrollment_data = wrapped_active_students_and_enrollments(
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
