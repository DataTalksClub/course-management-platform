from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from api.safety import require_staff_token
from api.utils import require_methods
from api.views.registration_campaign_mutations import (
    apply_campaign_patch,
    clean_campaign_payload,
    created_campaign,
)
from api.views.registration_campaign_registrations import (
    registration_campaign_registrations_payload,
)
from api.views.registration_campaign_serializers import campaign_to_dict
from courses.models.course import RegistrationCampaign


def campaigns_list_response():
    campaigns = RegistrationCampaign.objects.select_related(
        "current_course"
    ).order_by("title", "slug")
    campaign_records = []
    for campaign in campaigns:
        campaign_record = campaign_to_dict(campaign)
        campaign_records.append(campaign_record)

    payload = {"registration_campaigns": campaign_records}
    response = JsonResponse(payload)
    return response


def campaign_create_response(request):
    data, err = clean_campaign_payload(request, action="set")
    if err:
        return err

    campaign, error = created_campaign(data)
    if error:
        return error

    campaign_data = campaign_to_dict(campaign)
    response = JsonResponse(campaign_data, status=201)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def registration_campaigns_view(request):
    if request.method == "GET":
        return campaigns_list_response()

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    return campaign_create_response(request)


def campaign_patch_response(request, campaign):
    data, err = clean_campaign_payload(request, action="update")
    if err:
        return err

    err = apply_campaign_patch(campaign, data)
    if err:
        return err

    campaign_data = campaign_to_dict(campaign)
    response = JsonResponse(campaign_data)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "PATCH")
def registration_campaign_detail_view(request, campaign_slug):
    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(
        campaigns,
        slug=campaign_slug,
    )

    if request.method == "PATCH":
        staff_error = require_staff_token(request)
        if staff_error:
            return staff_error

        return campaign_patch_response(request, campaign)

    campaign_data = campaign_to_dict(campaign)
    response = JsonResponse(campaign_data)
    return response


@token_required
@require_methods("GET")
def registration_campaign_registrations_view(request, campaign_slug):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    campaign = get_object_or_404(RegistrationCampaign, slug=campaign_slug)
    payload, err = registration_campaign_registrations_payload(
        campaign,
        request.GET,
    )
    if err:
        return err
    response = JsonResponse(payload)
    return response
