from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from course_management.datamailer.client import check_relay_availability
from course_management.datamailer.score_notification_status import (
    get_homework_score_notification_status,
)
from course_management.datamailer.sync.score_notifications import (
    queue_homework_score_notification,
)
from courses.models.course import Course
from courses.models.homework import Homework, HomeworkState, Question
from courses.homework_correct_answers import (
    clear_correct_answers,
    fill_correct_answers,
)
from courses.scoring_queue import (
    enqueue_homework_scoring,
    homework_score_precheck,
    latest_homework_job,
    scoring_banner,
)
from cadmin.deadline_extension import extend_deadlines
from cadmin.views.homework_submission_edit import (
    homework_submission_edit_response,
)
from cadmin.views.homework_submission_list import (
    HomeworkSubmissionsContextData,
    homework_submissions_context,
    homework_submissions_queryset,
)
from .helpers import (
    paginate_queryset,
    redirect_after_action,
    staff_required,
)


@staff_required
def homework_score(request, course_slug, homework_slug):
    """Queue homework scoring in the background worker."""
    if request.method != "POST":
        response = redirect("cadmin_course", course_slug=course_slug)
        return response
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    error = homework_score_precheck(homework)
    if error:
        messages.warning(request, error)
    else:
        requested_by = getattr(request.user, "username", "") or ""
        job, created = enqueue_homework_scoring(
            homework, requested_by=requested_by
        )
        if created:
            messages.success(
                request,
                f"Scoring queued for {homework.title} (job #{job.id}). "
                "Refresh to see progress.",
            )
        else:
            messages.success(
                request,
                f"Scoring already in progress for {homework.title} "
                f"(job #{job.id}).",
            )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_extend_deadline(request, course_slug, homework_slug):
    """Push the homework due date forward by a fixed amount."""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    if homework.state != HomeworkState.OPEN.value:
        messages.warning(
            request,
            "Only open homework can have its deadline extended.",
        )
        return redirect_after_action(
            request, "cadmin_course", course_slug=course_slug
        )

    return extend_deadlines(
        request,
        homework,
        ["due_date"],
        f"the deadline for {homework.title}",
        course_slug,
    )


@staff_required
def homework_rescore(request, course_slug, homework_slug):
    """Re-score an already scored homework via the background worker.

    Resets the homework to OPEN so the normal scoring logic applies.
    """
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    if not homework.is_scored():
        messages.warning(
            request,
            f"{homework.title} is not scored yet. "
            "Use Score submissions instead.",
        )
        return redirect_after_action(
            request, "cadmin_course", course_slug=course_slug
        )

    homework.state = HomeworkState.OPEN.value
    homework.save(update_fields=["state"])

    error = homework_score_precheck(homework, force=True)
    if error:
        homework.state = HomeworkState.SCORED.value
        homework.save(update_fields=["state"])
        messages.warning(request, error)
        return redirect_after_action(
            request, "cadmin_course", course_slug=course_slug
        )

    requested_by = getattr(request.user, "username", "") or ""
    job, created = enqueue_homework_scoring(
        homework, requested_by=requested_by, force=True
    )
    if created:
        messages.success(
            request,
            f"Rescoring queued for {homework.title} (job #{job.id}). "
            "Refresh to see progress.",
        )
    else:
        messages.success(
            request,
            f"Rescoring already in progress for {homework.title} "
            f"(job #{job.id}).",
        )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_notify_scores(request, course_slug, homework_slug):
    """Send score notification emails for an already-scored homework"""
    if request.method != "POST":
        response = redirect("cadmin_course", course_slug=course_slug)
        return response
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    if not homework.is_scored():
        messages.warning(
            request,
            f"{homework.title} is not scored yet. "
            "Score it before notifying students.",
        )
        return redirect_after_action(
            request, "cadmin_course", course_slug=course_slug
        )

    is_available, relay_error = check_relay_availability()
    queue_homework_score_notification(homework)
    if is_available:
        messages.success(
            request,
            f"Score notifications for {homework.title} queued. "
            "They will be sent shortly.",
        )
    else:
        messages.warning(
            request,
            f"Score notifications for {homework.title} queued, but Relay is "
            f"currently unavailable ({relay_error}). "
            "Delivery will be retried automatically when Relay recovers.",
        )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_set_correct_answers(request, course_slug, homework_slug):
    """Set correct answers to most popular for a homework"""
    if request.method != "POST":
        response = redirect("cadmin_course", course_slug=course_slug)
        return response
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    fill_correct_answers(homework)

    messages.success(
        request,
        f"Correct answers for {homework.title} set to most popular",
    )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_clear_correct_answers(request, course_slug, homework_slug):
    """Clear correct answers for a homework"""
    if request.method != "POST":
        response = redirect("cadmin_course", course_slug=course_slug)
        return response
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    updated_count = clear_correct_answers(homework)

    messages.success(
        request,
        f"Correct answers for {updated_count} questions in {homework.title} cleared",
    )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_submissions(request, course_slug, homework_slug):
    """View all submissions for a homework"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    raw_search_query = request.GET.get("q", "")
    search_query = raw_search_query.strip()
    submissions = homework_submissions_queryset(homework, search_query)
    submissions_page = paginate_queryset(request, submissions)
    context_data = HomeworkSubmissionsContextData(
        request=request,
        course=course,
        homework=homework,
        submissions_page=submissions_page,
        search_query=search_query,
    )
    context = homework_submissions_context(context_data)
    questions = list(
        Question.objects.filter(homework=homework).order_by("id")
    )
    context["questions"] = questions
    context["score_notification_status"] = (
        get_homework_score_notification_status(homework)
    )
    context["scoring_job"] = scoring_banner(latest_homework_job(homework))
    response = render(request, "cadmin/homework_submissions.html", context)
    return response


@staff_required
def homework_save_answers(request, course_slug, homework_slug):
    """Save correct answers from the submissions page"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    questions = list(
        Question.objects.filter(homework=homework).order_by("id")
    )
    for question in questions:
        field_name = f"correct_answer_{question.id}"
        if question.has_choice_answers():
            indices = request.POST.getlist(field_name)
            correct_answer = ",".join(indices)
        else:
            correct_answer = request.POST.get(field_name, "")
        answer_type = request.POST.get(
            f"answer_type_{question.id}", ""
        )
        question.correct_answer = correct_answer
        question.answer_type = answer_type or None
        question.save(update_fields=["correct_answer", "answer_type"])

    messages.success(
        request,
        f"Correct answers for {homework.title} updated.",
    )
    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_submission_edit(
    request, course_slug, homework_slug, submission_id
):
    """Edit a homework submission"""
    response = homework_submission_edit_response(
        request, course_slug, homework_slug, submission_id
    )
    return response
