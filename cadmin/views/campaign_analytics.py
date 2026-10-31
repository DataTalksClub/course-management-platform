from datetime import date, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, render

from courses.models.course import CourseRegistration, RegistrationCampaign

from .helpers import staff_required

TOP_N = 10

STATUS_ORDER = ["pending", "approved", "rejected"]


def parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def date_range(request):
    start = parse_date(request.GET.get("from"))
    end = parse_date(request.GET.get("to"))
    return start, end


def filtered_registrations(campaign, start, end):
    registrations = CourseRegistration.objects.filter(campaign=campaign)
    if start:
        registrations = registrations.filter(created_at__date__gte=start)
    if end:
        registrations = registrations.filter(created_at__date__lte=end)
    return registrations


def with_percent(rows, total):
    result = []
    for label, count in rows:
        percent = round(100 * count / total, 1) if total else 0
        result.append({"label": label, "count": count, "percent": percent})
    return result


def breakdown(registrations, field, total, labels=None, top=TOP_N):
    rows = (
        registrations.values(field)
        .annotate(count=Count("id"))
        .order_by("-count", field)
    )
    labels = labels or {}
    pairs = []
    for row in rows:
        raw = row[field]
        label = labels.get(raw) or raw or "Not provided"
        pairs.append((label, row["count"]))
    if len(pairs) > top:
        rest = sum(count for _, count in pairs[top:])
        pairs = pairs[:top] + [("All others", rest)]
    return with_percent(pairs, total)


def daily_series(registrations, start, end):
    rows = (
        registrations.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    counts = {row["day"]: row["count"] for row in rows}
    if not counts:
        return []
    first = start or min(counts)
    last = end or max(counts)
    series = []
    running = 0
    day = first
    while day <= last:
        count = counts.get(day, 0)
        running += count
        series.append({"day": day, "count": count, "cumulative": running})
        day += timedelta(days=1)
    return series


def line_chart(series, key, width=720, height=220, pad=32):
    if not series:
        return None
    peak = max(point[key] for point in series) or 1
    n = len(series)
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad
    coords = []
    for i, point in enumerate(series):
        x = pad + (inner_w * i / (n - 1) if n > 1 else inner_w / 2)
        y = pad + inner_h - inner_h * point[key] / peak
        coords.append((round(x, 1), round(y, 1)))
    points = " ".join(f"{x},{y}" for x, y in coords)
    baseline = pad + inner_h
    area = f"{coords[0][0]},{baseline} {points} {coords[-1][0]},{baseline}"
    return {
        "width": width,
        "height": height,
        "pad": pad,
        "points": points,
        "area": area,
        "peak": peak,
        "baseline": baseline,
        "first_day": series[0]["day"],
        "last_day": series[-1]["day"],
        "dots": [
            {"x": x, "y": y, "day": p["day"], "value": p[key]}
            for (x, y), p in zip(coords, series)
        ]
        if n <= 60
        else [],
    }


def analytics_context(campaign, start, end):
    registrations = filtered_registrations(campaign, start, end)
    totals = registrations.aggregate(
        total=Count("id"),
        confirmed=Count("id", filter=Q(email_confirmed=True)),
        nebius=Count("id", filter=Q(accepted_nebius_sharing=True)),
        newsletter=Count("id", filter=Q(accepted_newsletter=True)),
    )
    total = totals["total"]
    status_counts = dict(
        registrations.values_list("status").annotate(c=Count("id"))
    )
    status_labels = dict(CourseRegistration.Status.choices)
    funnel = with_percent(
        [(status_labels[s], status_counts.get(s, 0)) for s in STATUS_ORDER],
        total,
    )
    funnel_max = max([row["count"] for row in funnel] + [1])
    for row in funnel:
        row["width"] = round(100 * row["count"] / funnel_max, 1)
    unconfirmed = total - totals["confirmed"]
    series = daily_series(registrations, start, end)
    sources = breakdown(
        registrations, "source", total, labels={"": "Direct (registration form)"}
    )
    return {
        "campaign": campaign,
        "course": campaign.current_course,
        "range_from": start.isoformat() if start else "",
        "range_to": end.isoformat() if end else "",
        "total": total,
        "confirmed": totals["confirmed"],
        "unconfirmed": unconfirmed,
        "confirmed_percent": round(100 * totals["confirmed"] / total, 1) if total else 0,
        "nebius": totals["nebius"],
        "nebius_percent": round(100 * totals["nebius"] / total, 1) if total else 0,
        "newsletter_percent": round(100 * totals["newsletter"] / total, 1) if total else 0,
        "funnel": funnel,
        "confirmation": with_percent(
            [("Confirmed", totals["confirmed"]), ("Unconfirmed", unconfirmed)],
            total,
        ),
        "daily_chart": line_chart(series, "count"),
        "cumulative_chart": line_chart(series, "cumulative"),
        "breakdowns": [
            ("Country", breakdown(registrations, "country", total)),
            ("Region", breakdown(registrations, "region", total)),
            (
                "Role",
                breakdown(
                    registrations, "role", total, dict(CourseRegistration.Role.choices)
                ),
            ),
            (
                "Years of experience",
                breakdown(
                    registrations,
                    "years_experience",
                    total,
                    dict(CourseRegistration.YearsExperience.choices),
                ),
            ),
            ("Company", breakdown(registrations, "company_name", total)),
            ("Source", sources),
        ],
    }


@staff_required
def campaign_analytics(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(campaigns, slug=campaign_slug)
    start, end = date_range(request)
    context = analytics_context(campaign, start, end)
    return render(request, "cadmin/campaign_analytics.html", context)
