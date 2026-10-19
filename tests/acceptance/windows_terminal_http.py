#!/usr/bin/env python3
"""Isolated Windows HTTP terminal acceptance with an installed ConPTY child.

This runs the source HTTP router with a synthetic chat and no client manager.
The supplied installed gateway executable is launched only as the terminal
bootstrap. No Codex or Claude client can be activated by this fixture.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import uuid
from unittest.mock import patch


def require(value, message):
    if not value:
        raise AssertionError(message)


def until(check, description, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError(description + ' timed out')


class HTTP:
    def __init__(self, port):
        self.port = port
        self.cookie = None
        self.csrf = None
        self.trace = []

    def request(self, method, path, body=None, csrf=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        headers = {'Origin': f'http://127.0.0.1:{self.port}', 'Content-Type': 'application/json'}
        if self.cookie:
            headers['Cookie'] = self.cookie
        if method == 'POST' and csrf and self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            reply = connection.getresponse()
            status, raw, cookie = reply.status, reply.read(), reply.getheader('Set-Cookie')
        finally:
            connection.close()
        self.trace.append({'method': method, 'route': path.split('?', 1)[0], 'status': status})
        return status, json.loads(raw), cookie

    def checked(self, method, path, body=None):
        status, value, _ = self.request(method, path, body)
        require(status == 200, f'{method} {path} returned {status}: {value.get("error", "")}')
        return value

    def login(self, password):
        status, value, cookie = self.request('POST', '/api/login',
                                              {'username': 'admin', 'password': password})
        require(status == 200 and cookie and value.get('csrf'), 'HTTP login failed')
        self.cookie = cookie.split(';', 1)[0]
        self.csrf = value['csrf']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', type=Path, required=True, help='Installed Test gateway exe used as ConPTY child')
    parser.add_argument('--test-root', type=Path, required=True, help='Isolated project .tmp directory')
    parser.add_argument('--extended-cwd', action='store_true', help='Use a synthetic extended local drive cwd')
    args = parser.parse_args()
    require(sys.platform == 'win32', 'This acceptance requires Windows ConPTY')
    gateway = args.gateway.resolve(strict=True)
    require(gateway.is_file() and gateway.name.lower().endswith('.exe'), 'Supply an installed gateway exe')
    test_root = args.test_root.absolute()
    require('.tmp' in test_root.parts and not test_root.is_symlink(), 'Use a project .tmp directory')
    run = test_root / ('terminal-http-' + uuid.uuid4().hex[:8])
    workspace = run / ('workspace 中文 space' if args.extended_cwd else 'workspace')
    (workspace / 'nested').mkdir(parents=True)
    stored_cwd = '\\\\?\\' + str(workspace) if args.extended_cwd else str(workspace)

    source_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(source_root))
    from bridge.api.httpd import GatewayServer
    from bridge.app.service import Bridge
    from bridge.features.auth.auth import password_record
    from bridge.features.terminals.manager import TerminalManager

    thread_id, tab_id = str(uuid.uuid4()), str(uuid.uuid4())
    class SyntheticBridge:
        host = 'local'
        def __init__(self):
            self.store = type('Store', (), {'get': lambda _, identifier: {'cwd': stored_cwd}
                              if identifier == thread_id else None})()
            self.terminals = TerminalManager()
        def for_host(self, host):
            if host != 'local': raise KeyError(host)
            return self
        terminal = Bridge.terminal
        def close(self):
            self.terminals.close()

    password = secrets.token_urlsafe(18)
    config = {'auth': {'mode': 'password', 'username': 'admin', **password_record(password)}, 'origins': []}
    bridge = SyntheticBridge()
    server = GatewayServer(('127.0.0.1', 0), bridge, config, source_root / 'web')
    port = server.server_address[1]
    server.origins.add(f'http://127.0.0.1:{port}')
    server.hosts.add(f'127.0.0.1:{port}')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    http = HTTP(port)
    path = f'/api/sessions/{thread_id}/terminal'
    summary = {'schema': 1, 'status': 'failed', 'gatewayChild': str(gateway), 'run': str(run),
               'extendedCwd': args.extended_cwd,
               'threadId': thread_id, 'checks': {}, 'error': None}
    cursor, output = 0, ''

    def poll():
        nonlocal cursor, output
        value = http.checked('GET', f'{path}?mode=pty&id={tab_id}&after={cursor}')
        output += value['output']
        cursor = value['cursor']
        return value

    def streamed(marker):
        poll()
        return marker(output)

    def input_text(value):
        http.checked('POST', path, {'action': 'input', 'id': tab_id, 'inputId': str(uuid.uuid4()), 'data': value})

    try:
        require(http.request('GET', path)[0] == 401, 'Terminal GET must require login')
        http.login(password)
        require(http.request('POST', path, {'action': 'open', 'id': tab_id, 'cols': 80, 'rows': 24}, csrf=False)[0] == 403,
                'Terminal open must require CSRF')
        info = http.checked('GET', path)
        require(info['cwd'] == stored_cwd, 'Synthetic chat cwd was not resolved')
        with patch.object(sys, 'executable', str(gateway)), patch.object(sys, 'frozen', True, create=True):
            opened = http.checked('POST', path, {'action': 'open', 'id': tab_id, 'cols': 80, 'rows': 24})
        require(opened['running'], 'ConPTY did not start')
        until(lambda: streamed(lambda text: '>' in text), 'Initial cmd prompt')
        summary['checks']['authCsrfOpen'] = True

        if args.extended_cwd:
            marker = run / 'startup-cwd.txt'
            input_text('cd > "' + str(marker) + '"\r')
            until(marker.exists, 'Initial CMD cwd')
            require(run.name in marker.read_bytes().decode('ascii', 'ignore'),
                    'CMD did not start in the synthetic chat cwd')
            summary['checks']['extendedLocalCwd'] = True

        input_text('cd nested\rset CMB_HTTP_STATE=retained\r')
        reopened = http.checked('POST', path, {'action': 'open', 'id': tab_id, 'cols': 80, 'rows': 24})
        require(reopened['running'], 'Opening same tab restarted or closed its shell')
        require(http.checked('POST', path, {'action': 'resize', 'id': tab_id, 'cols': 100, 'rows': 30})['resized'],
                'Resize failed')
        input_text('echo %CMB_HTTP_STATE%> continuity.txt\r')
        continuity = workspace / 'nested' / 'continuity.txt'
        until(continuity.exists, 'cd/env persistence')
        require(continuity.read_text().strip() == 'retained', 'Reopened tab lost cwd or environment')
        summary['checks']['reopenResizeCwdEnv'] = True

        cursor = poll()['cursor']; output = ''
        input_text('ping 127.0.0.1 -n 2\r')
        until(lambda: streamed(lambda text: text.count('127.0.0.1') >= 3), 'Ping output', 20)
        input_text('echo done> ping-done.txt\r')
        until((workspace / 'nested' / 'ping-done.txt').exists, 'Ping command completion')
        summary['checks']['pingStream'] = True

        cursor = poll()['cursor']; output = ''
        input_text('ping 127.0.0.1 -t\r')
        until(lambda: streamed(lambda text: text.count('127.0.0.1') >= 3), 'Continuous ping output', 20)
        cursor = poll()['cursor']; output = ''
        input_text('\x03')
        until(lambda: streamed(lambda text: '>' in text), 'Prompt after Ctrl+C')
        input_text('echo survived> after-ctrl-c.txt\r')
        after = workspace / 'nested' / 'after-ctrl-c.txt'
        until(after.exists, 'Shell after Ctrl+C')
        require(after.read_text().strip() == 'survived', 'Ctrl+C killed shell')
        summary['checks']['ctrlCShellAlive'] = True

        http.checked('POST', path, {'action': 'close', 'id': tab_id})
        until(lambda: not poll()['running'], 'Terminal close', 20)
        summary['checks']['close'] = True
        summary['status'] = 'passed'
    except Exception as exc:
        summary['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        bridge.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        (run / 'http-trace.json').write_text(json.dumps(http.trace, indent=2), encoding='utf-8')
        (run / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
