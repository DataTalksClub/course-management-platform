REMINDER_TEMPLATES = {
    "deadline-reminder": {
        "name": "Deadline Reminder",
        "description": (
            "Triggered by the scheduled send_deadline_reminders job, 24h "
            "before a homework, project, or peer-review deadline."
        ),
        "subject": "{{ email_subject }}",
        "html_body": (
            "<p>{{ intro_text }}</p>"
            "<p>Deadline: {{ deadline_at }}</p>"
            "<p><a href=\"{{ action_url }}\">{{ action_text|default:'Open course platform' }}</a></p>"
            '<hr><p style="color:#57606a;font-size:13px;line-height:1.5">'
            "{{ notification_footer }} Manage preferences: "
            '<a href="{{ profile_url }}">{{ profile_url }}</a></p>'
        ),
        "text_body": (
            "{{ intro_text }}\n\n"
            "Deadline: {{ deadline_at }}\n"
            "{{ action_text }}\n\n"
            "{{ notification_footer }}\n"
            "Manage preferences: {{ profile_url }}\n"
        ),
        "required_context": [
            {"name": "course_title", "description": "Course title."},
            {"name": "item_title", "description": "Homework, project, or peer-review item title."},
            {"name": "deadline_at", "description": "Rendered deadline."},
            {"name": "action_url", "description": "URL for the learner action."},
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "intro_text", "description": "Opening sentence."},
            {"name": "notification_footer", "description": "Preference footer."},
        ],
        "example_context": {
            "email_subject": "Homework deadline soon: Homework 1",
            "course_title": "ML Zoomcamp",
            "item_type": "homework",
            "item_title": "Homework 1",
            "deadline_at": "Thursday, 18 June 2026, 23:00 UTC",
            "action_url": "https://courses.datatalks.club/ml-zoomcamp/homework/homework-1",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "intro_text": "Homework 1 in ML Zoomcamp is due within 24 hours.",
            "action_text": "Submit or update homework: https://courses.datatalks.club/ml-zoomcamp/homework/homework-1",
            "notification_footer": "You are receiving this because deadline reminders are enabled.",
        },
        "is_active": True,
    }
}
