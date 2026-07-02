CERTIFICATE_TEMPLATES = {
    "certificate-availability-notification": {
        "name": "Certificate Availability Notification",
        "description": (
            "Triggered when a certificate is generated for an enrollment. "
            "Sent to that learner."
        ),
        "subject": "{{ email_subject }}",
        "html_body": (
            "<p>{{ intro_text }}</p>"
            '<p><a href="{{ certificate_url }}">Download certificate</a></p>'
            '<p>Course page: <a href="{{ course_url }}">{{ course_url }}</a></p>'
            '<hr><p style="color:#57606a;font-size:13px;line-height:1.5">'
            "{{ notification_footer }} Manage preferences: "
            '<a href="{{ profile_url }}">{{ profile_url }}</a></p>'
        ),
        "text_body": (
            "{{ intro_text }}\n\n"
            "Download certificate: {{ certificate_url }}\n"
            "Course page: {{ course_url }}\n\n"
            "Manage preferences: {{ profile_url }}\n"
        ),
        "required_context": [
            {"name": "course_title", "description": "Course title."},
            {"name": "certificate_url", "description": "Certificate URL."},
            {"name": "course_url", "description": "Course page URL."},
            {"name": "profile_url", "description": "Preference settings URL."},
            {"name": "intro_text", "description": "Opening sentence."},
            {"name": "notification_footer", "description": "Preference footer."},
        ],
        "example_context": {
            "email_subject": "Certificate available: ML Zoomcamp",
            "course_title": "ML Zoomcamp",
            "certificate_url": "https://courses.datatalks.club/certificates/example.pdf",
            "course_url": "https://courses.datatalks.club/ml-zoomcamp/",
            "profile_url": "https://courses.datatalks.club/accounts/settings/",
            "intro_text": "Congratulations - your certificate for ML Zoomcamp is available.",
            "notification_footer": "You are receiving this because general course-related emails are enabled.",
        },
        "is_active": True,
    }
}
