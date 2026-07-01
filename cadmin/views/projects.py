from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from course_management.datamailer.sync.peer_review_notifications import (
    send_peer_review_assignment_notification,
)
from course_management.datamailer.sync.score_notifications import (
    send_project_score_notification,
)
from courses.models.course import Course
from courses.models.project import Project
from courses.project_assignment import (
    ProjectActionStatus,
    assign_peer_reviews_for_project,
)
from courses.project_scoring import (
    score_project,
)
from .helpers import (
    redirect_after_action,
    staff_required,
)
from .project_submission_edit import (
    handle_project_submission_edit_post,
    project_submission_edit_objects,
    project_submission_edit_page_data,
    project_submission_edit_response,
)
from .project_submission_list import (
    apply_project_action_flags,
    project_submissions_context,
    project_submissions_page_data,
)


@staff_required
def project_assign_reviews(request, course_slug, project_slug):
    """Assign peer reviews for a project"""
    if request.method != "POST":
        response = redirect("cadmin_course", course_slug=course_slug)
        return response
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    status, message = assign_peer_reviews_for_project(project)

    if status == ProjectActionStatus.OK:
        messages.success(request, message)
        send_peer_review_assignment_notification(project)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def project_score(request, course_slug, project_slug):
    """Score a project"""
    if request.method != "POST":
        response = redirect("cadmin_course", course_slug=course_slug)
        return response
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    status, message = score_project(project)

    if status == ProjectActionStatus.OK:
        messages.success(request, message)
        send_project_score_notification(project)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def project_submissions(request, course_slug, project_slug):
    """View all submissions for a project"""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    apply_project_action_flags(project)
    context_data = project_submissions_page_data(
        request,
        course,
        project,
    )
    context = project_submissions_context(context_data)
    response = render(request, "cadmin/project_submissions.html", context)
    return response


@staff_required
def project_submission_edit(
    request, course_slug, project_slug, submission_id
):
    """Edit a project submission"""
    edit_objects = project_submission_edit_objects(
        course_slug,
        project_slug,
        submission_id,
    )
    edit_data = project_submission_edit_page_data(request, edit_objects)

    if request.method == "POST":
        response = handle_project_submission_edit_post(edit_data)
        if response is not None:
            return response

    return project_submission_edit_response(edit_data)
