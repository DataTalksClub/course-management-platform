from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DatamailerRequestData:
    method: str
    path: str
    json: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
