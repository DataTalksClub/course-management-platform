from api.openapi_primitives import JSON, array_of, ref

INTEGRATION_SCHEMAS = {
    "Graduates": {
        "type": "object",
        "required": ["graduates"],
        "properties": {
            "graduates": array_of(
                {
                    "type": "object",
                    "required": ["email", "name"],
                    "properties": {
                        "email": {"type": "string"},
                        "name": {"type": "string"},
                    },
                }
            )
        },
    },
    "CertificateUpdate": {
        "type": "object",
        "required": ["email", "certificate_path"],
        "properties": {
            "email": {"type": "string"},
            "certificate_path": {"type": "string"},
        },
    },
    "CertificateUpdateRequest": {
        "oneOf": [
            {
                "type": "object",
                "required": ["certificates"],
                "properties": {
                    "certificates": array_of(ref("CertificateUpdate")),
                },
            },
            array_of(ref("CertificateUpdate")),
        ],
    },
    "CertificateUpdateResult": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "email": {"type": "string"},
            "enrollment_id": {"type": "integer"},
            "certificate_url": {"type": "string"},
        },
    },
    "CertificateUpdateError": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "email": {"type": "string"},
            "code": {"type": "string"},
            "error": {"type": "string"},
        },
    },
    "CertificateUpdateResponse": {
        "type": "object",
        "required": ["success", "updated_count", "error_count"],
        "properties": {
            "success": {"type": "boolean"},
            "updated_count": {"type": "integer"},
            "error_count": {"type": "integer"},
            "updated": array_of(ref("CertificateUpdateResult")),
            "errors": array_of(ref("CertificateUpdateError")),
        },
    },
    "DatamailerEvent": {
        "type": "object",
        "required": ["event_id", "event_type", "email"],
        "properties": {
            "event_id": {"type": "string"},
            "event_type": {
                "type": "string",
                "enum": [
                    "contact.hard_bounced",
                    "contact.complained",
                    "subscription.unsubscribed",
                    "subscription.resubscribed",
                    "message.delivered",
                    "message.opened",
                    "message.clicked",
                    "transactional.skipped",
                    "transactional.failed",
                ],
            },
            "email": {"type": "string", "format": "email"},
            "occurred_at": {"type": "string", "format": "date-time"},
            "audience": {"type": "string"},
            "client": {"type": "string"},
            "preference_key": {
                "type": "string",
                "enum": [
                    "email_submission_confirmations",
                    "email_deadline_reminders",
                    "email_course_updates",
                ],
            },
            "metadata": JSON,
        },
        "additionalProperties": True,
    },
    "DatamailerEventAccepted": {
        "type": "object",
        "required": ["ok", "created", "preference_updated"],
        "properties": {
            "ok": {"type": "boolean"},
            "created": {"type": "boolean"},
            "preference_updated": {"type": "boolean"},
        },
    },
}
