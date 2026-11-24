"""GenMedia started: accepted-student info drops the past pre-course Q&A."""

from django.db import migrations


COURSE_SLUG = "production-ai-agents-generative-media"

# Pre-start values seeded by 0069_accepted_student_info. Both point at the
# pre-course Q&A event page, which happened on 10 Nov 2026.
PRE_COURSE_SCHEDULE_DETAILS = (
    "Pre-course Q&A: Tue 10 Nov 2026, 17:00–18:00 Europe/Berlin"
)
PRE_COURSE_SCHEDULE_URL = "https://luma.com/i4x6x2zy"

STARTED_SCHEDULE_DETAILS = (
    "Module 1 is open. Catch up with the launch session recording: "
    "https://www.youtube.com/watch?v=Y5__PUmOTdg\n"
    "Pre-course Q&A recording: https://www.youtube.com/watch?v=iACtrkiXndw"
)
STARTED_SCHEDULE_URL = ""


def replace_pre_course_schedule(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    # Runs in installations without the example course as well.
    course = Course.objects.filter(slug=COURSE_SLUG).first()
    if course is None:
        return

    # Staff may already have edited the course in Django admin. Only the
    # recognised pre-start text is replaced; anything else is left alone.
    details = (course.live_session_schedule_details or "").strip()
    schedule_url = (course.live_session_schedule_url or "").strip()
    if (
        details != PRE_COURSE_SCHEDULE_DETAILS
        or schedule_url != PRE_COURSE_SCHEDULE_URL
    ):
        return

    course.live_session_schedule_details = STARTED_SCHEDULE_DETAILS
    course.live_session_schedule_url = STARTED_SCHEDULE_URL
    course.save(
        update_fields=[
            "live_session_schedule_details",
            "live_session_schedule_url",
        ]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0071_alter_applicationnotification_status"),
    ]

    operations = [
        migrations.RunPython(
            replace_pre_course_schedule,
            migrations.RunPython.noop,
        ),
    ]
