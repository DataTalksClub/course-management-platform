from django.http import JsonResponse


def error_response(message, code, status=400, details=None):
    data = {"error": message, "code": code}
    if details:
        data["details"] = details
    return JsonResponse(data, status=status)


def ensure_closed_for_delete(instance, closed_state, noun):
    if instance.state != closed_state:
        return error_response(
            f"Only closed {noun}s can be deleted",
            f"{noun}_not_closed",
            details={"state": instance.state},
        )
    return None


def ensure_no_related_records_for_delete(queryset, related_name, noun):
    count = queryset.count()
    if count > 0:
        return error_response(
            f"Cannot delete {noun} with existing {related_name}",
            f"{noun}_has_{related_name}",
            details={f"{related_name}_count": count},
        )
    return None
