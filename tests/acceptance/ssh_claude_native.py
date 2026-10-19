#!/usr/bin/env python3
"""Native Claude Code over disposable OpenSSH and a localhost Anthropic mock."""

import json
import os
import pwd
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bridge.clients.claude import remote
from bridge.clients.claude.remote import RemoteClaudeCli
from bridge.clients.errors import BridgeUnavailable


class MockAPI(BaseHTTPRequestHandler):
    bodies = []
    credentials = []
    approval_sent = False
    slow_sent = False
    root = None

    def log_message(self, *_):
        pass

    def do_CONNECT(self):
        self.send_error(403)

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"data":[]}')

    def do_POST(self):
        credential = self.headers.get('x-api-key') or self.headers.get('Authorization')
        if credential != 'isolated-fixture-key':
            self.send_error(401)
            return
        self.credentials.append(credential)
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.bodies.append(body)
        latest = json.dumps(next((message for message in reversed(body.get('messages', []))
                                  if message.get('role') == 'user'), {}))
        tool = 'REQUEST_BASH_APPROVAL' in latest and not type(self).approval_sent
        slow = 'SLOW_TURN' in latest and not type(self).slow_sent
        if tool:
            type(self).approval_sent = True
        if slow:
            type(self).slow_sent = True
            time.sleep(8)
        message = {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
                   'content': [], 'model': body.get('model'), 'stop_reason': None,
                   'stop_sequence': None, 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        if tool:
            command = 'printf APPROVAL_TOKEN > ' + str(self.root/'approval.txt')
            block = {'type': 'tool_use', 'id': 'toolu_approval_fixture', 'name': 'Bash', 'input': {}}
            delta = {'type': 'input_json_delta', 'partial_json': json.dumps({'command': command})}
            reason = 'tool_use'
        else:
            block = {'type': 'text', 'text': ''}
            delta = {'type': 'text_delta', 'text': 'Fixture reply.'}
            reason = 'end_turn'
        events = [
            ('message_start', {'type': 'message_start', 'message': message}),
            ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': block}),
            ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': delta}),
            ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': reason,
                                 'stop_sequence': None}, 'usage': {'output_tokens': 1}}),
            ('message_stop', {'type': 'message_stop'}),
        ]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        try:
            for name, value in events:
                self.wfile.write(f'event: {name}\ndata: {json.dumps(value)}\n\n'.encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def loopback_sshd(root):
    directory = root/'ssh'
    directory.mkdir(mode=0o700)
    keygen = '/usr/bin/ssh-keygen'
    for name in ('client', 'host'):
        subprocess.run([keygen, '-q', '-t', 'ed25519', '-N', '', '-f', str(directory/name)],
                       check=True, capture_output=True)
    authorized = directory/'authorized_keys'
    authorized.write_text((directory/'client.pub').read_text())
    authorized.chmod(0o600)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    config = directory/'sshd_config'
    config.write_text('\n'.join([
        'ListenAddress 127.0.0.1', f'Port {port}', f'HostKey {directory/"host"}',
        f'PidFile {directory/"sshd.pid"}', f'AuthorizedKeysFile {authorized}',
        'StrictModes no', 'PasswordAuthentication no', 'KbdInteractiveAuthentication no',
        'UsePAM no', 'PermitRootLogin no', 'PubkeyAuthentication yes', 'PermitTTY no',
        'AllowTcpForwarding no', 'PermitTunnel no', 'X11Forwarding no', 'LogLevel ERROR',
    ])+'\n')
    subprocess.run(['/usr/sbin/sshd', '-t', '-f', str(config)], check=True, capture_output=True)
    host_key = subprocess.run([keygen, '-y', '-f', str(directory/'host')], check=True,
                              capture_output=True, text=True).stdout.strip()
    known = directory/'known_hosts'
    known.write_text(f'[127.0.0.1]:{port} {host_key}\n')
    client_config = directory/'client_config'
    client_config.write_text('\n'.join([
        'Host fixture-loopback', '  HostName 127.0.0.1', f'  Port {port}',
        f'  User {pwd.getpwuid(os.getuid()).pw_name}', f'  IdentityFile {directory/"client"}',
        f'  UserKnownHostsFile {known}', '  GlobalKnownHostsFile /dev/null',
        '  IdentitiesOnly yes', '  StrictHostKeyChecking yes', '  UpdateHostKeys no',
        '  ControlMaster no', '  BatchMode yes', '  ForwardAgent no',
    ])+'\n')
    bindir = directory/'bin'
    bindir.mkdir()
    wrapper = bindir/'ssh'
    wrapper.write_text('#!/bin/sh\nexec /usr/bin/ssh -F ' + shlex.quote(str(client_config)) + ' "$@"\n')
    wrapper.chmod(0o700)
    stderr = (directory/'sshd.stderr').open('wb')
    process = subprocess.Popen(['/usr/sbin/sshd', '-D', '-e', '-f', str(config)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr)
    for _ in range(30):
        probe = subprocess.run(['/usr/bin/ssh', '-F', str(client_config), 'fixture-loopback',
                                'printf SSH_OK'], capture_output=True, text=True, timeout=5)
        if probe.returncode == 0 and probe.stdout == 'SSH_OK':
            return process, bindir, stderr
        if process.poll() is not None:
            break
        time.sleep(.1)
    process.terminate()
    stderr.close()
    raise RuntimeError('Disposable OpenSSH fixture unavailable')


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.05)
    return False


def main():
    binary = shutil.which('claude')
    if not binary or not Path('/usr/sbin/sshd').is_file():
        raise RuntimeError('Installed Claude and macOS OpenSSH server are required')
    (ROOT/'.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ssh-claude-native-', dir=ROOT/'.tmp') as temporary:
        root = Path(temporary).resolve()
        profile, cwd = root/'profile', root/'project'
        profile.mkdir()
        cwd.mkdir()
        skill = profile/'skills'/'fixture-skill'
        skill.mkdir(parents=True)
        (skill/'SKILL.md').write_text('---\nname: fixture-skill\ndescription: Isolated Skill\n---\nAlways include SKILL_TOKEN in reply.\n')
        MockAPI.root = root
        MockAPI.bodies = []
        MockAPI.credentials = []
        MockAPI.approval_sent = MockAPI.slow_sent = False
        server = ThreadingHTTPServer(('127.0.0.1', 0), MockAPI)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        endpoint = f'http://127.0.0.1:{server.server_port}'
        (profile/'settings.json').write_text(json.dumps({
            'permissions': {'defaultMode': 'plan'},
            'env': {'ANTHROPIC_API_KEY': 'isolated-fixture-key',
                    'ANTHROPIC_BASE_URL': endpoint, 'ANTHROPIC_MODEL': 'fixture-model'},
        }))
        clean_env = {key: value for key, value in os.environ.items()
                     if not key.startswith('ANTHROPIC_')}
        clean_env.update({'HOME': str(root), 'CLAUDE_CONFIG_DIR': str(profile),
                          'HTTP_PROXY': endpoint, 'HTTPS_PROXY': endpoint, 'ALL_PROXY': endpoint,
                          'NO_PROXY': '127.0.0.1,localhost'})
        sshd = cli = stderr = None
        try:
            original = subprocess.run([binary, '-p', 'Initial isolated fixture', '--output-format',
                                       'json', '--model', 'fixture-model', '--max-turns', '1'],
                                      cwd=cwd, env=clean_env, capture_output=True, text=True, timeout=40)
            assert original.returncode == 0, original.stderr[:500]
            native = json.loads(original.stdout)['session_id']
            sshd, bindir, stderr = loopback_sshd(root)

            class Hosts:
                def hosts(self):
                    return {'ssh:fixture': {'alias': 'fixture-loopback', 'displayName': 'Fixture SSH'}}

            cli = RemoteClaudeCli(Hosts())
            original_command = remote._command

            def isolated_command(alias):
                command = original_command(alias)
                environment = {'HOME': str(root), 'CLAUDE_CONFIG_DIR': str(profile),
                               'HTTP_PROXY': endpoint, 'HTTPS_PROXY': endpoint,
                               'ALL_PROXY': endpoint, 'NO_PROXY': '127.0.0.1,localhost'}
                prefix = ' '.join(key+'='+shlex.quote(value) for key, value in environment.items())
                command[-1] = prefix+' '+command[-1]
                return command

            with patch.object(remote, '_command', isolated_command), \
                 patch.dict(os.environ, {'PATH': str(bindir)+':'+os.environ['PATH']}):
                cli.listing()
                assert wait_for(lambda: len(cli.listing()['sessions']) == 1)
                row = cli.listing()['sessions'][0]
                sid = row['id']
                assert row['nativeId'] == native and row['cwd'] == str(cwd)
                detail = cli.call('detail', sid, {})
                assert detail['capabilities']['resume'] and detail['session']['permissionMode'] == 'plan'
                assert cli.call('resume', sid, {})['status'] == 'ready'
                catalog = cli.call('catalog', sid, {})
                assert catalog['currentModel'] == 'fixture-model'
                assert any(skill['id'] == 'fixture-skill' for skill in catalog['skills'])
                model = next(item['id'] for item in catalog['models'] if item['id'] == 'opus')
                assert cli.call('settings', sid, {'model': model})['status'] == 'accepted'
                assert cli.call('access', sid, {'mode': 'default'})['status'] == 'accepted'
                assert cli.owned[sid].permission == 'default'
                assert cli.call('send', sid, {'text': 'First native SSH turn'})['status'] == 'accepted'
                assert wait_for(lambda: not cli.owned[sid].active)
                assert MockAPI.bodies[-1]['model'].startswith('claude-opus')

                attachment = root/'note.txt'
                attachment.write_bytes(b'FILE_TOKEN_REMOTE_BYTES')
                assert cli.call('send', sid, {'text': 'Check attachment',
                    'plugins': ['fixture-skill'], 'resolvedFiles': [{'id': str(uuid.uuid4()),
                    'name': 'note.txt', 'path': str(attachment)}]})['status'] == 'accepted'
                assert wait_for(lambda: not cli.owned[sid].active)
                uploaded = next((profile/'mobile-bridge'/'uploads').rglob('original.txt'))
                assert uploaded.read_bytes() == attachment.read_bytes()
                api_payload = json.dumps(MockAPI.bodies[-1], ensure_ascii=False)
                assert 'SKILL_TOKEN' in api_payload and str(uploaded) in api_payload
                assert str(attachment) not in api_payload

                assert cli.call('send', sid, {'text': 'REQUEST_BASH_APPROVAL'})['status'] == 'accepted'
                assert wait_for(lambda: bool(cli.owned[sid].pending))
                request_id, event = next(iter(cli.owned[sid].pending.items()))
                assert event['request']['tool_name'] == 'Bash'
                assert cli.call('respond', sid, {'requestId': request_id,
                                                'decision': 'decline'})['status'] == 'accepted'
                assert wait_for(lambda: not cli.owned[sid].active)
                assert not (root/'approval.txt').exists()

                assert cli.call('send', sid, {'text': 'SLOW_TURN'})['status'] == 'accepted'
                assert cli.call('stop', sid, {})['status'] == 'accepted'
                assert wait_for(lambda: not cli.owned[sid].active)

                owned = cli.owned[sid]
                actual_write = owned.write
                writes = []
                def sever(frame):
                    writes.append(frame)
                    actual_write(frame)
                    owned.process.kill()
                with patch.object(owned, 'write', sever):
                    try:
                        cli.call('send', sid, {'text': 'DISCONNECT_TURN'})
                    except BridgeUnavailable as exc:
                        assert '结果不明' in str(exc)
                    else:
                        raise AssertionError('Severed SSH write was reported accepted')
                assert len(writes) == 1
                assert MockAPI.credentials and len(MockAPI.credentials) == len(MockAPI.bodies)
                print('PASS: native saved resume, host profile/cwd/auth, model/permission, Skill and remote file, approval, interrupt, unknown disconnect with no replay')
        finally:
            if cli is not None:
                cli.close()
            if sshd is not None:
                sshd.terminate()
                sshd.wait(timeout=5)
            if stderr is not None:
                stderr.close()
            server.shutdown()
            server.server_close()
            time.sleep(.5)


if __name__ == '__main__':
    main()
