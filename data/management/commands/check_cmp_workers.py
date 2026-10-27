import json
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from data.models import CmpJobState, DatamailerOutboxEvent
from courses.models import ApplicationNotification
from courses.models.scoring_job import ScoringJob

LIMITS = {'outbox': 300, 'health': 900, 'reminders': 26*3600, 'digest': 26*3600, 'scoring': 600}


def worker_alarms(now=None):
    now = now or timezone.now()
    states = {s.job: s for s in CmpJobState.objects.all()}
    alarms = []
    for job, limit in LIMITS.items():
        state = states.get(job)
        if state is None or state.last_success_at is None or (now-state.last_success_at).total_seconds() > limit:
            alarms.append(f'{job}:success_stale')
        if state and state.last_failed_at and (state.last_success_at is None or state.last_failed_at > state.last_success_at):
            alarms.append(f'{job}:failed')
    overdue = DatamailerOutboxEvent.objects.filter(
        status__in=['pending','retrying'],
        next_attempt_at__lt=now-timezone.timedelta(seconds=300),
    ).exists()
    abandoned = DatamailerOutboxEvent.objects.filter(
        status='processing', last_attempt_at__lt=now-timezone.timedelta(seconds=540),
    ).exists()
    if overdue or abandoned:
        alarms.append('outbox:backlog_age')
    if ApplicationNotification.objects.filter(status='failed').exists():
        alarms.append('application_notifications:failed')
    if ApplicationNotification.objects.filter(
        status__in=['pending', 'processing'],
        created_at__lt=now-timezone.timedelta(seconds=600),
    ).exists():
        alarms.append('application_notifications:backlog_age')
    if ScoringJob.objects.filter(
        status__in=['queued', 'processing'],
        created_at__lt=now-timezone.timedelta(seconds=600),
    ).exists():
        alarms.append('scoring:backlog_age')
    if ScoringJob.objects.filter(
        status='processing',
        started_at__lt=now-timezone.timedelta(seconds=1800),
    ).exists():
        alarms.append('scoring:stuck')
    return alarms


class Command(BaseCommand):
    help = 'Independent worker success/age alarm; exits nonzero on stale work.'

    def handle(self, *args, **options):
        alarms = worker_alarms()
        self.stdout.write(json.dumps({'status':'warning' if alarms else 'ok', 'alarms':alarms}))
        if alarms:
            raise CommandError('CMP worker alarm')
