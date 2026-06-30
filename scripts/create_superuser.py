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
    characters = []
    for _ in range(length):
        character = secrets.choice(alphabet)
        characters.append(character)
    return "".join(characters)


def choose_user(matches, email):
    return unique_username_match(matches, email) or unique_active_admin(matches)


def unique_username_match(matches, email):
    username_matches = []
    for user in matches:
        if user.username == email:
            username_matches.append(user)
    return unique_match(username_matches)


def unique_active_admin(matches):
    active_admins = []
    for user in matches:
        if user.is_superuser and user.is_staff and user.is_active:
            active_admins.append(user)
    return unique_match(active_admins)


def unique_match(items):
    matches = list(items)
    if len(matches) == 1:
        return matches[0]
    return None


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="alexey@datatalks.club")
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Target a specific user id (use when the email is duplicated)",
    )
    return parser.parse_args()


def print_duplicate_users(email, matches):
    print(f"Multiple users with email {email}:")
    for user in matches:
        print(
            f"  id={user.pk} username={user.username!r} "
            f"superuser={user.is_superuser} staff={user.is_staff} "
            f"active={user.is_active}"
        )
    print("\nRe-run with --user-id <id> to pick one.")


def selected_duplicate_user(email, matches):
    user = choose_user(matches, email)
    if user is None:
        print_duplicate_users(email, matches)
        raise SystemExit(1)

    print(
        f"Multiple users with email {email}; selected "
        f"id={user.pk} username={user.username!r}."
    )
    return user


def find_or_create_user(email, user_id=None):
    if user_id is not None:
        return User.objects.get(pk=user_id), False

    matches = list(User.objects.filter(email=email))
    if len(matches) > 1:
        return selected_duplicate_user(email, matches), False
    if len(matches) == 1:
        return matches[0], False

    return User(username=email, email=email), True


def save_superuser(user, password):
    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.is_active = True
    user.save()


def print_result(user, password, created):
    action = "created" if created else "password reset"
    print(f"Superuser {action}: id={user.pk} {user.email}")
    print(f"Password: {password}")


def main():
    args = parse_args()
    password = args.password or generate_password()
    user, created = find_or_create_user(args.email, args.user_id)
    save_superuser(user, password)
    print_result(user, password, created)


if __name__ == "__main__":
    main()
