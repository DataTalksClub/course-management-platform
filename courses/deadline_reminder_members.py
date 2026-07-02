from accounts.services.timezones import format_deadline_for_user


def deadline_metadata(deadline, user):
    formatted = format_deadline_for_user(deadline, user)
    return {
        "deadline_at": formatted["deadline_summary"],
        "deadline_iso": formatted["deadline_iso"],
        "deadline_weekday": formatted["deadline_weekday"],
        "deadline_date": formatted["deadline_date"],
        "deadline_time": formatted["deadline_time"],
        "deadline_timezone": formatted["deadline_timezone"],
        "deadline_summary": formatted["deadline_summary"],
    }


def member_from_enrollment(enrollment, metadata, *, deadline=None):
    raw_email = enrollment.student.email or ""
    email_stripped = raw_email.strip()
    email = email_stripped.lower()
    if not email:
        return None
    member_metadata = metadata
    if deadline is not None:
        member_metadata = member_metadata | deadline_metadata(
            deadline, enrollment.student
        )
    return {
        "source_object_key": f"enrollment:{enrollment.pk}",
        "email": email,
        "status": "active",
        "metadata": member_metadata
        | {
            "enrollment_id": enrollment.pk,
            "user_id": enrollment.student_id,
            "source_object_key": f"enrollment:{enrollment.pk}",
        },
    }


def member_from_project_submission(submission, metadata, *, deadline=None):
    raw_email = submission.student.email or ""
    email_stripped = raw_email.strip()
    email = email_stripped.lower()
    if not email:
        return None
    source_object_key = f"project-submission:{submission.pk}"
    member_metadata = metadata
    if deadline is not None:
        member_metadata = member_metadata | deadline_metadata(
            deadline, submission.student
        )
    return {
        "source_object_key": source_object_key,
        "email": email,
        "status": "active",
        "metadata": member_metadata
        | {
            "submission_id": submission.pk,
            "enrollment_id": submission.enrollment_id,
            "user_id": submission.student_id,
            "source_object_key": source_object_key,
        },
    }


def reminder_members_from_enrollments(enrollments, metadata, deadline):
    members = []
    for enrollment in enrollments:
        member = member_from_enrollment(
            enrollment,
            metadata,
            deadline=deadline,
        )
        if member is not None:
            members.append(member)
    return members


def reminder_members_from_submissions(submissions, metadata, deadline):
    members = []
    for submission in submissions:
        member = member_from_project_submission(
            submission,
            metadata,
            deadline=deadline,
        )
        if member is not None:
            members.append(member)
    return members
