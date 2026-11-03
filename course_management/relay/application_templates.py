"""CMP-owned HTML/text drafts using the existing per-site email layout.

The raw HTML/text body format matches the existing registration-confirmation
template. No client branding/layout configuration is introduced here.
"""


"""CMP-owned HTML/text drafts in the DataTalks.Club newsletter style.

660px white card on light gray, Helvetica 16px/1.5, blue (#2056A2)
links and buttons, hairline dividers, clear sections. Hierarchy comes
from size, color and spacing - never font weight.
"""


FONT_STACK = "font-family:'Helvetica Neue',Helvetica,Arial,Verdana,sans-serif;"
LINK_BLUE = "#2056A2"


def email_shell(headline, inner_html):
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background-color:#f4f4f4;margin:0;padding:0;">'
        '<tr><td align="center" style="padding:24px 16px;">'
        '<table role="presentation" width="660" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;max-width:660px;background-color:#ffffff;">'
        '<tr><td style="padding:28px 32px 8px;color:#222222;'
        "font-size:26px;line-height:1.4;" + FONT_STACK + '">'
        + headline
        + "</td></tr>"
        '<tr><td style="padding:12px 32px 8px;color:#222222;font-size:16px;line-height:1.5;'
        + FONT_STACK + '">'
        + inner_html
        + "</td></tr>"
        '<tr><td style="padding:12px 32px 28px;color:#656565;font-size:14px;line-height:1.5;'
        + FONT_STACK + '">'
        "You are receiving this because you applied for this course. "
        "Manage course emails in your "
        '<a href="{{ profile_url }}" style="color:' + LINK_BLUE + ';">profile</a>.'
        "</td></tr>"
        "</table></td></tr></table>"
    )


def email_button(url_var, label):
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:0 auto;">'
        '<tr><td align="center" style="background-color:' + LINK_BLUE + ';border-radius:8px;">'
        '<a href="{{ ' + url_var + ' }}" '
        'style="display:inline-block;background-color:' + LINK_BLUE + ';border-radius:8px;'
        'color:#ffffff;text-decoration:none;padding:16px 28px;font-size:16px;' + FONT_STACK + '">'
        + label
        + "</a></td></tr></table>"
    )


def divider():
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        '<tr><td style="border-top:1px solid #E5E5E5;font-size:0;line-height:0;padding:0;margin:12px 0;">&nbsp;'
        "</td></tr></table>"
    )


def quote_block(text):
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        '<tr><td style="border-left:3px solid ' + LINK_BLUE + ';background-color:#f4f4f4;'
        'padding:12px 16px;border-radius:0 8px 8px 0;color:#222222;font-size:16px;line-height:1.5;'
        + FONT_STACK + '"><i>'
        + text
        + "</i></td></tr></table>"
    )


def invite_link_box():
    return (
        '<p style="background-color:#f4f4f4;border:1px solid #E5E5E5;border-radius:8px;'
        'padding:12px 16px;word-break:break-all;">'
        '<a href="{{ invite_url }}" style="color:' + LINK_BLUE + ';">{{ invite_url }}</a></p>'
    )


def section_title(text):
    return (
        '<p style="font-size:20px;color:#222222;margin:20px 0 8px;' + FONT_STACK + '">'
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
            "summary": "Example Course - 2 new (1 confirmed, 1 unconfirmed)\n"
            "Review pending: https://courses.datatalks.club/cadmin/campaigns/example/registrations/?status=pending",
            "summary_html": "<p>Example Course - 2 new (1 confirmed, 1 unconfirmed)</p>"
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
            + divider()
            + section_title("Invite friends, earn points")
            + "<p>Know someone who would love this course? Share your personal link with them - "
            "you will earn 1 leaderboard point for each invitee who gets accepted.</p>"
            + invite_link_box()
            + divider()
            + section_title("Spread the word")
            + "<p>Make it your own voice - personal invites work best. Copy, paste, adapt:</p>"
            + quote_block(
                "&ldquo;Excited to share: I got accepted to {{ course_title }} by DataTalks.Club! "
                "I will be learning to build and ship production-ready GenAI systems - containers, GPUs, "
                "real workloads. Join me: {{ invite_url }}&rdquo;"
            )
            + "<p>We look forward to learning with you.<br>DataTalks.Club</p>",
        ),
        "Hi {{ name }},\n\nYour application for {{ course_title }} has been accepted. Welcome!\n\n"
        "{% if custom_message_text %}{{ custom_message_text }}\n\n{% endif %}"
        "Open the course workspace: {{ course_url }}\n"
        "Sign in with the same email address you used for your application to access the course, homework and projects.\n\n"
        "Know someone who would love this course? Invite them with your personal link: {{ invite_url }} - "
        "you will earn 1 leaderboard point for each invitee who gets accepted.\n\n"
        "Your personal invite link: {{ invite_url }}\n\n"
        "Spread the word (make it your own voice - personal invites work best, "
        "works for DMs and public posts):\n"
        '"Excited to share: I got accepted to {{ course_title }} by DataTalks.Club! '
        "I will be learning to build and ship production-ready GenAI systems - containers, GPUs, "
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
            + divider()
            + section_title("Audit the course for free")
            + "<p>The course materials are free for everyone, with or without a seat. "
            "You can follow along at your own pace.</p>"
            + "{% if github_url %}"
            + "<p>Start here: "
            '<a href="{{ github_url }}" style="color:' + LINK_BLUE + ';">{{ github_url }}</a> '
            "- and if you like what you see, give the repo a star.</p>"
            + "{% endif %}"
            + "<p>Best wishes,<br>DataTalks.Club</p>",
        ),
        "Hi {{ name }},\n\nThank you for your interest in {{ course_title }} and for taking the time to apply.\n\n"
        "{% if custom_message_text %}{{ custom_message_text }}\n\n{% endif %}"
        "We're sorry that we are unable to offer you a place in this cohort. "
        "We appreciate your interest and hope you will join us for a future opportunity.\n\n"
        "You can still audit the course for free - the materials are open to everyone.\n"
        "{% if github_url %}Start here: {{ github_url }} - and give the repo a star if you like it.\n{% endif %}\n"
        "Best wishes,\nDataTalks.Club",
        # custom_message intentionally not required: see approved above.
        ["name", "course_title"],
    ),
}
