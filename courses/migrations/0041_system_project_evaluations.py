import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("courses", "0040_courseregistration_company_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemProjectEvaluation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=200)),
                ("feedback", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="system_project_evaluations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="system_evaluations",
                        to="courses.projectsubmission",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SystemEvaluationCriteriaResponse",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("answer", models.CharField(max_length=255)),
                (
                    "criteria",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="courses.reviewcriteria",
                    ),
                ),
                (
                    "evaluation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="criteria_responses",
                        to="courses.systemprojectevaluation",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="systemprojectevaluation",
            constraint=models.UniqueConstraint(
                fields=("submission", "idempotency_key"),
                name="unique_system_evaluation_idempotency_key",
            ),
        ),
        migrations.AddConstraint(
            model_name="systemevaluationcriteriaresponse",
            constraint=models.UniqueConstraint(
                fields=("evaluation", "criteria"),
                name="unique_system_evaluation_criteria_response",
            ),
        ),
    ]
