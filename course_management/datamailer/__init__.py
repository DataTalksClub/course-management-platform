from .client import *
from .keys import *
from .preferences import *
from .payloads import *
from .sync import *
from .sync import get_transactional_message_status


def get_email_status(email: str, *, limit: int = 25) -> dict | None:
    status = get_contact_status(email)
    if status is None:
        return None

    contact_id = status.get("contact_id")
    history = None
    if contact_id:
        history = get_contact_history(int(contact_id), limit=limit)

    return {
        "status": status,
        "history": history,
    }
