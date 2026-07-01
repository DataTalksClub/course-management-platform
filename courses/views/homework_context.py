from dataclasses import dataclass

from django.shortcuts import get_object_or_404

from courses.models.course import Course, Enrollment, User
from courses.models.homework import (
    Answer,
    Homework,
    HomeworkState,
    Question,
    Submission,
)
from courses.views.homework_answers import process_question_options
from courses.views.homework_post_preview import homework_state_context


@dataclass(frozen=True)
class HomeworkDetailContextData:
    course: Course
    homework: Homework
    questions: list[Question]
    submission: Submission | None
    enrollment: Enrollment | None


@dataclass(frozen=True)
class HomeworkDetailObjects:
    course: Course
    homework: Homework
    questions: list[Question]


@dataclass(frozen=True)
class AuthenticatedHomeworkContext:
    context: dict
    submission: Submission | None
    enrollment: Enrollment


def homework_detail_build_context_not_authenticated(
    course: Course,
    homework: Homework,
    questions: list[Question],
) -> dict:
    question_answers = question_answers_for_submission(
        homework,
        questions,
        None,
    )
    accepting_submissions = homework.state == HomeworkState.OPEN.value
    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "is_authenticated": False,
        "disabled": True,
        "accepting_submissions": accepting_submissions,
    }

    return context


def submission_answer_map(
    submission: Submission | None,
) -> dict[int, Answer]:
    if not submission:
        return {}

    answers = Answer.objects.filter(
        submission=submission
    ).select_related("question")
    answer_map = {}
    for answer in answers:
        answer_map[answer.question.id] = answer
    return answer_map


def question_answers_for_submission(
    homework: Homework,
    questions: list[Question],
    submission: Submission | None,
) -> list[tuple[Question, dict]]:
    question_answers_map = submission_answer_map(submission)
    question_answers = []

    for question in questions:
        answer = question_answers_map.get(question.id)
        processed_answer = process_question_options(
            homework,
            question,
            answer,
        )
        question_answer = (question, processed_answer)
        question_answers.append(question_answer)

    return question_answers


def learning_in_public_disabled(
    enrollment: Enrollment | None,
) -> bool:
    if enrollment is None:
        return False
    return enrollment.disable_learning_in_public


def homework_detail_build_context_authenticated(data) -> dict:
    question_answers = question_answers_for_submission(
        data.homework,
        data.questions,
        data.submission,
    )
    disable_learning_in_public = learning_in_public_disabled(
        data.enrollment
    )
    state_context = homework_state_context(data.homework)
    context = {
        "course": data.course,
        "homework": data.homework,
        "question_answers": question_answers,
        "submission": data.submission,
        "is_authenticated": True,
        "disable_learning_in_public": disable_learning_in_public,
    }
    context.update(state_context)
    return context


def homework_detail_objects(course_slug: str, homework_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework,
        course=course,
        slug=homework_slug,
    )
    questions = Question.objects.filter(homework=homework).order_by(
        "id"
    )
    return HomeworkDetailObjects(
        course=course,
        homework=homework,
        questions=questions,
    )


def authenticated_homework_context(
    user: User,
    course: Course,
    homework: Homework,
    questions: list[Question],
):
    submission = Submission.objects.filter(
        homework=homework,
        student=user,
    ).first()
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    context_data = HomeworkDetailContextData(
        course=course,
        homework=homework,
        questions=questions,
        submission=submission,
        enrollment=enrollment,
    )
    context = homework_detail_build_context_authenticated(context_data)
    return AuthenticatedHomeworkContext(
        context=context,
        submission=submission,
        enrollment=enrollment,
    )
