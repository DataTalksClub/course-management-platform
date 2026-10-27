"""Enqueue + status helpers for background scoring.

Fast pre-checks run synchronously in the request (<2s, a few indexed
queries). Heavy scoring runs in the worker (process_scoring_queue via
run_cmp_job scoring). Duplicate POSTs while a job is active return the
existing job instead of double-scoring.
"""

import uuid

from courses.models.project import PeerReview
from courses.models.scoring_job import ScoringJob, ScoringJobKind, ScoringJobStatus


def _requested_by_label(requested_by):
    return (requested_by or "")[:255]


def _active_job_for(kind, homework=None, project=None, force=None):
    filters = {"kind": kind, "status__in": [ScoringJobStatus.QUEUED, ScoringJobStatus.PROCESSING]}
    if homework is not None:
        filters["homework"] = homework
    if project is not None:
        filters["project"] = project
    if force is not None:
        filters["force"] = force
    return ScoringJob.objects.filter(**filters).order_by("-created_at").first()


def _new_key(kind, target_id):
    return f"{kind}:{target_id}:{uuid.uuid4().hex[:12]}"


def homework_score_precheck(homework, force=False):
    """Fast synchronous validation; returns error message or None."""
    from courses.scoring import _homework_scoring_error

    return _homework_scoring_error(homework, homework.id, force)


def project_score_precheck(project):
    from courses.project_scoring import _validate_project_scoreable

    error = _validate_project_scoreable(project)
    if error is not None:
        return error
    has_reviews = (
        PeerReview.objects.filter(submission_under_evaluation__project=project).exists()
    )
    if not has_reviews:
        return "No peer reviews found for the project."
    return None


def project_assign_reviews_precheck(project):
    from courses.project_assignment import _assignment_precondition_failure
    from courses.models.project import ProjectSubmission

    submissions_count = ProjectSubmission.objects.filter(project=project).count()
    failure = _assignment_precondition_failure(
        project, submissions_count, project.number_of_peers_to_evaluate
    )
    if failure is None:
        return None
    _, message = failure
    return message


def enqueue_homework_scoring(homework, requested_by="", force=False):
    existing = _active_job_for(
        ScoringJobKind.HOMEWORK_SCORE, homework=homework, force=force
    )
    if existing is not None:
        return existing, False
    job = ScoringJob.objects.create(
        kind=ScoringJobKind.HOMEWORK_SCORE,
        homework=homework,
        force=force,
        idempotency_key=_new_key("homework-score", homework.id),
        requested_by=_requested_by_label(requested_by),
    )
    return job, True


def enqueue_project_scoring(project, requested_by=""):
    existing = _active_job_for(ScoringJobKind.PROJECT_SCORE, project=project)
    if existing is not None:
        return existing, False
    job = ScoringJob.objects.create(
        kind=ScoringJobKind.PROJECT_SCORE,
        project=project,
        idempotency_key=_new_key("project-score", project.id),
        requested_by=_requested_by_label(requested_by),
    )
    return job, True


def enqueue_project_assign_reviews(project, requested_by=""):
    existing = _active_job_for(ScoringJobKind.PROJECT_ASSIGN_REVIEWS, project=project)
    if existing is not None:
        return existing, False
    job = ScoringJob.objects.create(
        kind=ScoringJobKind.PROJECT_ASSIGN_REVIEWS,
        project=project,
        idempotency_key=_new_key("project-assign-reviews", project.id),
        requested_by=_requested_by_label(requested_by),
    )
    return job, True


def latest_homework_job(homework, kinds=None):
    qs = ScoringJob.objects.filter(homework=homework)
    if kinds:
        qs = qs.filter(kind__in=kinds)
    return qs.order_by("-created_at").first()


def latest_project_job(project, kinds=None):
    qs = ScoringJob.objects.filter(project=project)
    if kinds:
        qs = qs.filter(kind__in=kinds)
    return qs.order_by("-created_at").first()


def job_poll_path_homework(course_slug, homework_id=None, homework_slug=None):
    if homework_slug is not None:
        return (
            f"/api/courses/{course_slug}/homeworks/by-slug/{homework_slug}/score/"
        )
    return f"/api/courses/{course_slug}/homeworks/{homework_id}/score/"


def job_poll_path_project(course_slug, project_id=None, project_slug=None):
    if project_slug is not None:
        return f"/api/courses/{course_slug}/projects/by-slug/{project_slug}/score/"
    return f"/api/courses/{course_slug}/projects/{project_id}/score/"


def job_to_dict(job):
    return {
        "job_id": job.id,
        "job_kind": job.kind,
        "job_status": job.status,
        "idempotency_key": job.idempotency_key,
        "attempt_count": job.attempt_count,
        "result_message": job.result_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def scoring_banner(job):
    """Small template-friendly status record; None when no job exists."""
    if job is None:
        return None
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "is_active": job.status
        in (ScoringJobStatus.QUEUED, ScoringJobStatus.PROCESSING),
        "is_failed": job.status == ScoringJobStatus.FAILED,
        "is_succeeded": job.status == ScoringJobStatus.SUCCEEDED,
        "result_message": job.result_message,
        "last_error": job.last_error,
        "created_at": job.created_at,
    }


def attach_homework_scoring_status(homeworks):
    """Annotate homework list with the latest scoring job (one query)."""
    ids = [h.id for h in homeworks]
    latest = {}
    if ids:
        for job in (
            ScoringJob.objects.filter(
                homework_id__in=ids, kind=ScoringJobKind.HOMEWORK_SCORE
            ).order_by("-created_at")
        ):
            latest.setdefault(job.homework_id, job)
    for homework in homeworks:
        homework.scoring_job = scoring_banner(latest.get(homework.id))
        homework.scoring_active = bool(
            homework.scoring_job and homework.scoring_job["is_active"]
        )
    return homeworks


def attach_project_scoring_status(projects):
    ids = [p.id for p in projects]
    latest = {}
    if ids:
        for job in (
            ScoringJob.objects.filter(project_id__in=ids).order_by("-created_at")
        ):
            latest.setdefault(job.project_id, job)
    for project in projects:
        project.scoring_job = scoring_banner(latest.get(project.id))
        project.scoring_active = bool(
            project.scoring_job and project.scoring_job["is_active"]
        )
    return projects
