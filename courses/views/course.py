from django.http import HttpRequest, HttpResponse

from django.shortcuts import render, redirect

from courses.views.course_page_context import (
    CoursePageData,
    course_page_context,
    course_page_data,
    should_redirect_to_registration_campaign,
)


def course_registration_redirect_response(data: CoursePageData):
    if should_redirect_to_registration_campaign(
        registration_campaign=data.registration_campaign,
        homeworks=data.homeworks,
        projects=data.projects,
        user=data.user,
    ):
        response = redirect(
            "registration_campaign",
            campaign_slug=data.registration_campaign.slug,
        )
        return response
    return None


def course_view(request: HttpRequest, course_slug: str) -> HttpResponse:
    data = course_page_data(course_slug, request.user)
    redirect_response = course_registration_redirect_response(data)
    if redirect_response is not None:
        return redirect_response

    context = course_page_context(data)
    response = render(
        request,
        "courses/course.html",
        context,
    )
    return response
