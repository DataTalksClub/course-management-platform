from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect

from courses.models.project import ProjectSubmission
from courses.votes import (
    PROJECT_VOTES_PER_PROJECT,
    get_project_vote_counts,
    get_voted_submission_ids,
    update_project_vote,
)


def project_vote_response(request, course, project):
    if not request.user.is_authenticated:
        response = redirect("login")
        return response

    submission = _apply_project_vote(request, project)

    requested_with = request.headers.get("x-requested-with")
    if requested_with == "XMLHttpRequest":
        payload = _project_vote_payload(
            request.user,
            course,
            project,
            submission,
        )
        response = JsonResponse(payload)
        return response

    response = redirect(
        "project_list",
        course_slug=course.slug,
        project_slug=project.slug,
    )
    return response


def _apply_project_vote(request, project):
    submission = _project_vote_submission(request, project)
    vote_action = request.POST.get("action", "vote")
    update_project_vote(
        request.user,
        submission,
        action=vote_action,
    )
    return submission


def _project_vote_submission(request, project):
    submissions = ProjectSubmission.objects.select_related("project")
    submission_id = request.POST.get("submission_id")
    return get_object_or_404(
        submissions,
        id=submission_id,
        project=project,
        volunteer_review_only=False,
    )


def _project_submission_vote_count(submission):
    submissions = ProjectSubmission.objects.filter(id=submission.id)
    vote_count_annotation = Count("votes")
    submissions = submissions.annotate(vote_count=vote_count_annotation)
    vote_counts = submissions.values_list("vote_count", flat=True)
    return vote_counts.get()


def _project_vote_payload(user, course, project, submission):
    voted_submission_ids = get_voted_submission_ids(user, course)
    project_vote_counts = get_project_vote_counts(user, course)
    project_vote_count = project_vote_counts.get(project.id, 0)
    votes_left = max(PROJECT_VOTES_PER_PROJECT - project_vote_count, 0)
    vote_limit_reached = project_vote_count >= PROJECT_VOTES_PER_PROJECT
    vote_count = _project_submission_vote_count(submission)
    voted = submission.id in voted_submission_ids
    voted_submission_id_list = list(voted_submission_ids)
    return {
        "submission_id": submission.id,
        "vote_count": vote_count,
        "voted": voted,
        "voted_submission_ids": voted_submission_id_list,
        "votes_left": votes_left,
        "vote_limit_reached": vote_limit_reached,
    }
