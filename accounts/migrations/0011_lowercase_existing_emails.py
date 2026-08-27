import logging
from collections import defaultdict

from django.db import migrations

logger = logging.getLogger(__name__)


def lowercase_existing_emails(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")

    groups = defaultdict(list)
    for user_id, email in CustomUser.objects.exclude(
        email=""
    ).values_list("id", "email"):
        groups[email.strip().lower()].append((user_id, email))

    updated = 0
    for email_lower, members in groups.items():
        if len(members) > 1:
            # Two or more accounts already differ only by email casing.
            # Merging accounts is a decision for a human, not a migration,
            # so leave them untouched and just report it.
            ids = [user_id for user_id, _ in members]
            logger.warning(
                "Skipping case-collision during email lowercasing: "
                "user ids %s all normalize to %r",
                ids,
                email_lower,
            )
            continue

        user_id, email = members[0]
        if email != email_lower:
            CustomUser.objects.filter(id=user_id).update(email=email_lower)
            updated += 1

    logger.info("Lowercased %s user email(s)", updated)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_remove_customuser_email_course_updates_and_more"),
    ]

    operations = [
        migrations.RunPython(
            lowercase_existing_emails, migrations.RunPython.noop
        ),
    ]
