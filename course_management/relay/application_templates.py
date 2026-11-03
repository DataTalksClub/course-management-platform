"""CMP-owned HTML/text drafts using the existing per-site email layout.

The raw HTML/text body format matches the existing registration-confirmation
template. No client branding/layout configuration is introduced here.
"""


FONT_STACK = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;"


def email_shell(headline, inner_html):
    """Readable email shell: 600px card, 16px/1.6 type, no bold anywhere.

    Hierarchy comes from size, color and spacing — never font weight.
    Table layout with inline styles for email-client compatibility.
    """
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background-color:#f6f8fa;margin:0;padding:0;">'
        '<tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;max-width:600px;background-color:#ffffff;border:1px solid #d0d7de;border-radius:12px;">'
        '<tr><td style="background-color:#0a3069;border-radius:11px 11px 0 0;padding:26px 32px;color:#ffffff;'
        "font-size:22px;line-height:1.4;" + FONT_STACK + '">'
        + headline
        + "</td></tr>"
        '<tr><td style="padding:28px 32px;color:#1f2328;font-size:16px;line-height:1.6;'
        + FONT_STACK + '">'
        + inner_html
        + "</td></tr>"
        '<tr><td style="padding:0 32px 24px;color:#57606a;font-size:13px;line-height:1.5;'
        + FONT_STACK + '">'
        "You are receiving this because you applied for this course. "
        "Manage course emails in your "
        '<a href="{{ profile_url }}" style="color:#0969da;">profile</a>.'
        "</td></tr>"
        "</table></td></tr></table>"
    )


def email_button(url_var, label):
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        '<tr><td align="center" style="padding:12px 0 6px;">'
        '<a href="{{ ' + url_var + ' }}" '
        'style="display:inline-block;background-color:#0969da;color:#ffffff;text-decoration:none;'
        'padding:13px 30px;border-radius:8px;font-size:16px;">'
        + label
        + "</a></td></tr></table>"
    )


def quote_block(text):
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        '<tr><td style="border-left:3px solid #0969da;background-color:#f6f8fa;'
        'padding:12px 16px;border-radius:0 8px 8px 0;color:#1f2328;font-size:15px;line-height:1.6;'
        + FONT_STACK + '"><i>'
        + text
        + "</i></td></tr></table>"
    )


def section_title(text):
    return (
        '<p style="font-size:18px;color:#0a3069;margin:24px 0 4px;">'
        + text
        + "</p>"
    )
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
        "example_context": {key: value for key, value in {
            "name": "Test Applicant",
            "applicant_email": "alexey.s.grigoriev@gmail.com",
            "course_title": "Example Course",
            "campaign_title": "Example Course",
            "course_url": "https://courses.datatalks.club/example/",
            "review_url": "https://courses.datatalks.club/cadmin/campaigns/example/registrations/?status=pending",
            "confirmation_url": "https://courses.datatalks.club/register/confirm/example/",
            "custom_message": "Example update: join the live workshop today at 18:00!",
            "invite_url": "https://courses.datatalks.club/register/example/?ref=7",
            "deadline": "2026-11-02 09:00:00 CET (Europe/Berlin)",
            "digest_date": "2026-10-26",
            "total_count": 2,
            "confirmed_count": 1,
            "unconfirmed_count": 1,
            "course_count": 1,
            "summary": "Example Course — 2 new (1 confirmed, 1 unconfirmed)\n"
            "Review pending: https://courses.datatalks.club/cadmin/campaigns/example/registrations/?status=pending",
            "summary_html": "<p>Example Course — 2 new (1 confirmed, 1 unconfirmed)</p>"
            '<p><a href="https://courses.datatalks.club/cadmin/campaigns/example/registrations/?status=pending">'
            "Review pending (1)</a></p>",
        }.items() if key in fields},
        "is_active": True,
    }


APPLICATION_TEMPLATES = {
    "application-pending-operator": template(
        "New course application",
        "New application: {{ campaign_title }}",
        "<p>A new application for {{ campaign_title }} is waiting for review.</p>"
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
        "<div>{{ summary_html|safe }}</div>",
        "{{ total_count }} new registration(s) in the last 24 hours "
        "({{ confirmed_count }} confirmed, {{ unconfirmed_count }} unconfirmed) "
        "across {{ course_count }} course(s), as of {{ digest_date }}.\n\n{{ summary }}",
        ["digest_date", "total_count", "confirmed_count", "unconfirmed_count", "course_count", "summary", "summary_html"],
    ),
    "registration-confirmation-reminder-1": template(
        "Registration confirmation reminder",
        "Please confirm your registration for {{ course_title }}",
        "<p>You registered for {{ course_title }} but haven't confirmed your email yet. "
        '<a href="{{ confirmation_url }}">Confirm here</a></p>',
        "You registered for {{ course_title }} but haven't confirmed your email yet. Confirm here: {{ confirmation_url }}",
        ["course_title", "confirmation_url"],
    ),
    "registration-confirmation-reminder-2": template(
        "Final registration confirmation reminder",
        "Last reminder: confirm your registration for {{ course_title }}",
        "<p>This is the last reminder. If you don't confirm by {{ deadline }}, "
        'your registration will be deleted. <a href="{{ confirmation_url }}">Confirm here</a></p>',
        "This is the last reminder. If you don't confirm by {{ deadline }}, your registration will be deleted. Confirm here: {{ confirmation_url }}",
        ["course_title", "confirmation_url", "deadline"],
    ),
    "application-approved": template(
        "Course application accepted",
        "You're accepted: {{ course_title }}",
        email_shell(
            "You&rsquo;re in, {{ name }}!",
            "<p>Your application for {{ course_title }} has been accepted. Welcome!</p>"
            "{% if custom_message_html %}{{ custom_message_html|safe }}{% endif %}"
            + email_button("course_url", "Open the course workspace")
            + "<p>Sign in with the same email address you used for your application "
            "to access the course, homework and projects.</p>"
            + section_title("Invite friends, earn points")
            + "<p>Know someone who would love this course? Share your personal link with them &mdash; "
            "you will earn 1 leaderboard point for each invitee who gets accepted.</p>"
            '<p style="background-color:#f6f8fa;border:1px solid #d0d7de;border-radius:8px;'
            'padding:12px 16px;word-break:break-all;">'
            '<a href="{{ invite_url }}" style="color:#0969da;">{{ invite_url }}</a></p>'
            + section_title("Copy and send")
            + "<p>Make it your own voice &mdash; personal invites work best:</p>"
            + quote_block(
                "&ldquo;I got accepted to {{ course_title }}. Join me &mdash; apply here: "
                "{{ invite_url }}&rdquo;"
            )
            + section_title("Posting publicly")
            + "<p>Here is an example post:</p>"
            + quote_block(
                "&ldquo;Excited to share: I got accepted to {{ course_title }} by DataTalks.Club! "
                "I will be learning to build and ship production-ready GenAI systems &mdash; containers, GPUs, "
                "real workloads. Join me: {{ invite_url }}&rdquo;"
            )
            + "<p>We look forward to learning with you.<br>DataTalks.Club</p>",
        ),
        "Hi {{ name }},\n\nYour application for {{ course_title }} has been accepted. Welcome!\n\n"
        "{% if custom_message %}{{ custom_message }}\n\n{% endif %}"
        "Open the course workspace: {{ course_url }}\n"
        "Sign in with the same email address you used for your application to access the course, homework and projects.\n\n"
        "Know someone who would love this course? Invite them with your personal link: {{ invite_url }} — "
        "you will earn 1 leaderboard point for each invitee who gets accepted.\n\n"
        "Your personal invite link: {{ invite_url }}\n\n"
        "Copy-paste starter (make it your own voice — personal invites work best):\n"
        '"I got accepted to {{ course_title }}. Join me — apply here: {{ invite_url }}"\n\n'
        "Posting publicly? Here is an example post (make it your own):\n"
        '"Excited to share: I got accepted to {{ course_title }} by DataTalks.Club! '
        "I will be learning to build and ship production-ready GenAI systems — containers, GPUs, "
        'real workloads. Join me: {{ invite_url }}"\n\n'
        "We look forward to learning with you.\nDataTalks.Club",
        # custom_message intentionally not required: empty (plain approval
        # emails) must validate. The {% if %} block skips it when empty.
        ["name", "course_title", "course_url", "invite_url"],
    ),
    "application-rejected": template(
        "Course application update",
        "Your application: {{ course_title }}",
        email_shell(
            "Update on your application, {{ name }}",
            "<p>Thank you for your interest in {{ course_title }} and for taking the time to apply.</p>"
            "{% if custom_message_html %}{{ custom_message_html|safe }}{% endif %}"
            "<p>We're sorry that we are unable to offer you a place in this cohort. "
            "We appreciate your interest and hope you will join us for a future opportunity.</p>"
            + "<p>Best wishes,<br>DataTalks.Club</p>",
        ),
        "Hi {{ name }},\n\nThank you for your interest in {{ course_title }} and for taking the time to apply.\n\n"
        "{% if custom_message %}{{ custom_message }}\n\n{% endif %}"
        "We're sorry that we are unable to offer you a place in this cohort. "
        "We appreciate your interest and hope you will join us for a future opportunity.\n\n"
        "Best wishes,\nDataTalks.Club",
        # custom_message intentionally not required: see approved above.
        ["name", "course_title"],
    ),
}
