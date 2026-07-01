import random

from pathlib import Path


RANDOM_NAMES_DIR = Path(__file__).with_name("random_names")
ADJECTIVES_PATH = RANDOM_NAMES_DIR / "adjectives.txt"
FAMOUS_PEOPLE_PATH = RANDOM_NAMES_DIR / "famous_people.txt"


def _random_name_parts(path):
    parts = []
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        parts.append(line)
    return tuple(parts)


ADJECTIVES = _random_name_parts(ADJECTIVES_PATH)
FAMOUS_PEOPLE = _random_name_parts(FAMOUS_PEOPLE_PATH)


def generate_random_name():
    adjective = random.choice(ADJECTIVES)
    famous_person = random.choice(FAMOUS_PEOPLE)

    return f"{adjective} {famous_person}"
