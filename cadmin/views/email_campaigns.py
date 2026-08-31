from dataclasses import dataclass

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import EmailCampaign, RegistrationCampaign
from cadmin.forms import EmailCampaignForm

from .campaign_datamailer import (
    datamailer_campaign_context,
    handle_datamailer_campaign_action,
)
from .helpers import staff_required


@dataclass(frozen=True)
class EmailCampaignEditPostResult:
    response: object
    form: object
    datamailer_preview: object


def get_registration_campaign(campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related(
        "current_course"
    )
    return get_object_or_404(campaigns, slug=campaign_slug)


def handle_email_campaign_datamailer_post(request, email_campaign):
    datamailer_preview, should_redirect = handle_datamailer_campaign_action(
        request, email_campaign
    )
    if should_redirect:
        response = redirect(
            "cadmin_email_campaign_edit",
            campaign_slug=email_campaign.registration_campaign.slug,
            email_campaign_id=email_campaign.id,
        )
        return EmailCampaignEditPostResult(
            response=response,
            form=None,
            datamailer_preview=None,
        )

    form = EmailCampaignForm(instance=email_campaign)
    return EmailCampaignEditPostResult(
        response=None,
        form=form,
        datamailer_preview=datamailer_preview,
    )


def handle_email_campaign_form_post(request, email_campaign):
    form = EmailCampaignForm(request.POST, instance=email_campaign)
    if form.is_valid():
        email_campaign = form.save()
        messages.success(request, "Email campaign saved.")
        response = redirect(
            "cadmin_email_campaign_edit",
            campaign_slug=email_campaign.registration_campaign.slug,
            email_campaign_id=email_campaign.id,
        )
        return EmailCampaignEditPostResult(
            response=response,
            form=None,
            datamailer_preview=None,
        )

    return EmailCampaignEditPostResult(
        response=None,
        form=form,
        datamailer_preview=None,
    )


def email_campaign_edit_post_result(request, email_campaign):
    if request.POST.get("datamailer_action"):
        return handle_email_campaign_datamailer_post(
            request, email_campaign
        )
    return handle_email_campaign_form_post(request, email_campaign)


def email_campaign_edit_context(
    registration_campaign, email_campaign, form, datamailer_preview
):
    context = {
        "form": form,
        "campaign": registration_campaign,
        "email_campaign": email_campaign,
        "page_title": "Edit email campaign",
        "submit_label": "Save changes",
        "datamailer_preview": datamailer_preview,
    }
    context.update(datamailer_campaign_context(email_campaign))
    return context


@staff_required
def email_campaign_create(request, campaign_slug):
    registration_campaign = get_registration_campaign(campaign_slug)

    if request.method == "POST":
        form = EmailCampaignForm(request.POST)
        if form.is_valid():
            email_campaign = form.save(commit=False)
            email_campaign.registration_campaign = registration_campaign
            email_campaign.save()
            messages.success(request, "Email campaign created.")
            response = redirect(
                "cadmin_email_campaign_edit",
                campaign_slug=registration_campaign.slug,
                email_campaign_id=email_campaign.id,
            )
            return response
    else:
        form = EmailCampaignForm(
            initial={"subject": registration_campaign.title}
        )

    context = {
        "form": form,
        "campaign": registration_campaign,
        "email_campaign": None,
        "page_title": "New email campaign",
        "submit_label": "Create email campaign",
    }
    response = render(request, "cadmin/email_campaign_form.html", context)
    return response


@staff_required
def email_campaign_edit(request, campaign_slug, email_campaign_id):
    registration_campaign = get_registration_campaign(campaign_slug)
    email_campaigns = EmailCampaign.objects.filter(
        registration_campaign=registration_campaign
    )
    email_campaign = get_object_or_404(
        email_campaigns, id=email_campaign_id
    )

    if request.method == "POST":
        post_result = email_campaign_edit_post_result(
            request, email_campaign
        )
        if post_result.response:
            return post_result.response
        form = post_result.form
        datamailer_preview = post_result.datamailer_preview
    else:
        form = EmailCampaignForm(instance=email_campaign)
        datamailer_preview = None

    context = email_campaign_edit_context(
        registration_campaign, email_campaign, form, datamailer_preview
    )
    response = render(request, "cadmin/email_campaign_form.html", context)
    return response
