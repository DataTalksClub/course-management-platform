from dataclasses import dataclass
from functools import partial

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from api.safety import error_response, require_staff_token
from api.utils import parse_json_body, require_methods
from course_management.observability import record_event
from course_management.datamailer.sync.memberships import (
    sync_project_passed_outcome_to_datamailer,
    sync_project_submission_to_datamailer,
)
from courses.models import (
    Course,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectSubmission,
    ProjectState,
    ReviewCriteria,
    ReviewCriteriaTypes,
    SystemEvaluationCriteriaResponse,
    SystemProjectEvaluation,
)
from courses.leaderboard import update_leaderboard
from courses.system_project_evaluations import (
    rescore_submission_with_system_evaluations,
)


@dataclass(frozen=True)
class ValidatedSystemEvaluation:
    idempotency_key: str
    feedback: str
    responses: list[tuple[ReviewCriteria, str]]


def _criteria_to_dict(criteria):
    return {
        "id": criteria.id,
        "description": criteria.description,
        "type": criteria.review_criteria_type,
        "options": criteria.options,
    }


def _response_to_dict(response):
    return {
        "criteria_id": response.criteria_id,
        "answer": response.answer,
        "score": response.get_score(),
    }


def _evaluation_to_dict(evaluation):
    criteria_responses = evaluation.criteria_responses.select_related(
        "criteria"
    ).order_by("criteria_id")
    return {
        "id": evaluation.id,
        "submission_id": evaluation.submission_id,
        "idempotency_key": evaluation.idempotency_key,
        "feedback": evaluation.feedback,
        "created_by_user_id": evaluation.created_by_id,
        "created_at": evaluation.created_at.isoformat(),
        "criteria_responses": [
            _response_to_dict(response) for response in criteria_responses
        ],
    }


def _peer_evaluation_to_dict(evaluation):
    criteria_responses = evaluation.criteria_responses.select_related(
        "criteria"
    ).order_by("criteria_id")
    submitted_at = None
    if evaluation.submitted_at is not None:
        submitted_at = evaluation.submitted_at.isoformat()
    return {
        "id": evaluation.id,
        "feedback": evaluation.note_to_peer,
        "submitted_at": submitted_at,
        "criteria_responses": [
            _response_to_dict(response) for response in criteria_responses
        ],
    }


def _submission_to_dict(submission):
    return {
        "id": submission.id,
        "student_id": submission.student_id,
        "student_email": submission.student.email,
        "github_link": submission.github_link,
        "commit_id": submission.commit_id,
        "project_score": submission.project_score,
        "total_score": submission.total_score,
        "passed": submission.passed,
    }


def _evaluation_page_payload(submission, criteria):
    peer_evaluations = PeerReview.objects.filter(
        submission_under_evaluation=submission,
        state=PeerReviewState.SUBMITTED.value,
    ).prefetch_related("criteria_responses__criteria").order_by(
        "submitted_at",
        "id",
    )
    evaluations = submission.system_evaluations.prefetch_related(
        "criteria_responses__criteria"
    ).order_by("created_at", "id")
    return {
        "submission": _submission_to_dict(submission),
        "criteria": [_criteria_to_dict(item) for item in criteria],
        "peer_evaluations": [
            _peer_evaluation_to_dict(evaluation)
            for evaluation in peer_evaluations
        ],
        "system_evaluations": [
            _evaluation_to_dict(evaluation) for evaluation in evaluations
        ],
    }


def _required_string(data, field, max_length=None):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        return None, error_response(
            f"{field} is required",
            "required_field",
            details={"field": field},
        )
    value = value.strip()
    if max_length is not None and len(value) > max_length:
        return None, error_response(
            f"{field} is too long",
            "invalid_field",
            details={"field": field, "max_length": max_length},
        )
    return value, None


def _answer_indexes(answer, criteria):
    if not isinstance(answer, str) or not answer.strip():
        return None
    values = [value.strip() for value in answer.split(",")]
    if any(not value.isdigit() for value in values):
        return None
    indexes = [int(value) for value in values]
    if len(indexes) != len(set(indexes)):
        return None
    if any(index < 1 or index > len(criteria.options) for index in indexes):
        return None
    if (
        criteria.review_criteria_type
        == ReviewCriteriaTypes.RADIO_BUTTONS.value
        and len(indexes) != 1
    ):
        return None
    return indexes


def _validate_criteria_responses(data, criteria):
    raw_responses = data.get("criteria_responses")
    if not isinstance(raw_responses, list):
        return None, error_response(
            "criteria_responses must be a list",
            "invalid_criteria_responses",
        )

    criteria_by_id = {item.id: item for item in criteria}
    responses_by_id = {}
    for raw_response in raw_responses:
        if not isinstance(raw_response, dict):
            return None, error_response(
                "Each criteria response must be an object",
                "invalid_criteria_response",
            )
        if set(raw_response) != {"criteria_id", "answer"}:
            return None, error_response(
                "Each criteria response requires criteria_id and answer",
                "invalid_criteria_response",
            )
        criteria_id = raw_response["criteria_id"]
        criterion = criteria_by_id.get(criteria_id)
        if criterion is None or criteria_id in responses_by_id:
            return None, error_response(
                "Criteria response is unknown or duplicated",
                "invalid_criteria_response",
                details={"criteria_id": criteria_id},
            )
        indexes = _answer_indexes(raw_response["answer"], criterion)
        if indexes is None:
            return None, error_response(
                "Criteria answer is invalid",
                "invalid_criteria_answer",
                details={"criteria_id": criteria_id},
            )
        answer = ",".join(str(index) for index in indexes)
        responses_by_id[criteria_id] = (criterion, answer)

    if set(responses_by_id) != set(criteria_by_id):
        missing_ids = sorted(set(criteria_by_id) - set(responses_by_id))
        return None, error_response(
            "A system evaluation must answer every review criterion",
            "incomplete_evaluation",
            details={"missing_criteria_ids": missing_ids},
        )
    responses = [responses_by_id[item.id] for item in criteria]
    return responses, None


def _validate_payload(data, criteria):
    if not isinstance(data, dict):
        return None, error_response(
            "JSON body must be an object",
            "invalid_request",
        )
    allowed_fields = {
        "idempotency_key",
        "feedback",
        "criteria_responses",
    }
    unknown_fields = sorted(set(data) - allowed_fields)
    if unknown_fields:
        return None, error_response(
            "Request contains unknown fields",
            "invalid_field",
            details={"fields": unknown_fields},
        )
    idempotency_key, error = _required_string(
        data,
        "idempotency_key",
        max_length=200,
    )
    if error:
        return None, error
    feedback, error = _required_string(data, "feedback")
    if error:
        return None, error
    responses, error = _validate_criteria_responses(data, criteria)
    if error:
        return None, error
    validated = ValidatedSystemEvaluation(
        idempotency_key=idempotency_key,
        feedback=feedback,
        responses=responses,
    )
    return validated, None


def _evaluation_matches(evaluation, validated):
    if evaluation.feedback != validated.feedback:
        return False
    existing = {
        response.criteria_id: response.answer
        for response in evaluation.criteria_responses.all()
    }
    expected = {
        criteria.id: answer for criteria, answer in validated.responses
    }
    return existing == expected


def _create_evaluation(request, submission, validated):
    with transaction.atomic():
        submission = ProjectSubmission.objects.select_for_update().get(
            id=submission.id
        )
        existing = SystemProjectEvaluation.objects.filter(
            submission=submission,
            idempotency_key=validated.idempotency_key,
        ).first()
        if existing is not None:
            if not _evaluation_matches(existing, validated):
                return None, error_response(
                    "Idempotency key was already used for another payload",
                    "idempotency_conflict",
                    status=409,
                )
            return JsonResponse(_evaluation_to_dict(existing)), None

        evaluation = SystemProjectEvaluation.objects.create(
            submission=submission,
            created_by=request.user,
            idempotency_key=validated.idempotency_key,
            feedback=validated.feedback,
        )
        responses = [
            SystemEvaluationCriteriaResponse(
                evaluation=evaluation,
                criteria=criteria,
                answer=answer,
            )
            for criteria, answer in validated.responses
        ]
        SystemEvaluationCriteriaResponse.objects.bulk_create(responses)
        rescore_submission_with_system_evaluations(submission)
        if submission.project.state == ProjectState.COMPLETED.value:
            transaction.on_commit(
                partial(update_leaderboard, submission.project.course)
            )
            transaction.on_commit(
                partial(sync_project_submission_to_datamailer, submission)
            )
            transaction.on_commit(
                partial(
                    sync_project_passed_outcome_to_datamailer,
                    submission,
                )
            )

    record_event(
        "project.system_evaluation_created",
        request=request,
        properties={
            "course_slug": submission.project.course.slug,
            "project_slug": submission.project.slug,
            "project_id": submission.project_id,
            "submission_id": submission.id,
            "evaluation_id": evaluation.id,
            "criteria_count": len(responses),
        },
    )
    return JsonResponse(_evaluation_to_dict(evaluation), status=201), None


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def project_system_evaluations_view(
    request,
    course_slug,
    project_slug,
    submission_id,
):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project,
        course=course,
        slug=project_slug,
    )
    submission = get_object_or_404(
        ProjectSubmission.objects.select_related("student"),
        id=submission_id,
        project=project,
        volunteer_review_only=False,
    )
    criteria = list(
        ReviewCriteria.objects.filter(course=course).order_by("id")
    )

    if request.method == "GET":
        return JsonResponse(_evaluation_page_payload(submission, criteria))

    data, error = parse_json_body(request)
    if error:
        return error
    validated, error = _validate_payload(data, criteria)
    if error:
        return error
    response, error = _create_evaluation(request, submission, validated)
    if error:
        return error
    return response
