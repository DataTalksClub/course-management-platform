from django.db import models

from django.core.validators import URLValidator
from django.contrib.auth import get_user_model

from courses.random_names import generate_random_name

User = get_user_model()


class Course(models.Model):
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses_teaching")
    slug = models.SlugField(unique=True, blank=False)
    title = models.CharField(max_length=200)

    description = models.TextField()
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

    def __str__(self):
        return self.title


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

    github_url = models.URLField(
        verbose_name="GitHub URL",
        blank=True,
        null=True,
        validators=[URLValidator()],
    )
    linkedin_url = models.URLField(
        verbose_name="LinkedIn URL",
        blank=True,
        null=True,
        validators=[URLValidator()],
    )
    personal_website_url = models.URLField(
        verbose_name="Personal website URL",
        blank=True,
        null=True,
        validators=[URLValidator()],
    )
    about_me = models.TextField(
        verbose_name="About me",
        blank=True,
        null=True,
        help_text="Any information about you",
    )

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = generate_random_name()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} enrolled in {self.course}"
