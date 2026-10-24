from django.test import TestCase, override_settings
from django.urls import reverse

RELAY_HEALTHY_SETTINGS = {
    "RELAY_URL": "https://relay.example.com",
    "RELAY_API_KEY": "secret-token",
    "RELAY_CLIENT": "dtc-courses",
    "RELAY_AUDIENCE": "dtc-courses",
    "RELAY_TRANSACTIONAL_DRY_RUN": False,
    "OBSERVABILITY_ENVIRONMENT": "production",
    "ENVIRONMENT": "production",
}


class HealthViewTests(TestCase):
    @override_settings(**RELAY_HEALTHY_SETTINGS)
    def test_health_healthy_config_returns_ok(self):
        url = reverse("api_health")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("version", data)
        self.assertEqual(data.get("relay_status"), "ok")

    @override_settings(
        **{**RELAY_HEALTHY_SETTINGS, "RELAY_TRANSACTIONAL_DRY_RUN": True},
    )
    def test_health_dry_run_on_prod_fails_loudly(self):
        url = reverse("api_health")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertTrue(data.get("degraded"))
        self.assertEqual(data.get("relay_status"), "FAIL")
        self.assertIn("RELAY_TRANSACTIONAL_DRY_RUN", data.get("relay_error", ""))
        self.assertIn("RELAY_TRANSACTIONAL_DRY_RUN", str(data.get("relay", {})))

    @override_settings(
        **{
            **RELAY_HEALTHY_SETTINGS,
            "OBSERVABILITY_ENVIRONMENT": "dev",
            "ENVIRONMENT": "dev",
            "RELAY_TRANSACTIONAL_DRY_RUN": True,
        },
    )
    def test_health_dry_run_on_dev_is_ok(self):
        url = reverse("api_health")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data.get("relay_status"), "ok")

    @override_settings(
        **{
            **RELAY_HEALTHY_SETTINGS,
            "OBSERVABILITY_ENVIRONMENT": "dev",
            "ENVIRONMENT": "dev",
            "RELAY_API_KEY": "",
            "RELAY_TRANSACTIONAL_DRY_RUN": True,
        },
    )
    def test_health_empty_api_key_on_dev_is_ok(self):
        url = reverse("api_health")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data.get("relay_status"), "unconfigured")

    @override_settings(
        **{**RELAY_HEALTHY_SETTINGS, "RELAY_API_KEY": ""},
    )
    def test_health_empty_api_key_fails_loudly(self):
        url = reverse("api_health")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertTrue(data.get("degraded"))
        self.assertEqual(data.get("relay_status"), "FAIL")
        self.assertIn("relay_config_missing", data.get("relay_error", ""))

    @override_settings(
        **{**RELAY_HEALTHY_SETTINGS, "RELAY_URL": "not-a-valid-url"},
    )
    def test_health_invalid_config_fails_loudly(self):
        url = reverse("api_health")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertTrue(data.get("degraded"))
        self.assertEqual(data.get("relay_status"), "FAIL")
        self.assertIn("relay_config_invalid", data.get("relay_error", ""))
