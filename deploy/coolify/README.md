# CMP environments

`cmp-staging` is the historical name of the private **production release**
service on contabo-a (`avcfd5kwb7cj9r1tx4ygjs6v`). It uses the `cmp_app`
role and `cmp` database. The main-push workflow and the existing Hetzner
image poller still target this service. Its domain metadata must stay empty
and its web component must keep `traefik.enable=false` in saved, generated,
and running configuration. The checked-in template enforces this guard.

Public `courses.datatalks.club` belongs to native Coolify Docker Image
Application `cmp-production-rolling-web` (`9gqubsq4lxubaxm27v1mtq9u`), also
on contabo-a. The shared machine-management release follower promotes only
the healthy private source's immutable image and runtime environment. A new
public container starts alongside the old one; Docker readiness and Traefik's
active health checks gate traffic. The old replica withdraws readiness, keeps
serving for six seconds, then receives TERM with a 45-second grace period.
A failed replacement retains the old healthy public container. One replica
normally remains after deployment; overlap occurs during replacement.

The shared implementation, pinned helper assets, drain-hook installer,
follower manifest/cron, tests and upgrade procedure live in
[machine-management's rolling-web runbook](https://github.com/alexeygrigorev/machine-management/blob/main/deployments/coolify-rolling-web.md),
first installed by commit `6efd197acf5d181414af4d9c9ce6aedd0e48ca5c`.
CMP and AISHL use this same pattern. Keep its follower cron and flock lock;
do not install a competing CMP controller. The public readiness listener is
internal port 8099, `/ready`, Host `localhost`; it checks the application at
port 80, `/api/health/`. Traefik checks every two seconds with a one-second
timeout. Exact versioned asset mounts and SHA-256 checks prevent stale helper
files. The follower refuses promotion if the reviewed Coolify 4.4.7 drain-hook
checksum, helper bindings, or native rolling settings change. Review/rebase
the hook before upgrading Coolify.

CMP currently migrates on container boot while the old public container
serves. Releases therefore require backward-compatible migrations. Source
health or a green build alone does not establish public promotion: require
the native deployment to finish and public `/api/health/` to report the
expected immutable release. Preserve the private source container: existing
CMP scheduled tasks execute there.

For a controlled replacement, continuously curl the public homepage and
`/api/health/` with cache-busting query strings and no-cache headers. Request
a normal native Application deployment, and correlate Docker lifecycle events
with `Rolling update started`, `New container is healthy`,
`Draining old web backend before termination.`, and `Rolling update completed`.
Require replacement health before old drain/termination and zero 502/503 or
curl failures. Also recreate the private `cmp-staging` source and confirm
its container changes while public web continues serving. Do not test this
by force-recreating the public native container outside Coolify.

When checking a later Recreate event, identify which resource it belongs to.
`web-avcfd5kwb7cj9r1tx4ygjs6v` is the private release source; its replacement
time alone does not show a public traffic interruption. Check that its saved,
generated and running labels still disable Traefik, then inspect the native
public Application's deployment and timestamped public probes. Accept a
controlled rollout only when the new public container becomes healthy before
the old container drains and terminates, and public probes remain successful
through both the native rollout and private source replacement.

## October 23 production incident

At intake, both CMP and AISHL production domains were on single-web Compose
Services: neither had rolling replacement, a two-replica overlap, nor a
Traefik active health gate. Alexey's t1286u expected rolling deployments;
the installed topology did not meet that expectation. Coolify activity 227,
created at `2026-10-23T12:39:54Z`, records CMP web Recreate, Recreated,
Starting, then Started on release `20261023-123901-9253b21`. Replacing the
only public backend caused the reported Bad Gateway gap. This was a real
deployment interruption. The activity does not establish an exact outage
duration. AISHL's corresponding activities were 218–220.

Standalone Compose `--force-recreate` has no start-first guarantee. Swarm's
`deploy.update_config` does not change that behavior, and a health check on
a lone killed backend cannot keep serving. The shared native rolling setup
above now closes that gap; source Service replacement remains non-rolling
and private. Public alerts remain enabled.

Independent CMP acceptance on October 23, `15:49:07–15:51:47Z`, replaced
the native public container and then actually recreated `cmp-staging`.
Cache-busted continuous curl recorded 117 homepage and 235 health responses,
all HTTP 200, with zero curl errors or 502/503 responses. Docker events put
new public health at `15:49:36.479Z`, old drain at `15:50:13.911Z`, and old
termination at `15:50:20.459Z`. The source became healthy at `15:50:37.075Z`;
observation continued for over a minute after recovery. The exact deployed
image stayed `20261023-143650-b1b7f4b`. These are sampled continuity results,
not a guarantee against host failure or incompatible future migrations.

The r2 revalidation repeated both replacements at `16:13:08–16:15:45Z`.
All 96 homepage and 235 health samples returned HTTP 200, with zero curl
errors. Coolify recorded replacement health at `16:14:06.591764Z`, the
old-backend drain hook at `16:14:06.901572Z`, and rolling completion at
`16:14:18.092658Z`. The public container changed during the native rollout
and stayed unchanged during the subsequent private source recreate. The
image stayed the same; helper hashes, routing guards and follower convergence
passed before and after. This rerun uses retained Coolify lifecycle markers:
a late query of Docker's bounded event history missed the early events.
The earlier complete Docker event stream remains in the private incident
evidence directory.

Related Hub intakes:

- [CMP rolling production e9f2f030](https://hub.dtcdev.click/#/intake/e9f2f030-a810-44b6-ab71-0fca8df7c516): activity 227 and controlled public replacement.
- [CMP DEV recovery e5c2fd40](https://hub.dtcdev.click/#/intake/e5c2fd40-130d-4896-9349-fbfa0385d11f): separate missing DEV route/backend incident; retain isolation.
- [AISHL network repair 4e78b705](https://hub.dtcdev.click/#/intake/4e78b705-d8a8-42e7-8581-cd932a865a14): creation-time network repair, retained alongside rolling web.
- [AISHL rolling d9c11a67](https://hub.dtcdev.click/#/intake/d9c11a67-c416-4c5c-84cc-92f0c3e2b543): shared health gate, overlap and drain pattern.

## Isolated DEV

`cmp-dev` (`qjnpmney8j8ehfuqcmzpjtzt`) is a separate Coolify service on
contabo-a, serving only `dev.courses.datatalks.club`. Its source template is
`docker-compose.dev.yml`. Set its URL through Coolify's service `urls` API
(`name: web`), so Coolify generates the Traefik labels and connects the proxy
to its network. Do not restore DEV as an alias of the production service.

DEV uses the existing `cmp_dev` role and database on pg-shared through the
WireGuard bridge. Put the connection string in the service's
`CMP_DEV_DATABASE_URL` environment variable. Database CONNECT grants isolate
this role from production. Bootstrap only synthetic staff/student accounts;
do not seed DEV with production data.

Set `SECRET_KEY`, `RELAY_WEBHOOK_TOKEN`, `AUTH_TOKEN`, and `DEV_AUTH_TOKEN`
through Coolify's environment API. The smoke suite authenticates with an
`accounts.Token` row belonging to its DEV staff user, rather than these
environment variables. Store that row's key and the staff login in GitHub's
`E2E_DEV_API_TOKEN`, `E2E_DEV_ADMIN_EMAIL`, and `E2E_DEV_ADMIN_PASSWORD`
secrets. Keep values private and pass them on stdin when setting secrets.

The DEV service keeps transactional dry-run enabled and user sync disabled.
Its Relay API key is initially empty; the two live email-render assertions
xfail until a DEV Relay client is configured. Browser/API lifecycle checks
still run. Never enable delivery to make a smoke test pass.

DEV image updates are explicit: pin both `web.image` and `web.environment.VERSION`
to the same tested release in its Coolify compose, then deploy **cmp-dev**.
The production poller's "converged" result only compares its own service's
image metadata; it says nothing about DEV's hostname or backend health.

After a DEV deployment, require all of:

1. Coolify's DEV container is running and its JSON healthcheck passes.
2. The external DEV `/api/health/` returns HTTP 200, `status: ok`, and the
   expected release. Confirm the production health response is unchanged.
3. A database identity check returns `cmp_dev` for both current database and
   current user. Check production CONNECT is denied for the DEV role.
4. Dispatch `E2E Smoke (Dev)` on main with `expected_version` set to that
   release, and require the smoke job to succeed.

The October 23 isolation change removed DEV from the production service but
left no DEV replacement. Traefik consequently returned its default 503 while
the production image poller reported convergence. The isolated service closes
that gap without changing production routing, data, or image.
