from typing import Any, List, Optional
from urllib.parse import urljoin, urlparse

from django.core.exceptions import ValidationError
from django.urls import reverse

from courses.views.homework_answers import format_submitted_value


def format_submission_lines(items: List[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        line = f"{item['label']}: {format_submitted_value(item['value'])}"
        lines.append(line)
    return "\n".join(lines)


def format_answer_lines(answers: List[dict[str, Any]]) -> str:
    lines = []
    for answer in answers:
        line = (
            f"{answer['question']}: "
            f"{format_submitted_value(answer['answer'])}"
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


def tryparsefloat(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def parse_time_spent_hours(
    value: Optional[str],
    field_label: str,
) -> Optional[float]:
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    parsed = tryparsefloat(value.replace(",", "."))
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
        return urljoin(f"{base_url}/", path.lstrip("/"))
    return path
