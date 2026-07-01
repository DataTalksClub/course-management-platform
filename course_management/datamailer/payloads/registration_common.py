def registration_email(registration) -> str:
    return (
        (registration.email_normalized or registration.email or "")
        .strip()
        .lower()
    )
