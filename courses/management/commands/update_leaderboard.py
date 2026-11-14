from django.core.management.base import BaseCommand, CommandError

from courses.leaderboard import update_leaderboard
from courses.models.course import Course


class Command(BaseCommand):
    help = "Recompute leaderboard totals, ranks, and cache version for courses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--course",
            dest="course_slug",
            help="Slug of a single course to refresh.",
        )
        parser.add_argument(
            "--all-active",
            action="store_true",
            help="Refresh all unfinished visible courses.",
        )

    def handle(self, *args, **options):
        course_slug = options.get("course_slug")
        all_active = options.get("all_active")
        if bool(course_slug) == bool(all_active):
            raise CommandError("Specify either --course <slug> or --all-active.")

        if course_slug:
            course = Course.objects.filter(slug=course_slug).first()
            if course is None:
                raise CommandError(f"Course not found: {course_slug}")
            courses = [course]
        else:
            courses = list(
                Course.objects.filter(finished=False, visible=True).order_by("id")
            )

        for course in courses:
            update_leaderboard(course)
            course.refresh_from_db(fields=["leaderboard_cache_version"])
            self.stdout.write(
                f"Updated {course.slug} (cache version {course.leaderboard_cache_version})"
            )
