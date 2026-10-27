from django.test import SimpleTestCase

from deploy.coolify.release_target import (
    DEV_SERVICE_UUID, release_tag, service_uuid, validate_service,
)


class ReleaseTargetTests(SimpleTestCase):
    def test_dev_tag_cannot_match_production_poller(self):
        tag = release_tag("20261027-120000", "1234567", True)
        self.assertEqual(tag, "dev-20261027-120000-1234567")
        self.assertNotRegex(tag, r"^\d{8}-\d{6}-[0-9a-f]{7}$")

    def test_production_tag_keeps_existing_format(self):
        self.assertEqual(
            release_tag("20261027-120000", "1234567", False),
            "20261027-120000-1234567",
        )

    def test_dev_selection_does_not_use_production_uuid(self):
        self.assertEqual(service_uuid(True, "production"), DEV_SERVICE_UUID)
        self.assertEqual(service_uuid(False, "production"), "production")

    def test_dev_validation_rejects_any_other_service(self):
        for uuid, name in (("production", "cmp-dev"),
                           (DEV_SERVICE_UUID, "cmp-staging")):
            with self.assertRaises(ValueError):
                validate_service(uuid, {"name": name}, True)
        validate_service(DEV_SERVICE_UUID, {"name": "cmp-dev"}, True)
