from datetime import date

import django.core.validators
from django.db import migrations, models


COURSE_SLUG = "production-ai-agents-generative-media"
COURSE_REPOSITORY_URL = (
    "https://github.com/DataTalksClub/"
    "production-ai-agents-for-media-generation"
)
LIVE_SESSION_SCHEDULE_DETAILS = (
    "Pre-course Q&A: Tue 10 Nov 2026, 17:00–18:00 Europe/Berlin"
)
LIVE_SESSION_SCHEDULE_URL = "https://luma.com/i4x6x2zy"
SUPPORT_CHANNEL_NAME = "#course-ai-mediagen on Slack"
SUPPORT_CHANNEL_URL = (
    "https://app.slack.com/client/T01ATQK62F8/C0CEG1BUDKL"
)


def populate_accepted_student_info(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    RegistrationCampaign = apps.get_model(
        "courses", "RegistrationCampaign"
    )
    try:
        course = Course.objects.get(slug=COURSE_SLUG)
    except Course.DoesNotExist as exc:
        raise RuntimeError(
            f"Required course {COURSE_SLUG!r} is missing"
        ) from exc

    course.start_date = date(2026, 11, 16)
    course.github_repo_url = COURSE_REPOSITORY_URL
    course.live_session_schedule_details = LIVE_SESSION_SCHEDULE_DETAILS
    course.live_session_schedule_url = LIVE_SESSION_SCHEDULE_URL
    course.support_channel_name = SUPPORT_CHANNEL_NAME
    course.support_channel_url = SUPPORT_CHANNEL_URL
    course.support_email = ""
    course.save(
        update_fields=[
            "start_date",
            "github_repo_url",
            "live_session_schedule_details",
            "live_session_schedule_url",
            "support_channel_name",
            "support_channel_url",
            "support_email",
        ]
    )

    try:
        campaign = RegistrationCampaign.objects.get(slug=COURSE_SLUG)
    except RegistrationCampaign.DoesNotExist as exc:
        raise RuntimeError(
            f"Required registration campaign {COURSE_SLUG!r} is missing"
        ) from exc

    marketing = campaign.marketing_markdown or ""
    q_and_a_schedule = (
        "- Pre-Course Live Q&A: Tue 10 Nov 2026, "
        "17:00–18:00 Europe/Berlin"
    )
    if "17:00–18:00 Europe/Berlin" not in marketing:
        marketing = marketing.replace(
            "- Welcome: Tue 10 Nov 2026",
            q_and_a_schedule,
        )
        marketing = marketing.replace(
            "- Pre-Course Live Q&A: Tue 10 Nov 2026",
            q_and_a_schedule,
        )
    replacements = {
        "- Course starts: Mon 17 Nov 2026": (
            "- Course starts: Mon 16 Nov 2026"
        ),
        "- Module 1 (two weeks): 17-30 Nov 2026 (through Sun 30 Nov)": (
            "- Module 1 (two weeks): Mon 16 – Sun 29 Nov 2026"
        ),
        "- Module 2: 1-7 Dec 2026": (
            "- Module 2: Mon 30 Nov – Sun 6 Dec 2026"
        ),
        "- Module 3: 8-14 Dec 2026": (
            "- Module 3: Mon 7 – Sun 13 Dec 2026"
        ),
        "- Module 4: 15-21 Dec 2026": (
            "- Module 4: Mon 14 – Sun 20 Dec 2026"
        ),
        "- Course ends: Sun 21 Dec 2026": (
            "- Teaching ends: Sun 20 Dec 2026"
        ),
    }
    for stale_text, current_text in replacements.items():
        marketing = marketing.replace(stale_text, current_text)
    if marketing != campaign.marketing_markdown:
        campaign.marketing_markdown = marketing
        campaign.save(update_fields=["marketing_markdown"])

    meta_description = getattr(campaign, "meta_description", "") or ""
    if "starts 17 Nov" in meta_description:
        campaign.meta_description = meta_description.replace(
            "starts 17 Nov", "starts 16 Nov"
        )
        campaign.save(update_fields=["meta_description"])


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0068_registration_utm_attribution"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="live_session_schedule_details",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Student-facing dates and times for live sessions, "
                    "including the pre-course Q&A."
                ),
            ),
        ),
        migrations.AddField(
            model_name="course",
            name="live_session_schedule_url",
            field=models.URLField(
                blank=True,
                default="",
                validators=[django.core.validators.URLValidator()],
                help_text=(
                    "Link to the live session and Q&A schedule or event page."
                ),
            ),
        ),
        migrations.AddField(
            model_name="course",
            name="support_channel_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Student help channel label, for example a Slack channel."
                ),
                max_length=150,
            ),
        ),
        migrations.AddField(
            model_name="course",
            name="support_channel_url",
            field=models.URLField(
                blank=True,
                default="",
                validators=[django.core.validators.URLValidator()],
                help_text=(
                    "Link to the course help channel, such as a Slack channel."
                ),
            ),
        ),
        migrations.AddField(
            model_name="course",
            name="support_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Optional course support email address.",
                max_length=254,
            ),
        ),
        migrations.RunPython(
            populate_accepted_student_info,
            migrations.RunPython.noop,
        ),
    ]
