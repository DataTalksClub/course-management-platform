"""A busy request must not starve the proxy's two-second liveness probe."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request


def probe_app(environ, start_response):
    if environ['PATH_INFO'] == '/busy':
        time.sleep(4)
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [b'OK']


def test_health_serves_while_another_request_is_busy():
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    with subprocess.Popen(
        [sys.executable, '-m', 'gunicorn',
         '--config', str(root / 'gunicorn.conf.py'),
         '--bind', f'127.0.0.1:{port}',
         'api.tests.test_gunicorn_liveness:probe_app'],
        cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) as server:
        def get(path, timeout=1):
            with urllib.request.urlopen(
                f'http://127.0.0.1:{port}{path}', timeout=timeout,
            ) as response:
                return response.status

        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    assert get('/ping') == 200
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            with ThreadPoolExecutor(max_workers=1) as pool:
                busy = pool.submit(get, '/busy', 8)
                time.sleep(0.5)
                assert not busy.done()
                # Below the rolling readiness probe's two-second deadline.
                assert get('/ping', timeout=1.5) == 200
                assert busy.result() == 200
        finally:
            server.terminate()
            server.wait(timeout=10)
