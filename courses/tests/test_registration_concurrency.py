"""Exercise duplicate POSTs on independent PostgreSQL connections."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection, connections
from django.test import Client

from courses.models import Course, CourseRegistration, RegistrationCampaign
from courses.views.registration_form import CourseRegistrationForm
from courses.views.registration import _save_registration_if_valid


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires PostgreSQL concurrent transaction semantics",
)
def test_simultaneous_registration_posts_preserve_one_registration():
    course = Course.objects.create(slug="concurrent", title="Concurrent")
    campaign = RegistrationCampaign.objects.create(
        slug="concurrent", title="Concurrent", current_course=course,
    )
    barrier = Barrier(2)
    save = CourseRegistrationForm.save

    def simultaneous_save(form, *args, **kwargs):
        # Both requests have passed duplicate validation before either inserts.
        barrier.wait(timeout=15)
        return save(form, *args, **kwargs)

    def post(email):
        try:
            response = Client(raise_request_exception=False).post(
                "/register/concurrent/",
                {"email": email, "accepted_newsletter": "on"},
            )
            return response.status_code, response.content.decode()
        finally:
            connections.close_all()

    with (
        patch.object(CourseRegistrationForm, "save", simultaneous_save),
        patch("courses.views.registration_form.email_domain_has_mx", return_value=True),
        patch("courses.views.registration.sync_registration_to_relay") as sync,
        patch("courses.views.registration.send_registration_confirmation_email") as send,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = [pool.submit(post, email) for email in (
            "Concurrent@Example.com", "concurrent@example.com",
        )]
        results = [future.result(timeout=30) for future in futures]

    assert sorted(status for status, _ in results) == [200, 200]
    assert sum("You have already registered for this course." in body
               for _, body in results) == 1
    assert CourseRegistration.objects.filter(campaign=campaign).count() == 1
    registration = CourseRegistration.objects.get(campaign=campaign)
    assert registration.email_normalized == "concurrent@example.com"
    assert registration.email_confirmation_token
    assert registration.email_confirmation_resend_count == 1
    # The losing request must not issue another token or send another email.
    sync.assert_called_once()
    send.assert_called_once()


@pytest.mark.django_db
def test_registration_does_not_hide_unrelated_integrity_errors():
    campaign = RegistrationCampaign.objects.create(
        slug="unrelated", title="Unrelated",
    )
    form = CourseRegistrationForm(
        {"email": "unique@example.com", "accepted_newsletter": "on"},
        campaign=campaign,
    )
    with (
        patch("courses.views.registration_form.email_domain_has_mx", return_value=True),
        patch.object(form, "save", side_effect=IntegrityError("unrelated constraint")),
        pytest.raises(IntegrityError, match="unrelated constraint"),
    ):
        _save_registration_if_valid(form)
