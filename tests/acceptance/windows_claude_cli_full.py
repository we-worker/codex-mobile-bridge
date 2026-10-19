"""Run Windows ClaudeCli replies and approvals against an isolated loopback API.

Set CLAUDE_ACCEPTANCE_ROOT to a fresh scratch directory. Set
CLAUDE_ACCEPTANCE_SOURCE to a packaged bridge source ZIP when the repository
is not present on the Windows host. No real model request is made.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ['CLAUDE_ACCEPTANCE_ROOT']).resolve()
ROOT.mkdir(parents=True, exist_ok=False)
SOURCE = Path(os.environ.get('CLAUDE_ACCEPTANCE_SOURCE',
                             str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(SOURCE))
from bridge.clients.claude.cli_session import ClaudeCli, _profile
from bridge.clients.claude.session_registry import assert_profile_idle

PROFILE = ROOT/'profile'
PROJECT = ROOT/'project'
DENIED = PROJECT/'denied-marker.txt'
ALLOWED = PROJECT/'allowed-marker.txt'
PROFILE.mkdir(exist_ok=True)
PROJECT.mkdir(exist_ok=True)
PHASES = ('first', 'second', 'resume', 'deny-tool', 'deny-result',
          'allow-tool', 'allow-result')
REPLIES = {'first': 'FIXTURE_FIRST_REPLY', 'second': 'FIXTURE_SECOND_REPLY',
           'resume': 'FIXTURE_RESUME_REPLY', 'deny-result': 'FIXTURE_DENIED_REPLY',
           'allow-result': 'FIXTURE_ALLOWED_REPLY'}


class MockAPI(BaseHTTPRequestHandler):
    lock = threading.Lock()
    calls = []
    endpoint = None

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
        path = self.path.split('?', 1)[0]
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        if path.endswith('/count_tokens'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"input_tokens":1}')
            return
        if not path.endswith('/v1/messages'):
            self.send_error(404)
            return
        with type(self).lock:
            index = len(type(self).calls)
            phase = PHASES[index] if index < len(PHASES) else 'unexpected'
            messages = body.get('messages', [])
            last = messages[-1] if messages else {}
            content = last.get('content') if isinstance(last, dict) else None
            result = next((part for part in content if isinstance(part, dict)
                           and part.get('type') == 'tool_result'), None) if isinstance(content, list) else None
            type(self).calls.append({'phase': phase, 'path': path,
                'model': body.get('model'),
                'keyMatches': self.headers.get('x-api-key') == 'sk-ant-test-isolated',
                'toolResultId': result.get('tool_use_id') if result else None,
                'toolResultIsError': result.get('is_error') is True if result else None,
                'toolResultSuccessText': 'File created successfully' in str(result.get('content'))
                    if result else False,
                'messageCount': len(messages)})
        if phase == 'unexpected':
            self.send_error(409)
            return
        tool = phase in ('deny-tool', 'allow-tool')
        message = {'id': 'msg_fixture_'+phase, 'type': 'message', 'role': 'assistant',
                   'content': [], 'model': body.get('model'), 'stop_reason': None,
                   'stop_sequence': None, 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        if tool:
            marker = DENIED if phase == 'deny-tool' else ALLOWED
            token = 'DENIED_MARKER' if phase == 'deny-tool' else 'ALLOWED_MARKER'
            block = {'type': 'tool_use', 'id': 'toolu_'+phase.replace('-', '_'),
                     'name': 'Write', 'input': {}}
            delta = {'type': 'input_json_delta',
                     'partial_json': json.dumps({'file_path': str(marker), 'content': token})}
            reason = 'tool_use'
        else:
            block = {'type': 'text', 'text': ''}
            delta = {'type': 'text_delta', 'text': REPLIES[phase]}
            reason = 'end_turn'
        events = [
            ('message_start', {'type': 'message_start', 'message': message}),
            ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': block}),
            ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': delta}),
            ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            ('message_delta', {'type': 'message_delta',
                               'delta': {'stop_reason': reason, 'stop_sequence': None},
                               'usage': {'output_tokens': 1}}),
            ('message_stop', {'type': 'message_stop'}),
        ]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        try:
            for name, value in events:
                self.wfile.write(('event: '+name+'\ndata: '+json.dumps(value)+'\n\n').encode('utf-8'))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def wait_for(predicate, seconds=25):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.1)
    return False


def text_seen(cli, sid, token):
    return any(item.get('role') == 'assistant' and token in item.get('text', '')
               for item in cli.call('detail', sid, {})['messages'])


def result_seen(cli, sid, token):
    native = cli._get(sid)
    return any(event.get('type') == 'assistant' and token in json.dumps(event.get('message', {}))
               for event in native['events'])


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), MockAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = 'http://127.0.0.1:'+str(server.server_port)
    (PROFILE/'settings.json').write_text(json.dumps({'env': {
        'ANTHROPIC_API_KEY': 'sk-ant-test-isolated',
        'ANTHROPIC_BASE_URL': endpoint, 'ANTHROPIC_MODEL': 'fixture-model'}},
        ensure_ascii=False), encoding='utf-8')
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('ANTHROPIC_') and not key.startswith('CLAUDE_CODE_USE_')}
    env.update(CLAUDE_CONFIG_DIR=str(PROFILE),
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', DISABLE_TELEMETRY='1',
               HTTP_PROXY=endpoint, HTTPS_PROXY=endpoint, ALL_PROXY=endpoint,
               http_proxy=endpoint, https_proxy=endpoint, all_proxy=endpoint,
               NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
    proof = {'schema': 1, 'platform': sys.platform, 'claudeVersion': None,
             'created': False, 'firstReply': False, 'secondReply': False,
             'closedResume': False, 'resumeReply': False,
             'denyPendingBeforeResponse': False, 'denyNoEffect': False,
             'denyToolResult': False, 'denyFinalReply': False,
             'allowPendingBeforeResponse': False, 'allowExactEffect': False,
             'allowToolResult': False, 'allowFinalReply': False,
             'duplicateRejected': False, 'staleNoSecondEffect': False,
             'providerAndModelCorrect': False, 'nativeHistoryPersisted': False,
             'profileCorrect': False, 'cwdCorrect': False, 'ownedWritersClosed': False,
             'listenerClosed': False, 'calls': [], 'error': None}
    cli = resumed = None
    try:
        with patch.dict(os.environ, env, clear=True):
            profile = _profile()
            version = subprocess.run([profile['binary'], '--version'], capture_output=True,
                                     text=True, timeout=5, check=True).stdout.strip()
            proof['claudeVersion'] = version
            assert version.startswith('2.1.168'), 'fixture expects the verified native version'
            proof['profileCorrect'] = profile['directory'] == PROFILE
            assert proof['profileCorrect'], 'isolated config directory not selected'
            cli = ClaudeCli()
            created = cli.create(str(PROJECT), profile['origin'], 'FULL_FIRST')
            sid = created['result']['id']
            proof['created'] = created['status'] == 'ready'
            native = cli._get(sid)['nativeId']
            row = cli._get(sid)
            registry = [json.loads(path.read_text(encoding='utf-8'))
                        for path in (PROFILE/'sessions').glob('*.json')]
            proof['cwdCorrect'] = (Path(row['cwd']).resolve() == PROJECT
                and any(entry.get('sessionId') == native and
                        Path(entry.get('cwd', '')).resolve() == PROJECT for entry in registry))
            assert proof['cwdCorrect'], 'native session cwd differs from isolated project'
            owner = cli.owned[native]
            assert wait_for(lambda: not owner.active, 25), 'first turn did not finish'
            proof['firstReply'] = text_seen(cli, sid, REPLIES['first'])
            assert proof['firstReply'], 'first reply missing from detail'
            cli.call('send', sid, {'text': 'FULL_SECOND'})
            assert wait_for(lambda: not owner.active, 25), 'second turn did not finish'
            proof['secondReply'] = text_seen(cli, sid, REPLIES['second'])
            assert proof['secondReply'], 'second reply missing from detail'
            cli.close()
            cli = None
            resumed = ClaudeCli()
            resumed.listing()
            proof['closedResume'] = resumed.call('resume', sid, {})['status'] == 'ready'
            assert proof['closedResume'], 'closed resume failed'
            owner = resumed.owned[native]
            resumed.call('send', sid, {'text': 'FULL_RESUME'})
            assert wait_for(lambda: not owner.active, 25), 'resumed turn did not finish'
            proof['resumeReply'] = text_seen(resumed, sid, REPLIES['resume'])
            assert proof['resumeReply'], 'resumed reply missing from detail'
            resumed.call('send', sid, {'text': 'REQUEST_DENY_WRITE'})
            assert wait_for(lambda: bool(owner.pending), 25), 'deny approval did not arrive'
            deny_id, deny_event = next(iter(owner.pending.items()))
            proof['denyPendingBeforeResponse'] = (deny_event['request']['tool_name'] == 'Write'
                                                  and not DENIED.exists())
            assert proof['denyPendingBeforeResponse'], 'deny request/effect ordering wrong'
            resumed.call('respond', sid, {'requestId': deny_id, 'decision': 'decline'})
            assert wait_for(lambda: not owner.active, 25), 'deny turn did not finish'
            proof['denyNoEffect'] = not DENIED.exists()
            proof['denyToolResult'] = (MockAPI.calls[-1]['toolResultId'] == 'toolu_deny_tool'
                                       and MockAPI.calls[-1]['toolResultIsError'] is True)
            proof['denyFinalReply'] = text_seen(resumed, sid, REPLIES['deny-result'])
            assert proof['denyNoEffect'] and proof['denyToolResult'] and proof['denyFinalReply']
            resumed.call('send', sid, {'text': 'REQUEST_ALLOW_WRITE'})
            assert wait_for(lambda: bool(owner.pending), 25), 'allow approval did not arrive'
            allow_id, allow_event = next(iter(owner.pending.items()))
            proof['allowPendingBeforeResponse'] = (allow_event['request']['tool_name'] == 'Write'
                                                   and not ALLOWED.exists())
            assert proof['allowPendingBeforeResponse'], 'allow request/effect ordering wrong'
            resumed.call('respond', sid, {'requestId': allow_id, 'decision': 'accept'})
            assert wait_for(lambda: not owner.active, 25), 'allow turn did not finish'
            proof['allowExactEffect'] = ALLOWED.read_text(encoding='utf-8') == 'ALLOWED_MARKER'
            proof['allowToolResult'] = (MockAPI.calls[-1]['toolResultId'] == 'toolu_allow_tool'
                                        and MockAPI.calls[-1]['toolResultIsError'] is False
                                        and MockAPI.calls[-1]['toolResultSuccessText'])
            proof['allowFinalReply'] = text_seen(resumed, sid, REPLIES['allow-result'])
            assert proof['allowExactEffect'] and proof['allowToolResult'] and proof['allowFinalReply']
            marker_mtime = ALLOWED.stat().st_mtime_ns
            try:
                resumed.call('respond', sid, {'requestId': allow_id, 'decision': 'accept'})
            except ValueError:
                proof['duplicateRejected'] = True
            proof['staleNoSecondEffect'] = (ALLOWED.stat().st_mtime_ns == marker_mtime
                                           and ALLOWED.read_text(encoding='utf-8') == 'ALLOWED_MARKER')
            proof['nativeHistoryPersisted'] = all(result_seen(resumed, sid, token)
                for token in REPLIES.values())
            proof['providerAndModelCorrect'] = (len(MockAPI.calls) == len(PHASES)
                and all(call['path'] == '/v1/messages' and call['keyMatches']
                        and call['model'] == 'fixture-model' for call in MockAPI.calls))
            assert proof['duplicateRejected'] and proof['staleNoSecondEffect']
            assert proof['nativeHistoryPersisted'] and proof['providerAndModelCorrect']
    except Exception as exc:
        proof['error'] = type(exc).__name__+':'+str(exc)[:180]
    finally:
        if resumed is not None:
            resumed.close()
        if cli is not None:
            cli.close()
        server.shutdown()
        server.server_close()
        try:
            assert_profile_idle(PROFILE)
            proof['ownedWritersClosed'] = True
        except Exception as exc:
            proof['error'] = proof['error'] or 'writer cleanup: '+type(exc).__name__
        try:
            with socket.create_connection(('127.0.0.1', server.server_port), timeout=.3):
                pass
        except OSError:
            proof['listenerClosed'] = True
        if not proof['listenerClosed']:
            proof['error'] = proof['error'] or 'loopback listener remained open'
        proof['calls'] = list(MockAPI.calls)
        (ROOT/'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(proof, ensure_ascii=False))
    if proof['error']:
        raise RuntimeError(proof['error'])


if __name__ == '__main__':
    main()
