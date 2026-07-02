SCORE_TEMPLATES = {
    "homework-score-notification": {
        "name": "Homework Score Notification",
        "description": (
            "Triggered when staff score the homework (cadmin -> Score "
            "homework). Sent to every homework submitter."
        ),
        "subject": "Scores available: {{ homework_title }}",
        "html_body": (
            "<p>Your score for <strong>{{ homework_title }}</strong> in {{ course_title }} is ready.</p>"
            "<p>Your score: <strong>{{ total_score }}</strong></p>"
            "<ul>"
            "<li>Questions: {{ questions_score }}</li>"
            "<li>Learning in public: {{ learning_in_public_score }}</li>"
            "<li>FAQ contribution: {{ faq_score }}</li>"
            "</ul>"
            "<h2>Next steps</h2>"
            "<ul>"
            '<li><a href="{{ scores_url }}">Review your homework score</a></li>'
            '<li><a href="{{ leaderboard_url }}">Check the course leaderboard</a></li>'
            '<li><a href="{{ course_url }}">Open the course page</a></li>'
            "</ul>"
            '<hr><p style="color:#57606a;font-size:13px;line-height:1.5">'
            "{{ notification_footer }} "
            'To stop receiving these emails, update your profile settings: '
            '<a href="{{ profile_url }}">{{ profile_url }}</a></p>'
        ),
        "text_body": (
            "Your score for {{ homework_title }} in {{ course_title }} is ready.\n\n"
            "Your score: {{ total_score }}\n"
            "Breakdown:\n"
            "- Questions: {{ questions_score }}\n"
            "- Learning in public: {{ learning_in_public_score }}\n"
            "- FAQ contribution: {{ faq_score }}\n\n"
            "Next steps:\n"
            "- Review your homework score: {{ scores_url }}\n"
            "- Check the course leaderboard: {{ leaderboard_url }}\n"
            "- Open the course page: {{ course_url }}\n\n"
            "{{ notification_footer_text }}\n"
        ),
        "required_context": [
            {"name": "course_title", "description": "Course title."},
            {"name": "homework_title", "description": "Homework title."},
            {"name": "course_url", "description": "Course page URL."},
            {"name": "questions_score", "description": "Homework question score for this learner."},
            {"name": "learning_in_public_score", "description": "Learning in public score for this learner."},
            {"name": "faq_score", "description": "FAQ contribution score for this learner."},
            {"name": "total_score", "description": "Total homework score for this learner."},
            {"name": "scores_url", "description": "URL where scores can be viewed."},
            {"name": "leaderboard_url", "description": "Course leaderboard URL."},
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "notification_footer", "description": "Preference footer."},
            {"name": "notification_footer_text", "description": "Plain-text preference footer."},
        ],
        "example_context": {
            "course_title": "ML Zoomcamp",
            "homework_title": "Homework 1",
            "course_url": "https://courses.datatalks.club/ml-zoomcamp/",
            "questions_score": 6,
            "learning_in_public_score": 2,
            "faq_score": 1,
            "total_score": 9,
            "scores_url": "https://courses.datatalks.club/ml-zoomcamp/homework/homework-1",
            "leaderboard_url": "https://courses.datatalks.club/ml-zoomcamp/leaderboard",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "notification_footer": (
                "You are receiving this because you submitted Homework 1 for ML Zoomcamp and "
                "homework/project submission emails are enabled in your profile."
            ),
            "notification_footer_text": (
                "If you don't want to receive homework/project submission and score emails, "
                "turn off homework and project submission emails in your profile: "
                "https://courses.datatalks.club/accounts/settings/"
            ),
        },
        "is_active": True,
    },
    "project-score-notification": {
        "name": "Project Score Notification",
        "description": (
            "Triggered when staff score the project (cadmin -> Score "
            "project). Sent to every project submitter."
        ),
        "subject": "Scores available: {{ project_title }}",
        "html_body": (
            "<p>Your score for <strong>{{ project_title }}</strong> in {{ course_title }} is ready.</p>"
            "<p>Your score: <strong>{{ total_score }}</strong></p>"
            "<ul>"
            "<li>Project: {{ project_score }}</li>"
            "<li>Project learning in public: {{ project_learning_in_public_score }}</li>"
            "<li>Project FAQ: {{ project_faq_score }}</li>"
            "<li>Peer review: {{ peer_review_score }}</li>"
            "<li>Peer review learning in public: {{ peer_review_learning_in_public_score }}</li>"
            "</ul>"
            "{% if github_link %}"
            "<p>Submission reviewed: "
            '<a href="{{ github_link }}">GitHub repository</a>'
            "{% if commit_id %} at commit <code>{{ commit_id }}</code>{% endif %}.</p>"
            "{% endif %}"
            "<h2>Next steps</h2>"
            "<ul>"
            '<li><a href="{{ scores_url }}">Review your project result</a></li>'
            '<li><a href="{{ project_url }}">Open the project page</a></li>'
            '<li><a href="{{ leaderboard_url }}">Check the course leaderboard</a></li>'
            '<li><a href="{{ course_url }}">Open the course page</a></li>'
            "</ul>"
            '<hr><p style="color:#57606a;font-size:13px;line-height:1.5">'
            "{{ notification_footer }} "
            'To stop receiving these emails, update your profile settings: '
            '<a href="{{ profile_url }}">{{ profile_url }}</a></p>'
        ),
        "text_body": (
            "Your score for {{ project_title }} in {{ course_title }} is ready.\n\n"
            "Your score: {{ total_score }}\n"
            "Breakdown:\n"
            "- Project: {{ project_score }}\n"
            "- Project learning in public: {{ project_learning_in_public_score }}\n"
            "- Project FAQ: {{ project_faq_score }}\n"
            "- Peer review: {{ peer_review_score }}\n"
            "- Peer review learning in public: {{ peer_review_learning_in_public_score }}\n\n"
            "{% if github_link %}"
            "Submission reviewed: {{ github_link }}{% if commit_id %} at commit {{ commit_id }}{% endif %}\n\n"
            "{% endif %}"
            "Next steps:\n"
            "- Review your project result: {{ scores_url }}\n"
            "- Open the project page: {{ project_url }}\n"
            "- Check the course leaderboard: {{ leaderboard_url }}\n"
            "- Open the course page: {{ course_url }}\n\n"
            "{{ notification_footer_text }}\n"
        ),
        "required_context": [
            {"name": "course_title", "description": "Course title."},
            {"name": "project_title", "description": "Project title."},
            {"name": "course_url", "description": "Course page URL."},
            {"name": "project_url", "description": "Project page URL."},
            {"name": "project_score", "description": "Project score for this learner."},
            {
                "name": "project_learning_in_public_score",
                "description": "Project learning in public score for this learner.",
            },
            {"name": "project_faq_score", "description": "Project FAQ contribution score for this learner."},
            {"name": "peer_review_score", "description": "Peer review score for this learner."},
            {
                "name": "peer_review_learning_in_public_score",
                "description": "Peer review learning in public score for this learner.",
            },
            {"name": "total_score", "description": "Total project score for this learner."},
            {"name": "scores_url", "description": "URL where scores can be viewed."},
            {"name": "leaderboard_url", "description": "Course leaderboard URL."},
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "notification_footer", "description": "Preference footer."},
            {"name": "notification_footer_text", "description": "Plain-text preference footer."},
        ],
        "example_context": {
            "course_title": "ML Zoomcamp",
            "project_title": "Midterm Project",
            "course_url": "https://courses.datatalks.club/ml-zoomcamp/",
            "project_url": "https://courses.datatalks.club/ml-zoomcamp/project/midterm",
            "project_score": 70,
            "project_learning_in_public_score": 5,
            "project_faq_score": 1,
            "peer_review_score": 18,
            "peer_review_learning_in_public_score": 4,
            "total_score": 98,
            "github_link": "https://github.com/example/project",
            "commit_id": "abc123",
            "scores_url": "https://courses.datatalks.club/ml-zoomcamp/project/midterm/results",
            "leaderboard_url": "https://courses.datatalks.club/ml-zoomcamp/leaderboard",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "notification_footer": (
                "You are receiving this because you submitted Midterm Project for ML Zoomcamp and "
                "homework/project submission emails are enabled in your profile."
            ),
            "notification_footer_text": (
                "If you don't want to receive homework/project submission and score emails, "
                "turn off homework and project submission emails in your profile: "
                "https://courses.datatalks.club/accounts/settings/"
            ),
        },
        "is_active": True,
    }
}
