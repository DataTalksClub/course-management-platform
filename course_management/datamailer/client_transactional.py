from typing import Any

from .client_types import DatamailerRequest, DatamailerRequestData


class DatamailerTransactionalClient:
    def __init__(
        self,
        config: Any,
        request: DatamailerRequest,
    ):
        self.config = config
        self.request = request

    def send_transactional(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="POST",
            path="/api/transactional/send",
            json=payload,
        )
        return self.request(request_data)

    def transactional_message_status(
        self,
        message_id: int,
    ) -> dict[str, Any] | None:
        request_data = DatamailerRequestData(
            method="GET",
            path=f"/api/transactional/messages/{message_id}",
        )
        return self.request(request_data)
