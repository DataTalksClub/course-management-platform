from dataclasses import dataclass

from courses.deadline_reminder_types import ReminderItemData


@dataclass(frozen=True)
class HomeworkDeadlineContext:
    homework: object

    def __call__(self, action_url):
        homework = self.homework
        return {
            "homework_slug": homework.slug,
            "homework_title": homework.title,
            "homework_due_at": homework.due_date.isoformat(),
            "email_subject": f"Homework deadline soon: {homework.title}",
            "email_preview": "Your homework deadline is within 24 hours.",
            "intro_text": (
                f"{homework.title} in {homework.course.title} "
                "is due within 24 hours."
            ),
            "action_text": f"Submit or update homework: {action_url}",
        }


@dataclass(frozen=True)
class ProjectSubmissionDeadlineContext:
    project: object

    def __call__(self, action_url):
        project = self.project
        return {
            "project_slug": project.slug,
            "project_title": project.title,
            "project_due_at": project.submission_due_date.isoformat(),
            "email_subject": f"Project deadline soon: {project.title}",
            "email_preview": "Your project submission deadline is coming up.",
            "intro_text": (
                f"{project.title} in {project.course.title} is due soon."
            ),
            "action_text": f"Submit or update project: {action_url}",
        }


@dataclass(frozen=True)
class PeerReviewDeadlineContext:
    project: object

    def __call__(self, action_url):
        project = self.project
        return {
            "project_slug": project.slug,
            "project_title": project.title,
            "peer_review_due_at": project.peer_review_due_date.isoformat(),
            "email_subject": f"Peer review deadline soon: {project.title}",
            "email_preview": (
                "Your assigned peer reviews are due within 24 hours."
            ),
            "intro_text": (
                f"Your assigned peer reviews for {project.title} "
                f"in {project.course.title} are due within 24 hours."
            ),
            "action_text": f"Complete peer reviews: {action_url}",
        }


def homework_reminder_item(homework):
    context_extra = HomeworkDeadlineContext(homework)
    return ReminderItemData(
        course=homework.course,
        item_slug=homework.slug,
        item_id=homework.pk,
        item_title=homework.title,
        reminder_key="24h",
        deadline=homework.due_date,
        context_extra=context_extra,
    )


def project_submission_reminder_item(project, reminder_key):
    context_extra = ProjectSubmissionDeadlineContext(project)
    return ReminderItemData(
        course=project.course,
        item_slug=project.slug,
        item_id=project.pk,
        item_title=project.title,
        reminder_key=reminder_key,
        deadline=project.submission_due_date,
        context_extra=context_extra,
    )


def peer_review_reminder_item(project):
    context_extra = PeerReviewDeadlineContext(project)
    return ReminderItemData(
        course=project.course,
        item_slug=project.slug,
        item_id=project.pk,
        item_title=project.title,
        reminder_key="24h",
        deadline=project.peer_review_due_date,
        context_extra=context_extra,
    )
