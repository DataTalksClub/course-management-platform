from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection

from courses.models import ProjectSubmission
from courses.tests.project_view_base import (
    ProjectViewTestBase,
)


class InvalidProjectRepositoryBackfillTestCase(ProjectViewTestBase):
    def test_backfill_flags_invalid_links_without_deleting_rows(self):
        invalid_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://pantry-prod.onrender.com",
            commit_id="abcdef1",
        )
        valid_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/example/project",
            commit_id="abcdef2",
            volunteer_review_only=True,
        )
        migration = import_module(
            "courses.migrations."
            "0061_flag_existing_invalid_project_submissions"
        )
        count_before = ProjectSubmission.objects.count()

        migration.flag_existing_invalid_project_submissions(
            apps,
            SimpleNamespace(connection=connection),
        )

        invalid_submission.refresh_from_db()
        valid_submission.refresh_from_db()
        self.assertTrue(invalid_submission.invalid_repository_flagged)
        self.assertFalse(valid_submission.invalid_repository_flagged)
        self.assertEqual(
            ProjectSubmission.objects.count(), count_before
        )
