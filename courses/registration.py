import bleach
import mistune

COUNTRIES_BY_REGION = {
    "Africa": [
        "Algeria",
        "Angola",
        "Benin",
        "Botswana",
        "Burkina Faso",
        "Burundi",
        "Cabo Verde",
        "Cameroon",
        "Central African Republic",
        "Chad",
        "Comoros",
        "Congo",
        "Democratic Republic of the Congo",
        "Cote d'Ivoire",
        "Djibouti",
        "Egypt",
        "Equatorial Guinea",
        "Eritrea",
        "Eswatini",
        "Ethiopia",
        "Gabon",
        "Gambia",
        "Ghana",
        "Guinea",
        "Guinea-Bissau",
        "Kenya",
        "Lesotho",
        "Liberia",
        "Libya",
        "Madagascar",
        "Malawi",
        "Mali",
        "Mauritania",
        "Mauritius",
        "Morocco",
        "Mozambique",
        "Namibia",
        "Niger",
        "Nigeria",
        "Rwanda",
        "Sao Tome and Principe",
        "Senegal",
        "Seychelles",
        "Sierra Leone",
        "Somalia",
        "South Africa",
        "South Sudan",
        "Sudan",
        "Tanzania",
        "Togo",
        "Tunisia",
        "Uganda",
        "Zambia",
        "Zimbabwe",
    ],
    "North America": [
        "Canada",
        "United States",
        "United States of America",
        "Mexico",
        "Bermuda",
        "Greenland",
        "Saint Pierre and Miquelon",
        "Belize",
        "Costa Rica",
        "El Salvador",
        "Guatemala",
        "Honduras",
        "Nicaragua",
        "Panama",
        "Cuba",
        "Dominican Republic",
        "Haiti",
        "Jamaica",
        "Trinidad and Tobago",
        "Barbados",
        "Bahamas",
        "Grenada",
        "Saint Lucia",
        "Saint Vincent and the Grenadines",
        "Dominica",
        "Antigua and Barbuda",
        "Saint Kitts and Nevis",
        "Puerto Rico",
        "Curacao",
        "Aruba",
        "Cayman Islands",
    ],
    "South America": [
        "Argentina",
        "Bolivia",
        "Brazil",
        "Chile",
        "Colombia",
        "Ecuador",
        "Guyana",
        "Paraguay",
        "Peru",
        "Suriname",
        "Uruguay",
        "Venezuela",
        "French Guiana",
        "Falkland Islands",
    ],
    "Asia": [
        "Afghanistan",
        "Armenia",
        "Azerbaijan",
        "Bahrain",
        "Bangladesh",
        "Bhutan",
        "Brunei",
        "Cambodia",
        "China",
        "Georgia",
        "India",
        "Indonesia",
        "Iran",
        "Iraq",
        "Israel",
        "Japan",
        "Jordan",
        "Kazakhstan",
        "Kuwait",
        "Kyrgyzstan",
        "Laos",
        "Lebanon",
        "Malaysia",
        "Maldives",
        "Mongolia",
        "Myanmar",
        "Nepal",
        "North Korea",
        "Oman",
        "Pakistan",
        "Palestine",
        "Philippines",
        "Qatar",
        "Saudi Arabia",
        "Singapore",
        "South Korea",
        "Sri Lanka",
        "Syria",
        "Tajikistan",
        "Thailand",
        "Timor-Leste",
        "Turkey",
        "Turkmenistan",
        "United Arab Emirates",
        "Uzbekistan",
        "Vietnam",
        "Yemen",
    ],
    "Europe": [
        "Albania",
        "Andorra",
        "Austria",
        "Belarus",
        "Belgium",
        "Bosnia and Herzegovina",
        "Bulgaria",
        "Croatia",
        "Cyprus",
        "Czechia",
        "Denmark",
        "Estonia",
        "Finland",
        "France",
        "Germany",
        "Greece",
        "Hungary",
        "Iceland",
        "Ireland",
        "Italy",
        "Kosovo",
        "Latvia",
        "Liechtenstein",
        "Lithuania",
        "Luxembourg",
        "Malta",
        "Moldova",
        "Monaco",
        "Montenegro",
        "Netherlands",
        "North Macedonia",
        "Norway",
        "Poland",
        "Portugal",
        "Romania",
        "Russia",
        "San Marino",
        "Serbia",
        "Slovakia",
        "Slovenia",
        "Spain",
        "Sweden",
        "Switzerland",
        "Ukraine",
        "United Kingdom",
        "Vatican City",
    ],
    "Oceania": [
        "Australia",
        "New Zealand",
        "Fiji",
        "Papua New Guinea",
        "Solomon Islands",
        "Vanuatu",
        "Samoa",
        "Tonga",
        "Kiribati",
        "Tuvalu",
        "Nauru",
        "Micronesia",
        "Palau",
        "Marshall Islands",
        "New Caledonia",
    ],
}

def _build_country_region_map():
    country_region = {}
    for region, countries in COUNTRIES_BY_REGION.items():
        for country in countries:
            country_region[country] = region
    return country_region


COUNTRY_REGION = _build_country_region_map()

TOP_COUNTRIES = [
    "United States",
    "Canada",
    "Germany",
    "United Kingdom",
    "France",
    "Spain",
    "Poland",
    "India",
    "Egypt",
    "Tunisia",
    "Nigeria",
    "Brazil",
    "Pakistan",
    "Indonesia",
    "Kenya",
    "Australia",
    "Morocco",
    "Singapore",
    "Argentina",
    "Algeria",
]


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


def youtube_embed_url(url):
    if not url:
        return ""

    if "youtube.com/watch" in url and "v=" in url:
        video_id = url.split("v=", 1)[1].split("&", 1)[0]
        return f"https://www.youtube.com/embed/{video_id}"

    if "youtu.be/" in url:
        video_id = url.rsplit("/", 1)[-1].split("?", 1)[0]
        return f"https://www.youtube.com/embed/{video_id}"

    return url
