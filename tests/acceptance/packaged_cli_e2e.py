#!/usr/bin/env python3
"""Installed gateway HTTP acceptance with isolated native Codex and Claude CLIs.

Run as the normal desktop user. All profiles and evidence stay below an explicit
``.../.tmp/cmb-package-20261014/e2e`` root. No source gateway is launched.
The source transports are used only to create closed native seed conversations.
"""

import argparse
import hashlib
import http.client
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CODEX_KEY = 'synthetic-codex-key'
CLAUDE_KEY = 'synthetic-claude-key'
CODEX_MODEL = 'cmb-package-codex-fixture'
CODEX_MODEL_ALT = 'cmb-package-codex-switched'
CLAUDE_MODEL = 'cmb-package-claude-fixture'
PASSWORD = 'synthetic-package-acceptance-password'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def wait_for(check, description, seconds=35):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, ValueError, KeyError, AssertionError) as exc:
            last = exc
        time.sleep(.2)
    raise AssertionError(description + ' timed out' + (': ' + str(last)[:120] if last else ''))


def wait_for_history_marker(http, path, marker, description, seconds=35):
    def read():
        try:
            status, value, _ = http.request('GET', path)
        except OSError as exc:
            raise RuntimeError('GET ' + path + ' failed') from exc
        if status != 200:
            raise RuntimeError('GET ' + path + ' returned HTTP ' + str(status))
        return value if marker in json.dumps(value) else None
    return wait_for(read, description, seconds)


class MockServer(ThreadingHTTPServer):
    def __init__(self, kind, address, markers):
        super().__init__(address, MockHandler)
        self.kind = kind
        self.markers = markers
        self.calls = []
        self.lock = threading.Lock()
        self.switched_model = None

    def record(self, **row):
        with self.lock:
            self.calls.append(row)


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_CONNECT(self):
        self.server.record(kind='blocked-external')
        self.send_error(403)

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"data":[]}')

    def do_POST(self):
        path = self.path.split('?', 1)[0]
        data = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        try:
            body = json.loads(data)
        except ValueError:
            self.send_error(400)
            return
        if self.server.kind == 'claude' and path.endswith('/count_tokens'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"input_tokens":1}')
            return
        expected = '/v1/responses' if self.server.kind == 'codex' else '/v1/messages'
        key = self.headers.get('Authorization') if self.server.kind == 'codex' else self.headers.get('x-api-key')
        key_ok = key == ('Bearer ' + CODEX_KEY if self.server.kind == 'codex' else CLAUDE_KEY)
        model = body.get('model')
        self.server.record(kind='model', path=path, keyMatches=key_ok, model=model)
        if self.server.kind == 'codex':
            model_ok = model in (CODEX_MODEL, CODEX_MODEL_ALT)
        else:
            selected = self.server.switched_model
            model_ok = model == CLAUDE_MODEL or (selected is not None and
                (model == selected or isinstance(model, str) and
                 model.startswith('claude-' + selected + '-')))
        if path != expected or not key_ok or not model_ok:
            self.send_error(403)
            return
        try:
            events = self._codex_events(body) if self.server.kind == 'codex' else self._claude_events(body)
        except ValueError as exc:
            messages = body.get('messages') or []
            last = messages[-1] if isinstance(messages, list) and messages else {}
            last = last if isinstance(last, dict) else {}
            latest_user = next((item for item in reversed(messages)
                                if isinstance(item, dict) and item.get('role') == 'user'), {})
            content = latest_user.get('content')
            self.server.record(kind='fixture-reject', reason=str(exc)[:80], path=path,
                               messageCount=len(messages) if isinstance(messages, list) else -1,
                               lastRole=last.get('role'), latestUserContentType=type(content).__name__,
                               markers=[marker for marker in ('CLAUDE_SEED', 'CLAUDE_HTTP_SEND',
                                   'REQUEST_DENY_WRITE', 'REQUEST_ALLOW_WRITE')
                                   if marker in json.dumps(content)])
            self.send_error(409)
            return
        content = ''.join('event: ' + name + '\ndata: ' + json.dumps(event) + '\n\n'
                          for name, event in events).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _codex_events(self, body):
        inputs = body.get('input') or []
        latest_user = next((item for item in reversed(inputs)
                            if isinstance(item, dict) and item.get('role') == 'user'), {})
        prompt = json.dumps(latest_user)
        if 'CODEX_SEED' in prompt:
            response_text = 'CODEX_SEED_REPLY'
        elif 'CODEX_HTTP_SEND' in prompt:
            response_text = 'CODEX_HTTP_REPLY'
        elif 'Synthetic package acceptance goal' in prompt:
            response_text = 'CODEX_GOAL_REPLY'
        else:
            raise ValueError('Unknown current Codex turn')
        item = {'id': 'msg_fixture_' + uuid.uuid4().hex, 'type': 'message', 'role': 'assistant',
                'status': 'completed', 'content': [{'type': 'output_text', 'text': response_text,
                                                   'annotations': []}]}
        response = {'id': 'resp_fixture_' + uuid.uuid4().hex, 'object': 'response',
                    'created_at': 0, 'status': 'completed', 'model': body['model'],
                    'output': [item], 'usage': {'input_tokens': 10, 'output_tokens': 5,
                                                'total_tokens': 15}}
        events = [
            {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
            {'type': 'response.output_item.added', 'output_index': 0,
             'item': {**item, 'status': 'in_progress', 'content': []}},
            {'type': 'response.content_part.added', 'item_id': item['id'], 'output_index': 0,
             'content_index': 0, 'part': {'type': 'output_text', 'text': '', 'annotations': []}},
            {'type': 'response.output_text.delta', 'item_id': item['id'], 'output_index': 0,
             'content_index': 0, 'delta': response_text},
            {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
            {'type': 'response.completed', 'response': response},
        ]
        return [(event['type'], event) for event in events]

    def _claude_events(self, body):
        messages = body.get('messages') or []
        latest_user = next((item for item in reversed(messages)
                            if isinstance(item, dict) and item.get('role') == 'user'), {})
        content = latest_user.get('content')
        text = json.dumps(content)
        tool_results = [item for item in content if isinstance(item, dict)
                        and item.get('type') == 'tool_result'] if isinstance(content, list) else []
        if len(tool_results) > 1:
            raise ValueError('Unexpected multiple tool results')
        tool_result = tool_results[0] if tool_results else None
        if tool_result:
            tool = False
            tool_id = tool_result.get('tool_use_id')
            if tool_id not in ('toolu_deny_fixture', 'toolu_allow_fixture'):
                raise ValueError('Unknown tool result')
            denied = tool_id == 'toolu_deny_fixture'
            if (tool_result.get('is_error') is True) != denied:
                raise ValueError('Tool result decision mismatched the pending tool')
            response_text = 'CLAUDE_DENIED_REPLY' if denied else 'CLAUDE_ALLOWED_REPLY'
            self.server.record(kind='tool-result', denied=tool_result.get('is_error') is True,
                               toolId=tool_id)
        elif 'REQUEST_DENY_WRITE' in text or 'REQUEST_ALLOW_WRITE' in text:
            if 'REQUEST_DENY_WRITE' in text and 'REQUEST_ALLOW_WRITE' in text:
                raise ValueError('Ambiguous current Claude tool request')
            tool = True
            allow = 'REQUEST_ALLOW_WRITE' in text
            marker = self.server.markers['allow' if allow else 'deny']
            tool_id = 'toolu_allow_fixture' if allow else 'toolu_deny_fixture'
            block = {'type': 'tool_use', 'id': tool_id, 'name': 'Write', 'input': {}}
            delta = {'type': 'input_json_delta', 'partial_json': json.dumps({
                'file_path': str(marker), 'content': 'ALLOWED_MARKER' if allow else 'DENIED_MARKER'})}
            response_text = None
        else:
            tool = False
            if 'CLAUDE_SEED' in text:
                response_text = 'CLAUDE_SEED_REPLY'
            elif 'CLAUDE_HTTP_SEND' in text:
                response_text = 'CLAUDE_HTTP_REPLY'
            else:
                raise ValueError('Unknown current Claude turn')
        message = {'id': 'msg_fixture_' + uuid.uuid4().hex, 'type': 'message',
                   'role': 'assistant', 'content': [], 'model': body['model'],
                   'stop_reason': None, 'stop_sequence': None,
                   'usage': {'input_tokens': 1, 'output_tokens': 1}}
        if not tool:
            block = {'type': 'text', 'text': ''}
            delta = {'type': 'text_delta', 'text': response_text}
        events = [
            ('message_start', {'type': 'message_start', 'message': message}),
            ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': block}),
            ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': delta}),
            ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            ('message_delta', {'type': 'message_delta', 'delta': {
                'stop_reason': 'tool_use' if tool else 'end_turn', 'stop_sequence': None},
                'usage': {'output_tokens': 1}}),
            ('message_stop', {'type': 'message_stop'}),
        ]
        return events


class InstalledWorker:
    def __init__(self, gateway, data, env):
        self.gateway, self.data, self.env = gateway, data, env

    def call(self, action, payload=None, timeout=35):
        command = [str(self.gateway), action, '--data-dir', str(self.data)]
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        result = subprocess.run(command, input=json.dumps(payload or {}), capture_output=True,
                                text=True, encoding='utf-8', errors='replace', env=self.env,
                                stdin=None, timeout=timeout, **options)
        try:
            response = json.loads(result.stdout)
        except ValueError as exc:
            raise AssertionError('Installed worker returned non-JSON for ' + action) from exc
        require(result.returncode == 0 and response.get('ok') is True,
                'Installed worker rejected ' + action + ': ' + str(response.get('error', ''))[:180])
        return response['result']


class GatewayHTTP:
    def __init__(self, port, trace=None):
        self.port = port
        self.cookie = None
        self.csrf = None
        self.trace = trace if trace is not None else []

    def request(self, method, path, body=None, authenticated=True, csrf=True):
        route = path.split('?', 1)[0]
        timeout = (10 if method == 'GET' else 45) if route == '/api/clients' else 12
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=timeout)
        started = time.monotonic()
        status = None
        headers = {'Host': '127.0.0.1:' + str(self.port),
                   'Origin': 'http://127.0.0.1:' + str(self.port),
                   'Content-Type': 'application/json'}
        if authenticated and self.cookie:
            headers['Cookie'] = self.cookie
        if method == 'POST' and authenticated and csrf and self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        try:
            connection.request(method, path, body=json.dumps(body) if body is not None else None,
                               headers=headers)
            reply = connection.getresponse()
            raw = reply.read()
            status = reply.status
            cookie = reply.getheader('Set-Cookie')
        except TimeoutError as exc:
            status = 'timeout'
            raise TimeoutError(method + ' ' + route + ' timed out') from exc
        except Exception as exc:
            status = type(exc).__name__
            raise
        finally:
            connection.close()
            self.trace.append({'method': method, 'route': route,
                               'durationMs': round((time.monotonic() - started) * 1000),
                               'status': status})
        try:
            value = json.loads(raw)
        except ValueError:
            value = {}
        return status, value, cookie

    def checked(self, method, path, body=None):
        status, value, _ = self.request(method, path, body)
        require(status == 200, method + ' ' + path + ' returned HTTP ' + str(status)
                + ': ' + str(value.get('error', ''))[:160])
        return value

    def login(self):
        status, value, cookie = self.request('POST', '/api/login',
                                             {'username': 'admin', 'password': PASSWORD},
                                             authenticated=False)
        require(status == 200 and cookie and isinstance(value.get('csrf'), str),
                'Installed gateway login failed')
        self.cookie = cookie.split(';', 1)[0]
        self.csrf = value['csrf']


def stage_managed_cli(cli, home, package=None):
    current = home/'packages'/'app-server-daemon'/'current'
    selected = current/'bin'/('codex.exe' if os.name == 'nt' else 'codex')
    if package is not None:
        require((package/'bin'/selected.name).resolve(strict=True) == cli.resolve(strict=True),
                'Supplied Codex package does not contain the selected native CLI')
        current.parent.mkdir(parents=True)
        if os.name == 'nt':
            shutil.copytree(package, current)
        else:
            current.symlink_to(package, target_is_directory=True)
    else:
        selected.parent.mkdir(parents=True)
        if os.name == 'nt':
            shutil.copy2(cli, selected)
        else:
            selected.symlink_to(cli)
    require(hashlib.sha256(cli.read_bytes()).digest() == hashlib.sha256(selected.read_bytes()).digest(),
            'Staged Codex CLI differs from the supplied installed executable')
    state = home/'app-server-daemon'
    state.mkdir()
    if os.name == 'nt':
        script = r'''$ErrorActionPreference='Stop'; $path=$env:CMB_FIXTURE_STATE_DIR;
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
$security=New-Object Security.AccessControl.DirectorySecurity;
$security.SetSecurityDescriptorSddlForm("O:${sid}D:P(A;OICI;FA;;;${sid})");
[IO.Directory]::CreateDirectory($path,$security)|Out-Null'''
        state.rmdir()
        env = {**os.environ, 'CMB_FIXTURE_STATE_DIR': str(state)}
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                env=env, capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        require(result.returncode == 0, 'Could not create private Windows daemon state')
    (state/'settings.json').write_text(json.dumps({'remoteControlEnabled': False,
        'updater': {'autoUpdateEnabled': False, 'updateIntervalMinutes': 120}}), encoding='utf-8')
    return selected


def codex_lifecycle(cli, home, action, env):
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    result = subprocess.run([str(cli), 'app-server', 'daemon', action], env=env,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=35, **options)
    require(result.returncode == 0, 'Native Codex daemon ' + action + ' failed: '
            + result.stderr[-180:])
    report = json.loads(result.stdout)
    require(isinstance(report, dict), 'Native Codex daemon lifecycle response invalid')
    return report


def seed_codex(cli, home, project, env):
    from bridge.clients.codex.app_server import CodexAppServer
    report = codex_lifecycle(cli, home, 'start', env)
    require(report.get('status') in ('started', 'alreadyRunning'), 'Native Codex daemon did not start')
    events = queue.Queue()
    socket = home/'app-server-control'/'app-server-control.sock'
    client = CodexAppServer(socket, cli=str(cli), on_event=events.put,
                            check_socket=True, client_name='codex-tui')
    try:
        require(client.connect().get('codexHome') == str(home), 'Native Codex daemon selected another home')
        thread = client.request('thread/start', {'cwd': str(project), 'threadSource': 'cli'})['thread']
        thread_id = thread['id']
        require(thread.get('cwd') == str(project), 'Native Codex seed project changed')
        client.request('turn/start', {'threadId': thread_id, 'input': [
            {'type': 'text', 'text': 'CODEX_SEED; synthetic local fixture only.'}]})
        def finished():
            while not events.empty():
                event = events.get_nowait()
                if (event.get('method') == 'turn/completed' and
                        (event.get('params') or {}).get('threadId') == thread_id):
                    return event['params']['turn'].get('status') == 'completed'
            return False
        require(wait_for(finished, 'native Codex seed turn', 40), 'Native Codex seed did not complete')
        return thread_id
    finally:
        client.close()


def seed_claude(project):
    from bridge.clients.claude.cli_session import ClaudeCli, _profile
    profile = _profile()
    require(profile is not None, 'Selected Claude CLI unavailable')
    client = ClaudeCli()
    try:
        result = client.create(str(project), profile['origin'], 'CLAUDE_SEED; synthetic local fixture only.')
        sid = result['result']['id']
        native = client._get(sid)['nativeId']
        require(wait_for(lambda: not client.owned[native].active,
                         'native Claude seed turn', 40), 'Native Claude seed did not complete')
        detail = client.call('detail', sid, {})
        require('CLAUDE_SEED_REPLY' in json.dumps(detail.get('messages', [])),
                'Native Claude seed reply missing')
        return sid, native
    finally:
        owned_processes = [owned.process for owned in client.owned.values()]
        client.close()
        require(all(process.poll() is not None for process in owned_processes),
                'Native Claude seed process survived its owner close')


def verify_native_idle(codex_home, codex_cli, claude_profile):
    from bridge.clients.claude.session_registry import assert_profile_idle
    from bridge.clients.codex.cli_session import CliSessions
    assert_profile_idle(claude_profile)
    if codex_cli is not None:
        cli = CliSessions(codex_home, lambda *_: None, lambda: None, cli=str(codex_cli))
        require(not cli.daemon_may_be_running(),
                'Task-owned Codex daemon still runs or has unknown native status')


def await_native_idle(codex_home, codex_cli, claude_profile):
    def idle():
        verify_native_idle(codex_home, codex_cli, claude_profile)
        return True
    wait_for(idle, 'task-owned native processes to stop', 12)


def ready_clients(http):
    deadline = time.monotonic() + 45
    while True:
        require(time.monotonic() < deadline, 'GET /api/clients stayed pending beyond 45 seconds')
        value = http.checked('GET', '/api/clients')
        require(http.trace[-1]['durationMs'] < 10_000,
                'GET /api/clients exceeded the UI status deadline')
        require(time.monotonic() < deadline, 'GET /api/clients exceeded the 45-second discovery window')
        require(type(value.get('pending')) is bool and isinstance(value.get('clients'), list),
                'Client status response has no pending state or client list')
        require(not value.get('refreshError'), 'Client status refresh failed')
        if value['pending'] is False:
            return value['clients']
        time.sleep(.25)


def verify_codex(http, thread_id, project, server, result):
    path = '/api/sessions/' + thread_id
    listed = http.checked('GET', '/api/sessions?source=cli')['sessions']
    require(any(row.get('id') == thread_id for row in listed), 'Closed native Codex session absent from HTTP list')
    def state_with(marker):
        state = http.checked('GET', path)
        return state if marker in json.dumps(state) else None
    def state_field(name, value):
        state = http.checked('GET', path)
        return state if state.get(name) == value else None
    saved = wait_for(lambda: state_with('CODEX_SEED_REPLY'),
                     'saved Codex history before activation')
    require(saved.get('access', {}).get('source') == 'cli' or saved.get('origin') == 'cli',
            'Saved Codex session origin changed')
    result['codexListedClosed'] = True
    resumed = http.checked('POST', path+'/reconnect', {'activate': True})
    require(resumed.get('connected') is True, 'Explicit Codex resume did not connect')
    def connected_state():
        state = http.checked('GET', path)
        return state if state.get('connected') else None
    state = wait_for(connected_state, 'Codex connected state')
    require(state.get('provider') == 'fixture' and Path(state.get('cwd', '')).resolve() == project,
            'Codex provider or cwd changed during resume')
    require(state.get('model') == CODEX_MODEL, 'Initial effective Codex model changed')
    initial_permission = state.get('permissionMode')
    require(isinstance(initial_permission, str), 'Initial effective Codex permission missing')
    effort = state.get('effort') if state.get('effort') in (
        'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra') else 'medium'
    changed_model = http.checked('POST', path+'/settings',
                                 {'model': CODEX_MODEL_ALT, 'effort': effort})
    require(changed_model.get('applied') is True and changed_model.get('confirmed') is True,
            'Native Codex model change was not confirmed')
    wait_for(lambda: state_field('model', CODEX_MODEL_ALT), 'changed Codex model')
    options = http.checked('GET', path+'/permissions')
    available = {row.get('preset') for row in options.get('options', [])
                 if row.get('available') is True}
    alternate = next((preset for preset in ('ask', 'full-access')
                      if preset != initial_permission and preset in available), None)
    require(alternate is not None, 'Native Codex offered no alternate ask/full-access permission mode')
    changed_permission = http.checked('POST', path+'/permissions',
        {'preset': alternate, 'confirmed': alternate == 'full-access', 'expectedRuntime': 'cli'})
    require(changed_permission.get('applied') is True and
            changed_permission.get('confirmed') is True and
            changed_permission.get('permissionMode') == alternate,
            'Native Codex permission change was not confirmed')
    wait_for(lambda: state_field('permissionMode', alternate), 'changed Codex permission')
    result['codexModelAndPermissionSwitched'] = True
    reply_count = len([row for row in server.calls if row['kind'] == 'model'])
    sent = http.checked('POST', path+'/send', {'text': 'CODEX_HTTP_SEND; synthetic only.',
                                               'id': str(uuid.uuid4())})
    require(sent.get('status') in ('accepted', 'queued'), 'Codex send not accepted')
    wait_for(lambda: len([row for row in server.calls if row['kind'] == 'model']) > reply_count,
             'Codex HTTP model request')
    final_state = wait_for(lambda: state_with('CODEX_HTTP_REPLY'), 'Codex HTTP assistant reply')
    wait_for(lambda: state_field('status', 'idle'), 'Codex HTTP turn completion')
    require(final_state.get('model') == CODEX_MODEL_ALT and
            final_state.get('permissionMode') == alternate and
            any(row['kind'] == 'model' and row['model'] == CODEX_MODEL_ALT
                for row in server.calls[reply_count:]),
            'Codex next turn did not retain selected model and permission')
    result['codexHttpReply'] = True
    goal_id = str(uuid.uuid4())
    goal = http.checked('POST', path+'/send', {'text': 'Synthetic package acceptance goal',
                                              'id': goal_id, 'workMode': 'goal'})
    goal_value = goal.get('result') or {}
    if 'goal' in goal_value:
        goal_value = goal_value['goal']
    require(goal.get('confirmed') is True and goal_value.get('status') == 'active',
            'Codex Goal was not confirmed by the native runtime')
    cleared = http.checked('POST', path+'/goal/cancel', {'id': str(uuid.uuid4()),
        'expected': goal_value})
    require(cleared.get('confirmed') is True, 'Codex Goal clear not confirmed')
    result['codexGoalSetClear'] = True


def verify_claude(http, sid, project, server, markers, result):
    base = '/api/desktop-sessions/claude/'
    query = '?sessionId=' + sid
    def detail_with(marker):
        detail = http.checked('GET', base+'detail'+query)
        return detail if marker in json.dumps(detail.get('messages', [])) else None
    listed = http.checked('GET', base+'list')['sessions']
    require(any(row.get('id') == sid for row in listed), 'Closed native Claude session absent from HTTP list')
    detail = http.checked('GET', base+'detail'+query)
    require(detail['session']['connectionState'] == 'closed'
            and 'CLAUDE_SEED_REPLY' in json.dumps(detail.get('messages', [])),
            'Closed Claude history unavailable before resume')
    require(Path(detail['session']['cwd']).resolve() == project and
            detail['session']['model'] == CLAUDE_MODEL,
            'Claude saved cwd or model changed')
    result['claudeListedClosed'] = True
    resumed = http.checked('POST', base+'resume', {'sessionId': sid, 'id': str(uuid.uuid4())})
    require(resumed.get('status') == 'ready', 'Explicit Claude resume did not connect')
    def ready_detail():
        detail = http.checked('GET', base+'detail'+query)
        return detail if detail['session']['connectionState'] == 'ready' else None
    detail = wait_for(ready_detail, 'Claude ready state')
    require(detail['session']['model'] == CLAUDE_MODEL and
            detail['session']['permissionMode'] == 'default',
            'Effective Claude model or permission changed')
    catalog = http.checked('GET', base+'catalog'+query)
    alternate_model = next((row.get('id') for row in catalog.get('models', [])
                            if isinstance(row.get('id'), str) and row['id'] != CLAUDE_MODEL and
                            (row['id'] in ('opus', 'sonnet', 'haiku') or
                             row['id'].startswith('claude-'))), None)
    require(alternate_model is not None, 'Native Claude offered no alternate model')
    changed_model = http.checked('POST', base+'settings',
        {'sessionId': sid, 'id': str(uuid.uuid4()), 'model': alternate_model})
    require(changed_model.get('status') == 'accepted', 'Native Claude model change was not accepted')
    server.switched_model = alternate_model
    changed_permission = http.checked('POST', base+'access',
        {'sessionId': sid, 'id': str(uuid.uuid4()), 'mode': 'plan'})
    require(changed_permission.get('status') == 'accepted',
            'Native Claude permission change was not accepted')
    detail = http.checked('GET', base+'detail'+query)
    access = http.checked('GET', base+'access'+query)
    require(detail['session']['model'] == alternate_model and
            detail['session']['permissionMode'] == 'plan' and access.get('mode') == 'plan',
            'Claude changed model or permission was not effective')
    restored_permission = http.checked('POST', base+'access',
        {'sessionId': sid, 'id': str(uuid.uuid4()), 'mode': 'default'})
    require(restored_permission.get('status') == 'accepted' and
            http.checked('GET', base+'detail'+query)['session']['permissionMode'] == 'default',
            'Claude permission was not restored for tool approval checks')
    result['claudeModelAndPermissionSwitched'] = True
    before_model_calls = len(server.calls)
    http.checked('POST', base+'send', {'sessionId': sid, 'id': str(uuid.uuid4()),
                                       'text': 'CLAUDE_HTTP_SEND; synthetic only.'})
    detail = wait_for(lambda: detail_with('CLAUDE_HTTP_REPLY'), 'Claude HTTP assistant reply')
    wait_for(ready_detail, 'Claude HTTP turn completion')
    next_models = [row['model'] for row in server.calls[before_model_calls:]
                   if row['kind'] == 'model']
    native_model = next_models[-1] if next_models else None
    require(native_model != CLAUDE_MODEL and isinstance(native_model, str) and
            (native_model == alternate_model or
             alternate_model in ('opus', 'sonnet', 'haiku') and
             native_model.startswith('claude-' + alternate_model + '-')) and
            detail['session']['model'] in (alternate_model, native_model),
            'Claude next turn model mismatch: selected=' + alternate_model +
            ', native=' + str(native_model) + ', detail=' + str(detail['session']['model']))
    result['claudeHttpReply'] = True
    for decision in ('decline', 'accept'):
        label = 'DENY' if decision == 'decline' else 'ALLOW'
        marker = markers['deny' if decision == 'decline' else 'allow']
        http.checked('POST', base+'send', {'sessionId': sid, 'id': str(uuid.uuid4()),
                                           'text': 'REQUEST_'+label+'_WRITE'})
        pending = wait_for(lambda: next((request for request in
            http.checked('GET', base+'detail'+query)['session'].get('requests', [])
            if request.get('tool') == 'Write'), None), 'Claude '+label+' approval')
        require(not marker.exists(), 'Claude tool executed before approval')
        response = http.checked('POST', base+'respond', {'sessionId': sid, 'id': str(uuid.uuid4()),
            'requestId': pending['id'], 'decision': decision})
        require(response.get('status') == 'accepted', 'Claude approval was not accepted')
        reply = 'CLAUDE_DENIED_REPLY' if decision == 'decline' else 'CLAUDE_ALLOWED_REPLY'
        wait_for(lambda: detail_with(reply), 'Claude '+label+' final reply')
        wait_for(ready_detail, 'Claude '+label+' turn completion')
        require((not marker.exists()) if decision == 'decline' else
                marker.read_text(encoding='utf-8') == 'ALLOWED_MARKER',
                'Claude '+label+' tool effect incorrect')
        result['claude'+label.title()+'Approval'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', type=Path,
                        help='Optional installed Test controller path check; this worker E2E does not launch the GUI')
    parser.add_argument('--gateway', type=Path, required=True, help='Installed bundled gateway worker')
    parser.add_argument('--codex-cli', type=Path, required=True, help='Installed native Codex CLI')
    parser.add_argument('--codex-package', type=Path,
                        help='Optional complete installed package root containing bin/codex')
    parser.add_argument('--claude-cli', type=Path, required=True, help='Installed native Claude executable')
    parser.add_argument('--source-root', type=Path,
                        default=Path(__file__).resolve().parents[2],
                        help='Matching source tree used only for native seed transports')
    parser.add_argument('--test-root', type=Path, required=True,
                        help='Fresh isolated .../.tmp/cmb-package-20261014/e2e root')
    args = parser.parse_args()
    for path in (args.gateway, args.codex_cli, args.claude_cli):
        require(path.is_absolute() and path.is_file(), 'Supply absolute installed executable paths')
    if args.gui is not None:
        require(args.gui.is_absolute() and args.gui.is_file() and 'test' in args.gui.name.lower(),
                'Supply the distinct installed Test controller executable')
        bundled = args.gui.parent/'resources'/'gateway'/args.gateway.name
        require(bundled.resolve(strict=True) == args.gateway.resolve(strict=True),
                'Gateway worker is not bundled with the supplied Test controller')
    if args.codex_package is not None:
        require(args.codex_package.is_absolute() and args.codex_package.is_dir(),
                'Supply an absolute complete installed Codex package path')
    require((args.source_root/'bridge'/'clients'/'codex'/'app_server.py').is_file()
            and (args.source_root/'bridge'/'clients'/'claude'/'cli_session.py').is_file(),
            'Supply a matching --source-root for native seed transports')
    sys.path.insert(0, str(args.source_root))
    root = args.test_root.expanduser().absolute()
    require(root.name == 'e2e' and root.parent.name == 'cmb-package-20261014'
            and root.parent.parent.name == '.tmp' and not any(path.is_symlink() for path in
            (root, root.parent, root.parent.parent)), 'Test root must be the authorized isolated .tmp path')
    if sys.platform == 'linux':
        require(os.geteuid() != 0, 'Run as the normal non-root desktop user')
    root.mkdir(parents=True, exist_ok=True)
    # Native Windows AF_UNIX paths have a 108-byte canonical-address limit.
    run = root / uuid.uuid4().hex[:6]
    run.mkdir(mode=0o700)
    data, home, codex_home, claude_profile, project = [run/name for name in
        ('d', 'u', 'h', 'c', 'p')]
    socket_path = codex_home/'app-server-control'/'app-server-control.sock'
    require(len(str(socket_path).encode('utf-8')) <= 107,
            'Isolated Codex socket path exceeds the native AF_UNIX limit')
    for path in (data, home, codex_home, claude_profile, project):
        path.mkdir(mode=0o700)
    markers = {'deny': project/'denied-marker.txt', 'allow': project/'allowed-marker.txt'}
    servers = [MockServer('codex', ('127.0.0.1', 0), markers),
               MockServer('claude', ('127.0.0.1', 0), markers)]
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    codex_url = 'http://127.0.0.1:' + str(servers[0].server_port)
    claude_url = 'http://127.0.0.1:' + str(servers[1].server_port)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('ANTHROPIC_') and not key.startswith('CLAUDE_CODE_USE_')
           and key not in ('PYTHONPATH', 'PYTHONHOME', 'ELECTRON_RUN_AS_NODE')}
    env.update({'CMB_DATA_DIR': str(data), 'CODEX_HOME': str(codex_home),
                'CLAUDE_CONFIG_DIR': str(claude_profile), 'CMB_FIXTURE_KEY': CODEX_KEY,
                'HOME': str(home), 'USERPROFILE': str(home),
                'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_TELEMETRY': '1',
                'HTTP_PROXY': claude_url, 'HTTPS_PROXY': claude_url, 'ALL_PROXY': claude_url,
                'http_proxy': claude_url, 'https_proxy': claude_url, 'all_proxy': claude_url,
                'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost',
                'PATH': str(args.claude_cli.parent) + os.pathsep + os.environ.get('PATH', '')})
    if os.name == 'nt':
        env.update({'APPDATA': str(run/'appdata'), 'LOCALAPPDATA': str(run/'localappdata'),
                    'TEMP': str(run/'temp'), 'TMP': str(run/'temp')})
        for name in ('appdata', 'localappdata', 'temp'):
            (run/name).mkdir(mode=0o700)
    else:
        env.update({'XDG_CONFIG_HOME': str(run/'xdg-config'), 'XDG_DATA_HOME': str(run/'xdg-data'),
                    'XDG_CACHE_HOME': str(run/'xdg-cache')})
    worker = InstalledWorker(args.gateway, data, env)
    http_trace = []
    result = {'schema': 1, 'status': 'failed', 'stage': 'setup', 'gatewayInstalled': str(args.gateway),
              'run': str(run), 'checks': {}, 'codexModelPosts': 0, 'claudeModelPosts': 0,
              'blockedExternalConnects': 0, 'errorType': None, 'error': None}
    started = False
    daemon_started = False
    codex_cli = None
    previous_env = os.environ.copy()
    try:
        os.environ.clear(); os.environ.update(env)
        metadata = json.loads((args.gateway.parent.parent/'update-version.json').read_text(encoding='utf-8'))
        require(metadata.get('version') == '2.0.3', 'Installed gateway version metadata is not 2.0.3')
        result['checks']['versionMetadata203'] = True
        if args.gui is not None:
            result['checks']['testControllerBundlePath'] = True
        codex_cli = stage_managed_cli(args.codex_cli, codex_home, args.codex_package)
        (codex_home/'config.toml').write_text(
            'model=' + json.dumps(CODEX_MODEL) + '\nmodel_provider="fixture"\n'
            'approval_policy="on-request"\nsandbox_mode="workspace-write"\n'
            '[model_providers.fixture]\nname="Package fixture"\nbase_url=' +
            json.dumps(codex_url+'/v1') + '\nwire_api="responses"\nenv_key="CMB_FIXTURE_KEY"\n'
            '[projects.' + json.dumps(str(project)) + ']\ntrust_level="trusted"\n', encoding='utf-8')
        (claude_profile/'settings.json').write_text(json.dumps({'permissions': {'defaultMode': 'default'},
            'env': {'ANTHROPIC_API_KEY': CLAUDE_KEY, 'ANTHROPIC_BASE_URL': claude_url,
                    'ANTHROPIC_MODEL': CLAUDE_MODEL}}), encoding='utf-8')
        result['stage'] = 'native-seed'
        daemon_started = True
        codex_id = seed_codex(codex_cli, codex_home, project, env)
        codex_lifecycle(codex_cli, codex_home, 'stop', env)
        daemon_started = False
        claude_id, claude_native = seed_claude(project)
        await_native_idle(codex_home, codex_cli, claude_profile)
        result['checks']['nativeSeedsClosed'] = True
        result['stage'] = 'installed-worker-start'
        settings = worker.call('snapshot')
        settings['preferences'].update({'port': _free_port(), 'lan': False,
            'connections': [], 'autoStart': False, 'tunnel': False,
            'codexHome': str(codex_home), 'codexBin': str(codex_cli),
            'ipcPath': str(run/'missing-desktop-ipc')})
        settings['auth']['password'] = PASSWORD
        worker.call('save', settings)
        started = True  # A timed-out start may still have launched this isolated gateway.
        worker.call('start')
        http = GatewayHTTP(settings['preferences']['port'], http_trace)
        wait_for(lambda: http.request('GET', '/api/auth')[0] == 200,
                 'installed gateway HTTP start', 40)
        result['stage'] = 'authenticated-http'
        require(http.request('GET', '/api/sessions', authenticated=False)[0] == 401,
                'Unauthenticated session read was not rejected')
        http.login()
        require(http.request('POST', '/api/sessions/'+codex_id+'/reconnect',
                             {'activate': True}, csrf=False)[0] == 403,
                'Write without CSRF was not rejected')
        result['checks']['authCsrf'] = True
        clients = ready_clients(http)
        claude_client = next((row for row in clients if row.get('id') == 'claude'), None)
        require(claude_client is not None and claude_client.get('cliAvailable') is True and
                claude_client.get('cliAuthReady') is True,
                'Installed gateway did not discover the authenticated isolated Claude CLI')
        enabled = http.checked('POST', '/api/clients',
            {'provider': 'claude', 'enabled': True, 'initializeDesktop': False})
        require(http.trace[-1]['durationMs'] < 45_000,
                'POST /api/clients exceeded the UI lifecycle deadline')
        require(any(row.get('id') == 'claude' and row.get('enabled') is True
                    for row in enabled.get('clients', [])) and
                any(row.get('id') == 'claude' and row.get('enabled') is True
                    for row in ready_clients(http)),
                'Installed gateway did not enable Claude CLI access')
        result['checks']['claudeCliEnabledWithoutDesktop'] = True
        result['stage'] = 'codex-http'
        verify_codex(http, codex_id, project, servers[0], result['checks'])
        result['stage'] = 'claude-http'
        verify_claude(http, claude_id, project, servers[1], markers, result['checks'])
        result['stage'] = 'restart-history'
        worker.call('stop')
        started = False
        codex_lifecycle(codex_cli, codex_home, 'stop', env)
        await_native_idle(codex_home, codex_cli, claude_profile)
        started = True
        worker.call('start')
        http = GatewayHTTP(settings['preferences']['port'], http_trace)
        wait_for(lambda: http.request('GET', '/api/auth')[0] == 200,
                 'installed gateway restart', 40)
        http.login()
        require(any(row.get('id') == codex_id for row in
                    http.checked('GET', '/api/sessions?source=cli')['sessions']),
                'Codex native thread missing after gateway restart')
        wait_for_history_marker(http, '/api/sessions/'+codex_id, 'CODEX_HTTP_REPLY',
                                'Codex native history after gateway restart')
        wait_for_history_marker(http, '/api/desktop-sessions/claude/detail?sessionId='+claude_id,
                                'CLAUDE_ALLOWED_REPLY', 'Claude native history after gateway restart')
        result['checks']['persistedNativeHistory'] = True
        require(all(row['path'] == '/v1/responses' and row['keyMatches'] and
                    row['model'] in (CODEX_MODEL, CODEX_MODEL_ALT)
                    for row in servers[0].calls if row['kind'] == 'model'),
                'Codex request escaped fixture endpoint or selected wrong credentials/model')
        require(all(row['path'] == '/v1/messages' and row['keyMatches'] and
                    (row['model'] == CLAUDE_MODEL or row['model'] == servers[1].switched_model or
                     isinstance(row['model'], str) and
                     row['model'].startswith('claude-' + servers[1].switched_model + '-'))
                    for row in servers[1].calls if row['kind'] == 'model'),
                'Claude request escaped fixture endpoint or selected wrong credentials/model')
        require(any(row['kind'] == 'tool-result' and row['denied'] for row in servers[1].calls)
                and any(row['kind'] == 'tool-result' and not row['denied'] for row in servers[1].calls),
                'Claude allow/deny native tool results missing')
        result['status'] = 'passed'
        result['stage'] = 'complete'
    except Exception as exc:
        result['errorType'] = type(exc).__name__
        error = str(exc)
        for secret in (CODEX_KEY, CLAUDE_KEY, PASSWORD):
            error = error.replace(secret, '[redacted]')
        result['error'] = error[:240]
    finally:
        if started:
            try:
                worker.call('stop')
            except Exception as exc:
                result['status'] = 'failed'
                result['cleanupError'] = 'gateway stop: ' + type(exc).__name__
        if codex_cli is not None and (daemon_started or
                (codex_home/'app-server-control'/'app-server-control.sock').exists() or
                any((codex_home/'app-server-daemon'/name).exists() for name in
                    ('daemon.pid', 'app-server.pid'))):
            try:
                codex_lifecycle(codex_cli, codex_home, 'stop', env)
            except Exception as exc:
                result['status'] = 'failed'
                result['cleanupError'] = 'daemon stop: ' + type(exc).__name__
        try:
            await_native_idle(codex_home, codex_cli, claude_profile)
            result['checks']['ownedNativeRuntimesStopped'] = True
        except Exception as exc:
            result['status'] = 'failed'
            result['cleanupError'] = 'native idle: ' + type(exc).__name__ + ': ' + str(exc)[:160]
        for server, thread in zip(servers, threads):
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        result['codexModelPosts'] = sum(row['kind'] == 'model' for row in servers[0].calls)
        result['claudeModelPosts'] = sum(row['kind'] == 'model' for row in servers[1].calls)
        result['blockedExternalConnects'] = sum(row['kind'] == 'blocked-external'
                                                 for server in servers for row in server.calls)
        result['fixtureRejections'] = [row for server in servers for row in server.calls
                                       if row['kind'] == 'fixture-reject'][-12:]
        result['httpTrace'] = http_trace
        (run/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        os.environ.clear(); os.environ.update(previous_env)
        summary = {key: value for key, value in result.items() if key != 'httpTrace'}
        summary['httpRequestCount'] = len(http_trace)
        summary['maxClientsGetMs'] = max((row['durationMs'] for row in http_trace
            if row['method'] == 'GET' and row['route'] == '/api/clients'), default=0)
        print(json.dumps(summary, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


def _free_port():
    import socket
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        return reservation.getsockname()[1]


if __name__ == '__main__':
    sys.exit(main())
