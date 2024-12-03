import os
import django
import string
import random

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "course_management.settings"
)
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()


def generate_password(length=12):
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length))


def create_user():
    print("Creating a new Django user")
    email = input("Enter email: ")

    password = generate_password()

    try:
        user = User.objects.create_user(
            username=email, email=email, password=password
        )
        print(f"User with email {email} created successfully.")
        print(f"Generated password: {password}")
        print("Please make sure to save this password securely.")

        is_superuser = (
            input("Make this user a superuser? (y/n): ").lower() == "y"
        )
        if is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save()
            print("User has been granted superuser privileges.")

    except django.db.utils.IntegrityError:
        print(f"A user with email {email} already exists.")


if __name__ == "__main__":
    create_user()
