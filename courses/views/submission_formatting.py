from typing import Any
from urllib.parse import urljoin, urlparse

from django.core.exceptions import ValidationError
from django.urls import reverse

from courses.views.homework_answer_formatting import format_submitted_value


def format_submission_lines(items: list[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        submitted_value = format_submitted_value(item["value"])
        line = f"{item['label']}: {submitted_value}"
        lines.append(line)
    return "\n".join(lines)


def format_answer_lines(answers: list[dict[str, Any]]) -> str:
    lines = []
    for answer in answers:
        submitted_answer = format_submitted_value(answer["answer"])
        line = (
            f"{answer['question']}: "
            f"{submitted_answer}"
        )
        lines.append(line)
    return "\n".join(lines)


def submission_summary_text(
    submitted_fields_text: str,
    submitted_answers_text: str,
) -> str:
    summary_sections = []
    if submitted_fields_text:
        summary_sections.append(submitted_fields_text)
    if submitted_answers_text:
        summary_sections.append(submitted_answers_text)
    return "\n\n".join(summary_sections)


def tryparsefloat(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def parse_time_spent_hours(
    value: str | None,
    field_label: str,
) -> float | None:
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    normalized_value = value.replace(",", ".")
    parsed = tryparsefloat(normalized_value)
    if parsed is None:
        raise ValidationError(
            f"Please enter a valid number of hours for {field_label} "
            "(for example, 2 or 2.5)."
        )
    return parsed


def request_base_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def build_account_settings_url(base_url: str) -> str:
    path = reverse("account_settings")
    if base_url:
        base_url_with_slash = f"{base_url}/"
        normalized_path = path.lstrip("/")
        return urljoin(base_url_with_slash, normalized_path)
    return path
