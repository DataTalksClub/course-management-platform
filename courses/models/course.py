from django.db import models

from django.core.validators import URLValidator

from django.contrib.auth import get_user_model
from django.db.models import Sum

from courses.random_names import generate_random_name



User = get_user_model()


class Course(models.Model):
    instructor = models.ManyToManyField(User, through="Instructor", related_name="courses_taught")
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

    display_name = models.CharField(max_length=255, blank=True)
    display_on_leaderboard = models.BooleanField(default=True)

    position_on_leaderboard = models.IntegerField(
        blank=True, null=True, default=None
    )

    certificate_name = models.CharField(
        max_length=255, blank=True, null=True
    )

    total_score = models.IntegerField(default=0)

    # def calculate_total_score(self):
    #     submissions = Submission.objects.filter(enrollment=self)
    #     total_score_sum = submissions.aggregate(Sum("total_score"))[
    #         "total_score__sum"
    #     ]
    #     self.total_score = total_score_sum or 0
    #     self.save()

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = generate_random_name()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} enrolled in {self.course}"