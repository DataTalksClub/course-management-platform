from .common import SUBMISSION_HTML, SUBMISSION_TEXT


SUBMISSION_TEMPLATES = {
    "registration-confirmation": {
        "name": "Course Registration Confirmation",
        "description": (
            "Triggered when a learner registers for a course campaign. "
            "Sent to that learner."
        ),
        "subject": "{{ email_subject }}",
        "html_body": (
            "<p>{{ intro_text }}</p>"
            "{% if course_url %}"
            '<p><a href="{{ course_url }}">Open the course workspace</a></p>'
            "{% endif %}"
            "{% if registration_url %}"
            '<p><a href="{{ registration_url }}">View registration page</a></p>'
            "{% endif %}"
            '<hr><p style="color:#57606a;font-size:13px;line-height:1.5">'
            "{{ notification_footer }} "
            'Manage preferences: <a href="{{ profile_url }}">{{ profile_url }}</a>'
            "</p>"
        ),
        "text_body": (
            "{{ intro_text }}\n\n"
            "{% if course_url %}Course workspace: {{ course_url }}\n{% endif %}"
            "{% if registration_url %}Registration page: {{ registration_url }}\n{% endif %}"
            "\n{{ notification_footer_text }}\n"
        ),
        "required_context": [
            {"name": "campaign_title", "description": "Registration campaign title."},
            {"name": "registration_id", "description": "CMP registration id."},
            {"name": "registration_url", "description": "Registration page URL."},
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "intro_text", "description": "Opening sentence."},
            {"name": "notification_footer", "description": "Preference footer."},
            {"name": "notification_footer_text", "description": "Plain-text preference footer."},
        ],
        "example_context": {
            "email_subject": "Registration confirmed: LLM Zoomcamp",
            "campaign_title": "LLM Zoomcamp",
            "campaign_slug": "llm-zoomcamp",
            "course_title": "LLM Zoomcamp 2026",
            "course_slug": "llm-zoomcamp-2026",
            "registration_id": 789,
            "registration_url": "https://courses.datatalks.club/register/llm-zoomcamp/",
            "course_url": "https://courses.datatalks.club/llm-zoomcamp-2026/",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "intro_text": "Your registration for LLM Zoomcamp is confirmed.",
            "notification_footer": "You are receiving this because course-related emails are enabled.",
            "notification_footer_text": "Manage preferences: https://courses.datatalks.club/accounts/settings/",
        },
        "is_active": True,
    },
    "homework-submission-confirmation": {
        "name": "Homework Submission Confirmation",
        "description": (
            "Triggered when a learner submits or updates a homework. "
            "Sent to that learner."
        ),
        "subject": "{{ email_subject }}",
        "html_body": SUBMISSION_HTML,
        "text_body": SUBMISSION_TEXT,
        "required_context": [
            {"name": "course_title", "description": "Course title."},
            {"name": "homework_title", "description": "Homework title."},
            {"name": "submission_id", "description": "CMP submission id."},
            {"name": "submitted_at", "description": "Submission timestamp."},
            {"name": "update_url", "description": "Submission update URL."},
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "intro_text", "description": "Opening sentence."},
            {"name": "notification_footer", "description": "Preference footer."},
            {"name": "notification_footer_text", "description": "Plain-text preference footer."},
        ],
        "example_context": {
            "email_subject": "Homework submission saved: Homework 1",
            "course_title": "ML Zoomcamp",
            "homework_title": "Homework 1",
            "submission_id": 123,
            "submitted_at": "2026-06-16T12:00:00+00:00",
            "update_url": "https://courses.datatalks.club/ml-zoomcamp/homework/homework-1",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "intro_text": "Your homework submission for Homework 1 in ML Zoomcamp was saved.",
            "update_text": "You can update your submission while the homework is open.",
            "update_link_text": "Update your submission",
            "submission_fields": [
                {
                    "key": "time_spent_homework",
                    "label": "Time spent on homework",
                    "value": "4 hours",
                }
            ],
            "submitted_answers": [
                {
                    "question": "Pick one option",
                    "answer": "2. Second option",
                }
            ],
            "submitted_fields_text": "Time spent on homework: 4 hours",
            "submitted_answers_text": "Pick one option: 2. Second option",
            "notification_footer": "You are receiving this because homework and project submission emails are enabled.",
            "notification_footer_text": "Manage preferences: https://courses.datatalks.club/accounts/settings/",
        },
        "is_active": True,
    },
    "project-submission-confirmation": {
        "name": "Project Submission Confirmation",
        "description": (
            "Triggered when a learner submits or updates a project. "
            "Sent to that learner."
        ),
        "subject": "{{ email_subject }}",
        "html_body": SUBMISSION_HTML,
        "text_body": SUBMISSION_TEXT,
        "required_context": [
            {"name": "course_title", "description": "Course title."},
            {"name": "project_title", "description": "Project title."},
            {"name": "submission_id", "description": "CMP submission id."},
            {"name": "submitted_at", "description": "Submission timestamp."},
            {"name": "update_url", "description": "Submission update URL."},
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "intro_text", "description": "Opening sentence."},
            {"name": "notification_footer", "description": "Preference footer."},
            {"name": "notification_footer_text", "description": "Plain-text preference footer."},
        ],
        "example_context": {
            "email_subject": "Project submission saved: Midterm Project",
            "course_title": "ML Zoomcamp",
            "project_title": "Midterm Project",
            "submission_id": 456,
            "submitted_at": "2026-06-16T12:00:00+00:00",
            "update_url": "https://courses.datatalks.club/ml-zoomcamp/project/midterm",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "intro_text": "Your project submission for Midterm Project in ML Zoomcamp was saved.",
            "update_text": "You can update your submission while the project is open.",
            "update_link_text": "Update your submission",
            "submission_fields": [
                {
                    "key": "github_link",
                    "label": "GitHub repository",
                    "value": "https://github.com/example/project",
                },
                {"key": "commit_id", "label": "Commit ID", "value": "abc123"},
            ],
            "submitted_fields_text": "GitHub repository: https://github.com/example/project\nCommit ID: abc123",
            "notification_footer": "You are receiving this because homework and project submission emails are enabled.",
            "notification_footer_text": "Manage preferences: https://courses.datatalks.club/accounts/settings/",
        },
        "is_active": True,
    }
}
