from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import (
    RegistrationCampaign,
)
from cadmin.forms import RegistrationCampaignForm
from .campaign_forms import (
    campaign_edit_context,
    campaign_form_course,
    campaign_form_initial,
    handle_campaign_datamailer_post,
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


def campaign_edit_post_result(request, campaign):
    if request.POST.get("datamailer_action"):
        post_result = handle_campaign_datamailer_post(
            request,
            campaign,
        )
        return post_result

    post_result = handle_campaign_form_post(request, campaign)
    return post_result


@staff_required
def campaign_edit(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )

    if request.method == "POST":
        post_result = campaign_edit_post_result(request, campaign)
        if post_result.response:
            return post_result.response
        form = post_result.form
        datamailer_preview = post_result.datamailer_preview
    else:
        form = RegistrationCampaignForm(instance=campaign)
        datamailer_preview = None

    context = campaign_edit_context(
        campaign,
        form,
        datamailer_preview,
    )
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
