from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from course_management.datamailer.client import DatamailerConfig
from courses.models import Course


@dataclass(frozen=True)
class ReminderEvent:
    key: str
    list_key: str
    list_name: str
    list_metadata: dict[str, Any]
    send_payload: dict[str, Any]
    members: list[dict[str, Any]]


@dataclass(frozen=True)
class ReminderSpec:
    deadline_kind: str
    event_kind: str
    list_kind: str
    item_type: str
    route_name: str
    route_slug_kwarg: str
    metadata_slug_key: str
    metadata_id_key: str
    list_name_suffix: str


@dataclass(frozen=True)
class ReminderWindow:
    key: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ReminderItemData:
    course: Course
    item_slug: str
    item_id: int
    item_title: str
    reminder_key: str
    deadline: datetime
    context_extra: Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class ReminderTemplateContextData:
    spec: ReminderSpec
    item: ReminderItemData
    action_url: str


@dataclass(frozen=True)
class ReminderEventData:
    config: DatamailerConfig
    spec: ReminderSpec
    item: ReminderItemData
    members: list[dict[str, Any]]
    metadata: dict[str, Any]
