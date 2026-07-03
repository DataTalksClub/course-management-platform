from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from course_management.datamailer.sync.score_notifications import (
    send_homework_score_notification,
)
from courses.models.course import Course
from courses.models.homework import Homework
from courses.homework_correct_answers import (
    clear_correct_answers,
    fill_correct_answers,
)
from courses.scoring import HomeworkScoringStatus, score_homework_submissions
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
    """Score a homework"""
    if request.method != "POST":
        response = redirect("cadmin_course", course_slug=course_slug)
        return response
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    status, message = score_homework_submissions(homework.id)

    if status == HomeworkScoringStatus.OK:
        messages.success(request, message)
    else:
        messages.warning(request, message)

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

    send_homework_score_notification(homework)
    messages.success(
        request,
        f"Score notifications for {homework.title} sent to students.",
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
    response = render(request, "cadmin/homework_submissions.html", context)
    return response


@staff_required
def homework_submission_edit(
    request, course_slug, homework_slug, submission_id
):
    """Edit a homework submission"""
    response = homework_submission_edit_response(
        request, course_slug, homework_slug, submission_id
    )
    return response
