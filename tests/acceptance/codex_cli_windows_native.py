#!/usr/bin/env python3
"""Isolated native Windows Codex daemon acceptance with a loopback model API.

The companion CMD/Python launcher runs this from a standard non-admin terminal.
It uses only the staged CLI and project under the caller's temporary test root.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))

from bridge.clients.codex.app_server import CodexAppServer
from bridge.clients.codex.cli_session import CliSessions
from bridge.features.sessions.linux_permissions import permission_settings

HOME = ROOT / 'h'
PROJECT = ROOT / 'p'
CLI = HOME / 'packages/app-server-daemon/current/bin/codex.exe'
SOCKET = HOME / 'app-server-control/app-server-control.sock'
MODEL = 'cmb-win-fixture-model'
EVENTS = []


def private_state_directory():
    """Create a fresh native-private state directory, or verify an existing one."""
    script = r'''
$ErrorActionPreference = 'Stop'
$path = $env:CMB_FIXTURE_STATE_DIR
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if (-not (Test-Path -LiteralPath $path)) {
    $security = New-Object Security.AccessControl.DirectorySecurity
    $security.SetSecurityDescriptorSddlForm("O:${sid}D:P(A;OICI;FA;;;${sid})")
    [IO.Directory]::CreateDirectory($path, $security) | Out-Null
}
$item = Get-Item -LiteralPath $path -Force
if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Isolated daemon state path is not a plain directory'
}
$security = Get-Acl -LiteralPath $path
$owner = ([Security.Principal.NTAccount]$security.Owner).Translate([Security.Principal.SecurityIdentifier]).Value
$rules = @($security.Access)
if ($owner -ne $sid -or -not $security.AreAccessRulesProtected -or $rules.Count -ne 1 -or
    $rules[0].IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ne $sid -or
    $rules[0].FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
    $rules[0].InheritanceFlags -ne [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit' -or
    $rules[0].PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None -or
    $rules[0].AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
    $rules[0].IsInherited) {
    throw 'Isolated daemon state directory lacks the native private ACL'
}
'''
    environment = os.environ.copy()
    environment['CMB_FIXTURE_STATE_DIR'] = str(HOME / 'app-server-daemon')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            env=environment, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Could not prepare isolated private daemon state: ' + result.stderr[-500:])


class MockAPI(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _record(self, kind, body=None):
        EVENTS.append({'kind': kind, 'path': self.path, 'body': body})

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
        self._record('post', {'model': body.get('model')})
        response = {'id': 'resp_fixture', 'object': 'response', 'status': 'completed',
                    'output': [], 'usage': {'input_tokens': 1, 'output_tokens': 0, 'total_tokens': 1}}
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        self.wfile.write(('data: ' + json.dumps({'type': 'response.completed', 'response': response}) + '\n\n').encode())


def lifecycle(action):
    result = subprocess.run([str(CLI), 'app-server', 'daemon', action],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            timeout=35, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f'isolated daemon {action} failed: {result.stderr[-500:]}')
    report = json.loads(result.stdout)
    if not isinstance(report, dict):
        raise RuntimeError(f'isolated daemon {action} returned invalid JSON')
    return report


def wait_original(events, thread_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=max(.01, deadline - time.monotonic()))
        except queue.Empty:
            break
        if event.get('method') == 'turn/completed' and (event.get('params') or {}).get('threadId') == thread_id:
            if event['params']['turn']['status'] != 'completed':
                raise AssertionError('Original synthetic turn failed')
            return
    raise AssertionError('Original synthetic turn did not complete')


def wait_joined(adapter, thread_id, prior):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = adapter.refresh(thread_id)
        turns = state.get('turns') or []
        if len(turns) > prior and turns[-1].get('status') == 'completed':
            return state
        time.sleep(.25)
    raise AssertionError('Joined synthetic turn did not complete')


def main():
    if os.name != 'nt' or not CLI.is_file():
        raise RuntimeError('Run with the staged Windows CLI')
    HOME.mkdir(parents=True, exist_ok=True)
    PROJECT.mkdir(exist_ok=True)
    private_state_directory()
    server = ThreadingHTTPServer(('127.0.0.1', 0), MockAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    config = ('model=' + json.dumps(MODEL) + '\nmodel_provider="fixture"\n'
              'approval_policy="on-request"\nsandbox_mode="workspace-write"\n'
              '[model_providers.fixture]\nname="Local fixture"\nbase_url=' +
              json.dumps(base + '/v1') + '\nwire_api="responses"\n'
              'env_key="CMB_FIXTURE_KEY"\n[projects.' + json.dumps(str(PROJECT)) +
              ']\ntrust_level="trusted"\n')
    (HOME / 'config.toml').write_text(config, encoding='utf-8')
    (HOME / 'app-server-daemon/settings.json').write_text(json.dumps({
        'remoteControlEnabled': False,
        'updater': {'autoUpdateEnabled': False, 'updateIntervalMinutes': 120}}), encoding='utf-8')
    os.environ.update({'CODEX_HOME': str(HOME), 'CMB_FIXTURE_KEY': 'synthetic-key',
                       'HTTP_PROXY': base, 'HTTPS_PROXY': base, 'ALL_PROXY': base,
                       'http_proxy': base, 'https_proxy': base, 'all_proxy': base,
                       'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'})
    for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE',
                'CODEX_THREAD_ID', 'CODEX_SESSION_ID'):
        os.environ.pop(key, None)
    original = joined = cold = None
    result = {'status': 'failed', 'stage': 'start', 'cliVersion': None}
    try:
        version = subprocess.run([str(CLI), '--version'], capture_output=True, text=True,
                                 timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        result['cliVersion'] = version.stdout.strip()
        started = lifecycle('start')
        if started.get('socketPath', '').lower() != str(SOCKET).lower() or started.get('status') not in ('started', 'alreadyRunning'):
            raise AssertionError('Isolated daemon started at another endpoint')
        result['stage'] = 'original'
        original_events = queue.Queue()
        original = CodexAppServer(SOCKET, cli=str(CLI), client_name='codex-tui',
                                  on_event=original_events.put)
        info = original.connect()
        if Path(info['codexHome']) != HOME:
            raise AssertionError('Original runtime belongs to another home')
        thread = original.request('thread/start', {'cwd': str(PROJECT), 'threadSource': 'cli'})['thread']
        thread_id = thread['id']
        if thread['cwd'] != str(PROJECT) or thread['modelProvider'] != 'fixture':
            raise AssertionError('Original thread identity differs')
        original.request('turn/start', {'threadId': thread_id, 'input': [
            {'type': 'text', 'text': 'ORIGINAL_WINDOWS_FIXTURE; no tools.'}]})
        wait_original(original_events, thread_id)
        original.close()
        original = None

        result['stage'] = 'resume'
        joined = CliSessions(HOME, lambda *_: None, lambda *_: None, cli=str(CLI))
        if joined.attach(thread_id) is not None:
            raise AssertionError('Passive attach activated a thread')
        state = joined.attach(thread_id, explicit=True)
        if state['id'] != thread_id or state['cwd'] != str(PROJECT) or state['modelProvider'] != 'fixture':
            raise AssertionError('Resumed thread identity differs')
        result['stage'] = 'permissions'
        facts, options = joined.permission_options(thread_id)
        available = next((row['available'] for row in options['options']
                          if row['preset'] == 'auto-review'), False)
        if not available:
            raise AssertionError('Native auto-review permission is unavailable')
        settings = permission_settings('auto-review', facts)
        joined.call(thread_id, 'thread-follower-update-thread-settings',
                    {'threadSettings': settings})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            effective = joined.refresh(thread_id).get('currentPermissions') or {}
            if effective.get('approvalsReviewer') == settings['approvalsReviewer']:
                break
            time.sleep(.25)
        else:
            raise AssertionError('Native permission change lacked effective confirmation')
        prior = len(state.get('turns') or [])
        joined.call(thread_id, 'thread-follower-start-turn', {'turnStart': {'request': {
            'input': [{'type': 'text', 'text': 'RESUMED_WINDOWS_FIXTURE; no tools.'}]}}})
        wait_joined(joined, thread_id, prior)
        result['permissionConfirmed'] = True

        result['stage'] = 'goal-create'
        result['goalSupported'] = joined.supports_goal(thread_id)
        if result['goalSupported']:
            goal = joined.set_goal(thread_id, 'Isolated Windows acceptance goal')
            if goal['status'] != 'active':
                raise AssertionError('Native Goal did not activate')
            joined.clear_goal(thread_id)
            if joined.get_goal(thread_id) is not None:
                raise AssertionError('Native Goal did not clear')
        created = joined.create(str(PROJECT), 'Isolated new CLI chat')
        if created['cwd'] != str(PROJECT) or created['modelProvider'] != 'fixture':
            raise AssertionError('New CLI chat identity differs')
        if joined.store.get(created['id'])['origin'] != 'cli':
            raise AssertionError('New chat did not retain CLI provenance')
        result['newChatId'] = created['id']
        result['threadId'] = thread_id
        joined.close()
        joined = None

        result['stage'] = 'cold-resume'
        lifecycle('stop')
        cold = CliSessions(HOME, lambda *_: None, lambda *_: None, cli=str(CLI))
        resumed = cold.attach(thread_id, explicit=True)
        if resumed['id'] != thread_id or resumed['cwd'] != str(PROJECT) or resumed['modelProvider'] != 'fixture':
            raise AssertionError('Cold-resumed thread identity differs')
        result['status'] = 'passed'
        result['stage'] = 'complete'
    except Exception as exc:
        result['errorType'] = type(exc).__name__
        result['error'] = str(exc)[-500:]
    finally:
        for client in (original, joined, cold):
            if client is not None:
                client.close()
        try:
            result['stopStatus'] = lifecycle('stop').get('status')
        except Exception as exc:
            result['stopError'] = type(exc).__name__
        server.shutdown()
        server.server_close()
        posts = [row for row in EVENTS if row['kind'] == 'post']
        result['modelPosts'] = len(posts)
        result['allModelPostsLoopback'] = all(row['path'] == '/v1/responses' and
                                              row['body']['model'] == MODEL for row in posts)
        result['blockedExternalConnects'] = sum(row['kind'] == 'blocked-external' for row in EVENTS)
        if result['status'] == 'passed' and (len(posts) < 2 or not result['allModelPostsLoopback']):
            result['status'] = 'failed'
            result['error'] = 'Synthetic model traffic did not remain on the loopback fixture'
        if 'stopError' in result:
            result['status'] = 'failed'
        (ROOT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
