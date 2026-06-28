from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from api.safety import (
    apply_patch_fields,
    delete_object_or_error,
    require_staff_token,
)
from api.utils import parse_json_body


def single_or_list(data):
    return data if isinstance(data, list) else [data]


def bulk_create_response(data, create_item, *, name_field="name"):
    created = []
    errors = []
    for item in single_or_list(data):
        item_dict, error = create_item(item)
        if error:
            errors.append(
                {
                    "name": item.get(name_field, "unknown"),
                    "error": error,
                }
            )
        else:
            created.append(item_dict)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    return JsonResponse(result, status=201 if created else 400)


def get_course_child_or_404(model, course, *, object_id=None, slug=None):
    if object_id is not None:
        return get_object_or_404(model, course=course, id=object_id)
    return get_object_or_404(model, course=course, slug=slug)


def patch_instance_response(
    instance,
    data,
    *,
    to_dict,
    allowed_fields,
    valid_states,
    invalid_state_code,
    date_fields,
):
    error = apply_patch_fields(
        instance,
        data,
        allowed_fields=allowed_fields,
        valid_states=valid_states,
        invalid_state_code=invalid_state_code,
        date_fields=date_fields,
    )
    if error:
        return error

    instance.save()
    return JsonResponse(to_dict(instance))


def detail_response(
    request,
    instance,
    *,
    to_dict,
    allowed_fields,
    valid_states,
    invalid_state_code,
    date_fields,
    closed_state,
    related_queryset,
    related_name,
    noun,
):
    if request.method == "GET":
        return JsonResponse(to_dict(instance))

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    if request.method == "DELETE":
        return delete_object_or_error(
            instance,
            closed_state=closed_state,
            related_queryset=related_queryset,
            related_name=related_name,
            noun=noun,
        )

    data, err = parse_json_body(request)
    if err:
        return err

    return patch_instance_response(
        instance,
        data,
        to_dict=to_dict,
        allowed_fields=allowed_fields,
        valid_states=valid_states,
        invalid_state_code=invalid_state_code,
        date_fields=date_fields,
    )
