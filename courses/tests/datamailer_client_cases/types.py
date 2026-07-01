from dataclasses import dataclass
from unittest.mock import Mock


@dataclass(frozen=True)
class DatamailerRequestExpectation:
    response: Mock
    session: Mock
    method: str
    path: str
    json_payload: dict | None = None
    params: dict | None = None


@dataclass(frozen=True)
class DatamailerMethodCase:
    method_name: str
    args: tuple
    method: str
    path: str
    response_payload: dict
    expected_result: dict
    kwargs: dict | None = None
    json_payload: dict | None = None
    params: dict | None = None
