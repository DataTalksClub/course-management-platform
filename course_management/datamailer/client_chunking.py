"""Request-body chunking for member-array Relay endpoints.

Relay's CloudFront distribution terminates AWS WAF, and the managed common
rule set rejects request bodies larger than 8 KiB with 403. Bulk member
payloads (deadline-reminder transient lists, recipient-list syncs) grow with
course size, so the client splits them into byte-budget requests instead of
letting large sends die at the edge.
"""

import json

# Comfortable margin under the WAF's 8192-byte body ceiling.
MAX_REQUEST_BODY_BYTES = 7000

MEMBERS_KEY = "members"


def request_body_size(payload) -> int:
    return len(json.dumps(payload).encode("utf-8"))


def chunk_payload_by_members(payload: dict, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> list[dict]:
    """Split a payload whose ``members`` list may exceed the body budget.

    Non-member keys are repeated on every chunk so each request is a valid
    standalone payload. Returns a single-element list with the original
    payload when everything already fits.
    """
    if request_body_size(payload) <= max_bytes:
        return [payload]

    envelope = {key: value for key, value in payload.items() if key != MEMBERS_KEY}
    # Size of the envelope as it will actually be serialized, including the
    # empty members array this accounting replaces chunk member by chunk
    # member (each member then adds its serialized length plus a separator).
    envelope_size = request_body_size(envelope | {MEMBERS_KEY: []})
    if envelope_size >= max_bytes:
        # Degenerate envelope (huge context or list metadata); a single-member
        # chunk is the best we can do.
        return [envelope | {MEMBERS_KEY: list(payload[MEMBERS_KEY])}]

    chunks: list[dict] = []
    current: list = []
    current_size = envelope_size
    for member in payload[MEMBERS_KEY]:
        # +2 for the ", " item separator json.dumps inserts between members.
        member_size = request_body_size(member) + 2
        if current and current_size + member_size > max_bytes:
            chunks.append(envelope | {MEMBERS_KEY: current})
            current = []
            current_size = envelope_size
        current.append(member)
        current_size += member_size
    if current:
        chunks.append(envelope | {MEMBERS_KEY: current})
    return chunks
