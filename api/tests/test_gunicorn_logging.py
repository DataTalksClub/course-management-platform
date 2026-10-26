"""Exercise the actual Gunicorn formatter without a database."""
import datetime
import io
import logging
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase
from gunicorn.config import Config


class GunicornAccessLogTests(SimpleTestCase):
    def render(self, path, request_id=None):
        config = Config()
        config_path = Path(__file__).resolve().parents[2] / 'gunicorn.conf.py'
        if config_path.exists():
            settings = {}
            exec(config_path.read_text(), settings)
            for name in ('accesslog', 'access_log_format', 'logger_class'):
                config.set(name, settings[name])
        logger = config.logger_class(config)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        old_handlers = logger.access_log.handlers[:]
        logger.access_log.handlers = [handler]
        self.addCleanup(setattr, logger.access_log, 'handlers', old_handlers)
        self.assertEqual(config.accesslog, '-')
        environ = {
            'REQUEST_METHOD': 'GET', 'PATH_INFO': path,
            'QUERY_STRING': 'email=person@example.test&token=secret-query',
            'RAW_URI': path + '?token=secret-query',
            'SERVER_PROTOCOL': 'HTTP/1.1', 'REMOTE_ADDR': '192.0.2.1',
            'HTTP_AUTHORIZATION': 'Bearer secret-header',
            'HTTP_REFERER': 'https://example.test/?token=secret-referrer',
            'HTTP_USER_AGENT': 'person@example.test',
        }
        if request_id:
            environ['HTTP_X_REQUEST_ID'] = request_id
        response = SimpleNamespace(status='200 OK', sent=2, headers=[])
        request = SimpleNamespace(headers=list(environ.items()))
        logger.access(response, request, environ, datetime.timedelta(microseconds=1234))
        return stream.getvalue()

    def test_duration_and_generated_request_id_without_private_data(self):
        line = self.render('/api/health/')
        self.assertIn('"GET /api/health/ HTTP/1.1" 200 2 1234 ', line)
        self.assertRegex(line, r'request_id="[0-9a-f]{32}"')
        for value in ('?', 'person', 'secret', '192.0.2.1', 'Bearer'):
            self.assertNotIn(value, line)

    def test_untrusted_request_id_cannot_leak_pii(self):
        line = self.render('/api/health/', 'person@example.test-secret')
        self.assertNotIn('person', line)
        self.assertRegex(line, r'request_id="[0-9a-f]{32}"')

    def test_dynamic_and_unknown_paths_do_not_leak_tokens_or_emails(self):
        for path in ('/register/confirm/secret-token/',
                     '/register/confirm/person@example.test/',
                     '/accounts/confirm-email/secret-token/',
                     '/unknown/person@example.test/secret-token/',
                     '/unknown/person%40example.test/secret-token/'):
            with self.subTest(path=path):
                line = self.render(path)
                self.assertNotIn('secret-token', line)
                self.assertNotIn('person', line)
                self.assertNotIn('?', line)
