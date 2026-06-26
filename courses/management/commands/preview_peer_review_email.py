"""Preview the peer-review-assignment notification for a project.

Renders the exact data the email carries -- the multi-timezone deadline and,
per submitting student, their submission date and the direct evaluation links
for the projects they were assigned to review. Works without Datamailer
configured; pass --json to also dump the full transactional-send payload
(requires Datamailer settings).

    uv run python manage.py preview_peer_review_email <course_slug> <project_slug>
"""

import json

from django.core.management.base import BaseCommand, CommandError

from courses.models import Course, Project
from course_management import datamailer
from course_management.deadlines import format_deadline_for_email


class Command(BaseCommand):
    help = "Preview the peer-review-assignment email for a project."

    def add_arguments(self, parser):
        parser.add_argument("course_slug")
        parser.add_argument("project_slug")
        parser.add_argument(
            "--json",
            action="store_true",
            help="Also print the full Datamailer payload (needs Datamailer "
            "settings).",
        )

    def handle(self, *args, **options):
        try:
            course = Course.objects.get(slug=options["course_slug"])
            project = Project.objects.get(
                course=course, slug=options["project_slug"]
            )
        except Course.DoesNotExist:
            raise CommandError(f"No course with slug '{options['course_slug']}'.")
        except Project.DoesNotExist:
            raise CommandError(
                f"No project '{options['project_slug']}' in "
                f"'{options['course_slug']}'."
            )

        out = self.stdout
        out.write(f"Project:  {project.title} ({project.slug})")
        out.write(f"Course:   {course.title} ({course.slug})")
        out.write(f"State:    {project.get_state_display()}")
        out.write(
            f"Reviews each student must do: "
            f"{project.number_of_peers_to_evaluate}"
        )
        out.write("")

        deadline = format_deadline_for_email(project.peer_review_due_date)
        out.write("Deadline shown in the email:")
        out.write(f"  {deadline['deadline_summary']}")
        out.write("")

        submissions = (
            project.projectsubmission_set.select_related("student")
            .order_by("student_id", "-submitted_at", "-id")
        )
        seen = set()
        recipients = 0
        for submission in submissions:
            student = submission.student
            if not getattr(student, "email_submission_confirmations", True):
                continue
            if submission.student_id in seen:
                continue
            seen.add(submission.student_id)
            recipients += 1

            links = datamailer._assigned_review_links(submission)
            submitted = (
                submission.submitted_at.isoformat()
                if submission.submitted_at
                else "(no date)"
            )
            out.write(f"- {student.email}")
            out.write(f"    submitted: {submitted}")
            out.write(f"    you were assigned {len(links)} projects to review:")
            for i, link in enumerate(links, start=1):
                out.write(f"      {i}. {link['eval_url']}")
                if link["submission_github_link"]:
                    out.write(
                        f"         (project: {link['submission_github_link']})"
                    )

        out.write("")
        out.write(
            self.style.SUCCESS(f"{recipients} recipient(s) would be emailed.")
        )

        if options["json"]:
            out.write("")
            list_payload = datamailer.peer_review_assignment_notification_payload(
                project
            )
            if list_payload is None:
                out.write(
                    self.style.WARNING(
                        "Datamailer not configured - no payload to show."
                    )
                )
            else:
                list_key, payload = list_payload
                out.write(f"list_key: {list_key}")
                out.write(json.dumps(payload, indent=2, sort_keys=True))
