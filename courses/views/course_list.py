from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from courses.models.course import Course
from courses.views.course_homepage import add_course_homepage_info
from courses.views.course_list_user_state import (
    attach_registration_campaigns,
    mark_enrolled_courses,
    mark_registered_courses,
)


@dataclass(frozen=True)
class CourseListCourses:
    courses: list
    active_courses: list
    finished_courses: list
    archive_courses_by_year: dict


def visible_course_list_queryset():
    courses = Course.objects.filter(visible=True)
    homework_count = Count("homework", distinct=True)
    project_count = Count("project", distinct=True)
    learner_count = Count("enrollment", distinct=True)
    courses = courses.annotate(
        homework_count=homework_count,
        project_count=project_count,
        learner_count=learner_count,
    )
    courses = courses.prefetch_related("homework_set", "project_set")
    return courses.order_by("-id")


def split_courses_by_status(courses, now):
    active_courses = []
    finished_courses = []
    archive_courses_by_year = defaultdict(list)

    for course in courses:
        add_course_homepage_info(course, now)

        if course.finished:
            finished_courses.append(course)
            archive_courses_by_year[course.home_year].append(course)
        else:
            active_courses.append(course)

    return CourseListCourses(
        courses=courses,
        active_courses=active_courses,
        finished_courses=finished_courses,
        archive_courses_by_year=archive_courses_by_year,
    )


def featured_course(active_courses):
    for course in active_courses:
        title = course.title.lower()
        if not title.startswith("fake"):
            return course

    if active_courses:
        return active_courses[0]

    return None


def archive_year_sort_key(year):
    return (year == "Archive", year)


def course_archive_groups(archive_courses_by_year):
    archive_year_keys = archive_courses_by_year.keys()
    archive_years = sorted(
        archive_year_keys,
        key=archive_year_sort_key,
        reverse=True,
    )
    if "Archive" in archive_years:
        archive_years.remove("Archive")
        archive_years.append("Archive")

    archive_groups = []
    for year in archive_years:
        archive_group = {
            "year": year,
            "courses": archive_courses_by_year[year],
        }
        archive_groups.append(archive_group)
    return archive_groups


def course_home_stats(courses, active_courses, finished_courses):
    homework_count = 0
    project_count = 0
    for course in courses:
        homework_count += course.homework_count
        project_count += course.project_count

    active_course_count = len(active_courses)
    archive_course_count = len(finished_courses)
    return {
        "active_courses": active_course_count,
        "archive_courses": archive_course_count,
        "homeworks": homework_count,
        "projects": project_count,
    }


def other_active_courses(active_courses, featured_course):
    other_courses = []
    for course in active_courses:
        if course != featured_course:
            other_courses.append(course)
    return other_courses


def prepare_course_list_courses(user):
    visible_courses = visible_course_list_queryset()
    courses = list(visible_courses)
    now = timezone.now()
    course_groups = split_courses_by_status(courses, now)

    mark_enrolled_courses(course_groups.courses, user)
    attach_registration_campaigns(course_groups.courses)
    mark_registered_courses(course_groups.courses, user)

    return course_groups


def course_list_context(user):
    course_groups = prepare_course_list_courses(user)
    selected_featured_course = featured_course(course_groups.active_courses)
    archive_groups = course_archive_groups(
        course_groups.archive_courses_by_year
    )
    secondary_active_courses = other_active_courses(
        course_groups.active_courses,
        selected_featured_course,
    )
    home_stats = course_home_stats(
        course_groups.courses,
        course_groups.active_courses,
        course_groups.finished_courses,
    )

    return {
        "active_courses": course_groups.active_courses,
        "archive_groups": archive_groups,
        "featured_course": selected_featured_course,
        "finished_courses": course_groups.finished_courses,
        "other_active_courses": secondary_active_courses,
        "home_stats": home_stats,
    }


def course_list(request):
    context = course_list_context(request.user)
    response = render(
        request,
        "courses/course_list.html",
        context,
    )
    return response
