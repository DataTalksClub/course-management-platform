"""
Homework-related data API views.

Provides views for retrieving homework submission data and managing homework questions.
"""

import json

from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.forms.models import model_to_dict
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required

from courses.models import (
    User,
    Course,
    Homework,
    Question,
    Answer,
)
from courses.models.homework import HomeworkState


@token_required
def homework_data_view(request, course_slug: str, homework_slug: str):
    """Get homework data including course info, homework details, and all submissions with answers."""
    course = get_object_or_404(Course, slug=course_slug)

    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    answers_prefetch = Prefetch(
        "answer_set", queryset=Answer.objects.all()
    )
    submissions = homework.submission_set.prefetch_related(
        answers_prefetch
    ).all()

    course_data = model_to_dict(
        course, exclude=["students", "first_homework_scored"]
    )

    submission_data = []
    for submission in submissions:
        submission_dict = {
            "student_id": submission.student_id,
            "homework_link": submission.homework_link,
            "learning_in_public_links": submission.learning_in_public_links,
            "time_spent_lectures": submission.time_spent_lectures,
            "time_spent_homework": submission.time_spent_homework,
            "problems_comments": submission.problems_comments,
            "faq_contribution": submission.faq_contribution,
            "questions_score": submission.questions_score,
            "faq_score": submission.faq_score,
            "learning_in_public_score": submission.learning_in_public_score,
            "total_score": submission.total_score,
            "answers": list(
                submission.answer_set.values(
                    "question_id", "answer_text", "is_correct"
                )
            ),
        }
        submission_data.append(submission_dict)

    result = {
        "course": course_data,
        "homework": model_to_dict(homework),
        "submissions": submission_data,
    }

    return JsonResponse(result)


@token_required
@csrf_exempt
def homework_content_view(request, course_slug: str, homework_slug: str):
    """
    Get or create questions for a homework.

    GET: Returns homework details and all questions.
    POST: Creates questions for the homework and optionally updates state.

    POST Expected JSON payload:
    {
        "questions": [
            {
                "text": "What is 2+2?",
                "question_type": "MC",
                "answer_type": "INT",
                "possible_answers": ["3", "4", "5"],
                "correct_answer": "2",
                "scores_for_correct_answer": 1
            }
        ],
        "state": "OP"  // Optional: Update homework state (CL=closed, OP=open, SC=scored)
    }
    """
    try:
        course = get_object_or_404(Course, slug=course_slug)
        homework = get_object_or_404(Homework, course=course, slug=homework_slug)

        # GET: Return homework details and questions
        if request.method == "GET":
            questions = Question.objects.filter(homework=homework).order_by('id')

            questions_data = []
            for q in questions:
                questions_data.append({
                    "id": q.id,
                    "text": q.text,
                    "question_type": q.question_type,
                    "answer_type": q.answer_type,
                    "possible_answers": q.get_possible_answers(),
                    "correct_answer": q.correct_answer,
                    "scores_for_correct_answer": q.scores_for_correct_answer,
                })

            return JsonResponse({
                "success": True,
                "course": course_slug,
                "homework": {
                    "id": homework.id,
                    "slug": homework.slug,
                    "title": homework.title,
                    "description": homework.description,
                    "due_date": homework.due_date.isoformat(),
                    "state": homework.state,
                    "learning_in_public_cap": homework.learning_in_public_cap,
                    "homework_url_field": homework.homework_url_field,
                    "time_spent_lectures_field": homework.time_spent_lectures_field,
                    "time_spent_homework_field": homework.time_spent_homework_field,
                    "faq_contribution_field": homework.faq_contribution_field,
                },
                "questions": questions_data,
            })

        # POST: Create new questions and optionally update state
        if request.method != "POST":
            return JsonResponse({"error": "Method not allowed"}, status=405)

        data = json.loads(request.body)

        # Update homework state if provided
        state_updated = False
        new_state = data.get("state")
        if new_state:
            valid_states = [s.value for s in HomeworkState]
            if new_state not in valid_states:
                return JsonResponse({
                    "error": f"Invalid state. Must be one of: {valid_states}"
                }, status=400)
            old_state = homework.state
            homework.state = new_state
            homework.save()
            state_updated = True

        questions_data = data.get("questions", [])
        created_questions = []
        errors = []

        for q_data in questions_data:
            try:
                question = Question.objects.create(
                    homework=homework,
                    text=q_data.get("text", ""),
                    question_type=q_data.get("question_type", "FF"),
                    answer_type=q_data.get("answer_type"),
                    possible_answers="\n".join(q_data.get("possible_answers", [])),
                    correct_answer=q_data.get("correct_answer", ""),
                    scores_for_correct_answer=q_data.get("scores_for_correct_answer", 1),
                )
                created_questions.append({
                    "id": question.id,
                    "text": question.text,
                    "question_type": question.question_type,
                })
            except Exception as e:
                errors.append({
                    "question": q_data.get("text", "unknown"),
                    "error": str(e)
                })

        response_data = {
            "success": True,
            "course": course_slug,
            "homework": homework_slug,
            "created_questions": created_questions,
            "errors": errors,
        }

        if state_updated:
            response_data["homework_state"] = {
                "old": old_state,
                "new": new_state
            }

        return JsonResponse(response_data)

    except Http404:
        return JsonResponse({"error": "Course or homework not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
