"""Transactional template registry: Relay owns bodies, code owns placeholders.

Bodies (subject/HTML/text) live in Relay and are edited there — this file
never contains email copy. Each entry declares the context fields CMP must
send (``required_context``); ``example_context`` holds placeholder values
used by the ``check_transactional_templates`` dry-run.

If code stops sending a field, or a template needs a new one, update both
sides together.
"""

EXAMPLE_CONTEXT = {
    "name": "Test Applicant",
    "applicant_email": "alexey.s.grigoriev@gmail.com",
    "course_title": "Example Course",
    "campaign_title": "Example Course",
    "course_url": "https://courses.datatalks.club/example/",
    "review_url": (
        "https://courses.datatalks.club/cadmin/campaigns/example/"
        "registrations/?status=pending"
    ),
    "confirmation_url": (
        "https://courses.datatalks.club/register/confirm/example/"
    ),
    "custom_message": (
        "Example update: join the live workshop today at 18:00!"
    ),
    "invite_url": "https://courses.datatalks.club/register/example/?ref=7",
    "deadline": "2026-11-02 09:00:00 CET (Europe/Berlin)",
    "digest_date": "2026-10-26",
    "total_count": 2,
    "confirmed_count": 1,
    "unconfirmed_count": 1,
    "course_count": 1,
    "summary": (
        "Example Course - 2 new (1 confirmed, 1 unconfirmed)\n"
        "Review pending: https://courses.datatalks.club/cadmin/campaigns/"
        "example/registrations/?status=pending"
    ),
    "summary_html": (
        "<p>Example Course - 2 new (1 confirmed, 1 unconfirmed)</p>"
        '<p><a href="https://courses.datatalks.club/cadmin/campaigns/'
        'example/registrations/?status=pending">'
        "Review pending (1)</a></p>"
    ),
}


def _entry(description, *fields):
    return {
        "description": description,
        "required_context": list(fields),
        "example_context": {
            key: EXAMPLE_CONTEXT[key] for key in fields
        },
    }


TRANSACTIONAL_TEMPLATES = {
    "application-pending-operator": _entry(
        "New course application",
        "campaign_title",
        "name",
        "applicant_email",
        "review_url",
    ),
    "registration-digest-operator": _entry(
        "Daily registration digest",
        "digest_date",
        "total_count",
        "confirmed_count",
        "unconfirmed_count",
        "course_count",
        "summary",
        "summary_html",
    ),
    "registration-confirmation-reminder-1": _entry(
        "Registration confirmation reminder",
        "course_title",
        "confirmation_url",
    ),
    "registration-confirmation-reminder-2": _entry(
        "Final registration confirmation reminder",
        "course_title",
        "confirmation_url",
        "deadline",
    ),
    "application-approved": _entry(
        "Course application accepted",
        "name",
        "course_title",
        "course_url",
        "invite_url",
    ),
    "application-rejected": _entry(
        "Course application update",
        "name",
        "course_title",
    ),
}
