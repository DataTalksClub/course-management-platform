from dataclasses import dataclass
from datetime import date

from django.http import JsonResponse
from django.utils.text import slugify

from courses.models import Homework, Question
from courses.models.homework import HomeworkState

from api.crud import bulk_create_response
from api.safety import require_staff_token
from api.utils import instructions_url_error, parse_date, parse_json_body
from api.views.homework_serializers import homework_to_dict


@dataclass(frozen=True)
class HomeworkCreateRequiredValues:
    name: str
    due_date_str: str


@dataclass(frozen=True)
class HomeworkCreateValues:
    name: str
    due_date: date
    instructions_url: str | None


@dataclass
class HomeworkCreateData:
    course: object
    homework_data: dict
    required_values: HomeworkCreateRequiredValues | None = None
    instructions_url: str | None = None
    due_date: date | None = None
    slug: str | None = None


def homework_create_defaults(homework_data, values):
    return {
        "title": values.name,
        "description": homework_data.get("description", ""),
        "instructions_url": values.instructions_url,
        "due_date": values.due_date,
        "state": HomeworkState.CLOSED.value,
    }


def create_questions(homework, questions_data):
    for question_data in questions_data:
        create_question(homework, question_data)


def homework_create_required_values(homework_data):
    name = homework_data.get("name")
    due_date_str = homework_data.get("due_date")

    if not name or not due_date_str:
        return None, "name and due_date are required"

    values = HomeworkCreateRequiredValues(name, due_date_str)
    return values, None


def homework_create_instructions_url(homework_data):
    instructions_url = homework_data.get("instructions_url")
    if instructions_url and (
        error := instructions_url_error(instructions_url)
    ):
        return None, error

    return instructions_url, None


def homework_create_due_date(due_date_str):
    due_date = parse_date(due_date_str)
    if due_date is None:
        return None, f"Invalid date format: {due_date_str}"

    return due_date, None


def homework_create_slug(course, homework_data, name):
    slug = homework_data.get("slug") or slugify(name)
    if Homework.objects.filter(course=course, slug=slug).exists():
        return None, f"Homework with slug '{slug}' already exists"

    return slug, None


def load_homework_create_required_values(create_data):
    required_values, error = homework_create_required_values(
        create_data.homework_data
    )
    if error:
        return error
    create_data.required_values = required_values
    return None


def load_homework_create_instructions_url(create_data):
    instructions_url, error = homework_create_instructions_url(
        create_data.homework_data
    )
    if error:
        return error
    create_data.instructions_url = instructions_url
    return None


def load_homework_create_due_date(create_data):
    required_values = create_data.required_values
    if required_values is None:
        return "name and due_date are required"
    due_date, error = homework_create_due_date(
        required_values.due_date_str
    )
    if error:
        return error
    create_data.due_date = due_date
    return None


def load_homework_create_slug(create_data):
    required_values = create_data.required_values
    if required_values is None:
        return "name and due_date are required"
    slug, error = homework_create_slug(
        create_data.course,
        create_data.homework_data,
        required_values.name,
    )
    if error:
        return error
    create_data.slug = slug
    return None


def homework_create_data(course, homework_data):
    create_data = HomeworkCreateData(
        course=course,
        homework_data=homework_data,
    )
    steps = (
        load_homework_create_required_values,
        load_homework_create_instructions_url,
        load_homework_create_due_date,
        load_homework_create_slug,
    )
    for step in steps:
        error = step(create_data)
        if error:
            return None, error

    return create_data, None


def homework_create_values(create_data):
    required_values = create_data.required_values
    if required_values is None:
        return None
    due_date = create_data.due_date
    if due_date is None:
        return None
    values = HomeworkCreateValues(
        name=required_values.name,
        due_date=due_date,
        instructions_url=create_data.instructions_url,
    )
    return values


def homework_create_attrs(course, homework_data):
    create_data, error = homework_create_data(course, homework_data)
    if error:
        return None, error

    values = homework_create_values(create_data)
    if values is None:
        return None, "name and due_date are required"

    attrs = homework_create_defaults(homework_data, values)
    attrs["slug"] = create_data.slug
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

    return bulk_create_response(
        data,
        lambda item: create_homework(course, item),
    )
