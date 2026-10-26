import re
from pathlib import Path

import yaml
from django.test import SimpleTestCase

from course_management.datamailer.client import DEFAULT_TIMEOUT_SECONDS

GUNICORN_DEFAULT_TIMEOUT_SECONDS = 30
SAFETY_MARGIN_SECONDS = 10


class DeploymentWorkflowTestCase(SimpleTestCase):
    def workflow_events(self, filename):
        workflow = (
            Path(__file__).resolve().parents[2]
            / ".github" / "workflows" / filename
        )
        # BaseLoader preserves GitHub's YAML key `on` as a string.
        return yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)["on"]

    def test_retired_aws_dev_workflow_is_manual_only(self):
        events = self.workflow_events("deploy-dev.yaml")

        self.assertEqual(
            set(events),
            {"workflow_dispatch"},
            "Automatic AWS dev deployments reference a deleted target "
            "group. Coolify owns main-push deployments after the "
            "Contabo migration; keep AWS dev manual-only.",
        )

    def test_coolify_owns_main_push_deployments(self):
        events = self.workflow_events("deploy-coolify.yml")

        self.assertIn("main", events["push"]["branches"])


class DeployConfigTestCase(SimpleTestCase):
    def test_production_release_service_cannot_advertise_public_traffic(self):
        template = (
            Path(__file__).resolve().parents[2]
            / "deploy/coolify/docker-compose.staging.yml"
        )
        web = yaml.safe_load(template.read_text())["services"]["web"]
        self.assertEqual(
            web.get("labels", {}).get("traefik.enable"),
            "false",
            "cmp-staging force-recreates its single web container. "
            "Public traffic must stay on the independent, health-gated "
            "rolling Application during release-service replacement.",
        )

    def test_dev_has_an_isolated_coolify_backend(self):
        template = (
            Path(__file__).resolve().parents[2]
            / "deploy/coolify/docker-compose.dev.yml"
        )
        self.assertTrue(
            template.exists(),
            "DEV needs its own Coolify backend after removing "
            "its production alias.",
        )
        web = yaml.safe_load(template.read_text())["services"]["web"]
        env = web["environment"]
        self.assertEqual(
            env["PUBLIC_BASE_URL"], "https://dev.courses.datatalks.club"
        )
        self.assertEqual(env["DATABASE_URL"], "${CMP_DEV_DATABASE_URL}")
        self.assertEqual(env["VERSION"], web["image"].rsplit(":", 1)[1])
        self.assertEqual(env["OBSERVABILITY_ENVIRONMENT"], "dev")
        self.assertEqual(env["RELAY_TRANSACTIONAL_DRY_RUN"], "1")
        self.assertEqual(env["RELAY_SYNC_ON_USER_CREATE"], "0")
        self.assertIn("/api/health/", str(web["healthcheck"]["test"]))

    def test_private_release_version_matches_image_tag(self):
        # Intake 91dbd820: prod /api/health/ reported a stale VERSION
        # (20261025-092420-c0db50c) after the 0c8eaab deploy because the
        # private release compose pinned a new image but kept an old
        # VERSION env. The public rolling follower mirrors this env, so
        # source VERSION must equal the image tag in the deploy config.
        template = (
            Path(__file__).resolve().parents[2]
            / "deploy/coolify/docker-compose.staging.yml"
        )
        web = yaml.safe_load(template.read_text())["services"]["web"]
        image_tag = web["image"].rsplit(":", 1)[1]
        self.assertEqual(
            str(web["environment"]["VERSION"]),
            image_tag,
            "Private release VERSION must equal its image tag; "
            "/api/health/ and the public rolling follower read this env.",
        )

    def gunicorn_timeout_seconds(self):
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        contents = dockerfile.read_text()
        cmd_match = re.search(r"^CMD \[(.*)\]$", contents, re.MULTILINE)
        self.assertIsNotNone(cmd_match, "Dockerfile CMD not found")
        args = [
            arg.strip().strip('"') for arg in cmd_match.group(1).split(",")
        ]
        if "--timeout" in args:
            return int(args[args.index("--timeout") + 1])
        return GUNICORN_DEFAULT_TIMEOUT_SECONDS

    def test_gunicorn_worker_timeout_exceeds_datamailer_timeout(self):
        gunicorn_timeout = self.gunicorn_timeout_seconds()

        self.assertGreaterEqual(
            gunicorn_timeout,
            DEFAULT_TIMEOUT_SECONDS + SAFETY_MARGIN_SECONDS,
            "gunicorn's worker timeout must comfortably exceed the "
            "Datamailer HTTP client timeout. Otherwise, a slow or "
            "unreachable Datamailer response gets the whole worker "
            "SIGKILLed mid-request (a hard 'Internal Server Error' with "
            "no clean message) instead of being caught as an ordinary "
            "requests.RequestException.",
        )


class HealthVersionWiringTestCase(SimpleTestCase):
    """Intake 91dbd820: VERSION must track the deployed image tag.

    /api/health/ returns settings.VERSION. If the image tag advances but the
    VERSION env does not, prod reports the previous release. These tests fail
    when the wiring drifts: baked build-arg missing, deploy automation pinning
    the image without VERSION, or the poller converging on image alone.
    """

    def repo_root(self):
        return Path(__file__).resolve().parents[2]

    def test_dockerfile_bakes_version_build_arg(self):
        contents = (self.repo_root() / "Dockerfile").read_text()
        self.assertRegex(
            contents,
            r"(?m)^ARG VERSION=",
            "Dockerfile must declare ARG VERSION so the release tag is baked "
            "into the image (/api/health/ fallback when runtime env is unset).",
        )
        self.assertRegex(
            contents,
            r"(?m)^ENV VERSION=",
            "Dockerfile must export ENV VERSION from the build arg.",
        )

    def test_coolify_build_passes_version_build_arg(self):
        workflow = (
            self.repo_root() / ".github/workflows/deploy-coolify.yml"
        ).read_text()
        self.assertIn(
            "VERSION=${{ steps.identity.outputs.version }}",
            workflow,
            "Coolify build must pass VERSION=<image tag> as a Docker "
            "build-arg so the baked version equals the pushed GHCR tag.",
        )

    def test_coolify_deploy_pins_version_env(self):
        workflow = (
            self.repo_root() / ".github/workflows/deploy-coolify.yml"
        ).read_text()
        self.assertIn(
            "VERSION",
            workflow,
            "Coolify deploy step must pin the VERSION env alongside the image.",
        )
        self.assertRegex(
            workflow,
            r"VERSION.*image_tag",
            "Coolify deploy must set VERSION from the same IMAGE_TAG value "
            "used for the image pin.",
        )

    def test_hetzner_poller_pins_version_env(self):
        poller = (
            self.repo_root() / "deploy/coolify/hetzner-rollout.sh"
        ).read_text()
        self.assertIn(
            "VERSION",
            poller,
            "Hetzner poller must pin VERSION alongside the image "
            "(it owns convergence when GHA cannot reach Coolify).",
        )
        self.assertRegex(
            poller,
            r"compose_version.*latest|VERSION.*latest",
            "Hetzner poller must compare/pin VERSION against the newest GHCR tag.",
        )
