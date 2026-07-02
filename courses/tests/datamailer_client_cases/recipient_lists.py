from .types import DatamailerMethodCase


def upsert_recipient_list_member_method_case():
    member_payload = {"email": "student@example.com"}
    return DatamailerMethodCase(
        endpoint_name="recipient_lists",
        method_name="upsert_recipient_list_member",
        args=("ml-zoomcamp-2026", "registration:42", member_payload),
        method="PUT",
        path="/api/recipient-lists/ml-zoomcamp-2026/members/registration:42",
        json_payload=member_payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def remove_recipient_list_member_method_case():
    scope_payload = {
        "audience": "dtc-courses",
        "client": "dtc-courses",
    }
    return DatamailerMethodCase(
        endpoint_name="recipient_lists",
        method_name="remove_recipient_list_member",
        args=("ml-zoomcamp-2026", "registration:42"),
        method="DELETE",
        path="/api/recipient-lists/ml-zoomcamp-2026/members/registration:42",
        json_payload=scope_payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def recipient_list_member_write_method_cases():
    cases = []
    case = upsert_recipient_list_member_method_case()
    cases.append(case)
    case = remove_recipient_list_member_method_case()
    cases.append(case)
    return cases


def recipient_list_members_method_case():
    params = {
        "audience": "dtc-courses",
        "client": "dtc-courses",
        "include_removed": "false",
        "limit": 500,
    }
    kwargs = {"limit": 500}
    return DatamailerMethodCase(
        endpoint_name="recipient_lists",
        method_name="recipient_list_members",
        args=("ml-zoomcamp-2026:@e",),
        kwargs=kwargs,
        method="GET",
        path="/api/recipient-lists/ml-zoomcamp-2026:@e/members",
        params=params,
        response_payload={"members": []},
        expected_result={"members": []},
    )


def recipient_list_member_read_method_cases():
    cases = []
    case = recipient_list_members_method_case()
    cases.append(case)
    return cases


def recipient_list_member_method_cases():
    cases = []
    for case in recipient_list_member_write_method_cases():
        cases.append(case)
    for case in recipient_list_member_read_method_cases():
        cases.append(case)
    return cases


def recipient_list_import_payload():
    return {
        "source_url": "https://storage.example.com/import.jsonl",
        "idempotency_key": "cmp-import-1",
    }


def create_recipient_list_import_method_case():
    import_payload = recipient_list_import_payload()
    json_payload = {
        "audience": "dtc-courses",
        "client": "dtc-courses",
        "source_url": "https://storage.example.com/import.jsonl",
        "idempotency_key": "cmp-import-1",
    }
    return DatamailerMethodCase(
        endpoint_name="recipient_lists",
        method_name="create_recipient_list_import",
        args=("ml-zoomcamp-2026:@e", import_payload),
        method="POST",
        path="/api/recipient-lists/ml-zoomcamp-2026:@e/imports",
        json_payload=json_payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def recipient_list_import_status_method_case():
    params = {"audience": "dtc-courses", "client": "dtc-courses"}
    return DatamailerMethodCase(
        endpoint_name="recipient_lists",
        method_name="recipient_list_import",
        args=("ml-zoomcamp-2026:@e", 42),
        method="GET",
        path="/api/recipient-lists/ml-zoomcamp-2026:@e/imports/42",
        params=params,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def recipient_list_import_method_cases():
    cases = []
    case = create_recipient_list_import_method_case()
    cases.append(case)
    case = recipient_list_import_status_method_case()
    cases.append(case)
    return cases


def recipient_list_method_cases():
    cases = []
    for case in recipient_list_member_method_cases():
        cases.append(case)
    for case in recipient_list_import_method_cases():
        cases.append(case)
    return cases
