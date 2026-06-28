import logging
import re

from collections import defaultdict
from datetime import timedelta

import requests
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Count, Q, Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from course_management.datamailer import (
    DatamailerClient,
    DatamailerConfig,
    registration_campaign_datamailer_payload,
    registration_campaign_external_key,
    send_homework_score_notification,
    send_project_score_notification,
    send_peer_review_assignment_notification,
)
from course_management.datamailer_outbox import (
    datamailer_outbox_status_summary,
)
from data.models import DatamailerContactEvent
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
)
from .forms import (
    HomeworkSubmissionEditForm,
    ProjectSubmissionEditForm,
    RegistrationCampaignForm,
)
from .services import (
    update_homework_submission_from_admin,
    update_project_submission_from_admin,
)
from .view_models import (
    enrollment_list_data,
    project_submission_list_data,
)
from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Project,
    ProjectState,
    Submission,
    ProjectSubmission,
    Question,
    Answer,
    ReviewCriteria,
    ProjectEvaluationScore,
    Enrollment,
    LeaderboardComplaint,
    CourseRegistration,
    RegistrationCampaign,
)
from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
    fill_correct_answers,
    clear_correct_answers,
    update_leaderboard,
)
from courses.services.enrollment_flags import (
    set_learning_in_public_disabled,
)
from courses.projects import (
    assign_peer_reviews_for_project,
    score_project,
    ProjectActionStatus,
)

logger = logging.getLogger(__name__)
CADMIN_PAGE_SIZE = 25
CADMIN_PROJECT_SUBMISSIONS_PAGE_SIZE = 50
DATAMAILER_RECIPIENT_LIST_KINDS = [
    "registrations",
    "enrollments",
    "homework",
    "project",
    "project-passed",
    "graduates",
]
DATAMAILER_CAMPAIGN_UPSERT_ACTIONS = {
    "sync",
    "preview",
    "test_send",
    "queue",
}


def paginate_queryset(request, queryset, per_page=CADMIN_PAGE_SIZE):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def pagination_querystring(request):
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""


def redirect_after_action(request, default_view_name, **kwargs):
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(default_view_name, **kwargs)


def first_form_error(form):
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return "Invalid form data"


def staff_required(function):
    """Decorator to require staff/admin access"""
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated and u.is_staff,
        login_url="/accounts/login/",
    )
    return actual_decorator(function)


def count_by(queryset, field):
    return list(
        queryset.values(field)
        .annotate(count=Count("id"))
        .order_by("-count", field)
    )


def registration_campaign_metrics(campaign):
    registrations = CourseRegistration.objects.filter(campaign=campaign)
    return {
        "campaign": campaign,
        "total": registrations.count(),
        "by_role": count_by(registrations, "role"),
        "by_country": count_by(registrations, "country"),
        "by_region": count_by(registrations, "region"),
    }


_TRAILING_YEAR_RE = re.compile(r"[\s_-]*(\d{4})\s*$")


def _split_trailing_year(text):
    """Split a trailing 4-digit year off the end of ``text``.

    Returns ``(base, year)`` where ``base`` has the year (and any joining
    separator) removed. ``year`` is an empty string when none is found.
    """
    match = _TRAILING_YEAR_RE.search(text or "")
    if not match:
        return (text or "").strip(), ""
    base = (text[: match.start()]).strip().rstrip("-_ ").strip()
    return base, match.group(1)


def campaign_form_initial(request):
    course_slug = request.GET.get("course", "").strip()
    if not course_slug:
        return {}

    course = Course.objects.filter(slug=course_slug).first()
    if course is None:
        return {}

    initial = {"current_course": course}

    title_base, title_year = _split_trailing_year(course.title)
    slug_base, slug_year = _split_trailing_year(course.slug)
    year = title_year or slug_year

    # Stable, year-agnostic public URL ("ml-zoomcamp-2025" -> "ml-zoomcamp").
    initial["slug"] = slug_base or course.slug

    # Title without the edition year ("Machine Learning Zoomcamp 2025" ->
    # "Machine Learning Zoomcamp"); the year becomes the edition label.
    if title_base:
        initial["title"] = title_base
    if year:
        initial["edition_label"] = f"{year} cohort"

    return initial


def campaign_form_course(form):
    course = form.initial.get("current_course")
    if course is not None:
        return course

    course_id = form.data.get("current_course") if form.is_bound else ""
    if not course_id:
        return None

    return Course.objects.filter(pk=course_id).first()


def parse_test_recipients(value):
    emails = [
        item.strip()
        for item in re.split(r"[\s,;]+", value or "")
        if item.strip()
    ]
    if not emails:
        raise ValidationError("Enter at least one test recipient.")
    if len(emails) > 25:
        raise ValidationError("Enter no more than 25 test recipients.")
    for email in emails:
        validate_email(email)
    return emails


def datamailer_campaign_context(campaign):
    return {
        "datamailer_external_key": registration_campaign_external_key(
            campaign
        ),
        "datamailer_payload": registration_campaign_datamailer_payload(
            campaign
        ),
    }


def datamailer_campaign_client_or_message(request):
    config = DatamailerConfig.from_settings()
    if config is None:
        messages.error(
            request,
            "Datamailer is not configured for campaign operations.",
        )
        return None
    return DatamailerClient(config)


def datamailer_campaign_queue_recipient_count(response):
    response = response or {}
    recipient_count = response.get("recipient_count")
    if recipient_count is None:
        campaign_payload = response.get("campaign") or {}
        recipient_count = campaign_payload.get("recipient_count", 0)
    return recipient_count


def run_datamailer_campaign_action(
    request,
    action,
    client,
    external_key,
):
    if action == "sync":
        messages.success(request, "Datamailer campaign draft synced.")
        return None, True

    if action == "preview":
        preview = client.preview_campaign(external_key)
        messages.success(
            request, "Datamailer campaign preview rendered."
        )
        return preview, False

    if action == "test_send":
        recipients = parse_test_recipients(
            request.POST.get("test_recipients", "")
        )
        client.test_send_campaign(external_key, recipients)
        messages.success(
            request,
            f"Datamailer test send queued for {len(recipients)} recipient(s).",
        )
        return None, True

    if action == "queue":
        response = client.queue_campaign(external_key)
        recipient_count = datamailer_campaign_queue_recipient_count(
            response
        )
        messages.success(
            request,
            f"Datamailer campaign queued for {recipient_count} recipient(s).",
        )
        return None, True

    if action == "cancel":
        client.cancel_campaign(external_key)
        messages.success(request, "Datamailer campaign cancelled.")
        return None, True

    messages.error(request, "Unknown Datamailer campaign action.")
    return None, False


def handle_datamailer_campaign_action(request, campaign):
    action = request.POST.get("datamailer_action", "").strip()
    client = datamailer_campaign_client_or_message(request)
    if client is None:
        return None, True

    external_key = registration_campaign_external_key(campaign)

    try:
        if action in DATAMAILER_CAMPAIGN_UPSERT_ACTIONS:
            payload = registration_campaign_datamailer_payload(campaign)
            client.upsert_campaign(external_key, payload)

        return run_datamailer_campaign_action(
            request,
            action,
            client,
            external_key,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return None, False
    except requests.RequestException as exc:
        messages.error(
            request,
            f"Datamailer campaign request failed: {exc}",
        )
        return None, False


@staff_required
def course_list(request):
    """List all courses with admin actions"""
    courses = Course.objects.all().order_by("finished", "-id")

    context = {
        "courses": courses,
    }

    return render(request, "cadmin/course_list.html", context)


def course_homeworks_for_admin(course):
    homeworks = list(
        Homework.objects.filter(course=course).order_by("due_date")
    )
    for homework in homeworks:
        homework.submissions_count = Submission.objects.filter(
            homework=homework
        ).count()
        homework.can_score = homework.state in [
            HomeworkState.OPEN.value,
            HomeworkState.CLOSED.value,
        ]
    return homeworks


def course_projects_for_admin(course):
    projects = list(Project.objects.filter(course=course).order_by("id"))
    for project in projects:
        project.submissions_count = ProjectSubmission.objects.filter(
            project=project
        ).count()
        project.needs_review_assignment = (
            project.state == ProjectState.COLLECTING_SUBMISSIONS.value
        )
        project.needs_scoring = (
            project.state == ProjectState.PEER_REVIEWING.value
        )
    return projects


def course_support_metrics(course):
    enrollments = Enrollment.objects.filter(course=course)
    return {
        "disabled_lip": enrollments.filter(
            disable_learning_in_public=True
        ).count(),
        "zero_score": enrollments.filter(total_score=0).count(),
        "hidden_leaderboard": enrollments.filter(
            display_on_leaderboard=False
        ).count(),
        "open_complaints": LeaderboardComplaint.objects.filter(
            enrollment__course=course,
            resolved=False,
        ).count(),
    }


def course_registration_metrics(course):
    campaigns = (
        RegistrationCampaign.objects.filter(current_course=course)
        .select_related("current_course")
        .order_by("title", "slug")
    )
    return {
        "registration_metrics": [
            registration_campaign_metrics(campaign)
            for campaign in campaigns
        ],
        "primary_campaign": campaigns.first(),
    }


def course_admin_context(course):
    context = course_registration_metrics(course)
    context.update(
        {
            "course": course,
            "homeworks": course_homeworks_for_admin(course),
            "projects": course_projects_for_admin(course),
            "total_enrollments": course.enrollment_set.count(),
            "support_metrics": course_support_metrics(course),
        }
    )
    return context


def send_audit_totals():
    return DatamailerSendAudit.objects.aggregate(
        total=Count("id"),
        intended_count=Sum("intended_count"),
        created_count=Sum("created_count"),
        enqueued_count=Sum("enqueued_count"),
        skipped_count=Sum("skipped_count"),
        idempotent_replay_count=Sum("idempotent_replay_count"),
    )


def send_audit_grouped(field):
    return list(
        DatamailerSendAudit.objects.values(field)
        .annotate(
            count=Count("id"),
            intended_count=Sum("intended_count"),
            enqueued_count=Sum("enqueued_count"),
            skipped_count=Sum("skipped_count"),
        )
        .order_by(field)
    )


def datamailer_operator_commands():
    return [
        {
            "title": "Bootstrap contacts",
            "description": "Load active CMP users into Datamailer contacts.",
            "command": "uv run python manage.py sync_datamailer_contacts --active-only",
        },
        {
            "title": "Bootstrap recipient lists",
            "description": (
                "Load the target path-key audience tree from CMP source data."
            ),
            "command": (
                "uv run python manage.py sync_datamailer_recipient_lists "
                "<kind> --reconcile"
            ),
        },
        {
            "title": "Audit list drift",
            "description": (
                "Compare one CMP recipient-list source with Datamailer members."
            ),
            "command": (
                "uv run python manage.py audit_datamailer_recipient_lists "
                "<kind> --fail-on-drift"
            ),
        },
        {
            "title": "Repair list drift",
            "description": (
                "Reconcile Datamailer to the CMP snapshot for one source."
            ),
            "command": (
                "uv run python manage.py audit_datamailer_recipient_lists "
                "<kind> --repair"
            ),
        },
    ]


def requeue_datamailer_outbox_events():
    now = timezone.now()
    return DatamailerOutboxEvent.objects.filter(
        status__in=[
            DatamailerOutboxStatus.FAILED,
            DatamailerOutboxStatus.DEAD,
        ]
    ).update(
        status=DatamailerOutboxStatus.RETRYING,
        next_attempt_at=now,
        last_error="",
        updated_at=now,
    )


def handle_datamailer_operations_post(request):
    if request.POST.get("action") != "requeue":
        return None

    requeued = requeue_datamailer_outbox_events()
    messages.success(
        request,
        f"Requeued {requeued} Datamailer outbox event(s).",
    )
    return redirect("cadmin_datamailer_operations")


def recent_failed_datamailer_outbox_events():
    return DatamailerOutboxEvent.objects.filter(
        status__in=[
            DatamailerOutboxStatus.RETRYING,
            DatamailerOutboxStatus.FAILED,
            DatamailerOutboxStatus.DEAD,
        ]
    ).exclude(last_error="")[:10]


def recent_failed_datamailer_sends():
    return DatamailerSendAudit.objects.filter(
        status=DatamailerSendAuditStatus.FAILED,
    )[:10]


def normalized_send_totals(send_totals):
    return {
        "total": send_totals["total"] or 0,
        "intended_count": send_totals["intended_count"] or 0,
        "created_count": send_totals["created_count"] or 0,
        "enqueued_count": send_totals["enqueued_count"] or 0,
        "skipped_count": send_totals["skipped_count"] or 0,
        "idempotent_replay_count": (
            send_totals["idempotent_replay_count"] or 0
        ),
        "failed": DatamailerSendAudit.objects.filter(
            status=DatamailerSendAuditStatus.FAILED,
        ).count(),
    }


def datamailer_outbox_status_rows(outbox_summary):
    return [
        {
            "status": status,
            "count": outbox_summary["event_counts"].get(status, 0),
        }
        for status in DatamailerOutboxStatus.values
    ]


def datamailer_operations_context():
    outbox_summary = datamailer_outbox_status_summary()
    return {
        "outbox_summary": outbox_summary,
        "outbox_statuses": datamailer_outbox_status_rows(
            outbox_summary
        ),
        "recent_failed_events": recent_failed_datamailer_outbox_events(),
        "send_totals": normalized_send_totals(send_audit_totals()),
        "send_by_status": send_audit_grouped("status"),
        "send_by_type": send_audit_grouped("send_type"),
        "recent_failed_sends": recent_failed_datamailer_sends(),
        "operator_commands": datamailer_operator_commands(),
        "recipient_list_kinds": DATAMAILER_RECIPIENT_LIST_KINDS,
    }


@staff_required
def datamailer_operations(request):
    if request.method == "POST":
        response = handle_datamailer_operations_post(request)
        if response is not None:
            return response

    return render(
        request,
        "cadmin/datamailer_operations.html",
        datamailer_operations_context(),
    )


@staff_required
def datamailer_events(request):
    events = DatamailerContactEvent.objects.all()
    event_type = request.GET.get("event_type", "").strip()
    search_query = request.GET.get("q", "").strip()

    if event_type:
        events = events.filter(event_type=event_type)
    if search_query:
        events = events.filter(
            Q(email__icontains=search_query)
            | Q(event_id__icontains=search_query)
            | Q(client__icontains=search_query)
            | Q(audience__icontains=search_query)
            | Q(preference_key__icontains=search_query)
        )

    event_types = list(
        DatamailerContactEvent.objects.order_by("event_type")
        .values_list("event_type", flat=True)
        .distinct()
    )
    events_page = paginate_queryset(request, events, per_page=50)
    total_events = DatamailerContactEvent.objects.count()
    since = timezone.now() - timedelta(hours=24)
    metrics = {
        "total": total_events,
        "last_24h": DatamailerContactEvent.objects.filter(
            created_at__gte=since
        ).count(),
        "duplicates": DatamailerContactEvent.objects.aggregate(
            total=Sum("duplicate_count")
        )["total"]
        or 0,
        "by_type": count_by(
            DatamailerContactEvent.objects.all(), "event_type"
        ),
    }

    return render(
        request,
        "cadmin/datamailer_events.html",
        {
            "events_page": events_page,
            "event_types": event_types,
            "selected_event_type": event_type,
            "search_query": search_query,
            "metrics": metrics,
            "page_range": events_page.paginator.get_elided_page_range(
                events_page.number
            ),
            "pagination_querystring": pagination_querystring(request),
        },
    )


@staff_required
def course_admin(request, course_slug):
    """Admin panel for a specific course"""
    course = get_object_or_404(Course, slug=course_slug)
    return render(
        request,
        "cadmin/course_admin.html",
        course_admin_context(course),
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
            return redirect(
                "cadmin_campaign_edit", campaign_slug=campaign.slug
            )
    else:
        form = RegistrationCampaignForm(
            initial=campaign_form_initial(request)
        )

    context = {
        "form": form,
        "campaign": None,
        "course": campaign_form_course(form),
        "page_title": "Create registration landing page",
        "submit_label": "Create landing page",
    }
    return render(request, "cadmin/campaign_form.html", context)


@staff_required
def campaign_edit(request, campaign_slug):
    campaign = get_object_or_404(
        RegistrationCampaign.objects.select_related("current_course"),
        slug=campaign_slug,
    )
    datamailer_preview = None

    if request.method == "POST" and request.POST.get(
        "datamailer_action"
    ):
        datamailer_preview, should_redirect = (
            handle_datamailer_campaign_action(request, campaign)
        )
        if should_redirect:
            return redirect(
                "cadmin_campaign_edit", campaign_slug=campaign.slug
            )
        form = RegistrationCampaignForm(instance=campaign)
    elif request.method == "POST":
        form = RegistrationCampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            campaign = form.save()
            messages.success(
                request, "Registration landing page saved."
            )
            return redirect(
                "cadmin_campaign_edit", campaign_slug=campaign.slug
            )
    else:
        form = RegistrationCampaignForm(instance=campaign)

    context = {
        "form": form,
        "campaign": campaign,
        "course": campaign.current_course,
        "page_title": "Edit registration landing page",
        "submit_label": "Save changes",
        "datamailer_preview": datamailer_preview,
        **datamailer_campaign_context(campaign),
    }
    return render(request, "cadmin/campaign_form.html", context)


@staff_required
def campaign_registrations(request, campaign_slug):
    campaign = get_object_or_404(
        RegistrationCampaign.objects.select_related("current_course"),
        slug=campaign_slug,
    )
    registrations = CourseRegistration.objects.filter(
        campaign=campaign
    ).select_related("campaign", "course", "user")

    filters = {
        "role": request.GET.get("role", "").strip(),
        "country": request.GET.get("country", "").strip(),
        "region": request.GET.get("region", "").strip(),
    }
    for field, value in filters.items():
        if value:
            registrations = registrations.filter(**{field: value})

    search_query = request.GET.get("q", "").strip()
    if search_query:
        registrations = registrations.filter(
            Q(email_normalized__icontains=search_query)
            | Q(name__icontains=search_query)
        )

    metrics = registration_campaign_metrics(campaign)
    registrations_page = paginate_queryset(request, registrations, 50)

    context = {
        "campaign": campaign,
        "course": campaign.current_course,
        "registrations_page": registrations_page,
        "page_range": registrations_page.paginator.get_elided_page_range(
            registrations_page.number
        ),
        "metrics": metrics,
        "filters": filters,
        "search_query": search_query,
        "pagination_querystring": pagination_querystring(request),
    }
    return render(
        request, "cadmin/campaign_registrations.html", context
    )


@staff_required
def homework_score(request, course_slug, homework_slug):
    """Score a homework"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    status, message = score_homework_submissions(homework.id)

    if status == HomeworkScoringStatus.OK:
        messages.success(request, message)
        send_homework_score_notification(homework)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_set_correct_answers(request, course_slug, homework_slug):
    """Set correct answers to most popular for a homework"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    fill_correct_answers(homework)

    messages.success(
        request,
        f"Correct answers for {homework.title} set to most popular",
    )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_clear_correct_answers(request, course_slug, homework_slug):
    """Clear correct answers for a homework"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    updated_count = clear_correct_answers(homework)

    messages.success(
        request,
        f"Correct answers for {updated_count} questions in {homework.title} cleared",
    )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_submissions(request, course_slug, homework_slug):
    """View all submissions for a homework"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    search_query = request.GET.get("q", "").strip()

    submissions = (
        Submission.objects.filter(homework=homework)
        .select_related("student", "enrollment")
        .order_by("-submitted_at")
    )

    if search_query:
        submissions = submissions.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
        )

    submissions_page = paginate_queryset(request, submissions)

    submissions_data = []
    for submission in submissions_page.object_list:
        submissions_data.append(
            {
                "submission": submission,
            }
        )

    context = {
        "course": course,
        "homework": homework,
        "submissions_data": submissions_data,
        "submissions_page": submissions_page,
        "search_query": search_query,
        "pagination_querystring": pagination_querystring(request),
    }

    return render(request, "cadmin/homework_submissions.html", context)


def _questions_with_submission_answers(homework, submission):
    questions = Question.objects.filter(homework=homework).order_by(
        "id"
    )
    answers = Answer.objects.filter(
        submission=submission
    ).select_related("question")
    answer_map = {answer.question_id: answer for answer in answers}
    return questions, [
        {
            "question": question,
            "answer": answer_map.get(question.id),
            "answer_text": (
                answer_map[question.id].answer_text
                if question.id in answer_map
                else ""
            ),
        }
        for question in questions
    ]


def _homework_submission_edit_redirect(course_slug, homework_slug):
    return redirect(
        "cadmin_homework_submissions",
        course_slug=course_slug,
        homework_slug=homework_slug,
    )


def _handle_homework_submission_edit_post(
    request,
    *,
    submission,
    questions,
    course_slug,
    homework_slug,
):
    form = HomeworkSubmissionEditForm(
        request.POST,
        submission=submission,
        questions=questions,
    )

    if not form.is_valid():
        messages.error(
            request,
            f"Error updating submission: {first_form_error(form)}",
        )
        return None

    try:
        update_homework_submission_from_admin(
            submission,
            form.cleaned_data,
        )
    except Exception as e:
        messages.error(request, f"Error updating submission: {e}")
        return None

    messages.success(
        request,
        f"Homework submission for {submission.student.username} updated successfully",
    )
    return _homework_submission_edit_redirect(
        course_slug, homework_slug
    )


@staff_required
def homework_submission_edit(
    request, course_slug, homework_slug, submission_id
):
    """Edit a homework submission"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    submission = get_object_or_404(
        Submission, id=submission_id, homework=homework
    )

    questions, questions_with_answers = (
        _questions_with_submission_answers(
            homework,
            submission,
        )
    )

    if request.method == "POST":
        faq_contribution_url = request.POST.get(
            "faq_contribution_url", ""
        ).strip()
        faq_score = request.POST.get("faq_score", submission.faq_score)
        response = _handle_homework_submission_edit_post(
            request,
            submission=submission,
            questions=questions,
            course_slug=course_slug,
            homework_slug=homework_slug,
        )
        if response is not None:
            return response
    else:
        faq_contribution_url = submission.faq_contribution_url or ""
        faq_score = submission.faq_score

    context = {
        "course": course,
        "homework": homework,
        "submission": submission,
        "questions_with_answers": questions_with_answers,
        "learning_in_public_links_text": "\n".join(
            submission.learning_in_public_links or []
        ),
        "faq_contribution_url": faq_contribution_url,
        "faq_score": faq_score,
    }

    return render(
        request, "cadmin/homework_submission_edit.html", context
    )


@staff_required
def project_assign_reviews(request, course_slug, project_slug):
    """Assign peer reviews for a project"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    status, message = assign_peer_reviews_for_project(project)

    if status == ProjectActionStatus.OK:
        messages.success(request, message)
        send_peer_review_assignment_notification(project)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def project_score(request, course_slug, project_slug):
    """Score a project"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    status, message = score_project(project)

    if status == ProjectActionStatus.OK:
        messages.success(request, message)
        send_project_score_notification(project)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def project_submissions(request, course_slug, project_slug):
    """View all submissions for a project"""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    project.needs_review_assignment = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )
    project.needs_scoring = (
        project.state == ProjectState.PEER_REVIEWING.value
    )
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    submissions, project_filter_counts = project_submission_list_data(
        project,
        search_query,
        status_filter,
    )

    submissions_page = paginate_queryset(
        request,
        submissions,
        per_page=CADMIN_PROJECT_SUBMISSIONS_PAGE_SIZE,
    )

    context = {
        "course": course,
        "project": project,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "page_range": submissions_page.paginator.get_elided_page_range(
            submissions_page.number
        ),
        "project_filter_counts": project_filter_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "pagination_querystring": pagination_querystring(request),
    }

    return render(request, "cadmin/project_submissions.html", context)


def _project_submission_edit_objects(
    course_slug,
    project_slug,
    submission_id,
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    submission = get_object_or_404(
        ProjectSubmission, id=submission_id, project=project
    )
    return course, project, submission


def _project_review_criteria(course):
    return ReviewCriteria.objects.filter(course=course).order_by("id")


def _project_evaluation_score_map(submission):
    return {
        score.review_criteria_id: score
        for score in ProjectEvaluationScore.objects.filter(
            submission=submission
        )
    }


def _criteria_with_project_scores(review_criteria, submission):
    evaluation_scores = _project_evaluation_score_map(submission)
    return [
        {
            "criteria": criteria,
            "score": (
                evaluation_scores[criteria.id].score
                if criteria.id in evaluation_scores
                else 0
            ),
            "score_id": (
                evaluation_scores[criteria.id].id
                if criteria.id in evaluation_scores
                else None
            ),
        }
        for criteria in review_criteria
    ]


def _project_submission_edit_redirect(course_slug, project_slug):
    return redirect(
        "cadmin_project_submissions",
        course_slug=course_slug,
        project_slug=project_slug,
    )


def _handle_project_submission_edit_post(
    request,
    *,
    submission,
    review_criteria,
    course_slug,
    project_slug,
):
    form = ProjectSubmissionEditForm(
        request.POST,
        review_criteria=review_criteria,
    )
    if not form.is_valid():
        messages.error(
            request,
            f"Error updating submission: {first_form_error(form)}",
        )
        return None

    update_project_submission_from_admin(
        submission,
        form.cleaned_data,
    )
    messages.success(
        request,
        f"Project submission for {submission.student.username} updated successfully",
    )
    return _project_submission_edit_redirect(course_slug, project_slug)


@staff_required
def project_submission_edit(
    request, course_slug, project_slug, submission_id
):
    """Edit a project submission"""
    course, project, submission = _project_submission_edit_objects(
        course_slug,
        project_slug,
        submission_id,
    )

    review_criteria = _project_review_criteria(course)
    criteria_with_scores = _criteria_with_project_scores(
        review_criteria,
        submission,
    )

    if request.method == "POST":
        response = _handle_project_submission_edit_post(
            request,
            submission=submission,
            review_criteria=review_criteria,
            course_slug=course_slug,
            project_slug=project_slug,
        )
        if response is not None:
            return response

    context = {
        "course": course,
        "project": project,
        "submission": submission,
        "criteria_with_scores": criteria_with_scores,
    }

    return render(
        request, "cadmin/project_submission_edit.html", context
    )


@staff_required
def enrollments_list(request, course_slug):
    """List all enrollments for a course"""
    course = get_object_or_404(Course, slug=course_slug)
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    enrollments, enrollment_filter_counts = enrollment_list_data(
        course,
        search_query,
        status_filter,
    )

    enrollments_page = paginate_queryset(request, enrollments)

    context = {
        "course": course,
        "enrollments": enrollments_page.object_list,
        "enrollments_page": enrollments_page,
        "total_enrollments": len(enrollments),
        "enrollment_filter_counts": enrollment_filter_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "pagination_querystring": pagination_querystring(request),
    }

    return render(request, "cadmin/enrollments.html", context)


def complaint_enrollments(course):
    return (
        Enrollment.objects.filter(course=course)
        .select_related("student")
        .annotate(
            open_complaints=Count(
                "complaints",
                filter=Q(complaints__resolved=False),
            ),
            total_complaints=Count("complaints"),
        )
        .filter(total_complaints__gt=0)
        .order_by(
            "-open_complaints",
            "-total_complaints",
            "position_on_leaderboard",
        )
    )


def complaints_grouped_by_enrollment(course):
    complaints_by_enrollment = defaultdict(list)
    complaints = (
        LeaderboardComplaint.objects.filter(enrollment__course=course)
        .select_related("enrollment", "reporter", "resolved_by")
        .order_by("resolved", "-created_at")
    )
    for complaint in complaints:
        complaints_by_enrollment[complaint.enrollment_id].append(
            complaint
        )
    return complaints_by_enrollment


def complaint_enrollment_rows(course):
    complaints_by_enrollment = complaints_grouped_by_enrollment(course)
    return [
        {
            "enrollment": enrollment,
            "complaints": complaints_by_enrollment[enrollment.id],
        }
        for enrollment in complaint_enrollments(course)
    ]


def leaderboard_complaint_counts(course):
    complaints = LeaderboardComplaint.objects.filter(
        enrollment__course=course,
    )
    return {
        "open_complaints_count": complaints.filter(
            resolved=False,
        ).count(),
        "total_complaints_count": complaints.count(),
    }


def leaderboard_complaints_context(course):
    context = leaderboard_complaint_counts(course)
    context.update(
        {
            "course": course,
            "enrollment_rows": complaint_enrollment_rows(course),
        }
    )
    return context


@staff_required
def leaderboard_complaints(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    return render(
        request,
        "cadmin/leaderboard_complaints.html",
        leaderboard_complaints_context(course),
    )


@staff_required
def leaderboard_complaint_resolve(request, course_slug, complaint_id):
    if request.method != "POST":
        return redirect(
            "cadmin_leaderboard_complaints", course_slug=course_slug
        )

    course = get_object_or_404(Course, slug=course_slug)
    complaint = get_object_or_404(
        LeaderboardComplaint,
        id=complaint_id,
        enrollment__course=course,
    )
    complaint.resolved = True
    complaint.resolved_at = timezone.now()
    complaint.resolved_by = request.user
    complaint.save(
        update_fields=["resolved", "resolved_at", "resolved_by"]
    )

    messages.success(request, "Flag marked as resolved.")
    return redirect(
        "cadmin_leaderboard_complaints", course_slug=course_slug
    )


def toggle_learning_in_public_response(
    request,
    enrollment,
    course_slug,
    enrollment_id,
):
    disabled = not enrollment.disable_learning_in_public
    set_learning_in_public_disabled(enrollment, disabled)
    enrollment.disable_learning_in_public = disabled

    if enrollment.disable_learning_in_public:
        messages.success(
            request,
            f"Learning in public disabled for {enrollment.student.username}. All scores zeroed out.",
        )
    else:
        messages.success(
            request,
            f"Learning in public re-enabled for {enrollment.student.username}. You may need to re-score homework and projects.",
        )

    return redirect(
        "cadmin_enrollment_edit",
        course_slug=course_slug,
        enrollment_id=enrollment_id,
    )


def enrollment_homework_submissions(enrollment):
    return (
        Submission.objects.filter(enrollment=enrollment)
        .select_related("homework")
        .order_by("-submitted_at")
    )


def enrollment_project_submissions(enrollment):
    return (
        ProjectSubmission.objects.filter(enrollment=enrollment)
        .select_related("project")
        .order_by("-submitted_at")
    )


def total_project_lip_score(project_submissions):
    return sum(
        submission.project_learning_in_public_score
        + submission.peer_review_learning_in_public_score
        for submission in project_submissions
    )


def enrollment_edit_context(course, enrollment):
    homework_submissions = enrollment_homework_submissions(enrollment)
    project_submissions = enrollment_project_submissions(enrollment)
    return {
        "course": course,
        "enrollment": enrollment,
        "homework_submissions": homework_submissions,
        "homework_submissions_count": homework_submissions.count(),
        "project_submissions": project_submissions,
        "project_submissions_count": project_submissions.count(),
        "total_homework_lip_score": sum(
            submission.learning_in_public_score
            for submission in homework_submissions
        ),
        "total_project_lip_score": total_project_lip_score(
            project_submissions
        ),
    }


@staff_required
def enrollment_edit(request, course_slug, enrollment_id):
    """Edit an enrollment - mainly to disable learning in public"""
    course = get_object_or_404(Course, slug=course_slug)
    enrollment = get_object_or_404(
        Enrollment, id=enrollment_id, course=course
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_learning_in_public":
            return toggle_learning_in_public_response(
                request,
                enrollment,
                course_slug,
                enrollment_id,
            )

    return render(
        request,
        "cadmin/enrollment_edit.html",
        enrollment_edit_context(course, enrollment),
    )
