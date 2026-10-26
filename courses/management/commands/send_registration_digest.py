from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from course_management.relay.registration_digest import (
    collect_digest_registrations,
    digest_day,
    digest_due,
    digest_moment,
    render_digest_summary,
    send_registration_digest,
)


class Command(BaseCommand):
    help = (
        "Send the daily registration digest to operators "
        "(covers the last 24h; skipped when empty or already sent)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass the local already-sent guard and re-run "
            "(same Relay idempotency keys; Relay will not duplicate delivery).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the digest summary without sending or recording.",
        )

    def handle(self, *args, **options):
        now = digest_moment()
        day = digest_day(now)
        if options["dry_run"]:
            window_end = now
            registrations = collect_digest_registrations(
                window_end - timedelta(hours=24), window_end,
            )
            self.stdout.write(f"Digest date: {day.isoformat()}")
            self.stdout.write(f"Due now: {digest_due(now)}")
            self.stdout.write(f"Registrations in window: {len(registrations)}")
            if registrations:
                from course_management.relay.registration_digest import (
                    group_digest_registrations,
                )
                self.stdout.write(render_digest_summary(
                    group_digest_registrations(registrations),
                ))
            return
        try:
            result = send_registration_digest(now=now, force=options["force"])
        except Exception as exc:
            raise CommandError(f"Registration digest failed: {type(exc).__name__}") from None
        if result.sent:
            self.stdout.write(
                f"Sent registration digest for {result.date} "
                f"({result.total_count} registrations): "
                f"{', '.join(result.relay_message_ids)}"
            )
        else:
            self.stdout.write(
                f"Registration digest for {result.date} not sent: {result.reason}"
            )
