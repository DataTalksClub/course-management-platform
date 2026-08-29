---
name: cmp-incident-response
description: Investigate and resolve Course Management Platform CloudWatch alert issues end to end. Use when Codex is asked to inspect a CMP GitHub alert issue, pull dev or production AWS logs, diagnose 5xx responses or failed background work, fix an incident with test-driven development, validate a fix in dev, or deploy and verify an authorized production fix.
---

# CMP incident response

Use the GitHub alert issue as the incident record. Keep production diagnosis
read-only, reproduce the failure locally before changing code, and promote one
tested image from dev to production.

## Respect the requested scope

- For an investigation or status request, stop after diagnosis and report the
  evidence. Do not edit code or deploy.
- For a fix request, continue through local verification and dev deployment.
- Dispatch production only when the user explicitly authorizes a production
  deployment for the incident. General use of this skill is not authorization.
- Never paste unreviewed CloudWatch output into a GitHub issue. This repository
  is public and logs can contain personal or sensitive data.

## 1. Establish the incident

Read the issue and note the alarm name, state-change time, metric, environment,
and suggested log window:

```bash
gh issue view <issue-number> \
  --repo DataTalksClub/course-management-platform \
  --comments
```

Confirm the current deployed versions before drawing conclusions:

```bash
curl --fail --silent https://dev.courses.datatalks.club/api/health/
curl --fail --silent https://courses.datatalks.club/api/health/
```

## 2. Assume read-only production access

The default AWS profile is the phone-controlled AWS Gate identity in account
`817685572750`. Ask the user to open AWS Gate if credential resolution returns
HTTP 403. Then assume the cross-account diagnostic profile:

```bash
aws sts get-caller-identity
aws --profile cmp-alert-investigator sts get-caller-identity
```

Require the second ARN to start with:

```text
arn:aws:sts::387546586013:assumed-role/cmp-alert-investigator/
```

Stop if the account or role differs. Do not fall back to broader credentials.
The role is diagnostic only; it cannot deploy, mutate services, execute in
containers, or read Secrets Manager values.

## 3. Collect and interpret evidence

Run the bundled collector from the repository root using the UTC window in the
issue:

```bash
.claude/skills/cmp-incident-response/scripts/collect_cloudwatch_context.sh \
  --environment prod \
  --alarm cmp-prod-alb-target-5xx \
  --start '2026-08-13T01:48:01Z' \
  --end '2026-08-13T02:03:01Z'
```

Use `dev` for dev alarms. The collector writes private evidence under
`.tmp/cmp-incidents/`; never commit that directory. Inspect only the relevant
events and correlate timestamps across:

- application logs and tracebacks;
- alarm history and metric reason;
- ECS service events, task lifecycle, and task definition;
- ALB target health;
- deployed health/version response.

Separate the proximate failure from its root cause. If permissions are denied,
record the exact action and resource; update the narrowly scoped investigator
role in `DataTalksClub/aws-infra` rather than using admin access.

## 4. Reproduce with a failing test

Follow `AGENTS.md` bug rules exactly:

1. Add or update the smallest test that exercises the observed failure.
2. Run that focused test with `uv run python manage.py test <test-label>`.
3. Confirm it fails for the production reason, not from bad setup.
4. Preserve the failing output in the incident notes.
5. Only then change production code.

Do not encode the current implementation into the test. Assert the externally
correct behavior or the regression boundary demonstrated by the logs.

## 5. Fix and verify locally

Implement the smallest root-cause fix. Rerun, in order:

```bash
uv run python manage.py test <test-label>
uv run python manage.py test <affected-app-or-module>
make tests
make typecheck
```

For UI changes, also read `docs/design-system.md` and use the existing
`.claude/skills/verify` workflow. Review the diff and preserve unrelated user
changes in a dirty worktree.

## 6. Deploy and validate dev

Commit only the incident fix and push it directly to `main`, as required by
`AGENTS.md`. A qualifying push runs `.github/workflows/deploy-dev.yaml`, which
tests, type-checks, builds one image, and deploys it to dev.

```bash
gh run list --workflow deploy-dev.yaml --branch main --limit 5
gh run watch <run-id> --exit-status
curl --fail --silent https://dev.courses.datatalks.club/api/health/
```

Require the workflow to succeed and the dev health version to contain the
fix commit's seven-character SHA. Exercise the exact regression safely in dev,
then collect the corresponding dev logs and confirm the original error is gone.
Do not proceed on a merely green health endpoint if the failing path was not
verified.

## 7. Promote the verified image to production

Use the exact version returned by the dev health endpoint. Do not rebuild or
substitute another tag. Once the user has explicitly authorized production:

```bash
gh workflow run deploy-prod.yaml \
  --repo DataTalksClub/course-management-platform \
  --ref main \
  -f confirmProdDeploy=true \
  -f deployTag='<verified-dev-version>'
gh run list --workflow deploy-prod.yaml --branch main --limit 5
gh run watch <run-id> --exit-status
```

After success, require production `/api/health/` to report that exact version.
Exercise a safe production verification, inspect the production logs and alarm
state, and watch for recurrence. If deployment or verification fails, stop and
report the evidence; do not improvise a rollback without explicit authority.

## 8. Close the loop

Add a concise, sanitized issue comment containing:

- root cause and evidence timestamps;
- regression test and its fail/pass result;
- fix commit;
- dev workflow, version, and verification;
- production workflow, version, and verification, if deployed;
- any follow-up monitoring or remaining risk.

Close the issue only after the requested scope is complete and the relevant
environment is verified. Keep it open for diagnosis-only work or unresolved
production risk.
