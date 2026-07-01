"""Definitions for CMP-owned transactional email templates.

Each entry records which CMP process triggers it, so it is visible in the
Datamailer template list. Edit a template here, then run
``uv run python manage.py upsert_datamailer_templates`` to publish the change.

Templates use Django template syntax. For recipient-list sends, each member's
metadata is merged into the per-learner template context.
"""

from .certificates import CERTIFICATE_TEMPLATES
from .peer_review import PEER_REVIEW_TEMPLATES
from .reminders import REMINDER_TEMPLATES
from .scores import SCORE_TEMPLATES
from .submissions import SUBMISSION_TEMPLATES


TEMPLATES = {}
TEMPLATES.update(SUBMISSION_TEMPLATES)
TEMPLATES.update(SCORE_TEMPLATES)
TEMPLATES.update(CERTIFICATE_TEMPLATES)
TEMPLATES.update(REMINDER_TEMPLATES)
TEMPLATES.update(PEER_REVIEW_TEMPLATES)


__all__ = ["TEMPLATES"]
