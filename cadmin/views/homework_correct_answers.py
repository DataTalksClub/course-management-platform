"""Autosave endpoints for the "Correct answers" panel on homework submissions.

Every checkbox click or free-text change on the panel is saved immediately
through ``homework_question_save_answer``. Failures are never silent: the
server logs them at ERROR (forwarded to VictoriaLogs on Contabo) and records
an observability event, and the browser reports failures the server could not
see itself (timeouts, network errors) through
``homework_correct_answers_client_error``.
"""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from course_management.observability import record_event
from courses.models.course import Course
from courses.models.homework import Homework, Question
from cadmin.correct_answers import (
    CorrectAnswerError,
    save_question_correct_answer,
)
from .helpers import staff_required


logger = logging.getLogger("cadmin.correct_answers")

SAVE_FAILED_EVENT = "cadmin.correct_answer_save_failed"
CLIENT_FAILURE_EVENT = "cadmin.correct_answer_autosave_client_failure"
MAX_CLIENT_TEXT = 300

_UNSET = object()


def _parse_json_body(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise CorrectAnswerError("Request body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise CorrectAnswerError("Request body must be a JSON object")
    return payload


def _log_save_failure(request, homework, question_id, reason):
    properties = {
        "course_slug": homework.course.slug,
        "homework_slug": homework.slug,
        "question_id": question_id,
        "reason": reason[:MAX_CLIENT_TEXT],
    }
    logger.error(
        "correct_answer_save_failed course=%s homework=%s question=%s "
        "reason=%s",
        homework.course.slug,
        homework.slug,
        question_id,
        properties["reason"],
        extra={"event": SAVE_FAILED_EVENT, **properties},
    )
    record_event(SAVE_FAILED_EVENT, request=request, properties=properties)


def _error_response(message, status):
    return JsonResponse({"ok": False, "error": message}, status=status)


@staff_required
@require_POST
def homework_question_save_answer(
    request, course_slug, homework_slug, question_id
):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(Homework, course=course, slug=homework_slug)
    question = get_object_or_404(Question, homework=homework, id=question_id)

    try:
        payload = _parse_json_body(request)
        answer_type = payload.get("answer_type", _UNSET)
        if answer_type is _UNSET:
            save_question_correct_answer(
                question, payload.get("correct_answer")
            )
        else:
            save_question_correct_answer(
                question, payload.get("correct_answer"), answer_type
            )
    except CorrectAnswerError as exc:
        _log_save_failure(request, homework, question.id, str(exc))
        return _error_response(str(exc), status=400)
    except Exception:
        logger.exception(
            "correct_answer_save_failed course=%s homework=%s question=%s "
            "reason=unexpected",
            course.slug,
            homework.slug,
            question.id,
            extra={"event": SAVE_FAILED_EVENT},
        )
        record_event(
            SAVE_FAILED_EVENT,
            request=request,
            properties={
                "course_slug": course.slug,
                "homework_slug": homework.slug,
                "question_id": question.id,
                "reason": "unexpected",
            },
        )
        return _error_response("Server error while saving", status=500)

    logger.info(
        "correct_answer_saved course=%s homework=%s question=%s",
        course.slug,
        homework.slug,
        question.id,
    )
    return JsonResponse(
        {
            "ok": True,
            "question_id": question.id,
            "correct_answer": question.correct_answer or "",
            "answer_type": question.answer_type or "",
        }
    )


def _clip(value):
    return str(value)[:MAX_CLIENT_TEXT]


@staff_required
@require_POST
def homework_correct_answers_client_error(request, course_slug, homework_slug):
    """Record an autosave failure observed in the browser (timeout/network)."""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(Homework, course=course, slug=homework_slug)
    try:
        payload = _parse_json_body(request)
    except CorrectAnswerError:
        payload = {}

    properties = {
        "course_slug": course.slug,
        "homework_slug": homework.slug,
        "question_id": _clip(payload.get("question_id", "")),
        "reason": _clip(payload.get("reason", "unknown")),
        "detail": _clip(payload.get("detail", "")),
    }
    logger.error(
        "correct_answer_autosave_client_failure course=%s homework=%s "
        "question=%s reason=%s detail=%s",
        properties["course_slug"],
        properties["homework_slug"],
        properties["question_id"],
        properties["reason"],
        properties["detail"],
        extra={"event": CLIENT_FAILURE_EVENT, **properties},
    )
    record_event(CLIENT_FAILURE_EVENT, request=request, properties=properties)
    return JsonResponse({"ok": True})
