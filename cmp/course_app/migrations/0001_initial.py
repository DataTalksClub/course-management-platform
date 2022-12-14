# Generated by Django 4.1.1 on 2022-09-29 18:57

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Course",
            fields=[
                (
                    "id",
                    models.AutoField(
                        editable=False, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, null=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="Homework",
            fields=[
                (
                    "id",
                    models.AutoField(
                        editable=False, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, null=True)),
                ("hidden", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "active"),
                            ("inactive", "inactive"),
                            ("finished", "finished"),
                        ],
                        max_length=8,
                    ),
                ),
                ("due_date", models.DateTimeField()),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="course_app.course",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Submission",
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
                ("participant_email", models.EmailField(max_length=255)),
                ("answer", models.JSONField(blank=True, null=True)),
                ("status", models.CharField(max_length=255)),
                (
                    "homework",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="course_app.homework",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Question",
            fields=[
                (
                    "id",
                    models.AutoField(
                        editable=False, primary_key=True, serialize=False, unique=True
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("text", "text"),
                            ("radio", "radio"),
                            ("links", "links"),
                        ],
                        max_length=5,
                    ),
                ),
                ("question", models.TextField(max_length=1000)),
                ("options", models.JSONField(blank=True, null=True)),
                ("correct_answer", models.JSONField(blank=True, null=True)),
                (
                    "hw",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="course_app.homework",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Leaderboard",
            fields=[
                (
                    "id",
                    models.AutoField(
                        editable=False, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("email_hash", models.CharField(max_length=40)),
                ("scores", models.JSONField()),
                ("total_score", models.IntegerField(blank=True, default=0, null=True)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="course_app.course",
                    ),
                ),
            ],
        ),
    ]
