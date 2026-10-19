#!/usr/bin/env python3
"""Isolated managed Claude API selection against two local mock endpoints."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bridge.features.accounts.accounts import private_json
from bridge.features.accounts.cli_sync import LocalCliSync
from bridge.clients.claude.cli_session import managed_api_env


class MockAPI(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_CONNECT(self):
        self.server.calls.append(('external', self.path, '', ''))
        self.send_error(403)

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"data":[]}')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        self.server.calls.append(('model', self.path, self.headers.get('x-api-key') or
                                  self.headers.get('Authorization'), body.get('model')))
        response = {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
                    'content': [{'type': 'text', 'text': 'Fixture reply.'}], 'model': body.get('model'),
                    'stop_reason': 'end_turn', 'stop_sequence': None,
                    'usage': {'input_tokens': 1, 'output_tokens': 1}}
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        events = [
            ('message_start', {'type': 'message_start', 'message': {**response, 'content': [], 'stop_reason': None}}),
            ('content_block_start', {'type': 'content_block_start', 'index': 0,
                                     'content_block': {'type': 'text', 'text': ''}}),
            ('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                     'delta': {'type': 'text_delta', 'text': 'Fixture reply.'}}),
            ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None},
                               'usage': {'output_tokens': 1}}),
            ('message_stop', {'type': 'message_stop'}),
        ]
        for event, value in events:
            self.wfile.write(f'event: {event}\ndata: {json.dumps(value)}\n\n'.encode())
        self.wfile.flush()


def native_turn(binary, root, profile, server, credential):
    before = len(server.calls)
    run_env = managed_api_env()
    result = subprocess.run([binary, '-p', 'Synthetic local fixture only.', '--output-format', 'json',
                             '--max-turns', '1', '--no-session-persistence'],
                            cwd=root, env=run_env, capture_output=True, text=True, timeout=35)
    assert any(kind == 'model' and path.split('?', 1)[0] == '/v1/messages'
               and actual == credential and model == profile['model']
               for kind, path, actual, model in server.calls[before:]), [
        (kind, path, model) for kind, path, _, model in server.calls[before:]]
    assert result.returncode == 0, 'Native CLI rejected mock response'


def main():
    binary = shutil.which('claude')
    if not binary:
        raise RuntimeError('Installed Claude CLI unavailable')
    parent = ROOT/'.tmp'
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='claude-sync-native-', dir=parent) as temporary:
        root = Path(temporary)
        native = root/'original-claude'
        native.mkdir()
        original = {'permissions': {'defaultMode': 'plan'}, 'hooks': {'PreToolUse': []},
                    'env': {'UNRELATED_FIXTURE': 'preserved',
                            'ANTHROPIC_API_KEY': 'native-fixture-key',
                            'ANTHROPIC_MODEL': 'native-fixture-model'}}
        private_json(native/'settings.json', original)
        servers = [ThreadingHTTPServer(('127.0.0.1', 0), MockAPI) for _ in range(2)]
        for server in servers:
            server.calls = []
            threading.Thread(target=server.serve_forever, daemon=True).start()
        origins = [f'http://127.0.0.1:{server.server_port}' for server in servers]
        env = {'HOME': str(root), 'CLAUDE_CONFIG_DIR': str(native), 'ANTHROPIC_API_KEY': 'ambient-wrong',
               'ANTHROPIC_BASE_URL': 'https://ambient.invalid', 'ANTHROPIC_MODEL': 'ambient-wrong-model',
               'HTTP_PROXY': origins[0], 'HTTPS_PROXY': origins[0], 'ALL_PROXY': origins[0],
               'http_proxy': origins[0], 'https_proxy': origins[0], 'all_proxy': origins[0],
               'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'}
        bridge = SimpleNamespace(data_dir=root)
        sync = LocalCliSync(bridge)
        rows = []
        for name, origin in zip(('A', 'B'), origins):
            identifier = (name.lower()*32)
            path = root/'cli-access'/'claude'/identifier/'api.json'
            private_json(path, {'key': f'fixture-key-{name}'})
            rows.append({'id': identifier, 'kind': 'api', 'directory': str(native),
                         'secretPath': str(path), 'baseUrl': origin,
                         'model': f'fixture-model-{name}',
                         'authScheme': 'bearer' if name == 'B' else 'x-api-key'})
        try:
            with patch.dict(os.environ, env):
                assert sync.preflight('claude')['sharedWithDesktop'] is False
                owned = SimpleNamespace(process=SimpleNamespace(poll=lambda: None),
                                        condition=threading.Condition(), active=True, pending={})
                busy_cli = SimpleNamespace(lock=threading.RLock(), owned={'fixture': owned})
                bridge.desktop_sessions = SimpleNamespace(adapters={'claude': SimpleNamespace(cli=busy_cli)})
                try:
                    sync.preflight('claude')
                except ValueError:
                    pass
                else:
                    raise AssertionError('Active gateway-owned Claude session did not block switching')
                del bridge.desktop_sessions
                assert sync.apply('claude', rows[0])['status'] == 'applied'
                assert sync.verify('claude', rows[0])['status'] == 'configured'
                assert json.loads((native/'settings.json').read_text())['hooks'] == original['hooks']
                native_turn(binary, root, rows[0], servers[0], 'fixture-key-A')
                before = (native/'settings.json').read_bytes()
                assert sync.apply('claude', rows[1])['status'] == 'applied'
                with patch.object(sync, '_claude_auth', side_effect=ValueError('fixture verification failure')):
                    try:
                        sync.verify('claude', rows[1])
                    except ValueError as error:
                        assert str(error) == 'fixture verification failure'
                    else:
                        raise AssertionError('Expected injected verification failure')
                sync.restore('claude', {})
                assert (native/'settings.json').read_bytes() == before
                assert sync.verify('claude', rows[0])['status'] == 'configured'
                native_turn(binary, root, rows[0], servers[0], 'fixture-key-A')
                assert sync.apply('claude', rows[1])['status'] == 'applied'
                assert sync.verify('claude', rows[1])['status'] == 'configured'
                selected = json.loads((native/'settings.json').read_text())
                assert selected['env']['UNRELATED_FIXTURE'] == 'preserved'
                assert selected['permissions'] == original['permissions']
                assert selected['hooks'] == original['hooks']
                native_turn(binary, root, rows[1], servers[1], 'Bearer fixture-key-B')
                assert sync.apply('claude', {'kind': 'native', 'directory': str(native)})['status'] == 'selected'
                with patch.dict(os.environ, managed_api_env(), clear=True):
                    assert sync.verify('claude', {'kind': 'native', 'directory': str(native)})['status'] == 'configured'
                assert json.loads((native/'settings.json').read_text()) == original
                blocked = sum(kind == 'external' for server in servers for kind, *_ in server.calls)
                print('PASS: native A/B endpoints, credentials and default models; injected B verification rollback restores native A turn; native switch-back preserves settings; '
                      f'{blocked} external CONNECT attempts denied')
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    main()
