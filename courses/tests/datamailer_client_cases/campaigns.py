from .types import DatamailerMethodCase, DatamailerRequestExpectation


def campaign_upsert_payload():
    return {
        "subject": "Course starts tomorrow",
        "html_body": "<p>Hello</p>",
        "text_body": "Hello",
    }


def campaign_upsert_expected_payload():
    payload = {
        "audience": "dtc-courses",
        "client": "dtc-courses",
    }
    upsert_payload = campaign_upsert_payload()
    payload.update(upsert_payload)
    return payload


def campaign_upsert_expectation(response, session):
    expected_payload = campaign_upsert_expected_payload()
    return DatamailerRequestExpectation(
        response=response,
        session=session,
        method="PUT",
        path="/api/campaigns/course-start-2026",
        json_payload=expected_payload,
    )


def campaign_case_scope_payload():
    return {
        "audience": "dtc-courses",
        "client": "dtc-courses",
    }


def campaign_detail_method_case():
    params = campaign_case_scope_payload()
    response_payload = {"campaign": {"external_key": "course-start-2026"}}
    return DatamailerMethodCase(
        method_name="campaign",
        args=("course-start-2026",),
        method="GET",
        path="/api/campaigns/course-start-2026",
        params=params,
        response_payload=response_payload,
        expected_result=response_payload,
    )


def campaign_preview_method_case():
    json_payload = campaign_case_scope_payload()
    return DatamailerMethodCase(
        method_name="preview_campaign",
        args=("course-start-2026",),
        method="POST",
        path="/api/campaigns/course-start-2026/preview",
        json_payload=json_payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def campaign_read_method_cases():
    cases = []
    case = campaign_detail_method_case()
    cases.append(case)
    case = campaign_preview_method_case()
    cases.append(case)
    return cases


def queue_campaign_method_case():
    json_payload = campaign_case_scope_payload()
    return DatamailerMethodCase(
        method_name="queue_campaign",
        args=("course-start-2026",),
        method="POST",
        path="/api/campaigns/course-start-2026/queue",
        json_payload=json_payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def cancel_campaign_method_case():
    json_payload = campaign_case_scope_payload()
    return DatamailerMethodCase(
        method_name="cancel_campaign",
        args=("course-start-2026",),
        method="POST",
        path="/api/campaigns/course-start-2026/cancel",
        json_payload=json_payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def campaign_control_method_cases():
    cases = []
    case = queue_campaign_method_case()
    cases.append(case)
    case = cancel_campaign_method_case()
    cases.append(case)
    return cases


def campaign_test_send_method_case():
    emails = ["test@example.com"]
    json_payload = {
        "audience": "dtc-courses",
        "client": "dtc-courses",
        "emails": emails,
    }
    return DatamailerMethodCase(
        method_name="test_send_campaign",
        args=("course-start-2026", emails),
        method="POST",
        path="/api/campaigns/course-start-2026/test-send",
        json_payload=json_payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def campaign_send_method_cases():
    cases = []
    case = campaign_test_send_method_case()
    cases.append(case)
    return cases


def campaign_method_cases():
    cases = []
    for case in campaign_read_method_cases():
        cases.append(case)
    for case in campaign_control_method_cases():
        cases.append(case)
    for case in campaign_send_method_cases():
        cases.append(case)
    return cases
