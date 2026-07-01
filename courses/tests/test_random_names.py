from unittest.mock import patch

from django.test import SimpleTestCase

from courses.random_names import (
    ADJECTIVES,
    FAMOUS_PEOPLE,
    generate_random_name,
)


class RandomNamesTest(SimpleTestCase):
    def test_random_name_parts_load_from_config_files(self):
        self.assertIn("Admiring", ADJECTIVES)
        self.assertIn("Turing", FAMOUS_PEOPLE)

    @patch("courses.random_names.random.choice")
    def test_generate_random_name_combines_configured_parts(self, choice):
        choice.side_effect = ["Admiring", "Turing"]

        name = generate_random_name()

        self.assertEqual(name, "Admiring Turing")
