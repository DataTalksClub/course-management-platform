from django.http import JsonResponse

from courses.models.project import PeerReview
from courses.project_assignment import ProjectActionStatus
from courses.scoring_queue import (
    enqueue_project_assign_reviews,
    enqueue_project_scoring,
    job_poll_path_project,
    job_to_dict,
    latest_project_job,
    project_assign_reviews_precheck,
    project_score_precheck,
)


def project_action_base(project, status, message):
    project.refresh_from_db()
    return {
        "status": status.name,
        "message": message,
        "project_id": project.id,
        "project_slug": project.slug,
        "state": project.state,
    }


def _project_enqueued_response(request, project, job, created, verb):
    project.refresh_from_db()
    if created:
        message = (
            f"{verb} queued for project {project.id} "
            f"(job #{job.id}). Poll for status."
        )
    else:
        message = (
            f"{verb} already in progress for project {project.id} "
            f"(job #{job.id})."
        )
    by_slug = "by_slug" in request.path
    poll_path = job_poll_path_project(
        project.course.slug,
        project_slug=project.slug if by_slug else None,
        project_id=None if by_slug else project.id,
    )
    data = project_action_base(project, ProjectActionStatus.OK, message)
    data["status"] = job.status.upper()
    data.update(
        {
            "peer_reviews_count": PeerReview.objects.filter(
                submission_under_evaluation__project=project,
            ).count(),
            "submissions_count": project.projectsubmission_set.count(),
            "poll_url": poll_path,
        }
    )
    data.update(job_to_dict(job))
    data["job_id"] = job.id
    data["job_status"] = job.status
    return JsonResponse(data, status=202)


def _project_blocked_response(project, message):
    data = project_action_base(project, ProjectActionStatus.FAIL, message)
    data.update(
        {
            "peer_reviews_count": PeerReview.objects.filter(
                submission_under_evaluation__project=project,
            ).count(),
            "submissions_count": project.projectsubmission_set.count(),
            "scored_submissions_count": 0,
            "passed_submissions_count": 0,
            "assigned_peer_reviews_count": 0,
        }
    )
    return JsonResponse(data, status=400)


def project_assign_reviews_enqueue_response(request, project):
    error = project_assign_reviews_precheck(project)
    if error is not None:
        return _project_blocked_response(project, error)
    requested_by = getattr(request.user, "username", "") or ""
    job, created = enqueue_project_assign_reviews(
        project, requested_by=requested_by
    )
    return _project_enqueued_response(
        request, project, job, created, "Peer review assignment"
    )


def project_score_enqueue_response(request, project):
    error = project_score_precheck(project)
    if error is not None:
        return _project_blocked_response(project, error)
    requested_by = getattr(request.user, "username", "") or ""
    job, created = enqueue_project_scoring(project, requested_by=requested_by)
    return _project_enqueued_response(
        request, project, job, created, "Scoring"
    )


def project_score_status_response(project):
    job = latest_project_job(project)
    if job is None:
        return JsonResponse({"error": "No scoring job for this project"}, status=404)
    project.refresh_from_db()
    data = project_action_base(project, ProjectActionStatus.OK, "")
    data["status"] = job.status.upper()
    data["message"] = job.result_message or job.last_error
    data.update(
        {
            "submissions_count": project.projectsubmission_set.count(),
            "scored_submissions_count": 0,
            "passed_submissions_count": 0,
        }
    )
    if job.status == "succeeded":
        data["scored_submissions_count"] = data["submissions_count"]
        data["passed_submissions_count"] = (
            project.projectsubmission_set.filter(passed=True).count()
        )
    data.update(job_to_dict(job))
    data["job_id"] = job.id
    data["job_status"] = job.status
    return JsonResponse(data)


def project_assign_reviews_status_response(project):
    job = latest_project_job(project)
    if job is None:
        return JsonResponse({"error": "No assign-reviews job for this project"}, status=404)
    project.refresh_from_db()
    data = project_action_base(project, ProjectActionStatus.OK, "")
    data["status"] = job.status.upper()
    data["message"] = job.result_message or job.last_error
    data["peer_reviews_count"] = PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).count()
    data.update(job_to_dict(job))
    data["job_id"] = job.id
    data["job_status"] = job.status
    return JsonResponse(data)
