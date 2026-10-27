# Traefik bespoke config for CMP (courses.datatalks.club) on contabo-a

## cmp-ratelimit.yml — per-IP rate limiting (AC: ~10 req/s avg, burst 30)

Source of truth: `cmp-ratelimit.yml` in this directory.
Install: copy to `/data/coolify/proxy/dynamic/cmp-ratelimit.yml` on
contabo-a (root-owned, mode 600 like the neighbouring origin-enforce.yml).
Traefik file-watch hot-reloads it — no proxy restart.

Verify after install:

```bash
# file picked up (no "service not found" for cmp-* routers)
sudo docker logs coolify-proxy --since 2m 2>&1 | grep -i "cmp-" | head
# burst from one IP: leaderboard pages 429, health stays 200
for i in $(seq 1 50); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    "https://courses.datatalks.club/ml-zoomcamp/leaderboard/1/"
done | sort | uniq -c
curl -s -o /dev/null -w "%{http_code} %{time_total}\n" \
  https://courses.datatalks.club/api/health/
```

Rollback: delete `/data/coolify/proxy/dynamic/cmp-ratelimit.yml`.
Coolify's own routers (priority 110) take over again immediately.

Service-name note: the `service:` lines reference the public app's Docker
service names, which are stable across Coolify redeploys (verified identical
on the 23:21Z and 23:56Z 2026-10-26 public containers). If a future
recreate ever renames them, compare
`docker inspect <public-container> | grep traefik.http.services` output and
update `cmp-ratelimit.yml` accordingly.

Second layer: the Django app also enforces the same budget per IP
(`course_management/middleware.py::RateLimitMiddleware`, 10/s avg, burst 30,
same path exemptions) so the protection survives any Traefik config drift
and deploys through the normal GHCR/Coolify path.

## Traefik JSON access logs (ClientHost + User-Agent) → VictoriaLogs

Traefik static flags (one-time change to the proxy compose on contabo-a,
`/data/coolify/proxy/docker-compose.yml`, with a `.bak` copy first —
same practice as the existing `.bak-*` files there):

```yaml
command:
  - '--accesslog=true'
  - '--accesslog.format=json'
  - '--accesslog.fields.defaultmode=keep'
  - '--accesslog.fields.headers.defaultmode=drop'
  - '--accesslog.fields.headers.names.User-Agent=keep'
```

Then `docker compose up -d traefik` in `/data/coolify/proxy` (brief
recreate, seconds). `fields.defaultmode=keep` retains ClientHost (plus
method/path/status/duration); the headers stanza adds User-Agent.

Shipping: no Vector change needed. contabo-a Vector `docker_logs` source
ships every container except vector/victoria ones, so coolify-proxy JSON
lines flow to VictoriaLogs automatically. Verify with a VL query for
`container_name="coolify-proxy"` containing ClientHost and User-Agent.
