from django.db import models

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from accounts.models import CustomUser

from courses.random_names import generate_random_name

User = CustomUser


class Course(models.Model):
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


class Enrollment(models.Model):
    class Meta:
        unique_together = ["student", "course"]

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
