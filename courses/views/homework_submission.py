from dataclasses import dataclass
from functools import partial

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils import timezone

from course_management.datamailer.sync.memberships import (
    sync_homework_submission_to_datamailer,
)
from course_management.observability import record_event
from courses.models.course import Course, Enrollment
from courses.models.homework import (
    Answer,
    Homework,
    Question,
    Submission,
)
from courses.views.homework_confirmation import (
    HomeworkConfirmationEmailData,
    build_homework_update_url,
    send_homework_confirmation_email,
)
from courses.views.homework_submission_fields import (
    HomeworkSubmissionFieldData,
    apply_homework_submission_fields,
)


@dataclass(frozen=True)
class HomeworkPostData:
    request: HttpRequest
    course: Course
    homework: Homework
    questions: list[Question]
    submission: Submission | None
    enrollment: Enrollment


def homework_answers_from_post(request):
    answers_dict = {}
    posted_answers = request.POST.lists()
    for answer_id, answer in posted_answers:
        if not answer_id.startswith("answer_"):
            continue
        cleaned_answer_items = []
        for answer_item in answer:
            cleaned_answer_item = answer_item.strip()
            cleaned_answer_items.append(cleaned_answer_item)
        answers_dict[answer_id] = ",".join(cleaned_answer_items)
    return answers_dict


def homework_submission_for_user(user, course, homework, submission):
    if submission:
        submission.submitted_at = timezone.now()
        return submission

    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    return Submission.objects.create(
        homework=homework,
        student=user,
        enrollment=enrollment,
    )


def save_homework_answers(submission, questions, answers_dict):
    for question in questions:
        answer_text = answers_dict.get(f"answer_{question.id}")
        Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults={"answer_text": answer_text},
        )


def register_homework_submission_callbacks(data, submission):
    user = data.request.user
    update_url = build_homework_update_url(
        data.request,
        data.course,
        data.homework,
    )
    confirmation_data = HomeworkConfirmationEmailData(
        user=user,
        course=data.course,
        homework=data.homework,
        submission=submission,
        update_url=update_url,
    )
    email_callback = partial(
        send_homework_confirmation_email,
        confirmation_data,
    )
    sync_callback = partial(
        sync_homework_submission_to_datamailer,
        submission,
    )
    transaction.on_commit(email_callback)
    transaction.on_commit(sync_callback)


def homework_submission_success_response(request, course, homework):
    success_message = (
        "Thank you for submitting your homework, now your solution "
        + "is saved. You can update it at any point. You will see "
        + "your score after the form is closed."
    )
    messages.success(
        request,
        success_message,
        extra_tags="homework",
    )
    response = redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )
    return response


def save_homework_submission_data(data):
    user = data.request.user
    answers_dict = homework_answers_from_post(data.request)
    submission = homework_submission_for_user(
        user,
        data.course,
        data.homework,
        data.submission,
    )
    save_homework_answers(submission, data.questions, answers_dict)
    field_data = HomeworkSubmissionFieldData(
        submission=submission,
        request=data.request,
        course=data.course,
        homework=data.homework,
        user=user,
    )
    apply_homework_submission_fields(field_data)
    submission.full_clean()
    submission.save()
    return submission


def process_homework_submission(data: HomeworkPostData):
    is_update = data.submission is not None
    submission = save_homework_submission_data(data)
    record_event(
        "homework.submitted",
        request=data.request,
        properties={
            "course_slug": data.course.slug,
            "homework_slug": data.homework.slug,
            "homework_id": data.homework.id,
            "submission_id": submission.id,
            "enrollment_id": submission.enrollment_id,
            "is_update": is_update,
            "question_count": len(data.questions),
        },
    )
    register_homework_submission_callbacks(data, submission)
    return homework_submission_success_response(
        data.request,
        data.course,
        data.homework,
    )
