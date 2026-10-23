"""Session locks fence live dispatches even when a processing timeout expires."""
from contextlib import contextmanager
import fcntl
import hashlib
import tempfile
from pathlib import Path

from django.db import connection


@contextmanager
def worker_lock(key):
    lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', [lock_id])
            acquired = cursor.fetchone()[0]
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(%s)', [lock_id])
    else:
        # Local SQLite development only. Production uses shared PostgreSQL locks.
        db_key = hashlib.sha256(str(connection.settings_dict['NAME']).encode()).hexdigest()[:16]
        path = Path(tempfile.gettempdir()) / f'cmp-worker-{db_key}-{lock_id}.lock'
        with path.open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                acquired = False
            try:
                yield acquired
            finally:
                if acquired:
                    fcntl.flock(handle, fcntl.LOCK_UN)
