from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bleach
import mistune

COUNTRIES_CONFIG_PATH = Path(__file__).with_name("countries.txt")
TOP_COUNTRIES_SECTION = "Top Countries"
YOUTUBE_EMBED_BASE_URL = "https://www.youtube.com/embed"


def _countries_config_lines():
    content = COUNTRIES_CONFIG_PATH.read_text(encoding="utf-8")
    return content.splitlines()


def _country_config_section(line):
    if not line.startswith("["):
        return None
    if not line.endswith("]"):
        return None

    section = line[1:-1].strip()
    return section


def _add_country_to_config(countries_by_region, top_countries, section, country):
    if section is None:
        return

    if section == TOP_COUNTRIES_SECTION:
        top_countries.append(country)
        return

    region_countries = countries_by_region.setdefault(section, [])
    region_countries.append(country)


def _build_countries_config():
    top_countries = []
    countries_by_region = {}
    section = None

    config_lines = _countries_config_lines()
    for raw_line in config_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        section_name = _country_config_section(line)
        if section_name:
            section = section_name
            if section != TOP_COUNTRIES_SECTION:
                countries_by_region[section] = []
            continue

        _add_country_to_config(countries_by_region, top_countries, section, line)

    return countries_by_region, top_countries


COUNTRIES_BY_REGION, TOP_COUNTRIES = _build_countries_config()


def _build_country_region_map():
    country_region = {}
    for region, countries in COUNTRIES_BY_REGION.items():
        for country in countries:
            country_region[country] = region
    return country_region


COUNTRY_REGION = _build_country_region_map()


def ordered_countries():
    top_countries = []
    for country in TOP_COUNTRIES:
        if country in COUNTRY_REGION:
            top_countries.append(country)

    top_country_set = set(top_countries)
    remaining_countries = []
    country_names = COUNTRY_REGION.keys()
    for country in country_names:
        if country not in top_country_set:
            remaining_countries.append(country)
    remaining_countries.sort()

    countries = []
    for country in top_countries:
        countries.append(country)
    for country in remaining_countries:
        countries.append(country)
    return countries


def _build_country_choices():
    country_choices = []
    countries = ordered_countries()
    for country in countries:
        country_choice = (country, country)
        country_choices.append(country_choice)
    return country_choices


COUNTRY_CHOICES = _build_country_choices()

ALLOWED_MARKDOWN_TAGS = [
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
]
ALLOWED_MARKDOWN_ATTRIBUTES = {"a": ["href", "title", "rel", "target"]}


def region_for_country(country):
    return COUNTRY_REGION.get(country, "")


def render_markdown(markdown_text):
    if not markdown_text:
        return ""

    html = mistune.html(markdown_text)
    return bleach.clean(
        html,
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
    )


def _youtube_watch_video_id(url):
    parsed_url = urlparse(url)
    if "youtube.com" not in parsed_url.netloc:
        return None
    if parsed_url.path != "/watch":
        return None

    query = parse_qs(parsed_url.query)
    video_ids = query.get("v", [])
    if not video_ids:
        return None

    video_id = video_ids[0]
    return video_id


def _youtu_be_video_id(url):
    parsed_url = urlparse(url)
    if "youtu.be" not in parsed_url.netloc:
        return None

    video_id = parsed_url.path.lstrip("/")
    if not video_id:
        return None

    return video_id


def youtube_embed_url(url):
    if not url:
        return ""

    video_id = _youtube_watch_video_id(url)
    if video_id:
        embed_url = f"{YOUTUBE_EMBED_BASE_URL}/{video_id}"
        return embed_url

    video_id = _youtu_be_video_id(url)
    if video_id:
        embed_url = f"{YOUTUBE_EMBED_BASE_URL}/{video_id}"
        return embed_url

    return url
