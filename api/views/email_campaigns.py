from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from api.safety import require_staff_token
from api.utils import require_methods
from api.views.email_campaign_mutations import (
    clean_email_campaign_payload,
    created_email_campaign,
)
from api.views.email_campaign_serializers import email_campaign_to_dict
from courses.models.course import RegistrationCampaign


def email_campaigns_list_response(registration_campaign):
    email_campaigns = registration_campaign.email_campaigns.all()
    email_campaign_records = []
    for email_campaign in email_campaigns:
        email_campaign_records.append(email_campaign_to_dict(email_campaign))

    payload = {"email_campaigns": email_campaign_records}
    response = JsonResponse(payload)
    return response


def email_campaign_create_response(request, registration_campaign):
    data, err = clean_email_campaign_payload(request)
    if err:
        return err

    email_campaign, error = created_email_campaign(
        registration_campaign, data
    )
    if error:
        return error

    email_campaign_data = email_campaign_to_dict(email_campaign)
    response = JsonResponse(email_campaign_data, status=201)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def registration_campaign_emails_view(request, campaign_slug):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    registration_campaign = get_object_or_404(
        RegistrationCampaign, slug=campaign_slug
    )

    if request.method == "POST":
        return email_campaign_create_response(
            request, registration_campaign
        )

    return email_campaigns_list_response(registration_campaign)
