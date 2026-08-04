from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)

SEND_AUDITS_URL = "/api/datamailer/send-audits"


class DatamailerSendAuditsAPITestCase(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create(
            username="staff",
            email="staff@example.com",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = Client()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def _create_audit(
        self,
        *,
        email,
        template_key,
        idempotency_key,
        html_body="<p>link</p>",
        text_body="link",
        would_deliver=True,
    ):
        response_payload = {
            "message": {"email": email, "template_key": template_key},
            "rendered": {
                "subject": "Saved",
                "html_body": html_body,
                "text_body": text_body,
            },
            "would_deliver": would_deliver,
        }
        return DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            template_key=template_key,
            idempotency_key=idempotency_key,
            response_payload=response_payload,
        )

    def test_requires_token(self):
        response = self.client.get(SEND_AUDITS_URL)

        self.assertEqual(response.status_code, 401)

    def test_filters_by_email_and_template_key(self):
        self._create_audit(
            email="student@example.com",
            template_key="homework-submission-confirmation",
            idempotency_key="hw:1",
        )
        self._create_audit(
            email="other@example.com",
            template_key="homework-submission-confirmation",
            idempotency_key="hw:2",
        )
        self._create_audit(
            email="student@example.com",
            template_key="project-submission-confirmation",
            idempotency_key="proj:1",
        )

        response = self.client.get(
            SEND_AUDITS_URL,
            {
                "email": "Student@Example.com",
                "template_key": "homework-submission-confirmation",
            },
            **self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        audit = body["audits"][0]
        self.assertEqual(audit["idempotency_key"], "hw:1")
        self.assertEqual(
            audit["template_key"], "homework-submission-confirmation"
        )
        self.assertEqual(audit["message"]["email"], "student@example.com")

    def _create_failed_audit(self, *, idempotency_key, error, list_key=""):
        return DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.FAILED,
            template_key="deadline-reminder",
            idempotency_key=idempotency_key,
            list_key=list_key,
            intended_count=1200,
            error=error,
            response_payload={},
        )

    def test_surfaces_error_for_failed_send(self):
        self._create_failed_audit(
            idempotency_key="deadline-reminder:project:72:24h",
            error="HTTPSConnectionPool(...): Read timed out. (read timeout=10)",
            list_key="deadline-reminders:project-submission:llm:project1:24h",
        )

        response = self.client.get(
            SEND_AUDITS_URL,
            {"template_key": "deadline-reminder"},
            **self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        audit = response.json()["audits"][0]
        self.assertEqual(audit["status"], "failed")
        self.assertIn("Read timed out", audit["error"])
        self.assertEqual(audit["intended_count"], 1200)
        self.assertEqual(
            audit["list_key"],
            "deadline-reminders:project-submission:llm:project1:24h",
        )

    def test_filters_by_status(self):
        self._create_audit(
            email="student@example.com",
            template_key="homework-submission-confirmation",
            idempotency_key="hw:1",
        )
        self._create_failed_audit(
            idempotency_key="deadline-reminder:project:72:24h",
            error="Read timed out",
        )

        response = self.client.get(
            SEND_AUDITS_URL,
            {"status": "failed"},
            **self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(
            body["audits"][0]["idempotency_key"],
            "deadline-reminder:project:72:24h",
        )

    def test_filters_by_send_type(self):
        self._create_audit(
            email="student@example.com",
            template_key="homework-submission-confirmation",
            idempotency_key="hw:1",
        )
        self._create_failed_audit(
            idempotency_key="deadline-reminder:project:72:24h",
            error="Read timed out",
        )

        response = self.client.get(
            SEND_AUDITS_URL,
            {"send_type": "transient_recipient_list"},
            **self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(
            body["audits"][0]["idempotency_key"],
            "deadline-reminder:project:72:24h",
        )

    def test_surfaces_rendered_block(self):
        self._create_audit(
            email="student@example.com",
            template_key="homework-submission-confirmation",
            idempotency_key="hw:1",
            html_body="<a href='/homework/hw-1'>Update</a>",
            text_body="Update: /homework/hw-1",
        )

        response = self.client.get(
            SEND_AUDITS_URL,
            {"email": "student@example.com"},
            **self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        audit = response.json()["audits"][0]
        self.assertEqual(audit["would_deliver"], True)
        self.assertIn("/homework/", audit["rendered"]["html_body"])
        self.assertEqual(audit["rendered"]["text_body"], "Update: /homework/hw-1")
