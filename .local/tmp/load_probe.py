"""Bounded read-only load probe with TRUE concurrency.

GET /api/health/ + / with CONCURRENCY parallel workers for DURATION seconds.
Prints one JSON line with p50/p95/max + status counts. Read-only endpoints.
"""

import json
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = sys.argv[1]
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 100
CONCURRENCY = int(sys.argv[3]) if len(sys.argv) > 3 else 10
OUT = sys.argv[4] if len(sys.argv) > 4 else None

URLS = [f"{BASE}/api/health/", f"{BASE}/"]


def hit(url):
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            resp.read()
            return (time.time() - t0, resp.status, None)
    except Exception as exc:
        code = getattr(exc, "code", None)
        return (time.time() - t0, code or 0, type(exc).__name__)


def main():
    deadline = time.time() + DURATION
    lat, codes, errors = [], {}, {}
    i = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = set()
        while time.time() < deadline or futures:
            while time.time() < deadline and len(futures) < CONCURRENCY:
                futures.add(pool.submit(hit, URLS[i % len(URLS)]))
                i += 1
            done = set()
            for fut in as_completed(futures, timeout=35):
                done.add(fut)
                if len(done) >= max(1, len(futures) // 2):
                    break
            futures -= done
            for fut in done:
                dt, code, err = fut.result()
                lat.append(dt)
                codes[code] = codes.get(code, 0) + 1
                if err:
                    errors[err] = errors.get(err, 0) + 1
    lat.sort()
    result = {
        "base": BASE,
        "requests": len(lat),
        "p50_ms": round(statistics.median(lat) * 1000, 1),
        "p95_ms": round(lat[int(0.95 * (len(lat) - 1))] * 1000, 1) if lat else None,
        "max_ms": round(lat[-1] * 1000, 1) if lat else None,
        "status_counts": {str(k): v for k, v in codes.items()},
        "errors": errors,
    }
    line = json.dumps(result)
    print(line, flush=True)
    if OUT:
        with open(OUT, "w") as fh:
            fh.write(line + "\n")


main()
