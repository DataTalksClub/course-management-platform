"""Execute every row-locking path with real SQL and transaction boundaries.

CI uses PostgreSQL: SQLite neither enforces FOR UPDATE transactions nor
rejects locks on the nullable side of an outer join. Do not mock querysets.
Only external delivery is mocked here.
"""

from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.sites.models import Site
from django.db import connection, transaction
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import CustomUser
from courses.models import (
    ApplicationNotification,
    Course,
    CourseRegistration,
    Enrollment,
    Project,
    ProjectSubmission,
    RegistrationCampaign,
)
from courses.registration_confirmation import (
    confirm_registration_by_token,
    issue_confirmation_token,
    managed_registration,
    management_token,
)


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def registration():
    Site.objects.update_or_create(
        id=settings.SITE_ID,
        defaults={"domain": "testserver", "name": "Test"},
    )
    course = Course.objects.create(slug="locking", title="Locking")
    campaign = RegistrationCampaign.objects.create(
        slug="locking",
        title="Locking",
        current_course=course,
    )
    registration = CourseRegistration.objects.create(
        campaign=campaign,
        email="locking@example.com",
    )
    # Keep course NULL in the database despite save() filling it from campaign.
    # This exercises the actual LEFT OUTER JOIN, not just a non-null fixture.
    CourseRegistration.objects.filter(pk=registration.pk).update(
        course=None
    )
    registration.refresh_from_db()
    return registration


@contextmanager
def executed_lock(query_fragment):
    with CaptureQueriesContext(connection) as queries:
        yield
    if connection.vendor == "postgresql":
        assert any(
            "FOR UPDATE" in query["sql"]
            and query_fragment in query["sql"]
            for query in queries
        ), f"Expected a row lock containing {query_fragment!r}"


def test_confirmation_locks_registration_with_nullable_course(
    registration,
):
    issue_confirmation_token(registration)
    assert not connection.in_atomic_block
    with executed_lock(
        'WHERE "courses_courseregistration"."email_confirmation_token"'
    ):
        confirmed, outcome = confirm_registration_by_token(
            CourseRegistration,
            registration.email_confirmation_token,
        )
    assert outcome == "confirmed"
    assert confirmed.email_confirmed


def test_management_locks_registration_with_nullable_course(
    registration,
):
    with (
        transaction.atomic(),
        executed_lock('LEFT OUTER JOIN "courses_course"'),
    ):
        managed = managed_registration(
            CourseRegistration,
            management_token(registration),
        )
    assert managed.pk == registration.pk
    assert managed.course_id is None


@pytest.mark.parametrize("path", ["resend-confirmation", "fix-email"])
def test_management_views_supply_transaction(
    registration, client, path
):
    assert not connection.in_atomic_block
    payload = {
        "token": management_token(registration),
        "email": "updated@example.com",
    }
    with patch(
        "courses.views.registration_confirmation._queue_confirmation_send"
    ) as send:
        with patch(
            "courses.views.registration_confirmation.email_domain_has_mx",
            return_value=True,
        ):
            with executed_lock('LEFT OUTER JOIN "courses_course"'):
                response = client.post(f"/register/{path}/", payload)
    assert response.status_code == 200
    send.assert_called_once()
    registration.refresh_from_db()
    assert registration.email_confirmation_token
    if path == "fix-email":
        assert registration.email_normalized == "updated@example.com"


def test_public_resend_locks_registration_through_campaign_join(
    registration, client
):
    assert not connection.in_atomic_block
    with patch(
        "courses.views.registration_confirmation._queue_confirmation_send"
    ) as send:
        with executed_lock('INNER JOIN "courses_registrationcampaign"'):
            response = client.post(
                "/register/resend-confirmation/",
                {
                    "email": registration.email,
                    "campaign_slug": registration.campaign.slug,
                },
            )
    assert response.status_code == 200
    send.assert_called_once()
    registration.refresh_from_db()
    assert registration.email_confirmation_token


def test_registration_save_locks_persisted_status(registration):
    assert not connection.in_atomic_block
    registration.name = "Updated"
    with executed_lock('SELECT "courses_courseregistration"."status"'):
        registration.save(update_fields=["name"])
    registration.refresh_from_db()
    assert registration.name == "Updated"


def test_system_evaluation_locks_submission(registration):
    from api.views.project_system_evaluations import (
        ValidatedSystemEvaluation,
        _create_evaluation,
    )

    user = CustomUser.objects.create(
        username="locking", email="locking@example.com"
    )
    course = registration.campaign.current_course
    project = Project.objects.create(
        course=course,
        slug="locking",
        title="Locking",
        state="CL",
        submission_due_date=timezone.now(),
        peer_review_due_date=timezone.now(),
    )
    enrollment = Enrollment.objects.create(student=user, course=course)
    submission = ProjectSubmission.objects.create(
        student=user,
        project=project,
        enrollment=enrollment,
        github_link="https://github.com/example/project",
        commit_id="abc",
    )
    request = RequestFactory().post("/api/locking-test/")
    request.user = user
    assert not connection.in_atomic_block
    with executed_lock('FROM "courses_projectsubmission"'):
        response, error = _create_evaluation(
            request,
            submission,
            ValidatedSystemEvaluation("locking", "Good", []),
        )
    assert error is None
    assert response.status_code == 201
    assert submission.system_evaluations.count() == 1


def test_outbox_dispatch_locks_and_claims_event():
    from course_management.datamailer_outbox_dispatch import (
        dispatch_datamailer_outbox_event,
    )
    from data.models import DatamailerOutboxEvent

    event = DatamailerOutboxEvent.objects.create(
        event_id="locking",
        event_type="contact.upsert",
        idempotency_key="locking",
    )
    assert not connection.in_atomic_block
    with patch(
        "course_management.datamailer_outbox_dispatch.outbox_datamailer_config",
        return_value=SimpleNamespace(strict=True),
    ):
        with patch(
            "course_management.datamailer_outbox_dispatch.dispatch_claimed_outbox_event"
        ) as send:
            with executed_lock('FROM "data_datamaileroutboxevent"'):
                dispatch_datamailer_outbox_event(event)
    send.assert_called_once()
    event.refresh_from_db()
    assert event.status == "processing"
    assert event.attempt_count == 1


def test_application_notification_dispatch_locks_row(registration):
    from course_management.relay.application_notifications import (
        dispatch_notification,
    )

    notification = ApplicationNotification.objects.create(
        registration=registration,
        recipient="locking@example.com",
        template_key="application-approved",
    )
    now = timezone.now()
    assert not connection.in_atomic_block
    with patch(
        "course_management.relay.application_notifications.send_notification",
        return_value="123",
    ) as send:
        with executed_lock('FROM "courses_applicationnotification"'):
            dispatch_notification(
                notification.pk, now, now - timedelta(minutes=5)
            )
    send.assert_called_once()
    notification.refresh_from_db()
    assert notification.status == "sent"
    assert notification.attempt_count == 1
