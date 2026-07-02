from django.shortcuts import render

from .datamailer_events import (
    datamailer_event_filters,
    datamailer_events_context,
    filtered_datamailer_events,
)
from .datamailer_operations import (
    datamailer_operations_context,
    handle_datamailer_operations_post,
)
from .helpers import (
    staff_required,
)


@staff_required
def datamailer_operations(request):
    if request.method == "POST":
        response = handle_datamailer_operations_post(request)
        if response is not None:
            return response

    context = datamailer_operations_context()
    response = render(
        request,
        "cadmin/datamailer_operations.html",
        context,
    )
    return response


@staff_required
def datamailer_events(request):
    event_type, search_query = datamailer_event_filters(request)
    events = filtered_datamailer_events(event_type, search_query)
    context = datamailer_events_context(
        request, events, event_type, search_query
    )

    response = render(
        request,
        "cadmin/datamailer_events.html",
        context,
    )
    return response
