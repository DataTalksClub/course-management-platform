from django.http import JsonResponse
from django.utils.text import slugify

from courses.models.homework import Homework, Question
from courses.models.homework import HomeworkState

from api.crud import bulk_create_response
from api.safety import require_staff_token
from api.utils import instructions_url_error, parse_date, parse_json_body
from api.views.homework_serializers import homework_to_dict


def create_questions(homework, questions_data):
    for question_data in questions_data:
        create_question(homework, question_data)


def homework_create_instructions_url(homework_data):
    instructions_url = homework_data.get("instructions_url")
    if not instructions_url:
        return instructions_url, None

    error = instructions_url_error(instructions_url)
    if error:
        return None, error

    return instructions_url, None


def homework_create_due_date(due_date_str):
    due_date = parse_date(due_date_str)
    if due_date is None:
        return None, f"Invalid date format: {due_date_str}"

    return due_date, None


def homework_create_slug(course, homework_data, name):
    slug = homework_data.get("slug") or slugify(name)
    matching_homework = Homework.objects.filter(course=course, slug=slug)
    slug_exists = matching_homework.exists()
    if slug_exists:
        return None, f"Homework with slug '{slug}' already exists"

    return slug, None


def homework_create_attrs(course, homework_data):
    name = homework_data.get("name")
    due_date_str = homework_data.get("due_date")
    if not name or not due_date_str:
        return None, "name and due_date are required"

    instructions_url, error = homework_create_instructions_url(
        homework_data
    )
    if error:
        return None, error

    due_date, error = homework_create_due_date(due_date_str)
    if error:
        return None, error

    slug, error = homework_create_slug(course, homework_data, name)
    if error:
        return None, error

    attrs = {
        "title": name,
        "description": homework_data.get("description", ""),
        "instructions_url": instructions_url,
        "due_date": due_date,
        "state": HomeworkState.CLOSED.value,
        "slug": slug,
    }
    return attrs, None


def create_homework(course, homework_data):
    attrs, error = homework_create_attrs(course, homework_data)
    if error:
        return None, error

    homework = Homework.objects.create(
        course=course,
        **attrs,
    )

    questions_data = homework_data.get("questions", [])
    create_questions(homework, questions_data)

    return homework_to_dict(homework), None


def create_question(homework, question_data):
    text = question_data.get("text", "")
    question_type = question_data.get("question_type", "FF")
    answer_type = question_data.get("answer_type")
    possible_answers_data = question_data.get("possible_answers", [])
    possible_answers = "\n".join(possible_answers_data)
    correct_answer = question_data.get("correct_answer", "")
    score = question_data.get("scores_for_correct_answer", 1)

    Question.objects.create(
        homework=homework,
        text=text,
        question_type=question_type,
        answer_type=answer_type,
        possible_answers=possible_answers,
        correct_answer=correct_answer,
        scores_for_correct_answer=score,
    )


def homeworks_list_response(course):
    homeworks = Homework.objects.filter(course=course).order_by("id")
    homework_records = []
    for homework in homeworks:
        homework_record = homework_to_dict(homework)
        homework_records.append(homework_record)

    payload = {
        "homeworks": homework_records,
    }
    response = JsonResponse(payload)
    return response


def homeworks_create_response(request, course):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = parse_json_body(request)
    if err:
        return err

    response = bulk_create_response(
        data,
        create_homework,
        course,
    )
    return response
