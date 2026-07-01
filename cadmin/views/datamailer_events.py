from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from data.models import DatamailerContactEvent

from .helpers import count_by, paginate_queryset, pagination_querystring


def datamailer_event_filters(request):
    raw_event_type = request.GET.get("event_type", "")
    raw_search_query = request.GET.get("q", "")
    event_type = raw_event_type.strip()
    search_query = raw_search_query.strip()
    return (
        event_type,
        search_query,
    )


def filtered_datamailer_events(event_type, search_query):
    events = DatamailerContactEvent.objects.all()

    if event_type:
        events = events.filter(event_type=event_type)
    if search_query:
        events = events.filter(
            Q(email__icontains=search_query)
            | Q(event_id__icontains=search_query)
            | Q(client__icontains=search_query)
            | Q(audience__icontains=search_query)
            | Q(preference_key__icontains=search_query)
        )

    return events


def datamailer_events_metrics():
    since = timezone.now() - timedelta(hours=24)
    total = DatamailerContactEvent.objects.count()
    last_24h = DatamailerContactEvent.objects.filter(
        created_at__gte=since
    ).count()
    duplicate_count_sum = Sum("duplicate_count")
    duplicate_aggregate = DatamailerContactEvent.objects.aggregate(
        total=duplicate_count_sum
    )
    duplicates = duplicate_aggregate["total"] or 0
    events = DatamailerContactEvent.objects.all()
    by_type = count_by(events, "event_type")

    return {
        "total": total,
        "last_24h": last_24h,
        "duplicates": duplicates,
        "by_type": by_type,
    }


def datamailer_event_types():
    event_type_values = (
        DatamailerContactEvent.objects.order_by("event_type")
        .values_list("event_type", flat=True)
        .distinct()
    )
    event_types = list(event_type_values)
    return event_types


def datamailer_events_context(
    request, events, event_type, search_query
):
    events_page = paginate_queryset(request, events, per_page=50)
    event_types = datamailer_event_types()
    metrics = datamailer_events_metrics()
    page_range = events_page.paginator.get_elided_page_range(
        events_page.number
    )
    querystring = pagination_querystring(request)

    return {
        "events_page": events_page,
        "event_types": event_types,
        "selected_event_type": event_type,
        "search_query": search_query,
        "metrics": metrics,
        "page_range": page_range,
        "pagination_querystring": querystring,
    }
