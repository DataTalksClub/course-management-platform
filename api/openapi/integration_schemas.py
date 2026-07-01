from .primitives import JSON, array_of, ref

CERTIFICATE_UPDATE_REF = ref("CertificateUpdate")
CERTIFICATE_UPDATE_ARRAY = array_of(CERTIFICATE_UPDATE_REF)
CERTIFICATE_UPDATE_RESULT_REF = ref("CertificateUpdateResult")
CERTIFICATE_UPDATE_RESULT_ARRAY = array_of(CERTIFICATE_UPDATE_RESULT_REF)
CERTIFICATE_UPDATE_ERROR_REF = ref("CertificateUpdateError")
CERTIFICATE_UPDATE_ERROR_ARRAY = array_of(CERTIFICATE_UPDATE_ERROR_REF)
GRADUATE_SCHEMA = {
    "type": "object",
    "required": ["email", "name"],
    "properties": {
        "email": {"type": "string"},
        "name": {"type": "string"},
    },
}
GRADUATES_ARRAY = array_of(GRADUATE_SCHEMA)

INTEGRATION_SCHEMAS = {
    "Graduates": {
        "type": "object",
        "required": ["graduates"],
        "properties": {
            "graduates": GRADUATES_ARRAY,
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
                    "certificates": CERTIFICATE_UPDATE_ARRAY,
                },
            },
            CERTIFICATE_UPDATE_ARRAY,
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
            "updated": CERTIFICATE_UPDATE_RESULT_ARRAY,
            "errors": CERTIFICATE_UPDATE_ERROR_ARRAY,
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
