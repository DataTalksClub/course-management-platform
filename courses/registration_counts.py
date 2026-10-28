"""Cumulative "N people have already registered" count for course pages.

Counts exactly the records the daily registration digest counts: every
``CourseRegistration`` row whose course is this course — any review status
(pending, approved, rejected) and any email-confirmation state. The digest
(``collect_digest_registrations``) reports the last-24h window of this same
record set grouped per course; the course page shows the cumulative total.

The count is cached in the Django cache with a short TTL so course-page
renders never run the query per request.
"""

from django.core.cache import cache

REGISTERED_COUNT_CACHE_TTL = 600  # seconds; a few minutes of staleness is fine


def registered_count_cache_key(course) -> str:
    return f"course:registered-count:{course.pk}:v1"


def registered_people_count(course) -> int:
    from courses.models.course import CourseRegistration

    key = registered_count_cache_key(course)
    cached = cache.get(key)
    if cached is not None:
        return cached
    count = CourseRegistration.objects.filter(course=course).count()
    cache.set(key, count, REGISTERED_COUNT_CACHE_TTL)
    return count
