from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from api.safety import (
    DeleteObjectData,
    PatchFieldRules,
    apply_patch_fields,
    delete_object_or_error,
    require_staff_token,
)
from api.utils import parse_json_body


@dataclass(frozen=True)
class PatchResponseConfig:
    to_dict: Callable[[Any], dict[str, Any]]
    rules: PatchFieldRules


@dataclass(frozen=True)
class DeleteResponseConfig:
    closed_state: str
    related_queryset: Any
    related_name: str
    noun: str


@dataclass(frozen=True)
class DetailResponseConfig:
    patch: PatchResponseConfig
    delete: DeleteResponseConfig


def single_or_list(data):
    if isinstance(data, list):
        return data
    item_list = [data]
    return item_list


def bulk_create_response(data, create_item, *create_args, name_field="name"):
    created = []
    errors = []
    items = single_or_list(data)
    for item in items:
        item_dict, error = create_item(*create_args, item)
        if error:
            item_name = item.get(name_field, "unknown")
            error_record = {
                "name": item_name,
                "error": error,
            }
            errors.append(error_record)
        else:
            created.append(item_dict)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    if created:
        status = 201
    else:
        status = 400
    response = JsonResponse(result, status=status)
    return response


def get_course_child_or_404(model, course, *, object_id=None, slug=None):
    if object_id is not None:
        return get_object_or_404(model, course=course, id=object_id)
    return get_object_or_404(model, course=course, slug=slug)


def patch_instance_response(
    instance,
    data,
    config,
):
    error = apply_patch_fields(instance, data, config.rules)
    if error:
        return error

    instance.save()
    response_data = config.to_dict(instance)
    response = JsonResponse(response_data)
    return response


def detail_response(
    request,
    instance,
    config,
):
    if request.method == "GET":
        response_data = config.patch.to_dict(instance)
        response = JsonResponse(response_data)
        return response

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    if request.method == "DELETE":
        return detail_delete_response(
            instance,
            config.delete,
        )

    return detail_patch_response(
        request,
        instance,
        config.patch,
    )

def detail_delete_response(
    instance,
    config,
):
    delete_data = DeleteObjectData(
        instance=instance,
        closed_state=config.closed_state,
        related_queryset=config.related_queryset,
        related_name=config.related_name,
        noun=config.noun,
    )
    return delete_object_or_error(delete_data)


def detail_patch_response(
    request,
    instance,
    config,
):
    data, err = parse_json_body(request)
    if err:
        return err

    return patch_instance_response(
        instance,
        data,
        config,
    )
