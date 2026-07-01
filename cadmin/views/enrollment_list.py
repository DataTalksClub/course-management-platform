from .helpers import paginate_queryset, pagination_querystring
from .view_models import enrollment_list_data


def enrollment_list_filters(request):
    raw_search_query = request.GET.get("q", "")
    search_query = raw_search_query.strip()
    status_filter = request.GET.get("status", "all")
    return (
        search_query,
        status_filter,
    )


def enrollments_list_context(request, course):
    search_query, status_filter = enrollment_list_filters(request)
    enrollments, enrollment_filter_counts = enrollment_list_data(
        course,
        search_query,
        status_filter,
    )

    enrollments_page = paginate_queryset(request, enrollments)
    total_enrollments = len(enrollments)
    querystring = pagination_querystring(request)

    return {
        "course": course,
        "enrollments": enrollments_page.object_list,
        "enrollments_page": enrollments_page,
        "total_enrollments": total_enrollments,
        "enrollment_filter_counts": enrollment_filter_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "pagination_querystring": querystring,
    }
