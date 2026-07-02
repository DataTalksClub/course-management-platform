from dataclasses import dataclass

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from courses.models.course import Course
from courses.models.project import (
    Project,
    ProjectEvaluationScore,
    ProjectSubmission,
    ReviewCriteria,
)
from cadmin.forms import ProjectSubmissionEditForm
from cadmin.services import update_project_submission_from_admin

from .helpers import first_form_error


@dataclass(frozen=True)
class ProjectSubmissionEditPageData:
    request: object
    course: Course
    project: Project
    submission: ProjectSubmission
    review_criteria: list
    criteria_with_scores: list


@dataclass(frozen=True)
class ProjectSubmissionEditObjects:
    course: Course
    project: Project
    submission: ProjectSubmission


def project_submission_edit_objects(
    course_slug,
    project_slug,
    submission_id,
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    submission = get_object_or_404(
        ProjectSubmission, id=submission_id, project=project
    )
    return ProjectSubmissionEditObjects(
        course=course,
        project=project,
        submission=submission,
    )


def project_evaluation_score_map(submission):
    scores = ProjectEvaluationScore.objects.filter(submission=submission)
    score_map = {}
    for score in scores:
        score_map[score.review_criteria_id] = score
    return score_map


def criteria_with_project_scores(review_criteria, submission):
    evaluation_scores = project_evaluation_score_map(submission)
    criteria_scores = []
    for criteria in review_criteria:
        evaluation_score = evaluation_scores.get(criteria.id)
        score = 0
        score_id = None
        if evaluation_score is not None:
            score = evaluation_score.score
            score_id = evaluation_score.id
        record = {
            "criteria": criteria,
            "score": score,
            "score_id": score_id,
        }
        criteria_scores.append(record)
    return criteria_scores


def handle_project_submission_edit_post(data):
    form = ProjectSubmissionEditForm(
        data.request.POST,
        review_criteria=data.review_criteria,
    )
    if not form.is_valid():
        error = first_form_error(form)
        messages.error(
            data.request,
            f"Error updating submission: {error}",
        )
        return None

    update_project_submission_from_admin(
        data.submission,
        form.cleaned_data,
    )
    messages.success(
        data.request,
        f"Project submission for {data.submission.student.username} updated successfully",
    )
    response = redirect(
        "cadmin_project_submissions",
        course_slug=data.course.slug,
        project_slug=data.project.slug,
    )
    return response


def project_submission_edit_page_data(request, edit_objects):
    criteria = ReviewCriteria.objects.filter(course=edit_objects.course)
    review_criteria = criteria.order_by("id")
    criteria_with_scores = criteria_with_project_scores(
        review_criteria,
        edit_objects.submission,
    )
    return ProjectSubmissionEditPageData(
        request=request,
        course=edit_objects.course,
        project=edit_objects.project,
        submission=edit_objects.submission,
        review_criteria=review_criteria,
        criteria_with_scores=criteria_with_scores,
    )
