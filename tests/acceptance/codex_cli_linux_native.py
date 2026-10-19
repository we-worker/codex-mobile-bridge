#!/usr/bin/env python3
"""Exercise local CliSessions through SSH into an isolated Linux Codex home.

Start codex_cli_linux_mock_server.py on the remote host first. The remote root
must be an authorized temporary directory; this script never uses the default
remote Codex home. It creates only synthetic model turns and uses no paid API.
"""
import argparse
import atexit
import json
import os
import queue
import shlex
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bridge.clients.codex.app_server import CodexAppServer
from bridge.clients.codex.cli_session import CliSessions, _ssh_daemon_start_command
from bridge.clients.codex.remote import RemoteStore, ssh_command

ALIAS = REMOTE = HOME = PROJECT = CLI = SOCKET = SSH = PORT = None


def remote_env(command):
    environment = (f'CODEX_HOME={shlex.quote(str(HOME))} CMB_FIXTURE_KEY=synthetic-key '
                   f'HTTP_PROXY=http://127.0.0.1:{PORT} HTTPS_PROXY=http://127.0.0.1:{PORT} '
                   f'ALL_PROXY=http://127.0.0.1:{PORT} NO_PROXY=127.0.0.1,localhost ')
    return environment + command


def native(command):
    result = subprocess.run(SSH + [remote_env(shlex.quote(CLI) + ' app-server daemon ' + command)],
                            capture_output=True, text=True, timeout=35)
    if result.returncode:
        raise RuntimeError(f'daemon {command} failed: {result.stderr[-500:]}')
    return json.loads(result.stdout)


class IsolatedRemoteStore(RemoteStore):
    def call(self, method, args):
        def command(alias):
            selected = ssh_command(alias)
            selected[-1] = remote_env(selected[-1])
            return selected
        with patch('bridge.clients.codex.remote.ssh_command', command):
            return super().call(method, args)


def session():
    adapter = CliSessions(HOME, lambda *_: None, lambda *_: None, alias=ALIAS)
    # Keep CliSessions' generated SSH transport and native login shell, but
    # select the isolated test home without changing the user's shell profile.
    adapter.client.command[-1] = remote_env(adapter.client.command[-1])
    adapter.store = IsolatedRemoteStore(ALIAS)
    return adapter


def wait_turn(adapter, thread_id, previous, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = adapter.refresh(thread_id)
        turns = state.get('turns') or []
        if len(turns) > previous and turns[-1].get('status') == 'completed':
            return state
        time.sleep(.25)
    raise AssertionError('Native turn did not complete through SSH adapter')


def main():
    global ALIAS, REMOTE, HOME, PROJECT, CLI, SOCKET, SSH, PORT
    parser = argparse.ArgumentParser()
    parser.add_argument('--alias', required=True)
    parser.add_argument('--remote-root', required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    ALIAS = args.alias
    REMOTE = args.remote_root.rstrip('/')
    if (not REMOTE.startswith('/') or any(c.isspace() for c in ALIAS) or
            ALIAS.startswith('-') or not 0 < args.port < 65536):
        raise ValueError('An absolute remote temporary root and loopback port are required')
    HOME = Path(REMOTE) / 'codex-home'
    PROJECT = str(Path(REMOTE) / 'project')
    CLI = str(HOME / 'packages/app-server-daemon/current/bin/codex')
    SOCKET = str(HOME / 'app-server-control/app-server-control.sock')
    PORT = args.port
    SSH = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ClearAllForwardings=yes',
           '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'UpdateHostKeys=no', ALIAS]
    native('start')
    def clean_up():
        try:
            native('stop')
        except Exception:
            pass
    atexit.register(clean_up)
    events = queue.Queue()
    original = CodexAppServer(SOCKET, command=SSH + [remote_env(
        shlex.quote(CLI) + ' app-server proxy --sock ' + shlex.quote(SOCKET))], check_socket=False,
        client_name='codex-tui', on_event=events.put)
    try:
        info = original.connect()
        assert info['codexHome'] == str(HOME), info
        thread = original.request('thread/start', {'cwd': PROJECT, 'threadSource': 'cli'})['thread']
        thread_id = thread['id']
        assert thread['cwd'] == PROJECT and thread['modelProvider'] == 'fixture', thread
        original.request('turn/start', {'threadId': thread_id, 'input': [
            {'type': 'text', 'text': 'ORIGINAL_WRITER_SYNTHETIC_MARKER; no tools.'}]})
        deadline = time.monotonic() + 30
        completed = False
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if event.get('method') == 'turn/completed' and (event.get('params') or {}).get('threadId') == thread_id:
                assert event['params']['turn']['status'] == 'completed'
                completed = True
                break
        if not completed:
            raise AssertionError('Original synthetic turn did not complete')
    finally:
        original.close()

    adapter = session()
    try:
        assert adapter.attach(thread_id) is None
        state = adapter.attach(thread_id, explicit=True)
        assert state['id'] == thread_id and state['cwd'] == PROJECT
        assert state['modelProvider'] == 'fixture'
        _, options = adapter.permission_options(thread_id)
        print('PERMISSION_OPTIONS=' + json.dumps(options, ensure_ascii=False), flush=True)
        allowed = next((row for row in options['options'] if row['preset'] == 'auto-review' and row['available']), None)
        if allowed:
            from bridge.features.sessions.linux_permissions import permission_settings
            facts, _ = adapter.permission_options(thread_id)
            settings = permission_settings('auto-review', facts)
            adapter.call(thread_id, 'thread-follower-update-thread-settings',
                         {'threadSettings': settings})
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                permissions = (adapter.refresh(thread_id).get('currentPermissions') or {})
                if (permissions.get('approvalPolicy') == settings['approvalPolicy'] and
                        permissions.get('approvalsReviewer') == settings['approvalsReviewer']):
                    break
                time.sleep(.25)
            else:
                raise AssertionError('Native permission update lacked effective confirmation')
        count = len(state.get('turns') or [])
        adapter.call(thread_id, 'thread-follower-start-turn', {'turnStart': {'request': {
            'input': [{'type': 'text', 'text': 'RESUMED_WRITER_SYNTHETIC_MARKER; no tools.'}]}}})
        wait_turn(adapter, thread_id, count)
        goal = None
        if adapter.supports_goal(thread_id):
            goal = adapter.set_goal(thread_id, 'Isolated Linux acceptance goal')
            assert goal and goal['status'] == 'active'
            adapter.clear_goal(thread_id)
            assert adapter.get_goal(thread_id) is None
        created = adapter.create(PROJECT, 'Isolated new CLI chat')
        assert created['cwd'] == PROJECT and created['modelProvider'] == 'fixture'
        assert adapter.store.get(created['id'])['origin'] == 'cli'
        print('WARM_RESULT=' + json.dumps({'threadId': thread_id, 'createdId': created['id'],
            'permissionApplied': bool(allowed), 'goalSupported': goal is not None}), flush=True)
    finally:
        adapter.close()

    stopped = native('stop')
    assert stopped.get('status') in ('stopped', 'alreadyStopped'), stopped
    # The actual remote source reader checks saved metadata in the isolated
    # home during cold resume; the production home remains untouched.
    cold = session()
    original_start = _ssh_daemon_start_command
    def isolated_start(alias):
        command = original_start(alias)
        command[-1] = remote_env(command[-1])
        return command
    try:
        with patch('bridge.clients.codex.cli_session._ssh_daemon_start_command', isolated_start):
            resumed = cold.attach(thread_id, explicit=True)
        assert resumed['id'] == thread_id and resumed['cwd'] == PROJECT
        print('COLD_RESULT=' + json.dumps({'threadId': thread_id,
            'provider': resumed['modelProvider'], 'daemon': native('version')['status']}), flush=True)
    finally:
        cold.close()
        native('stop')
        atexit.unregister(clean_up)


if __name__ == '__main__':
    main()
