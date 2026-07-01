from .types import DatamailerMethodCase


def transient_transactional_payload():
    member = {"email": "learner@example.com"}
    members = []
    members.append(member)
    return {
        "template_key": "deadline-reminder",
        "members": members,
    }


def recipient_list_transactional_send_method_case():
    payload = {"template_key": "homework-score-notification"}
    return DatamailerMethodCase(
        method_name="send_recipient_list_transactional",
        args=("ml-zoomcamp-2026:@e:@homework:homework-1", payload),
        method="POST",
        path=(
            "/api/recipient-lists/"
            "ml-zoomcamp-2026:@e:@homework:homework-1"
            "/transactional-send"
        ),
        json_payload=payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def transient_transactional_send_method_case():
    payload = transient_transactional_payload()
    return DatamailerMethodCase(
        method_name="send_transient_recipient_list_transactional",
        args=(payload,),
        method="POST",
        path="/api/transient-recipient-lists/transactional-send",
        json_payload=payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def transactional_send_method_cases():
    cases = []
    case = recipient_list_transactional_send_method_case()
    cases.append(case)
    case = transient_transactional_send_method_case()
    cases.append(case)
    return cases


def transactional_status_method_cases():
    cases = []
    response_payload = {"message": {"id": 42}}
    case = DatamailerMethodCase(
        method_name="transactional_message_status",
        args=(42,),
        method="GET",
        path="/api/transactional/messages/42",
        response_payload=response_payload,
        expected_result=response_payload,
    )
    cases.append(case)
    return cases


def transactional_method_cases():
    cases = []
    for case in transactional_status_method_cases():
        cases.append(case)
    for case in transactional_send_method_cases():
        cases.append(case)
    return cases
