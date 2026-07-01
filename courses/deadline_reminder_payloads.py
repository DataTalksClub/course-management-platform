from django.urls import reverse

from course_management import email_templates
from course_management.datamailer.client import public_url
from accounts.services.timezones import format_deadline_for_user
from courses.deadline_reminder_types import (
    ReminderEvent,
    ReminderTemplateContextData,
)


def deadline_send_payload(
    config,
    *,
    event_key,
    template_context,
    metadata,
):
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.DEADLINE_REMINDER,
        "category_tag": "deadline-reminders",
        "idempotency_key": event_key,
        "context": template_context,
        "metadata": metadata
        | {
            "source": "course-management-platform",
            "event": "deadline_reminder",
        },
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return payload


def transient_recipient_list_send_payload(event):
    return event.send_payload | {
        "list": {
            "key": event.list_key,
            "name": event.list_name,
            "metadata": event.list_metadata,
        },
        "members": event.members,
    }


def base_context(data):
    formatted_deadline = format_deadline_for_user(data.item.deadline)
    deadline_summary = formatted_deadline["deadline_summary"]
    profile_path = reverse("account_settings")
    profile_url = public_url(profile_path)

    return {
        "course_slug": data.item.course.slug,
        "course_title": data.item.course.title,
        "reminder_key": data.item.reminder_key,
        "item_type": data.spec.item_type,
        "item_slug": data.item.item_slug,
        "item_title": data.item.item_title,
        "deadline_at": deadline_summary,
        "deadline_iso": data.item.deadline.isoformat(),
        "action_url": data.action_url,
        "profile_url": profile_url,
        "notification_category": "deadline reminders",
        "notification_footer": (
            "You are receiving this because deadline reminders are "
            "enabled in your profile."
        ),
    }


def reminder_metadata(spec, item):
    return {
        "course_slug": item.course.slug,
        spec.metadata_slug_key: item.item_slug,
        spec.metadata_id_key: item.item_id,
        "reminder_key": item.reminder_key,
        "deadline_kind": spec.deadline_kind,
    }


def deadline_action_url(spec, item):
    action_path = reverse(
        spec.route_name,
        kwargs={
            "course_slug": item.course.slug,
            spec.route_slug_kwarg: item.item_slug,
        },
    )
    action_url = public_url(action_path)
    return action_url


def deadline_context(data):
    context = base_context(data)
    extra_context = data.item.context_extra(data.action_url)
    context.update(extra_context)
    return context


def reminder_event_context(data, action_url):
    context_data = ReminderTemplateContextData(
        spec=data.spec,
        item=data.item,
        action_url=action_url,
    )
    return deadline_context(context_data)


def build_reminder_event(data):
    item = data.item
    action_url = deadline_action_url(data.spec, item)
    event_key = reminder_event_key(
        data.spec,
        item.item_id,
        item.reminder_key,
    )
    context = reminder_event_context(data, action_url)
    list_key = reminder_list_key(
        data.spec,
        item,
    )
    list_name = reminder_list_name(
        data.spec,
        item,
    )
    send_payload = deadline_send_payload(
        data.config,
        event_key=event_key,
        template_context=context,
        metadata=data.metadata,
    )
    return ReminderEvent(
        key=event_key,
        list_key=list_key,
        list_name=list_name,
        list_metadata=data.metadata,
        send_payload=send_payload,
        members=data.members,
    )


def reminder_event_key(spec, item_id, reminder_key):
    return f"deadline-reminder:{spec.event_kind}:{item_id}:{reminder_key}"


def reminder_list_key(spec, item):
    return (
        "deadline-reminders:"
        f"{spec.list_kind}:{item.course.slug}:"
        f"{item.item_slug}:{item.reminder_key}"
    )


def reminder_list_name(spec, item):
    return (
        f"{item.course.title} {item.item_title} "
        f"{item.reminder_key} {spec.list_name_suffix}"
    )
