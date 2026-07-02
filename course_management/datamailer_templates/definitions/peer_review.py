PEER_REVIEW_ASSIGNMENT_HTML = (
    "<p>{{ intro_text }}</p>"
    "{% if submitted_at %}"
    "<p>You submitted your project on {{ submitted_at }}.</p>"
    "{% endif %}"
    "<p><strong>Deadline:</strong> {{ deadline_summary }}</p>"
    "<h2>Your {{ number_of_peers_to_evaluate }} projects to review</h2>"
    "<ol>"
    "{% for review in assigned_reviews %}"
    '<li><a href="{{ review.eval_url }}">Review assignment #{{ review.review_id }}</a>'
    "{% if review.submission_github_link %}"
    ' &mdash; <a href="{{ review.submission_github_link }}">repository</a>'
    "{% endif %}</li>"
    "{% endfor %}"
    "</ol>"
    '<p><a href="{{ evaluations_url }}">Open all your peer reviews</a></p>'
    '<hr><p style="color:#57606a;font-size:13px;line-height:1.5">'
    "{{ notification_footer }} "
    "To stop receiving these emails, update your profile settings: "
    '<a href="{{ profile_url }}">{{ profile_url }}</a></p>'
)

PEER_REVIEW_ASSIGNMENT_TEXT = (
    "{{ intro_text }}\n\n"
    "{% if submitted_at %}You submitted your project on {{ submitted_at }}.\n\n"
    "{% endif %}"
    "Deadline: {{ deadline_summary }}\n\n"
    "Your {{ number_of_peers_to_evaluate }} projects to review:\n"
    "{% for review in assigned_reviews %}"
    "- {{ review.eval_url }}"
    "{% if review.submission_github_link %} (repo: {{ review.submission_github_link }}){% endif %}\n"
    "{% endfor %}\n"
    "Open all your peer reviews: {{ evaluations_url }}\n\n"
    "{{ notification_footer_text }}\n"
)



PEER_REVIEW_TEMPLATES = {
    "peer-review-assignment": {
        "name": "Peer Review Assignment",
        "description": (
            "Triggered when staff assign peer reviews / close project "
            "submissions (cadmin -> Assign peer reviews). Sent to every "
            "project submitter with their assigned projects and the deadline."
        ),
        "subject": "Peer review is open: {{ project_title }}",
        "html_body": PEER_REVIEW_ASSIGNMENT_HTML,
        "text_body": PEER_REVIEW_ASSIGNMENT_TEXT,
        "required_context": [
            {"name": "course_title", "description": "Course title."},
            {"name": "project_title", "description": "Project title."},
            {
                "name": "deadline_summary",
                "description": "Peer-review deadline, e.g. 'Thursday, 2 July "
                "2026, 20:00 Europe/Berlin'.",
            },
            {
                "name": "number_of_peers_to_evaluate",
                "description": "How many projects this learner must review.",
            },
            {
                "name": "evaluations_url",
                "description": "URL listing all of the learner's peer reviews.",
            },
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "intro_text", "description": "Opening sentence."},
            {"name": "notification_footer", "description": "Preference footer."},
            {
                "name": "notification_footer_text",
                "description": "Plain-text preference footer.",
            },
        ],
        "example_context": {
            "course_title": "ML Zoomcamp",
            "project_title": "Capstone 1",
            "submitted_at": "2026-06-18T14:05:00+00:00",
            "deadline_summary": "Thursday, 2 July 2026, 20:00 Europe/Berlin",
            "deadline_weekday": "Thursday",
            "number_of_peers_to_evaluate": 3,
            "evaluations_url": "https://courses.datatalks.club/ml-zoomcamp/project/capstone-1/eval",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "intro_text": (
                "Thanks for submitting Capstone 1 in ML Zoomcamp. Peer review "
                "is now open - you have 3 projects to evaluate before the "
                "deadline."
            ),
            "assigned_reviews": [
                {
                    "review_id": 4567,
                    "eval_url": "https://courses.datatalks.club/ml-zoomcamp/project/capstone-1/eval/4567",
                    "submission_github_link": "https://github.com/example/project-a",
                },
                {
                    "review_id": 4581,
                    "eval_url": "https://courses.datatalks.club/ml-zoomcamp/project/capstone-1/eval/4581",
                    "submission_github_link": "https://github.com/example/project-b",
                },
                {
                    "review_id": 4602,
                    "eval_url": "https://courses.datatalks.club/ml-zoomcamp/project/capstone-1/eval/4602",
                    "submission_github_link": "",
                },
            ],
            "notification_footer": (
                "You are receiving this because you submitted Capstone 1 for "
                "ML Zoomcamp and homework/project submission emails are enabled "
                "in your profile."
            ),
            "notification_footer_text": (
                "If you don't want to receive homework/project submission and "
                "score emails, turn off homework and project submission emails "
                "in your profile: https://courses.datatalks.club/accounts/settings/"
            ),
        },
        "is_active": True,
    }
}
