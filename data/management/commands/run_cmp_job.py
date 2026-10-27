"""Stable scheduled entry point, fenced across rolling web replicas."""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from course_management.worker_lock import worker_lock
from data.models import CmpJobState

JOBS = {
    'outbox': 'process_datamailer_outbox',
    'health': 'monitoring_datamailer_health',
    'reminders': 'send_deadline_reminders',
    'scoring': 'process_scoring_queue',
}


class Command(BaseCommand):
    help = 'Run one singleton CMP job and persist independent success evidence.'

    def add_arguments(self, parser):
        parser.add_argument('job', choices=JOBS)

    def handle(self, *args, **options):
        job = options['job']
        with worker_lock(f'cmp-job:{job}') as acquired:
            if not acquired:
                self.stdout.write('Already running; skipped')
                return
            state, _ = CmpJobState.objects.get_or_create(job=job)
            state.last_started_at = timezone.now()
            state.save(update_fields=['last_started_at'])
            try:
                # Explicit business timezone: 09:00 UTC, no DST ambiguity.
                # Reminders select only the current window; never replay missed days.
                with timezone.override('UTC'):
                    call_command(JOBS[job], stdout=self.stdout, stderr=self.stderr)
            except Exception:
                state.last_failed_at = timezone.now()
                state.save(update_fields=['last_failed_at'])
                raise
            state.last_success_at = timezone.now()
            state.save(update_fields=['last_success_at'])
