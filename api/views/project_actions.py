from django.http import JsonResponse

from courses.models.project import PeerReview
from courses.project_assignment import (
    ProjectActionStatus,
    assign_peer_reviews_for_project,
)
from courses.project_scoring import score_project


def project_action_base(project, status, message):
    project.refresh_from_db()
    return {
        "status": status.name,
        "message": message,
        "project_id": project.id,
        "project_slug": project.slug,
        "state": project.state,
    }


def project_assign_reviews_response(project):
    before_count = PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).count()
    status, message = assign_peer_reviews_for_project(project)
    after_count = PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).count()
    if status == ProjectActionStatus.OK:
        assigned_peer_reviews_count = after_count - before_count
        response_status = 200
    else:
        assigned_peer_reviews_count = 0
        response_status = 400
    data = project_action_base(project, status, message)
    data.update(
        {
            "peer_reviews_count": after_count,
            "assigned_peer_reviews_count": assigned_peer_reviews_count,
        }
    )
    response = JsonResponse(
        data,
        status=response_status,
    )
    return response


def project_scorable_submissions_count(project):
    return (
        PeerReview.objects.filter(
            submission_under_evaluation__project=project,
        )
        .values("submission_under_evaluation")
        .distinct()
        .count()
    )


def project_score_response(project):
    scorable_submissions_count = project_scorable_submissions_count(project)
    status, message = score_project(project)
    submissions = project.projectsubmission_set.all()
    response_status = 400
    scored_count = 0
    passed_count = 0
    if status == ProjectActionStatus.OK:
        response_status = 200
        scored_count = scorable_submissions_count
        passed_count = submissions.filter(passed=True).count()

    submissions_count = submissions.count()
    data = project_action_base(project, status, message)
    data.update(
        {
            "submissions_count": submissions_count,
            "scored_submissions_count": scored_count,
            "passed_submissions_count": passed_count,
        }
    )
    response = JsonResponse(
        data,
        status=response_status,
    )
    return response
