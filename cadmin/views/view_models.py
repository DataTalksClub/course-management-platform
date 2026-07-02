from operator import attrgetter

from django.db.models import Count, Q

from courses.models.course import Enrollment
from courses.models.project import (
    PeerReview,
    PeerReviewState,
    ProjectSubmission,
)


def _project_submission_has_incomplete_reviews(submission):
    return (
        submission.peer_reviews_completed
        < submission.peer_reviews_total
    )


def _project_submission_is_missing_repository(submission):
    return not submission.github_link


def _project_submission_is_unscored(submission):
    return submission.total_score is None


def _project_submission_did_not_pass(submission):
    return submission.passed is False


PROJECT_SUBMISSION_STATUS_FILTERS = {
    "incomplete-reviews": _project_submission_has_incomplete_reviews,
    "missing-repository": _project_submission_is_missing_repository,
    "unscored": _project_submission_is_unscored,
    "not-passed": _project_submission_did_not_pass,
}

PROJECT_SUBMISSION_FILTER_COUNTS = {
    "incomplete_reviews": _project_submission_has_incomplete_reviews,
    "missing_repository": _project_submission_is_missing_repository,
    "unscored": _project_submission_is_unscored,
    "not_passed": _project_submission_did_not_pass,
}


def _project_submission_queryset(project, search_query):
    queryset = (
        ProjectSubmission.objects.filter(project=project)
        .select_related("student", "enrollment")
        .order_by("-submitted_at")
    )

    if search_query:
        queryset = queryset.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
        )
    return queryset


def project_submission_list_data(project, search_query, status_filter):
    queryset = _project_submission_queryset(project, search_query)
    submissions = list(queryset)
    _attach_project_review_counts(project, submissions)

    filter_counts = _status_filter_counts(
        submissions,
        PROJECT_SUBMISSION_FILTER_COUNTS,
    )

    filtered_submissions = _filter_by_status(
        submissions,
        status_filter,
        PROJECT_SUBMISSION_STATUS_FILTERS,
    )
    return filtered_submissions, filter_counts


def _attach_project_review_counts(project, submissions):
    peer_reviews = PeerReview.objects.filter(
        reviewer__project=project
    ).select_related("reviewer")

    review_counts = {}
    for review in peer_reviews:
        if review.optional:
            continue
        counts = review_counts.get(review.reviewer_id)
        if counts is None:
            counts = {"completed": 0, "total": 0}
            review_counts[review.reviewer_id] = counts
        counts["total"] += 1
        if review.state == PeerReviewState.SUBMITTED.value:
            counts["completed"] += 1

    for submission in submissions:
        counts = review_counts.get(submission.id)
        if counts is None:
            submission.peer_reviews_completed = 0
            submission.peer_reviews_total = 0
            continue
        submission.peer_reviews_completed = counts["completed"]
        submission.peer_reviews_total = counts["total"]


def _enrollment_has_zero_score(enrollment):
    return enrollment.total_score == 0


def _enrollment_is_hidden(enrollment):
    return not enrollment.display_on_leaderboard


ENROLLMENT_STATUS_FILTERS = {
    "lip-disabled": attrgetter("disable_learning_in_public"),
    "zero-score": _enrollment_has_zero_score,
    "hidden": _enrollment_is_hidden,
    "no-submissions": attrgetter("has_no_submissions"),
}

ENROLLMENT_FILTER_COUNTS = {
    "lip_disabled": attrgetter("disable_learning_in_public"),
    "zero_score": _enrollment_has_zero_score,
    "hidden": _enrollment_is_hidden,
    "no_submissions": attrgetter("has_no_submissions"),
}


def _enrollment_queryset(course, search_query):
    homework_count_annotation = Count("submission", distinct=True)
    project_count_annotation = Count("projectsubmission", distinct=True)
    queryset = (
        Enrollment.objects.filter(course=course)
        .select_related("student")
        .annotate(
            homework_count=homework_count_annotation,
            project_count=project_count_annotation,
        )
        .order_by("position_on_leaderboard", "id")
    )
    if search_query:
        queryset = queryset.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
            | Q(display_name__icontains=search_query)
        )
    return queryset


def enrollment_list_data(course, search_query, status_filter):
    queryset = _enrollment_queryset(course, search_query)
    enrollments = list(queryset)
    _attach_enrollment_support_flags(enrollments)

    filter_counts = _status_filter_counts(
        enrollments,
        ENROLLMENT_FILTER_COUNTS,
    )

    filtered_enrollments = _filter_by_status(
        enrollments,
        status_filter,
        ENROLLMENT_STATUS_FILTERS,
    )
    return filtered_enrollments, filter_counts


def _attach_enrollment_support_flags(enrollments):
    for enrollment in enrollments:
        enrollment.has_no_submissions = (
            enrollment.homework_count == 0
            and enrollment.project_count == 0
        )
        enrollment.has_support_flags = (
            enrollment.disable_learning_in_public
            or not enrollment.display_on_leaderboard
            or enrollment.has_no_submissions
        )


def _status_filter_counts(items, count_predicates):
    total_count = len(items)
    counts = {"all": total_count}
    for key, predicate in count_predicates.items():
        count = 0
        for item in items:
            if predicate(item):
                count += 1
        counts[key] = count
    return counts


def _filter_by_status(items, status_filter, predicates):
    predicate = predicates.get(status_filter)
    if predicate is None:
        return items

    filtered_items = []
    for item in items:
        if predicate(item):
            filtered_items.append(item)
    return filtered_items
