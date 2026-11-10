---
name: cmp-incident-response
description: Investigate and resolve Course Management Platform alerts in its current Coolify deployment. Use when Codex is asked to inspect a CMP GitHub alert issue, diagnose availability or failed background work, fix an incident, validate a fix in dev, or deploy and verify an authorized production fix.
---

# CMP incident response

Use the GitHub alert issue as the incident record. Keep production diagnosis
read-only, reproduce failures locally before changing code, and verify the
deployed public release after promotion.

## Respect the requested scope

- For an investigation or status request, stop after diagnosis and report the
  evidence. Do not edit code or deploy.
- For a fix request, continue through focused local verification and dev
  deployment.
- Deploy to production only when the user explicitly authorizes it or has
  already granted standing permission for the task.
- Never paste unreviewed production logs into a public GitHub issue. Logs may
  contain personal or sensitive data.
- Do not use AWS MAIN credentials on Hetzner. The retired AWS ECS workflow is
  not a current production deploy path.

## 1. Establish the incident

Read the issue and record the alarm name, state-change time, metric,
environment, and suggested log window:

```bash
gh issue view <issue-number> \
  --repo DataTalksClub/course-management-platform \
  --comments
```

Check the deployed versions before drawing conclusions:

```bash
curl --fail --silent https://dev.courses.datatalks.club/api/health/
curl --fail --silent https://courses.datatalks.club/api/health/
```

Dev and production use separate Coolify services and databases. A dev-only
workflow dispatch does not promote its image to production.

## 2. Use current, read-only evidence sources

The live CMP deployment is on Coolify/Contabo. Application events use the
`log` backend, and Contabo's Docker log collector forwards container logs to
VictoriaLogs. Host log access and proxy-level evidence are owned by the
infrastructure operators; use the approved read-only access path documented
in the relevant Hub infrastructure intake. If that access is unavailable,
record the gap and stop rather than switching to AWS credentials or a broader
identity.

For deployment history and worker ownership, consult:

- `deploy/coolify/README.md`
- `deploy/coolify/CMP-WORKERS.md`
- GitHub Actions runs for `deploy-coolify.yml`

The app's CloudWatch backend remains available for explicitly configured
environments, but it is not the current Contabo log or deploy path.

## 3. Collect and interpret evidence

Inspect the issue's UTC window and correlate only the evidence needed to
identify the failure:

- application exceptions and request timings;
- Coolify deployment and container lifecycle events;
- public and dev health/version responses;
- worker success/failure timestamps and due backlog where relevant.

Separate the proximate failure from its root cause. Preserve sensitive log
evidence in the approved private location and report sanitized findings.

## 4. Reproduce with a focused test

Follow the repository's reported-bug rules:

1. Add or update the smallest test that exercises the observed failure.
2. Run only that focused test locally with `uv run pytest <test-path>`.
3. Confirm it fails for the reported reason before implementing the fix.
4. Rerun the focused test and confirm it passes.
5. Let the pull request CI run the full suite; do not run the full local suite
   on the Hetzner host.

Assert the externally correct behavior or the regression boundary shown by
the evidence, not the current implementation detail.

## 5. Fix and verify locally

Implement the smallest root-cause fix and run focused tests for the changed
files. For UI changes, read `docs/design-system.md` and follow the existing
verification workflow. Review the diff and preserve unrelated worktree
changes.

## 6. Validate the fix in dev

Use the isolated dev target with a dev-only workflow dispatch:

```bash
gh workflow run deploy-coolify.yml \
  --repo DataTalksClub/course-management-platform \
  --ref <fix-branch> \
  -f dev_only=true
gh run list --workflow deploy-coolify.yml --branch <fix-branch> --limit 5
gh run watch <run-id> --exit-status
curl --fail --silent https://dev.courses.datatalks.club/api/health/
```

Require the workflow to succeed and the dev health response to report the
expected dev-prefixed release tag. Exercise the regression safely in dev and
confirm the original error is gone. Do not proceed on a green health endpoint
alone if the failing path was not verified.

If a GitHub environment gate blocks the run, do not approve it. Report the
run link and the gate that is waiting.

## 7. Promote an authorized production fix

The current production path is `Deploy CMP Coolify (Contabo)`. A push to
`main` builds and deploys the private release service; the shared release
follower promotes a healthy image to the public rolling application. Never
dispatch the removed `deploy-prod.yaml` workflow.

After the authorized production deployment, require the public
`https://courses.datatalks.club/api/health/` response to report `status=ok` and
the exact built version. Record the workflow link, merge SHA, deployed version,
and live HTTP status. Do not approve a GitHub environment gate; report its run
link instead. If deployment or verification fails, stop and report the
evidence; do not improvise a rollback without explicit authority.

## 8. Close the loop

Add a concise, sanitized issue comment containing:

- root cause and evidence timestamps;
- regression test and its fail/pass result;
- fix commit;
- dev workflow, version, and verification;
- production workflow, version, and verification, if deployed;
- follow-up monitoring or remaining risk.

Close the issue only after the requested scope is complete and the relevant
environment is verified. Keep it open for diagnosis-only work or unresolved
production risk.
