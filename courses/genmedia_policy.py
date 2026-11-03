"""Configured eligibility policy for the Production AI Agents campaign.

Port of DataTalksClub/website ``courses/genmedia_policy.py`` (PR #479),
adapted to CMP model field names (identical semantics).
"""

CAMPAIGN_SLUG = "production-ai-agents-generative-media"
AUTO_APPROVAL_LIMIT = 2000
AUTO_APPROVAL_TIMEZONE = "Europe/Berlin"
AUTO_APPROVAL_HOUR = 20

RESTRICTED_ENTRIES = (
    "Belarus",
    "Benin",
    "Bolivia",
    "Cameroon",
    "China",
    "Costa Rica",
    "Crimea (Ukraine)",
    "Cuba",
    "DPR / LPR (Ukraine)",
    "Georgia",
    "Hong Kong",
    "Indonesia",
    "Iran",
    "Kyrgyzstan",
    "Moldova",
    "Nigeria",
    "North Korea",
    "Pakistan",
    "Russia",
)
RESTRICTED_COUNTRIES = frozenset(
    entry for entry in RESTRICTED_ENTRIES if "(Ukraine)" not in entry
)

UKRAINE_REGIONS = (
    ("crimea", "Crimea"),
    ("vinnytsia", "Vinnytsia Oblast"),
    ("volyn", "Volyn Oblast"),
    ("dnipropetrovsk", "Dnipropetrovsk Oblast"),
    ("donetsk_controlled", "Donetsk Oblast (government-controlled)"),
    ("donetsk_occupied", "Donetsk Oblast (DPR-occupied)"),
    ("zhytomyr", "Zhytomyr Oblast"),
    ("zakarpattia", "Zakarpattia Oblast"),
    ("zaporizhzhia", "Zaporizhzhia Oblast"),
    ("ivano_frankivsk", "Ivano-Frankivsk Oblast"),
    ("kyiv_oblast", "Kyiv Oblast"),
    ("kyiv_city", "Kyiv City"),
    ("kirovohrad", "Kirovohrad Oblast"),
    ("luhansk_controlled", "Luhansk Oblast (government-controlled)"),
    ("luhansk_occupied", "Luhansk Oblast (LPR-occupied)"),
    ("lviv", "Lviv Oblast"),
    ("mykolaiv", "Mykolaiv Oblast"),
    ("odesa", "Odesa Oblast"),
    ("poltava", "Poltava Oblast"),
    ("rivne", "Rivne Oblast"),
    ("sumy", "Sumy Oblast"),
    ("ternopil", "Ternopil Oblast"),
    ("kharkiv", "Kharkiv Oblast"),
    ("kherson", "Kherson Oblast"),
    ("khmelnytskyi", "Khmelnytskyi Oblast"),
    ("cherkasy", "Cherkasy Oblast"),
    ("chernivtsi", "Chernivtsi Oblast"),
    ("chernihiv", "Chernihiv Oblast"),
)
UKRAINE_REGION_CHOICES = (("", "Select your region or oblast"), *UKRAINE_REGIONS)
EXCLUDED_UKRAINE_REGIONS = frozenset(
    {"crimea", "donetsk_occupied", "luhansk_occupied"}
)


def normalize_country(country: str) -> str:
    return " ".join((country or "").strip().casefold().split())


def excluded_reason(registration) -> str:
    restricted = {normalize_country(country) for country in RESTRICTED_COUNTRIES}
    if normalize_country(registration.country) in restricted:
        return "country"
    if (
        normalize_country(registration.country) == "ukraine"
        and registration.ukraine_region in EXCLUDED_UKRAINE_REGIONS
    ):
        return "Ukraine region"
    return ""
