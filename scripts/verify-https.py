#!/usr/bin/env python3
"""Exercise the packaged HTTPS preflight without login grants or notifications."""
import argparse
import http.server
import json
import os
import ssl
import subprocess
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/tls'
TLS_ERROR = 'HTTPS 证书或 TLS 握手失败；请检查域名、证书和反代配置'


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"instanceId":"tls-test","authenticated":false,"passwordless":false}')

    def log_message(self, *args):
        pass


def verify(runtime):
    (ROOT/'.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='https-package-', dir=ROOT/'.tmp') as temporary:
        directory = Path(temporary)
        local = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        secure = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(FIXTURES/'server.pem', FIXTURES/'server-key.pem')
        secure.socket = context.wrap_socket(secure.socket, server_side=True)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (local, secure)]
        for thread in threads:
            thread.start()
        try:
            (directory/'gateway-control.json').write_text(json.dumps({'pid': os.getpid(), 'instanceId': 'tls-test'}), encoding='utf-8')
            # OpenSSL must not depend on paths from the machine which built Python.
            empty = directory/'empty-certs'
            empty.mkdir()
            env = {**os.environ, 'SSL_CERT_FILE': str(empty/'missing.pem'), 'SSL_CERT_DIR': str(empty)}

            def probe(url, extra=None):
                preferences = {'port': local.server_port, 'lan': True, 'connections': [{
                    'id': 'probe', 'name': 'TLS test', 'enabled': True, 'accessMode': 'nas',
                    'publicUrl': url, 'proxyUpstream': f'http://192.0.2.1:{local.server_port}'}]}
                (directory/'desktop.json').write_text(json.dumps(preferences), encoding='utf-8')
                result = subprocess.run([str(runtime), 'check-entry', '--data-dir', str(directory)],
                                        input='{"id":"probe"}', env={**env, **(extra or {})},
                                        capture_output=True, text=True, encoding='utf-8', timeout=30)
                value = json.loads(result.stdout)
                if result.returncode not in (0, 1):
                    raise AssertionError(f'Runtime exited {result.returncode}: {result.stderr}')
                return value

            # This real public endpoint returns 404 for /api/auth after a verified TLS handshake.
            public = probe('https://pypi.org')
            assert not public['ok'] and 'HTTP 404' in public.get('error', ''), public
            print('PASS: public HTTPS with default OpenSSL certificate paths unavailable')
            untrusted = probe(f'https://localhost:{secure.server_port}')
            assert untrusted['ok'] is False and untrusted.get('error') == TLS_ERROR, untrusted
            print('PASS: untrusted certificate rejected')
            custom = {'SSL_CERT_FILE': str(FIXTURES/'ca.pem')}
            trusted = probe(f'https://localhost:{secure.server_port}', custom)
            assert trusted['ok'], trusted
            mismatch = probe(f'https://127.0.0.1:{secure.server_port}', custom)
            assert mismatch['ok'] is False and mismatch.get('error') == TLS_ERROR, mismatch
            print('PASS: explicit custom CA works; incorrect hostname rejected')
        finally:
            for server in (local, secure):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    verify(parser.parse_args().runtime.resolve())
