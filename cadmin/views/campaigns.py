from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import CourseRegistration, RegistrationCampaign
from courses.registration_wall import approve_registration
from cadmin.forms import RegistrationCampaignForm
from .campaign_forms import (
    campaign_edit_context,
    campaign_form_course,
    campaign_form_initial,
    handle_campaign_form_post,
)
from .campaign_registration_list import (
    campaign_registrations_context,
    campaign_registrations_context_data,
)
from .helpers import (
    staff_required,
)


@staff_required
def campaign_create(request):
    if request.method == "POST":
        form = RegistrationCampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save()
            messages.success(
                request, "Registration landing page created."
            )
            response = redirect(
                "cadmin_campaign_edit", campaign_slug=campaign.slug
            )
            return response
    else:
        initial = campaign_form_initial(request)
        form = RegistrationCampaignForm(initial=initial)

    course = campaign_form_course(form)
    context = {
        "form": form,
        "campaign": None,
        "course": course,
        "page_title": "Create registration landing page",
        "submit_label": "Create landing page",
    }
    response = render(request, "cadmin/campaign_form.html", context)
    return response


@staff_required
def campaign_edit(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )

    if request.method == "POST":
        post_result = handle_campaign_form_post(request, campaign)
        if post_result.response:
            return post_result.response
        form = post_result.form
    else:
        form = RegistrationCampaignForm(instance=campaign)

    context = campaign_edit_context(campaign, form)
    response = render(request, "cadmin/campaign_form.html", context)
    return response


@staff_required
def campaign_registrations(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )
    context_data = campaign_registrations_context_data(
        request, campaign
    )
    context = campaign_registrations_context(context_data)
    response = render(
        request, "cadmin/campaign_registrations.html", context
    )
    return response


@staff_required
def campaign_registration_decide(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )
    if request.method != "POST":
        return redirect(
            "cadmin_campaign_registrations",
            campaign_slug=campaign.slug,
        )

    registration = get_object_or_404(
        CourseRegistration,
        campaign=campaign,
        pk=request.POST.get("registration_id"),
    )
    action = (request.POST.get("action") or "").strip()
    if action == "approve":
        enrollment = approve_registration(registration)
        if enrollment is not None:
            messages.success(
                request,
                f"Approved {registration.email_normalized} and enrolled "
                f"them in {enrollment.course}.",
            )
        else:
            messages.success(
                request,
                f"Approved {registration.email_normalized}. No user "
                f"account matched, so no enrollment was created yet.",
            )
    elif action == "reject":
        registration.status = CourseRegistration.Status.REJECTED
        registration.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            f"Rejected {registration.email_normalized}.",
        )
    elif action == "reset":
        registration.status = CourseRegistration.Status.PENDING
        registration.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            f"Moved {registration.email_normalized} back to pending.",
        )
    else:
        messages.error(request, "Unknown review action.")
    return redirect(
        "cadmin_campaign_registrations",
        campaign_slug=campaign.slug,
    )


@staff_required
def campaign_registrations_export(request, campaign_slug):
    import csv

    from django.http import HttpResponse

    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )
    context_data = campaign_registrations_context_data(
        request, campaign
    )
    registrations = context_data.registrations_page.paginator.object_list

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="registrations-{campaign.slug}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        [
            "email",
            "name",
            "company_name",
            "country",
            "region",
            "role",
            "status",
            "experience",
            "years_experience",
            "why_join",
            "linkedin_url",
            "github_url",
            "prereq_python",
            "prereq_docker",
            "prereq_http",
            "prereq_cli",
            "comment",
            "accepted_newsletter",
            "accepted_nebius_sharing",
            "created_at",
        ]
    )
    for registration in registrations.order_by("created_at"):
        writer.writerow(
            [
                registration.email_normalized,
                registration.name,
                registration.company_name,
                registration.country,
                registration.region,
                registration.role,
                registration.status,
                registration.experience,
                registration.years_experience,
                registration.why_join,
                registration.linkedin_url,
                registration.github_url,
                registration.prereq_python,
                registration.prereq_docker,
                registration.prereq_http,
                registration.prereq_cli,
                registration.comment,
                registration.accepted_newsletter,
                registration.accepted_nebius_sharing,
                registration.created_at.isoformat(),
            ]
        )
    return response
