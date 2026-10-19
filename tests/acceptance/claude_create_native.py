#!/usr/bin/env python3
"""Create native local and SSH Claude Code sessions with an isolated mock API."""

import json
import os
import shlex
import shutil
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bridge.clients.claude import remote
from bridge.clients.claude.cli_session import ClaudeCli, _profile
from bridge.clients.claude.remote import RemoteClaudeCli
from ssh_claude_native import MockAPI, loopback_sshd, wait_for


def main():
    if not shutil.which('claude') or not Path('/usr/sbin/sshd').is_file():
        raise RuntimeError('Installed Claude and macOS OpenSSH server are required')
    (ROOT/'.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='claude-create-native-', dir=ROOT/'.tmp') as temporary:
        root = Path(temporary).resolve()
        profile, cwd = root/'profile', root/'project'
        profile.mkdir()
        cwd.mkdir()
        MockAPI.root = root
        MockAPI.bodies = []
        MockAPI.credentials = []
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
        local = ClaudeCli(root/'uploads', profile_resolver=_profile)
        remote_cli = sshd = stderr = None
        try:
            with patch.dict(os.environ, clean_env, clear=True):
                selected = _profile()
                assert selected and local.status()['cliAuthReady']
                created = local.create(str(cwd), selected['origin'], 'LOCAL_CREATE_SENTINEL')
                sid = created['result']['id']
                row = next(row for row in local.listing()['sessions'] if row['id'] == sid)
                assert row['title'] == 'LOCAL_CREATE_SENTINEL'
                assert row['cwd'] == str(cwd) and row['model'] == 'fixture-model'
                assert row['permissionMode'] == 'plan'
                assert wait_for(lambda: not local.owned[row['nativeId']].active)
                assert len(MockAPI.bodies) == 1
                usage = local.call('detail', sid, {})['session']['contextUsage']
                assert usage['usedTokens'] == 1 and usage['model'] == 'fixture-model'
                assert usage['contextWindow'] == 200000
            local.close()

            sshd, bindir, stderr = loopback_sshd(root)

            class Hosts:
                def hosts(self):
                    return {'ssh:fixture': {'alias': 'fixture-loopback', 'displayName': 'Fixture SSH'}}
                def projects(self):
                    return [{'host': 'ssh:fixture', 'cwd': str(cwd)}]

            remote_cli = RemoteClaudeCli(Hosts())
            original_command = remote._command

            def isolated_command(alias):
                command = original_command(alias)
                variables = {'HOME': str(root), 'CLAUDE_CONFIG_DIR': str(profile),
                             'HTTP_PROXY': endpoint, 'HTTPS_PROXY': endpoint,
                             'ALL_PROXY': endpoint, 'NO_PROXY': '127.0.0.1,localhost'}
                command[-1] = ' '.join(key+'='+shlex.quote(value) for key, value in variables.items())+' '+command[-1]
                return command

            with patch.object(remote, '_command', isolated_command), \
                 patch.dict(os.environ, {'PATH': str(bindir)+':'+os.environ['PATH']}):
                project = next(row for row in remote_cli.projects() if row['cwd'] == str(cwd))
                created = remote_cli.create(project['host'], project['alias'], project['origin'],
                                            project['cwd'], 'SSH_CREATE_SENTINEL')
                sid = created['result']['id']
                row = remote_cli.index[sid]
                assert row['title'] == 'SSH_CREATE_SENTINEL'
                assert row['cwd'] == str(cwd) and row['model'] == 'fixture-model'
                assert row['permissionMode'] == 'plan'
                assert wait_for(lambda: not remote_cli.owned[sid].active)
                assert len(MockAPI.bodies) == 2
                usage = remote_cli.call('detail', sid, {})['session']['contextUsage']
                assert usage['usedTokens'] == 1 and usage['model'] == 'fixture-model'
                assert usage['contextWindow'] == 200000
                assert all(credential == 'isolated-fixture-key'
                           for credential in MockAPI.credentials)
                assert len(list(profile.glob('projects/**/*.jsonl'))) == 2
                print('PASS: native local and SSH create use selected profile/cwd/auth, send first message once, persist real session history, and expose native prompt usage')
        finally:
            local.close()
            if remote_cli is not None:
                remote_cli.close()
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
