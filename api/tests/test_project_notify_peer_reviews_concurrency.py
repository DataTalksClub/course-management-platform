"""Race two notify-peer-reviews POSTs on independent PostgreSQL connections."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import connection, connections
from django.test import Client
from django.utils import timezone

from accounts.models import CustomUser, Token
from course_management.datamailer.sync import peer_review_send_once
from courses.models import Course, Project
from courses.models.project import ProjectState
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)

from api.tests.test_project_notify_peer_reviews import (
    IDEMPOTENCY_KEY,
    SEND_PATH,
    _record_succeeded_send,
)

URL = (
    "/api/courses/test-course/projects/by-slug/proj1/"
    "notify-peer-reviews/"
)


def _setup_project():
    user = CustomUser.objects.create(
        username="notify-race", email="notify-race@example.com",
        is_staff=True,
    )
    token = Token.objects.create(user=user)
    course = Course.objects.create(slug="test-course", title="Test")
    Project.objects.create(
        course=course, title="Project 1", slug="proj1",
        submission_due_date=timezone.now(),
        peer_review_due_date=timezone.now(),
        state=ProjectState.PEER_REVIEWING.value,
    )
    return token.key


def _race_two_posts(token_key):
    barrier = Barrier(2)
    claim = peer_review_send_once._claim

    def simultaneous_claim(project):
        # Both requests passed every precheck before either claims.
        barrier.wait(timeout=15)
        return claim(project)

    def post():
        try:
            client = Client(
                HTTP_AUTHORIZATION=f"Token {token_key}",
                raise_request_exception=False,
            )
            return client.post(URL).status_code
        finally:
            connections.close_all()

    with (
        patch.object(peer_review_send_once, "_claim", simultaneous_claim),
        patch(SEND_PATH, side_effect=_record_succeeded_send) as send,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = [pool.submit(post) for _ in range(2)]
        statuses = sorted(f.result(timeout=30) for f in futures)
    return statuses, send.call_count


requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires PostgreSQL concurrent transaction semantics",
)


@pytest.mark.django_db(transaction=True)
@requires_postgres
def test_simultaneous_first_posts_send_exactly_once():
    token_key = _setup_project()

    statuses, send_count = _race_two_posts(token_key)

    assert statuses == [200, 409]
    assert send_count == 1
    audit = DatamailerSendAudit.objects.get(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        idempotency_key=IDEMPOTENCY_KEY,
    )
    assert audit.status == DatamailerSendAuditStatus.SUCCEEDED


@pytest.mark.django_db(transaction=True)
@requires_postgres
def test_simultaneous_retries_after_failure_send_exactly_once():
    token_key = _setup_project()
    DatamailerSendAudit.objects.create(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        idempotency_key=IDEMPOTENCY_KEY,
        status=DatamailerSendAuditStatus.FAILED,
        error="Relay unavailable",
    )

    statuses, send_count = _race_two_posts(token_key)

    assert statuses == [200, 409]
    assert send_count == 1
