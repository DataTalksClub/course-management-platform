"""Email domain validation for course registration.

Two layers:

1. Typo suggestion (no network): warns on common domain typos such as
   ``gmial.com`` or ``yahooo.com`` with a "did you mean ...?" suggestion.
2. MX check (DNS, server-side): rejects domains that cannot receive mail,
   including null-MX domains ("0 ."). DNS failures/timeouts never block
   registration; they are logged and treated as unknown.
"""

import logging

import dns.resolver

logger = logging.getLogger(__name__)

DNS_LOOKUP_TIMEOUT_SECONDS = 3.0

# Explicit typo map: domain typed -> domain almost certainly meant.
# Covers the common cases from registration UX reports.
DOMAIN_TYPO_MAP = {
    "hmail.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmali.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gmail.co": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.cm": "gmail.com",
    "gnail.com": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
    "yahoo.co": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "hotmai.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "hotamil.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "outllok.com": "outlook.com",
    "outlook.co": "outlook.com",
    "outlook.con": "outlook.com",
    "iclod.com": "icloud.com",
    "icloud.con": "icloud.com",
    "protonmai.com": "protonmail.com",
}


def _split_email(email):
    raw = (email or "").strip()
    if "@" not in raw:
        return None, None
    local_part, _, domain = raw.rpartition("@")
    if not local_part or not domain:
        return None, None
    if "@" in local_part:
        return None, None
    return local_part, domain.lower()


def suggest_email_correction(email):
    """Return a corrected email address when the domain looks mistyped.

    Returns the suggested full address, or None when the domain looks
    fine (or the address is too malformed to judge).
    """
    local_part, domain = _split_email(email)
    if local_part is None or domain is None:
        return None

    mapped = DOMAIN_TYPO_MAP.get(domain)
    if mapped:
        return f"{local_part}@{mapped}"

    return None


def _mx_records_for_domain(domain):
    """Return the MX answer list for a domain, or raise on DNS failure."""
    resolver = dns.resolver.Resolver()
    resolver.lifetime = DNS_LOOKUP_TIMEOUT_SECONDS
    resolver.timeout = DNS_LOOKUP_TIMEOUT_SECONDS
    return resolver.resolve(domain, "MX")


def _has_usable_mx_answer(answers):
    for answer in answers:
        exchange = str(answer.exchange).rstrip(".").lower()
        preference = int(answer.preference)
        # Null MX (RFC 7505): "0 ." means the domain accepts no mail.
        if preference == 0 and exchange == "":
            return False
    return len(list(answers)) > 0


def domain_has_mx(domain):
    """Check whether a domain can receive mail.

    Returns True (has MX), False (no MX / null MX), or None (DNS lookup
    failed or timed out — unknown, must NOT block registration).
    """
    domain = (domain or "").strip().rstrip(".").lower()
    if not domain:
        return False
    try:
        answers = _mx_records_for_domain(domain)
    except Exception as exc:
        if _is_unknown_domain(exc):
            return False
        logger.warning(
            "MX lookup failed for domain %r: %s", domain, exc
        )
        return None

    try:
        return _has_usable_mx_answer(answers)
    except Exception as exc:
        logger.warning(
            "MX answer parsing failed for domain %r: %s", domain, exc
        )
        return None


def _is_unknown_domain(exc):
    """True when DNS proves the domain cannot receive mail.

    NXDOMAIN (the name does not exist) and NoAnswer (no MX records)
    are definitive: reject. Timeouts, unreachable nameservers and any
    other lookup failure are unknown: do NOT block registration.
    """
    return isinstance(
        exc, (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer)
    )


def email_domain_has_mx(email):
    """MX check for a full address; malformed addresses return False."""
    _, domain = _split_email(email)
    if domain is None:
        return False
    return domain_has_mx(domain)
