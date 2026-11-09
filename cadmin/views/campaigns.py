from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from courses.genmedia_policy import CAMPAIGN_SLUG
from courses.decision_messages import REJECTION_MESSAGE_LOCATION
from courses.genmedia_policy import (
    CAMPAIGN_SLUG as GENMEDIA_CAMPAIGN_SLUG,
)
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


MAX_DECISION_MESSAGE_LENGTH = 2000
BULK_APPROVE_LIMIT = 500


def _clean_decision_message(request) -> str:
    raw_message = request.POST.get("custom_message") or ""
    return raw_message.strip()[:MAX_DECISION_MESSAGE_LENGTH]


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

    action = (request.POST.get("action") or "").strip()
    custom_message = _clean_decision_message(request)
    if action == "reject_excluded":
        if campaign.slug != GENMEDIA_CAMPAIGN_SLUG:
            messages.error(
                request, "Bulk location-policy reject is genmedia only."
            )
            return redirect(
                "cadmin_campaign_registrations",
                campaign_slug=campaign.slug,
            )
        pending = CourseRegistration.objects.filter(
            campaign=campaign,
            status=CourseRegistration.Status.PENDING,
        ).order_by("pk")[:BULK_APPROVE_LIMIT]
        rejected_count = 0
        for registration in pending:
            if not registration.genmedia_excluded_reason:
                continue
            registration.status = CourseRegistration.Status.REJECTED
            registration._decision_custom_message = (
                REJECTION_MESSAGE_LOCATION
            )
            registration.save(update_fields=["status", "updated_at"])
            rejected_count += 1
        if rejected_count == 0:
            messages.info(
                request, "No excluded pending applications to reject."
            )
        else:
            messages.success(
                request,
                f"Rejected {rejected_count} excluded applications. "
                "Update emails are queued for delivery.",
            )
        return redirect(
            "cadmin_campaign_registrations",
            campaign_slug=campaign.slug,
        )
    if action == "approve_all_pending":
        pending = CourseRegistration.objects.filter(
            campaign=campaign,
            status=CourseRegistration.Status.PENDING,
        ).order_by("pk")[:BULK_APPROVE_LIMIT]
        approved_count = 0
        skipped_excluded = 0
        for registration in pending:
            if (
                campaign.slug == GENMEDIA_CAMPAIGN_SLUG
                and registration.genmedia_excluded_reason
            ):
                skipped_excluded += 1
                continue
            approve_registration(
                registration, custom_message=custom_message
            )
            approved_count += 1
        if approved_count == 0:
            messages.info(request, "No pending applications to approve.")
        else:
            detail = (
                f"Approved {approved_count} applications. "
                "Approval emails are queued for delivery."
            )
            if skipped_excluded:
                detail += (
                    f" Skipped {skipped_excluded} excluded "
                    "by eligibility policy."
                )
            messages.success(request, detail)
        return redirect(
            "cadmin_campaign_registrations",
            campaign_slug=campaign.slug,
        )

    registration = get_object_or_404(
        CourseRegistration,
        campaign=campaign,
        pk=request.POST.get("registration_id"),
    )
    if action == "approve":
        enrollment = approve_registration(
            registration, custom_message=custom_message
        )
        if enrollment is not None:
            messages.success(
                request,
                f"Approved {registration.email_normalized} and enrolled "
                f"them in {enrollment.course}. "
                "Approval email queued for delivery.",
            )
        else:
            messages.success(
                request,
                f"Approved {registration.email_normalized}. No user "
                f"account matched, so no enrollment was created yet. "
                "Approval email queued for delivery.",
            )
    elif action == "reject":
        registration.status = CourseRegistration.Status.REJECTED
        registration._decision_custom_message = custom_message
        registration.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            f"Rejected {registration.email_normalized}. "
            "Update email queued for delivery.",
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
def campaign_genmedia_preview(request, campaign_slug):
    """Staff-only daily approved-list preview for Nebius.

    Shows the latest Europe/Berlin day of nightly auto-approvals with a
    manual CSV download. There is deliberately no POST action and no
    auto-send: nothing here emails registrants, Nebius, or anyone.
    """
    import csv
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo

    from django.http import HttpResponse
    from django.utils import timezone

    from courses.genmedia_policy import AUTO_APPROVAL_TIMEZONE
    from courses.models.genmedia_approval import GenmediaApprovalRun

    campaigns = RegistrationCampaign.objects.select_related("current_course")
    campaign = get_object_or_404(campaigns, slug=campaign_slug)
    if campaign.slug != CAMPAIGN_SLUG:
        raise Http404("No Nebius preview for this campaign.")

    zone = ZoneInfo(AUTO_APPROVAL_TIMEZONE)
    auto_approved = CourseRegistration.objects.filter(
        campaign=campaign,
        course_id=campaign.current_course_id,
        auto_approved_at__isnull=False,
    )
    latest = auto_approved.order_by("-auto_approved_at").first()
    local_date = None
    registrations = CourseRegistration.objects.none()
    if latest is not None:
        local_date = timezone.localtime(
            latest.auto_approved_at, zone
        ).date()
        local_start = timezone.make_aware(
            datetime.combine(local_date, time.min), zone
        )
        local_end = timezone.make_aware(
            datetime.combine(local_date + timedelta(days=1), time.min),
            zone,
        )
        registrations = auto_approved.filter(
            auto_approved_at__gte=local_start,
            auto_approved_at__lt=local_end,
        ).order_by("auto_approved_at", "pk")

    if request.GET.get("format") == "csv":
        filename_date = local_date.isoformat() if local_date else "empty"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="genmedia-approved-{filename_date}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            ("name", "email", "country", "ukraine_region", "approved_at")
        )
        for registration in registrations:
            writer.writerow(
                (
                    registration.name,
                    registration.email_normalized,
                    registration.country,
                    registration.get_ukraine_region_display(),
                    timezone.localtime(
                        registration.auto_approved_at, zone
                    ).isoformat(),
                )
            )
        return response

    context = {
        "campaign": campaign,
        "registrations": registrations,
        "local_date": local_date,
        "runs": GenmediaApprovalRun.objects.order_by("-date")[:14],
        "approved_total": CourseRegistration.objects.filter(
            campaign=campaign,
            course_id=campaign.current_course_id,
            status=CourseRegistration.Status.APPROVED,
        ).count(),
        "pending_total": CourseRegistration.objects.filter(
            campaign=campaign,
            course_id=campaign.current_course_id,
            status=CourseRegistration.Status.PENDING,
        ).count(),
    }
    return render(request, "cadmin/campaign_genmedia_preview.html", context)


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
            "ukraine_region",
            "excluded_reason",
            "role",
            "status",
            "auto_approved_at",
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
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "landing_referrer",
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
                registration.ukraine_region,
                registration.genmedia_excluded_reason,
                registration.role,
                registration.status,
                (
                    registration.auto_approved_at.isoformat()
                    if registration.auto_approved_at
                    else ""
                ),
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
                registration.utm_source,
                registration.utm_medium,
                registration.utm_campaign,
                registration.utm_content,
                registration.utm_term,
                registration.landing_referrer,
                registration.created_at.isoformat(),
            ]
        )
    return response
