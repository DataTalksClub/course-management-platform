"""Claim and execute pending scoring jobs (worker side).

Invoked via `python manage.py run_cmp_job scoring` (Coolify scheduled task
+ always-on worker service). Each invocation drains the queue (max 25 jobs).
Crash-safe: jobs stuck in PROCESSING for >10 minutes are reclaimed; scoring
itself runs in an atomic transaction, and terminal states are re-checked
before scoring so a retry never double-scores.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q as models_Q
from django.utils import timezone

from course_management.worker_lock import worker_lock
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState
from courses.models.scoring_job import ScoringJob, ScoringJobKind, ScoringJobStatus

STALE_PROCESSING_SECONDS = 600
MAX_JOBS_PER_RUN = 25


def _locked_first(condition):
    qs = ScoringJob.objects.filter(condition).order_by("created_at")
    try:
        return qs.select_for_update(skip_locked=True).first()
    except Exception:
        return qs.first()


def _claimable(now):
    stale_cutoff = now - timedelta(seconds=STALE_PROCESSING_SECONDS)
    with transaction.atomic():
        job = _locked_first(models_Q(status=ScoringJobStatus.QUEUED))
        expected = {"status": ScoringJobStatus.QUEUED}
        if job is None:
            job = _locked_first(
                models_Q(
                    status=ScoringJobStatus.PROCESSING,
                    started_at__lt=stale_cutoff,
                )
            )
            expected = {
                "status": ScoringJobStatus.PROCESSING,
                "started_at__lt": stale_cutoff,
            }
        if job is None:
            return None
        claimed = (
            ScoringJob.objects.filter(id=job.id, **expected).update(
                status=ScoringJobStatus.PROCESSING,
                started_at=now,
                attempt_count=job.attempt_count + 1,
            )
        )
        if not claimed:
            return None
        job.refresh_from_db()
        return job


def _target_lock_key(job):
    if job.homework_id is not None:
        return f"scoring:homework:{job.homework_id}"
    return f"scoring:project:{job.project_id}"


def _already_scored_skip(job):
    """Idempotent skip when a retry finds the work already done."""
    if job.kind == ScoringJobKind.HOMEWORK_SCORE and not job.force:
        job.homework.refresh_from_db()
        if job.homework.state == HomeworkState.SCORED.value:
            return "already scored (idempotent skip)"
    if job.kind == ScoringJobKind.PROJECT_SCORE:
        job.project.refresh_from_db()
        if job.project.state == ProjectState.COMPLETED.value:
            return "already scored (idempotent skip)"
    if job.kind == ScoringJobKind.PROJECT_ASSIGN_REVIEWS:
        from courses.models.project import PeerReview

        job.project.refresh_from_db()
        if job.project.state != ProjectState.COLLECTING_SUBMISSIONS.value:
            if PeerReview.objects.filter(
                submission_under_evaluation__project=job.project
            ).exists():
                return "peer reviews already assigned (idempotent skip)"
    return None


def _execute(job):
    if job.kind == ScoringJobKind.HOMEWORK_SCORE:
        from courses.scoring import score_homework_submissions

        job.homework.refresh_from_db()
        return score_homework_submissions(job.homework_id, force=job.force)
    if job.kind == ScoringJobKind.PROJECT_SCORE:
        from courses.project_scoring import score_project

        job.project.refresh_from_db()
        return score_project(job.project)
    if job.kind == ScoringJobKind.PROJECT_ASSIGN_REVIEWS:
        from courses.project_assignment import assign_peer_reviews_for_project

        job.project.refresh_from_db()
        return assign_peer_reviews_for_project(job.project)
    raise ValueError(f"Unknown scoring job kind: {job.kind}")


def _is_ok(status):
    return str(getattr(status, "name", status)) == "OK"


def process_one_job():
    now = timezone.now()
    job = _claimable(now)
    if job is None:
        return None
    with worker_lock(_target_lock_key(job)) as acquired:
        if not acquired:
            job.status = ScoringJobStatus.QUEUED
            job.save(update_fields=["status"])
            return job
        skipped = _already_scored_skip(job)
        if skipped is not None:
            job.status = ScoringJobStatus.SUCCEEDED
            job.result_message = skipped
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "result_message", "finished_at"])
            return job
        try:
            status, message = _execute(job)
        except Exception as exc:  # crash: record it; stuck jobs are reclaimed, never retried blindly
            job.status = ScoringJobStatus.FAILED
            job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "last_error", "finished_at"])
            return job
        if _is_ok(status):
            job.status = ScoringJobStatus.SUCCEEDED
            job.result_message = message
            job.last_error = ""
        else:
            # Validation outcome (e.g. window moved while queued): terminal, no retry.
            job.status = ScoringJobStatus.FAILED
            job.result_message = ""
            job.last_error = message
        job.finished_at = timezone.now()
        job.save(
            update_fields=["status", "result_message", "last_error", "finished_at"]
        )
        return job


class Command(BaseCommand):
    help = "Process pending homework/project scoring jobs."

    def handle(self, *args, **options):
        processed = 0
        for _ in range(MAX_JOBS_PER_RUN):
            job = process_one_job()
            if job is None:
                break
            if job.status == ScoringJobStatus.QUEUED:
                # Target locked by a concurrent worker; stop to avoid hot spin.
                break
            processed += 1
        self.stdout.write(f"Processed {processed} scoring job(s)")
