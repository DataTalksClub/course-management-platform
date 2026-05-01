from django.db import migrations, models


def backfill_certificate_name_from_latest_enrollment(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    Enrollment = apps.get_model("courses", "Enrollment")
    db_alias = schema_editor.connection.alias

    fields = [
        "certificate_name",
        "github_url",
        "linkedin_url",
        "personal_website_url",
        "about_me",
    ]

    enrollments = (
        Enrollment.objects.using(db_alias)
        .order_by("student_id", "-enrollment_date", "-id")
        .values("student_id", *fields)
    )

    profile_updates = {}
    for enrollment in enrollments.iterator():
        student_id = enrollment["student_id"]
        profile = profile_updates.setdefault(student_id, {})
        for field in fields:
            value = enrollment[field]
            if value and field not in profile:
                profile[field] = value

    for student_id, profile in profile_updates.items():
        if profile:
            CustomUser.objects.using(db_alias).filter(id=student_id).update(
                **profile
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_customuser_dark_mode"),
        ("courses", "0026_enrollment_disable_learning_in_public_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="about_me",
            field=models.TextField(
                blank=True,
                null=True,
                verbose_name="About me",
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="github_url",
            field=models.URLField(
                blank=True,
                null=True,
                verbose_name="GitHub URL",
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="linkedin_url",
            field=models.URLField(
                blank=True,
                null=True,
                verbose_name="LinkedIn URL",
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="personal_website_url",
            field=models.URLField(
                blank=True,
                null=True,
                verbose_name="Personal website URL",
            ),
        ),
        migrations.RunPython(
            backfill_certificate_name_from_latest_enrollment,
            migrations.RunPython.noop,
        ),
    ]
