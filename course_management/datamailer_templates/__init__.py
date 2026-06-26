"""CMP-owned transactional email templates published to Datamailer.

Datamailer is client-agnostic: it stores/renders whatever templates a client
pushes over ``PUT /api/transactional/templates/{key}``. CMP owns the *content*
here and publishes it with the ``upsert_datamailer_templates`` command.
"""

from course_management.datamailer_templates.definitions import TEMPLATES

__all__ = ["TEMPLATES"]
