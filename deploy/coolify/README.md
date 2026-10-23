# CMP environments

`cmp-staging` is the historical name of the **production** service on
contabo-a (`avcfd5kwb7cj9r1tx4ygjs6v`). It serves `courses.datatalks.club`
using the `cmp_app` role and `cmp` database. The main-push workflow and the
existing Hetzner image poller still target this service.

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
