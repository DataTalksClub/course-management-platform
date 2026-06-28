from collections import defaultdict

from django.db.models import Count, Q

from courses.models import (
    Enrollment,
    PeerReview,
    PeerReviewState,
    ProjectSubmission,
)


def project_submission_list_data(project, search_query, status_filter):
    submissions = (
        ProjectSubmission.objects.filter(project=project)
        .select_related("student", "enrollment")
        .order_by("-submitted_at")
    )

    if search_query:
        submissions = submissions.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
        )

    submissions = list(submissions)
    _attach_project_review_counts(project, submissions)

    filter_counts = {
        "all": len(submissions),
        "incomplete_reviews": sum(
            1
            for submission in submissions
            if submission.peer_reviews_completed
            < submission.peer_reviews_total
        ),
        "missing_repository": sum(
            1 for submission in submissions if not submission.github_link
        ),
        "unscored": sum(
            1 for submission in submissions if submission.total_score is None
        ),
        "not_passed": sum(
            1 for submission in submissions if submission.passed is False
        ),
    }

    return _filter_project_submissions(submissions, status_filter), filter_counts


def _attach_project_review_counts(project, submissions):
    peer_reviews = PeerReview.objects.filter(
        reviewer__project=project
    ).select_related("reviewer")

    review_counts = defaultdict(lambda: {"completed": 0, "total": 0})
    for review in peer_reviews:
        if review.optional:
            continue
        review_counts[review.reviewer_id]["total"] += 1
        if review.state == PeerReviewState.SUBMITTED.value:
            review_counts[review.reviewer_id]["completed"] += 1

    for submission in submissions:
        counts = review_counts[submission.id]
        submission.peer_reviews_completed = counts["completed"]
        submission.peer_reviews_total = counts["total"]


def _filter_project_submissions(submissions, status_filter):
    if status_filter == "incomplete-reviews":
        return [
            submission
            for submission in submissions
            if submission.peer_reviews_completed
            < submission.peer_reviews_total
        ]
    if status_filter == "missing-repository":
        return [
            submission for submission in submissions if not submission.github_link
        ]
    if status_filter == "unscored":
        return [
            submission
            for submission in submissions
            if submission.total_score is None
        ]
    if status_filter == "not-passed":
        return [
            submission for submission in submissions if submission.passed is False
        ]
    return submissions


def enrollment_list_data(course, search_query, status_filter):
    enrollments = (
        Enrollment.objects.filter(course=course)
        .select_related("student")
        .annotate(
            homework_count=Count("submission", distinct=True),
            project_count=Count("projectsubmission", distinct=True),
        )
        .order_by("position_on_leaderboard", "id")
    )
    if search_query:
        enrollments = enrollments.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
            | Q(display_name__icontains=search_query)
        )

    enrollments = list(enrollments)
    _attach_enrollment_support_flags(enrollments)

    filter_counts = {
        "all": len(enrollments),
        "lip_disabled": sum(
            1
            for enrollment in enrollments
            if enrollment.disable_learning_in_public
        ),
        "zero_score": sum(
            1 for enrollment in enrollments if enrollment.total_score == 0
        ),
        "hidden": sum(
            1
            for enrollment in enrollments
            if not enrollment.display_on_leaderboard
        ),
        "no_submissions": sum(
            1 for enrollment in enrollments if enrollment.has_no_submissions
        ),
    }

    return _filter_enrollments(enrollments, status_filter), filter_counts


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


def _filter_enrollments(enrollments, status_filter):
    if status_filter == "lip-disabled":
        return [
            enrollment
            for enrollment in enrollments
            if enrollment.disable_learning_in_public
        ]
    if status_filter == "zero-score":
        return [
            enrollment for enrollment in enrollments if enrollment.total_score == 0
        ]
    if status_filter == "hidden":
        return [
            enrollment
            for enrollment in enrollments
            if not enrollment.display_on_leaderboard
        ]
    if status_filter == "no-submissions":
        return [
            enrollment for enrollment in enrollments if enrollment.has_no_submissions
        ]
    return enrollments
