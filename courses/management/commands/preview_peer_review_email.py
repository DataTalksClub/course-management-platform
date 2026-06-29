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
from course_management.datamailer.payloads import _assigned_review_links
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
        course, project = self.get_project(options)

        self.write_project_summary(course, project)
        self.write_deadline(project)
        recipients = self.write_submission_previews(project)
        self.write_recipient_count(recipients)

        if options["json"]:
            self.write_json_payload(project)

    def get_project(self, options):
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

        return course, project

    def write_project_summary(self, course, project):
        out = self.stdout
        out.write(f"Project:  {project.title} ({project.slug})")
        out.write(f"Course:   {course.title} ({course.slug})")
        out.write(f"State:    {project.get_state_display()}")
        out.write(
            f"Reviews each student must do: "
            f"{project.number_of_peers_to_evaluate}"
        )
        out.write("")

    def write_deadline(self, project):
        out = self.stdout
        deadline = format_deadline_for_email(project.peer_review_due_date)
        out.write("Deadline shown in the email:")
        out.write(f"  {deadline['deadline_summary']}")
        out.write("")

    def write_submission_previews(self, project):
        out = self.stdout
        recipients = 0
        submissions = latest_student_submissions(project)
        for submission in submissions:
            recipients += 1
            preview_lines = submission_preview_lines(submission)
            for line in preview_lines:
                out.write(line)

        return recipients

    def write_recipient_count(self, recipients):
        out = self.stdout
        out.write("")
        out.write(
            self.style.SUCCESS(f"{recipients} recipient(s) would be emailed.")
        )

    def write_json_payload(self, project):
        out = self.stdout
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
            return

        list_key, payload = list_payload
        out.write(f"list_key: {list_key}")
        out.write(json.dumps(payload, indent=2, sort_keys=True))


def ordered_project_submissions(project):
    return project.projectsubmission_set.select_related("student").order_by(
        "student_id",
        "-submitted_at",
        "-id",
    )


def latest_student_submissions(project):
    seen = set()
    submissions = ordered_project_submissions(project)
    for submission in submissions:
        if submission.student_id in seen:
            continue
        seen.add(submission.student_id)
        yield submission


def submission_preview_lines(submission):
    lines = [
        f"- {submission.student.email}",
        f"    submitted: {submission_submitted_at(submission)}",
    ]
    links = _assigned_review_links(submission)
    lines.append(f"    you were assigned {len(links)} projects to review:")
    indexed_links = enumerate(links, start=1)
    for i, link in indexed_links:
        lines.append(f"      {i}. {link['eval_url']}")
        if link["submission_github_link"]:
            lines.append(f"         (project: {link['submission_github_link']})")
    return lines


def submission_submitted_at(submission):
    if submission.submitted_at:
        return submission.submitted_at.isoformat()
    return "(no date)"
