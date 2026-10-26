"""CMP-owned HTML/text drafts using the existing per-site email layout.

The raw HTML/text body format matches the existing registration-confirmation
template. No client branding/layout configuration is introduced here.
"""


def template(name, subject, html, text, fields):
    return {
        "name": name,
        "description": "CMP application lifecycle notification.",
        "subject": subject,
        "html_body": html,
        "text_body": text,
        "markdown_body": "",
        "category": "transactional",
        "required_context": [{"name": field} for field in fields],
        "example_context": {
            "name": "Test Applicant",
            "applicant_email": "alexey.s.grigoriev@gmail.com",
            "course_title": "Example Course",
            "campaign_title": "Example Course",
            "course_url": "https://courses.datatalks.club/example/",
            "review_url": "https://courses.datatalks.club/cadmin/campaigns/example/registrations/?status=pending",
            "digest_date": "2026-10-26",
            "total_count": 2,
            "confirmed_count": 1,
            "unconfirmed_count": 1,
            "course_count": 1,
            "summary": "Example Course — 2 new (1 confirmed, 1 unconfirmed)\n"
            "Review pending: https://courses.datatalks.club/cadmin/campaigns/example/registrations/?status=pending\n"
            "- Test Applicant <alexey.s.grigoriev@gmail.com> — confirmed",
            "summary_html": "Example Course — 2 new (1 confirmed, 1 unconfirmed)\n"
            "Review pending: https://courses.datatalks.club/cadmin/campaigns/example/registrations/?status=pending\n"
            "- Test Applicant &lt;alexey.s.grigoriev@gmail.com&gt; — confirmed",
        },
        "is_active": True,
    }


APPLICATION_TEMPLATES = {
    "application-pending-operator": template(
        "New course application",
        "New application: {{ campaign_title }}",
        "<p>A new application for <strong>{{ campaign_title }}</strong> is waiting for review.</p>"
        "<p>{{ name }} ({{ applicant_email }})</p>"
        '<p><a href="{{ review_url }}">Review pending applications in CMP</a></p>',
        "A new application for {{ campaign_title }} is waiting for review.\n\n"
        "{{ name }} ({{ applicant_email }})\n\nReview pending applications: {{ review_url }}",
        ["campaign_title", "name", "applicant_email", "review_url"],
    ),
    "registration-digest-operator": template(
        "Daily registration digest",
        "Daily registration digest: {{ total_count }} new ({{ digest_date }})",
        "<p>{{ total_count }} new registration(s) in the last 24 hours "
        "({{ confirmed_count }} confirmed, {{ unconfirmed_count }} unconfirmed) "
        "across {{ course_count }} course(s), as of {{ digest_date }}.</p>"
        "<pre>{{ summary_html }}</pre>",
        "{{ total_count }} new registration(s) in the last 24 hours "
        "({{ confirmed_count }} confirmed, {{ unconfirmed_count }} unconfirmed) "
        "across {{ course_count }} course(s), as of {{ digest_date }}.\n\n{{ summary }}",
        ["digest_date", "total_count", "confirmed_count", "unconfirmed_count", "course_count", "summary", "summary_html"],
    ),
    "application-approved": template(
        "Course application accepted",
        "You're accepted: {{ course_title }}",
        "<p>Hi {{ name }},</p>"
        "<p>Your application for <strong>{{ course_title }}</strong> has been accepted. Welcome!</p>"
        '<p><a href="{{ course_url }}">Open the course workspace</a> and sign in '
        "with the same email address you used for your application to access the course, homework and projects.</p>"
        "<p>We look forward to learning with you.<br>DataTalks.Club</p>",
        "Hi {{ name }},\n\nYour application for {{ course_title }} has been accepted. Welcome!\n\n"
        "Open the course workspace: {{ course_url }}\n"
        "Sign in with the same email address you used for your application to access the course, homework and projects.\n\n"
        "We look forward to learning with you.\nDataTalks.Club",
        ["name", "course_title", "course_url"],
    ),
    "application-rejected": template(
        "Course application update",
        "Your application: {{ course_title }}",
        "<p>Hi {{ name }},</p>"
        "<p>Thank you for your interest in <strong>{{ course_title }}</strong> and for taking the time to apply.</p>"
        "<p>We're sorry that we are unable to offer you a place in this cohort. "
        "We appreciate your interest and hope you will join us for a future opportunity.</p>"
        "<p>Best wishes,<br>DataTalks.Club</p>",
        "Hi {{ name }},\n\nThank you for your interest in {{ course_title }} and for taking the time to apply.\n\n"
        "We're sorry that we are unable to offer you a place in this cohort. "
        "We appreciate your interest and hope you will join us for a future opportunity.\n\n"
        "Best wishes,\nDataTalks.Club",
        ["name", "course_title"],
    ),
}
