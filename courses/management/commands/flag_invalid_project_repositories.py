from django.core.management.base import BaseCommand

from courses.models.project import ProjectSubmission
from courses.validators.custom_url_validators import (
    is_github_repository_url,
)


class Command(BaseCommand):
    help = (
        "Flag project submissions whose repository link is not a GitHub "
        "repository URL. Never deletes anything."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        bad_ids = []
        for sub in ProjectSubmission.objects.only("id", "github_link"):
            if not is_github_repository_url(sub.github_link):
                bad_ids.append(sub.id)

        if not dry_run:
            ProjectSubmission.objects.filter(id__in=bad_ids).update(
                invalid_repository_flagged=True
            )
            ProjectSubmission.objects.exclude(id__in=bad_ids).filter(
                invalid_repository_flagged=True
            ).update(invalid_repository_flagged=False)

        self.stdout.write(
            f"{'Would flag' if dry_run else 'Flagged'} {len(bad_ids)} "
            f"submission(s): {bad_ids}"
        )
