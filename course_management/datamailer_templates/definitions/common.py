SUBMISSION_HTML = (
    "<p>{{ intro_text }}</p>"
    "<p>{{ update_text }} "
    "<a href=\"{{ update_url }}\">{{ update_link_text|default:'Update submission' }}</a></p>"
    "{% if submitted_answers %}"
    "<h2>Submitted answers</h2><ol>"
    "{% for answer in submitted_answers %}"
    "<li>{{ answer.question }}: "
    "{% if answer.answer %}{{ answer.answer|linebreaksbr }}{% else %}Not submitted{% endif %}</li>"
    "{% endfor %}</ol>"
    "{% endif %}"
    "{% if submission_fields %}"
    "<h2>Submitted details</h2><ul>"
    "{% for field in submission_fields %}"
    "<li>{{ field.label }}: "
    "{% if field.value %}{{ field.value|linebreaksbr }}{% else %}Not submitted{% endif %}</li>"
    "{% endfor %}</ul>"
    "{% endif %}"
    '<hr><p style="color:#57606a;font-size:13px;line-height:1.5">'
    "{{ notification_footer }} "
    'Manage preferences: <a href="{{ profile_url }}">{{ profile_url }}</a>'
    "</p>"
)
SUBMISSION_TEXT = (
    "{{ intro_text }}\n\n"
    "{{ update_text }}\n\n"
    "{% if submitted_answers_text %}"
    "Submitted answers:\n{{ submitted_answers_text }}\n\n"
    "{% endif %}"
    "{% if submitted_fields_text %}"
    "Submitted details:\n{{ submitted_fields_text }}\n\n"
    "{% endif %}"
    "{{ notification_footer_text }}\n"
)
