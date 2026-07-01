from dataclasses import dataclass


@dataclass(frozen=True)
class MemberDriftData:
    expected: dict
    actual: dict
    drift: dict


def member_drift(payload, response):
    expected = expected_members(payload)
    actual = actual_members(response or {})
    drift = compare_members(expected, actual)
    return MemberDriftData(expected, actual, drift)


def expected_members(payload):
    payload_members = payload["members"]
    return active_member_records(payload_members)


def actual_members(response):
    response_members = response.get("members", [])
    return active_member_records(response_members)


def active_member_records(raw_members):
    members = {}
    for member in raw_members:
        if member.get("status", "active") == "removed":
            continue

        source_object_key = member["source_object_key"]
        member_record = active_member_record(member)
        members[source_object_key] = member_record
    return members


def active_member_record(member):
    email_stripped = member["email"].strip()
    email = email_stripped.lower()
    metadata = member.get("metadata") or {}
    return {
        "email": email,
        "metadata": metadata,
    }


def compare_members(expected, actual):
    expected_keys = set(expected)
    actual_keys = set(actual)
    shared_keys = expected_keys & actual_keys
    missing_keys = sorted(expected_keys - actual_keys)
    unexpected_keys = sorted(actual_keys - expected_keys)
    email_mismatches = member_field_mismatches(
        expected, actual, shared_keys, "email"
    )
    metadata_mismatches = member_field_mismatches(
        expected, actual, shared_keys, "metadata"
    )
    drift = {
        "missing": missing_keys,
        "unexpected": unexpected_keys,
        "email_mismatches": email_mismatches,
        "metadata_mismatches": metadata_mismatches,
    }
    drift["has_drift"] = has_member_drift(drift)
    return drift


def member_field_mismatches(expected, actual, shared_keys, field):
    mismatches = []
    for key in shared_keys:
        if expected[key][field] == actual[key][field]:
            continue
        mismatches.append(key)
    return sorted(mismatches)


def has_member_drift(drift):
    drift_labels = (
        "missing",
        "unexpected",
        "email_mismatches",
        "metadata_mismatches",
    )
    for label in drift_labels:
        if drift[label]:
            return True
    return False
