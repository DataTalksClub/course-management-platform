from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from course_management.datamailer_outbox_runs import process_due_datamailer_outbox
from data.models import DatamailerOutboxEvent
from courses.tests.datamailer_outbox_base import RELAY_SETTINGS


@override_settings(**RELAY_SETTINGS)
class WorkerRecoveryTests(TestCase):
    @patch('course_management.datamailer_outbox_dispatch.send_event', return_value={})
    def test_abandoned_processing_is_recovered_after_restart(self, send):
        event = DatamailerOutboxEvent.objects.create(
            event_id='restart-test', event_type='recipient_list.member_upsert',
            idempotency_key='stable-key', status='processing',
            last_attempt_at=timezone.now()-timedelta(minutes=10),
        )
        process_due_datamailer_outbox()
        event.refresh_from_db()
        self.assertEqual(event.status, 'acked')
        self.assertEqual(send.call_count, 1)

    @patch('course_management.datamailer_outbox_dispatch.send_event', return_value={})
    def test_not_due_retry_is_not_dispatched_by_overlapping_snapshot(self, send):
        from course_management.datamailer_outbox_dispatch import dispatch_datamailer_outbox_event
        event = DatamailerOutboxEvent.objects.create(
            event_id='future-test', event_type='recipient_list.member_upsert',
            idempotency_key='future-key', status='retrying',
            next_attempt_at=timezone.now()+timedelta(minutes=5),
        )
        dispatch_datamailer_outbox_event(event)
        self.assertEqual(send.call_count, 0)

    @patch('course_management.datamailer_outbox_dispatch.send_event')
    def test_transient_failure_retries_after_recovery_with_same_payload(self, send):
        import requests
        send.side_effect = [requests.Timeout('temporary outage'), {}]
        event = DatamailerOutboxEvent.objects.create(
            event_id='retry-test', event_type='recipient_list.member_upsert',
            idempotency_key='retry-stable', payload={'idempotency_key':'retry-stable'},
        )
        process_due_datamailer_outbox()
        event.refresh_from_db()
        self.assertEqual(event.status, 'retrying')
        DatamailerOutboxEvent.objects.filter(pk=event.pk).update(next_attempt_at=timezone.now())
        process_due_datamailer_outbox()
        event.refresh_from_db()
        self.assertEqual(event.status, 'acked')
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0].args[1:], send.call_args_list[1].args[1:])

    @patch('course_management.datamailer_outbox_dispatch.send_event', return_value={})
    def test_overlapping_snapshot_and_completed_restart_do_not_send_twice(self, send):
        from course_management.datamailer_outbox_dispatch import dispatch_datamailer_outbox_event
        event = DatamailerOutboxEvent.objects.create(
            event_id='overlap-test', event_type='recipient_list.member_upsert',
            idempotency_key='overlap-stable',
        )
        stale_snapshot = DatamailerOutboxEvent.objects.get(pk=event.pk)
        dispatch_datamailer_outbox_event(event)
        dispatch_datamailer_outbox_event(stale_snapshot)
        process_due_datamailer_outbox()
        self.assertEqual(send.call_count, 1)

    def test_controlled_worker_stall_and_backlog_raise_alarms(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from data.models import CmpJobState
        from data.management.commands.check_cmp_workers import worker_alarms
        from io import StringIO
        now = timezone.now()
        for job in ['outbox','health','reminders']:
            CmpJobState.objects.create(job=job,last_success_at=now)
        self.assertEqual(worker_alarms(), [])
        CmpJobState.objects.filter(job='outbox').update(last_success_at=now-timedelta(minutes=6))
        DatamailerOutboxEvent.objects.create(
            event_id='alarm-test', event_type='recipient_list.member_upsert',
            idempotency_key='alarm-key', next_attempt_at=now-timedelta(minutes=6),
        )
        self.assertIn('outbox:success_stale',worker_alarms())
        self.assertIn('outbox:backlog_age',worker_alarms())
        with self.assertRaises(CommandError):
            call_command('check_cmp_workers',stdout=StringIO())

    @override_settings(RELAY_API_KEY='')
    def test_missing_configuration_preserves_retryable_work(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        event = DatamailerOutboxEvent.objects.create(
            event_id='config-test', event_type='recipient_list.member_upsert',
            idempotency_key='config-key',
        )
        with self.assertRaises(CommandError):
            call_command('process_datamailer_outbox')
        event.refresh_from_db()
        self.assertEqual(event.status, 'pending')

    def test_job_success_and_failure_are_persisted(self):
        from django.core.management import call_command
        from data.models import CmpJobState
        from io import StringIO
        with patch('data.management.commands.run_cmp_job.call_command') as run:
            call_command('run_cmp_job','health',stdout=StringIO())
            state = CmpJobState.objects.get(job='health')
            self.assertIsNotNone(state.last_success_at)
            run.side_effect = RuntimeError('controlled failure')
            with self.assertRaises(RuntimeError):
                call_command('run_cmp_job','health',stdout=StringIO())
            state.refresh_from_db()
            self.assertGreater(state.last_failed_at,state.last_success_at)

    def test_successful_reminder_is_not_resent_after_restart(self):
        from types import SimpleNamespace
        from courses.management.commands.send_deadline_reminders import send_reminder_event
        from data.models import DatamailerSendAudit
        from unittest.mock import Mock
        DatamailerSendAudit.objects.create(
            send_type='transient_recipient_list',status='succeeded',
            idempotency_key='deadline-stable',
        )
        client = Mock()
        response,error=send_reminder_event(client,SimpleNamespace(key='deadline-stable'))
        self.assertEqual(error,'')
        client.recipient_lists.sends.send_to_transient_list.assert_not_called()


from django.test import TransactionTestCase
from django.db import connection, close_old_connections
from unittest import skipUnless


@skipUnless(connection.vendor == 'postgresql', 'Requires independent PostgreSQL sessions')
@override_settings(**RELAY_SETTINGS)
class PostgresWorkerOverlapTests(TransactionTestCase):
    def test_live_expired_processing_cannot_be_reclaimed(self):
        import threading
        from course_management.datamailer_outbox_dispatch import dispatch_datamailer_outbox_event
        event=DatamailerOutboxEvent.objects.create(
            event_id='pg-overlap',event_type='recipient_list.member_upsert',idempotency_key='pg-key',
        )
        entered=threading.Event()
        release=threading.Event()
        errors=[]
        def send(*args):
            entered.set()
            if not release.wait(15):
                raise RuntimeError('test release timeout')
            return {}
        def first_runner():
            close_old_connections()
            try:
                dispatch_datamailer_outbox_event(DatamailerOutboxEvent.objects.get(pk=event.pk))
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()
        with patch('course_management.datamailer_outbox_dispatch.send_event',side_effect=send) as transport:
            thread=threading.Thread(target=first_runner)
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                DatamailerOutboxEvent.objects.filter(pk=event.pk).update(last_attempt_at=timezone.now()-timedelta(minutes=10))
                process_due_datamailer_outbox()
                self.assertEqual(transport.call_count,1)
            finally:
                release.set()
                thread.join(15)
            self.assertFalse(errors)
            event.refresh_from_db()
            self.assertEqual(event.status,'acked')
