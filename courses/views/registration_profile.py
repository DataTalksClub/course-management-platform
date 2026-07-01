from dataclasses import dataclass


@dataclass(frozen=True)
class RegistrationProfileValue:
    field_name: str
    value: object


def can_update_registration_user_profile(user):
    return user is not None and user.is_authenticated


def update_user_profile_from_registration(user, registration):
    update_fields = []
    profile_values = registration_profile_values(registration)
    for profile_value in profile_values:
        update_user_profile_field(
            user,
            update_fields,
            profile_value.field_name,
            profile_value.value,
        )
    return update_fields


def registration_profile_values(registration):
    profile_values = []
    certificate_name_value = registration.name.strip()
    certificate_name = RegistrationProfileValue(
        "certificate_name",
        certificate_name_value,
    )
    country = RegistrationProfileValue("country", registration.country)
    region = RegistrationProfileValue("region", registration.region)
    registration_role = RegistrationProfileValue(
        "registration_role",
        registration.role,
    )
    profile_values.append(certificate_name)
    profile_values.append(country)
    profile_values.append(region)
    profile_values.append(registration_role)
    return profile_values


def update_user_profile_field(user, update_fields, field_name, value):
    if not value or getattr(user, field_name) == value:
        return

    setattr(user, field_name, value)
    update_fields.append(field_name)
