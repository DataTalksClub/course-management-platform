from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from accounts.models import CustomUser
from courses.random_names import generate_random_name

from .start_time import StartTimeModel

User = CustomUser


class Course(StartTimeModel):
    slug = models.SlugField(unique=True, blank=False)
    title = models.CharField(max_length=200)

    description = models.TextField()
    start_date = models.DateField(
        blank=True,
        null=True,
        help_text="The public start date for the course.",
    )
    end_date = models.DateField(
        blank=True,
        null=True,
        help_text="The public end date for the course.",
    )
    registration_url = models.URLField(
        blank=True,
        validators=[URLValidator()],
        help_text="Optional external registration page for the course.",
    )
    github_repo_url = models.URLField(
        blank=True,
        validators=[URLValidator()],
        help_text="Optional GitHub repository URL for the course.",
    )
    students = models.ManyToManyField(
        User, through="Enrollment", related_name="courses_enrolled"
    )

    social_media_hashtag = models.CharField(
        max_length=100,
        blank=True,
        help_text="The hashtag associated with the course for social media use.",
    )

    first_homework_scored = models.BooleanField(
        default=False,
        blank=False,
        help_text="Whether the first homework has been scored. "
        + "We use that for deciding whether to show the leaderboard.",
    )

    finished = models.BooleanField(
        default=False,
        blank=False,
        help_text="Whether the course has finished.",
    )

    faq_document_url = models.URLField(
        blank=True,
        validators=[URLValidator()],
        help_text="The URL of the FAQ document for the course.",
    )

    min_projects_to_pass = models.IntegerField(
        default=1,
        blank=False,
        help_text="The minimum number of projects to pass the course.",
    )

    homework_problems_comments_field = models.BooleanField(
        default=False,
        help_text="Include field for problems and comments in homework",
    )

    project_passing_score = models.IntegerField(
        default=0,
        help_text="Minimum score required to pass any project in this course",
    )

    visible = models.BooleanField(
        default=True,
        blank=False,
        help_text="Whether the course is visible in the course list. "
        + "Non-visible courses are still accessible via direct link.",
    )

    requires_registration_approval = models.BooleanField(
        default=False,
        blank=False,
        help_text="Registration wall: when enabled, students can only "
        + "access the gated course path (homework, projects, enrollment) "
        + "after their registration is manually approved. "
        + "Without approval they can only audit public materials.",
    )

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()

        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError(
                    {
                        "end_date": (
                            "End date cannot be earlier than start date."
                        )
                    }
                )


class RegistrationCampaign(models.Model):
    slug = models.SlugField(unique=True, blank=False)
    title = models.CharField(max_length=200)
    edition_label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Displayed cohort label, for example '2026 cohort'.",
    )
    current_course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registration_campaigns",
        help_text="Course edition currently promoted by this form.",
    )
    is_active = models.BooleanField(default=True)

    marketing_markdown = models.TextField(blank=True)
    meta_description = models.TextField(blank=True)
    hero_image_url = models.URLField(
        blank=True,
        validators=[URLValidator()],
    )
    video_url = models.URLField(
        blank=True,
        validators=[URLValidator()],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "slug"]
        indexes = [
            models.Index(
                fields=["current_course", "is_active"],
                name="camp_course_active_idx",
            ),
        ]

    def __str__(self):
        return self.title


class EmailCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SYNCED = "synced", "Synced"
        QUEUE_PENDING = "queue_pending", "Queue Pending"
        QUEUED = "queued", "Queued"
        CANCELLED = "cancelled", "Cancelled"

    registration_campaign = models.ForeignKey(
        RegistrationCampaign,
        on_delete=models.CASCADE,
        related_name="email_campaigns",
    )
    subject = models.CharField(max_length=200)
    preview_text = models.CharField(max_length=255, blank=True)
    body_markdown = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    external_key = models.CharField(
        max_length=100, unique=True, editable=False
    )
    last_recipient_count = models.PositiveIntegerField(
        null=True, blank=True
    )
    queued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject

    def save(self, *args, **kwargs):
        if not self.external_key:
            from course_management.datamailer.keys import (
                generate_email_campaign_external_key,
            )

            self.external_key = generate_email_campaign_external_key(
                self.registration_campaign.slug
            )
        super().save(*args, **kwargs)


class CourseRegistration(models.Model):
    class Role(models.TextChoices):
        DATA_ENGINEER = "data_engineer", "Data Engineer"
        DATA_SCIENTIST = "data_scientist", "Data Scientist"
        DATA_ANALYST = "data_analyst", "Data Analyst"
        ML_ENGINEER = "ml_engineer", "ML Engineer"
        SOFTWARE_ENGINEER_BACKEND = (
            "software_engineer_backend",
            "Software Engineer (Backend)",
        )
        SOFTWARE_ENGINEER_OTHER = (
            "software_engineer_other",
            "Software Engineer (Frontend, Test, etc)",
        )
        STUDENT_STEM = "student_stem", "Student (STEM)"
        STUDENT_NON_STEM = "student_non_stem", "Student (Non-STEM)"
        FOUNDER_CTO = "founder_cto", "Founder/CTO"
        MLOPS_PLATFORM = "mlops_platform", "MLOps/Platform Engineer"
        OTHER = "other", "Other"

    class YearsExperience(models.TextChoices):
        LESS_THAN_1 = "lt1", "<1"
        ONE_TO_THREE = "1_3", "1–3"
        THREE_TO_SIX = "3_6", "3–6"
        SIX_PLUS = "6plus", "6+"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    campaign = models.ForeignKey(
        RegistrationCampaign,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registrations",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_registrations",
    )

    email = models.EmailField()
    email_normalized = models.EmailField(editable=False)
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=100)
    region = models.CharField(max_length=100)
    role = models.CharField(max_length=40, choices=Role.choices)
    comment = models.TextField(blank=True)
    accepted_newsletter = models.BooleanField(default=False)
    accepted_nebius_sharing = models.BooleanField(
        default=False,
        help_text="Share application with Nebius and Nebius Academy "
        "for review, credits and course operation.",
    )
    years_experience = models.CharField(
        max_length=10,
        choices=YearsExperience.choices,
        blank=True,
        default="",
        help_text="Years of professional software or ML experience.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Review status for registration-wall courses. "
        + "Only approved registrations unlock the gated course path.",
    )
    email_confirmed = models.BooleanField(
        default=False,
        help_text="Whether the registrant clicked the email "
        + "confirmation link (double opt-in).",
    )
    email_confirmation_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        default=None,
        help_text="Secret token for the email confirmation link. "
        + "Null for rows confirmed by the backfill migration.",
    )
    email_confirmation_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the latest confirmation email was sent.",
    )
    email_confirmation_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the email confirmation link was clicked.",
    )
    email_confirmation_resend_count = models.PositiveIntegerField(
        default=0,
        help_text="How many confirmation emails were sent "
        + "(initial send counts as the first).",
    )
    experience = models.TextField(
        blank=True,
        default="",
        help_text="Applicant role and experience summary.",
    )
    why_join = models.TextField(
        blank=True,
        default="",
        help_text="Why the applicant wants to join the course.",
    )
    linkedin_url = models.URLField(
        blank=True,
        default="",
        help_text="Optional LinkedIn profile URL.",
    )
    github_url = models.URLField(
        blank=True,
        default="",
        help_text="Optional GitHub profile URL.",
    )
    prereq_python = models.BooleanField(
        default=False,
        help_text="Self-check: comfortable with Python.",
    )
    prereq_docker = models.BooleanField(
        default=False,
        help_text="Self-check: Docker basics.",
    )
    prereq_http = models.BooleanField(
        default=False,
        help_text="Self-check: HTTP APIs.",
    )
    prereq_cli = models.BooleanField(
        default=False,
        help_text="Self-check: command line.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["campaign", "email_normalized"]
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["campaign", "email_normalized"],
                name="reg_camp_email_idx",
            ),
            models.Index(
                fields=["course", "email_normalized", "status"],
                name="reg_course_email_st_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        raw_email = self.email or ""
        email_stripped = raw_email.strip()
        self.email_normalized = email_stripped.lower()
        if self.campaign and self.course_id is None:
            self.course = self.campaign.current_course
        from django.db import transaction
        from course_management.relay.application_notifications import (
            queue_application_notifications,
        )

        # Lock the persisted status so concurrent/repeated review requests
        # cannot enqueue the same decision twice. Queue in the same commit.
        with transaction.atomic():
            previous = None
            if self.pk:
                previous = type(self).objects.select_for_update().filter(
                    pk=self.pk,
                ).values_list("status", flat=True).first()
            super().save(*args, **kwargs)
            fields = kwargs.get("update_fields")
            if previous is None or fields is None or "status" in fields:
                queue_application_notifications(self, previous)

    @property
    def confirmation_management_token(self):
        from courses.registration_confirmation import management_token
        return management_token(self)

    def __str__(self):
        return f"{self.email_normalized} registered for {self.campaign}"


class Enrollment(models.Model):
    class Meta:
        unique_together = ["student", "course"]
        indexes = [
            models.Index(
                fields=[
                    "course",
                    "display_on_leaderboard",
                    "position_on_leaderboard",
                    "id",
                ],
                name="enroll_lb_list_idx",
            ),
            models.Index(
                fields=["course", "total_score"],
                name="enroll_course_score_idx",
            ),
        ]

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrollment_date = models.DateTimeField(auto_now_add=True)

    display_name = models.CharField(
        verbose_name="Leaderboard name", max_length=255, blank=True,
        help_text="Name on the leaderboard"
    )
    display_on_leaderboard = models.BooleanField(default=True)
    display_public_profile = models.BooleanField(default=False)

    position_on_leaderboard = models.IntegerField(
        blank=True, null=True, default=None
    )

    certificate_name = models.CharField(
        verbose_name="Certificate name",
        max_length=255,
        blank=True,
        null=True,
        help_text="Your actual name that will appear on your certificate"
    )

    total_score = models.IntegerField(default=0)

    certificate_url = models.CharField(
        max_length=255, null=True, blank=True
    )

    disable_learning_in_public = models.BooleanField(
        default=False,
        verbose_name="Disable learning in public",
        help_text="When enabled, all learning in public scores are removed and future submissions are not counted"
    )

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = generate_random_name()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} enrolled in {self.course}"


class LeaderboardComplaint(models.Model):
    class IssueType(models.TextChoices):
        LEARNING_IN_PUBLIC = (
            "learning_in_public",
            "Incorrect learning in public links",
        )
        HOMEWORK = "homework", "Incorrect homework"
        PROJECT = "project", "Incorrect project"
        OTHER = "other", "Other leaderboard issue"

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="complaints",
    )
    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leaderboard_complaints",
    )
    issue_type = models.CharField(
        max_length=32,
        choices=IssueType.choices,
    )
    description = models.TextField()
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_leaderboard_complaints",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["resolved", "-created_at"]

    def __str__(self):
        return (
            f"{self.get_issue_type_display()} for "
            f"{self.enrollment.display_name}"
        )
