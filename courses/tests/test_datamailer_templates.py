from django.template import Context, Template
from django.test import TestCase

from course_management import email_templates
from course_management.datamailer_templates.definitions.registry import TEMPLATES

EXPECTED_KEYS = {
    "registration-confirmation",
    "homework-submission-confirmation",
    "project-submission-confirmation",
    "homework-score-notification",
    "project-score-notification",
    "certificate-availability-notification",
    "deadline-reminder",
    "peer-review-assignment",
}


class DatamailerTemplatesTest(TestCase):
    def test_covers_every_cmp_template_key(self):
        template_keys = set(TEMPLATES)
        self.assertEqual(template_keys, EXPECTED_KEYS)
        # Every key CMP references as a constant has a definition here.
        for key in (
            email_templates.REGISTRATION_CONFIRMATION,
            email_templates.HOMEWORK_SUBMISSION_CONFIRMATION,
            email_templates.PROJECT_SUBMISSION_CONFIRMATION,
            email_templates.HOMEWORK_SCORE_NOTIFICATION,
            email_templates.PROJECT_SCORE_NOTIFICATION,
            email_templates.PEER_REVIEW_ASSIGNMENT,
            email_templates.CERTIFICATE_AVAILABILITY_NOTIFICATION,
            email_templates.DEADLINE_REMINDER,
        ):
            self.assertIn(key, TEMPLATES)

    def test_every_template_is_well_formed(self):
        for key, payload in TEMPLATES.items():
            with self.subTest(template=key):
                self.assertTrue(payload["name"])
                self.assertTrue(payload["subject"])
                self.assertTrue(payload["html_body"])
                self.assertTrue(payload["text_body"])
                self.assertTrue(payload["required_context"])
                self.assertTrue(payload["example_context"])
                self.assertIs(payload["is_active"], True)
                # The description records the triggering process.
                self.assertIn("Triggered", payload["description"])

    def test_examples_render_with_no_unresolved_variables(self):
        for key, payload in TEMPLATES.items():
            with self.subTest(template=key):
                context = Context(payload["example_context"])
                for field in ("subject", "html_body", "text_body"):
                    template = Template(payload[field])
                    rendered = template.render(context)
                    self.assertNotIn("{{", rendered)
                    self.assertNotIn("{%", rendered)
                self.assertIsNotNone(context)

    def test_peer_review_assignment_lists_assigned_links(self):
        template = Template(
            TEMPLATES["peer-review-assignment"]["html_body"]
        )
        context = Context(
            TEMPLATES["peer-review-assignment"]["example_context"]
        )
        html = template.render(context)
        self.assertIn("Open all your peer reviews", html)
        self.assertIn("/eval/4567", html)
        self.assertIn("20:00 Europe/Berlin", html)
