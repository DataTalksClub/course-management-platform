from .client import *  # noqa: F403
from .client import __all__ as _client_all
from .keys import *  # noqa: F403
from .keys import __all__ as _keys_all
from .payloads import *  # noqa: F403
from .payloads import __all__ as _payloads_all
from .preferences import *  # noqa: F403
from .preferences import __all__ as _preferences_all
from .sync import *  # noqa: F403
from .sync import get_contact_history, get_contact_status
from .sync import __all__ as _sync_all

__all__ = (
    *_client_all,
    *_keys_all,
    *_preferences_all,
    *_payloads_all,
    *_sync_all,
)


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
