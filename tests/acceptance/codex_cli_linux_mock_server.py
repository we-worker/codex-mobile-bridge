#!/usr/bin/env python3
"""Run an isolated loopback Responses fixture for Linux Codex CLI acceptance.

Run only with an explicitly authorized temporary root and an installed CLI
binary. Stop it by creating <root>/stop-fixture. No account credentials are used.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = HOME = PROJECT = REAL_CLI = None
MODEL = 'cmb-fixture-model'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _record(self, kind, body=None):
        with (ROOT / 'requests.jsonl').open('a') as stream:
            stream.write(json.dumps({'kind': kind, 'path': self.path, 'body': body}) + '\n')

    def do_CONNECT(self):
        self._record('blocked-external')
        self.send_error(403)

    def do_GET(self):
        self._record('get')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"data":[]}')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        self._record('post', {'model': body.get('model'), 'input': body.get('input')})
        response = {'id': 'resp_fixture', 'object': 'response', 'status': 'completed',
                    'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 0, 'total_tokens': 1}}
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        self.wfile.write(('data: ' + json.dumps({'type': 'response.completed', 'response': response}) + '\n\n').encode())


def main():
    global ROOT, HOME, PROJECT, REAL_CLI
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--cli', type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    REAL_CLI = args.cli.resolve(strict=True)
    if not ROOT.is_absolute() or not REAL_CLI.is_file():
        raise ValueError('An absolute temporary root and installed CLI are required')
    HOME = ROOT / 'codex-home'
    PROJECT = ROOT / 'project'
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'stop-fixture').unlink(missing_ok=True)
    HOME.mkdir(exist_ok=True)
    PROJECT.mkdir(exist_ok=True)
    managed = HOME / 'packages/app-server-daemon/current/bin/codex'
    managed.parent.mkdir(parents=True, exist_ok=True)
    if not managed.exists():
        managed.symlink_to(REAL_CLI)
    elif managed.resolve(strict=True) != REAL_CLI:
        raise ValueError('Selected managed package belongs to another CLI')
    state = HOME / 'app-server-daemon'
    state.mkdir(exist_ok=True)
    (state / 'settings.json').write_text(json.dumps({
        'remoteControlEnabled': False,
        'updater': {'autoUpdateEnabled': False, 'updateIntervalMinutes': 120}}))
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    port = server.server_port
    config = ('model=' + json.dumps(MODEL) + '\nmodel_provider="fixture"\n'
              'approval_policy="on-request"\nsandbox_mode="workspace-write"\n'
              '[model_providers.fixture]\nname="Local fixture"\nbase_url=' +
              json.dumps(f'http://127.0.0.1:{port}/v1') + '\nwire_api="responses"\n'
              'env_key="CMB_FIXTURE_KEY"\n[projects.' + json.dumps(str(PROJECT)) +
              ']\ntrust_level="trusted"\n')
    (HOME / 'config.toml').write_text(config)
    (ROOT / 'port').write_text(str(port))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({'ready': True, 'port': port, 'home': str(HOME)}), flush=True)
    try:
        while not (ROOT / 'stop-fixture').exists():
            time.sleep(1)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
