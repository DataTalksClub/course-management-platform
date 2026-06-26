#!/usr/bin/env python
"""
Create a superuser (or reset their password).

Run from the project root with the environment already configured:
    uv run python scripts/create_superuser.py --email alexey@datatalks.club
"""

import argparse
import os
import secrets
import string
import sys

import django

# Add parent directory to path so Django can find course_management module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_management.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()


def generate_password(length=16):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def choose_user(matches, email):
    username_matches = [user for user in matches if user.username == email]
    if len(username_matches) == 1:
        return username_matches[0]

    active_admins = [
        user
        for user in matches
        if user.is_superuser and user.is_staff and user.is_active
    ]
    if len(active_admins) == 1:
        return active_admins[0]

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="alexey@datatalks.club")
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Target a specific user id (use when the email is duplicated)",
    )
    args = parser.parse_args()

    password = args.password or generate_password()

    if args.user_id is not None:
        user = User.objects.get(pk=args.user_id)
        created = False
    else:
        matches = list(User.objects.filter(email=args.email))
        if len(matches) > 1:
            user = choose_user(matches, args.email)
            if user is None:
                print(f"Multiple users with email {args.email}:")
                for u in matches:
                    print(
                        f"  id={u.pk} username={u.username!r} "
                        f"superuser={u.is_superuser} staff={u.is_staff} "
                        f"active={u.is_active}"
                    )
                print("\nRe-run with --user-id <id> to pick one.")
                raise SystemExit(1)

            print(
                f"Multiple users with email {args.email}; selected "
                f"id={user.pk} username={user.username!r}."
            )
            created = False
        elif len(matches) == 1:
            user = matches[0]
            created = False
        else:
            user = User(username=args.email, email=args.email)
            created = True

    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.is_active = True
    user.save()

    action = "created" if created else "password reset"
    print(f"Superuser {action}: id={user.pk} {user.email}")
    print(f"Password: {password}")


if __name__ == "__main__":
    main()
