"""Synthetic request checks for the fixed, isolated HTML preview shell."""
import http.client
import tempfile
import unittest
from pathlib import Path

import test_bridge as support
from bridge.api.html_preview import SHELL_CSP, SHELL_FILE

ROOT = Path(__file__).resolve().parents[1]


class GatewayHtmlPreviewTests(unittest.TestCase):
    setUpClass = classmethod(support.HttpTests.setUpClass.__func__)
    setUp = support.HttpTests.setUp
    tearDown = support.HttpTests.tearDown
    login = support.HttpTests.login
    request = support.HttpTests.request

    def raw(self, path, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            conn.request('GET', path, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_fixed_shell_requires_login_and_has_independent_csp(self):
        self.assertEqual(self.raw('/html-preview-shell')[0], 401)
        login = self.login()
        status, headers, body = self.raw('/html-preview-shell', login)
        self.assertEqual(status, 200)
        self.assertEqual(body, (ROOT / 'web' / SHELL_FILE).read_bytes())
        self.assertEqual(headers['Content-Security-Policy'], SHELL_CSP)
        self.assertEqual(headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertIn("sandbox allow-scripts", SHELL_CSP)
        self.assertIn("connect-src 'none'", SHELL_CSP)
        self.assertIn("form-action 'none'", SHELL_CSP)
        self.assertEqual(self.raw('/html-preview-shell?text=untrusted', login)[0], 405)
        status, headers, _ = self.raw('/', login)
        self.assertEqual(status, 200)
        self.assertIn('frame-src ' + self.origin + '/html-preview-shell;', headers['Content-Security-Policy'])
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        self.assertNotIn("script-src 'unsafe-inline'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Frame-Options'], 'DENY')


class RelayHtmlPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            from aiohttp.test_utils import TestClient, TestServer
            from relay.server import create_app, STATE
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        (ROOT / '.tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp')
        self.app = create_app(Path(self.temp.name) / 'relay', 'http://127.0.0.1:1', test_http=True)
        self.server = TestServer(self.app)
        await self.server.start_server()
        self.client = TestClient(self.server)
        await self.client.start_server()
        self.state = self.app[STATE]
        self.origin = str(self.server.make_url('')).rstrip('/')
        self.state.origin = self.origin
        self.state.host = self.origin.removeprefix('http://')

    async def asyncTearDown(self):
        await self.client.close()
        self.state.registry.close()
        self.temp.cleanup()

    async def test_root_and_scoped_shell_are_fixed_and_authenticated(self):
        response = await self.client.get('/html-preview-shell')
        self.assertEqual(response.status, 401)
        self.state.phone_auth = lambda request: {'id': 'synthetic'}
        for prefix in ('', '/d/' + 'a' * 32):
            response = await self.client.get(prefix + '/html-preview-shell')
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.read(), (ROOT / 'web' / SHELL_FILE).read_bytes())
            self.assertEqual(response.headers['Content-Security-Policy'], SHELL_CSP)
            self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
            self.assertEqual((await self.client.get(prefix + '/html-preview-shell?text=untrusted')).status, 404)
            page = await self.client.get(prefix + '/')
            self.assertEqual(page.status, 200)
            self.assertIn('frame-src ' + self.origin + prefix + '/html-preview-shell;', page.headers['Content-Security-Policy'])
            self.assertIn("script-src 'self'", page.headers['Content-Security-Policy'])
            self.assertEqual(page.headers['X-Frame-Options'], 'DENY')
