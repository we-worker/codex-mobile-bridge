import copy
import json
import sqlite3
import tempfile
import threading
import unittest
import uuid
import io
from contextlib import redirect_stdout
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bridge.clients.codex.ipc import IPCError
from bridge.features.endpoints.wsl import WslEntry
from bridge.features.endpoints.registry import Entries, entry_id
from bridge.features.sessions.store import SessionStore
from bridge.platforms.windows import wsl

ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'.tmp')
        self.addCleanup(self.temp.cleanup)
        self.entries = Entries(self.temp.name)
        self.info = {'user': 'fixture', 'homes': [{'home': '/home/fixture/.codex', 'daemon': None}]}

    def test_only_explicit_scan_probes_running_distributions(self):
        with patch.object(wsl, 'running_distributions', return_value=['Ubuntu']), patch.object(wsl, 'probe', return_value=self.info) as probe:
            self.entries.public()
            probe.assert_not_called()
            result = self.entries.scan()
            probe.assert_called_once_with('Ubuntu')
            row = result['entries'][1]
            self.assertFalse(row['enabled'])
            self.entries.configure(row['id'], True)
        restarted = Entries(self.temp.name)
        self.assertEqual(restarted.entries[0]['id'], entry_id('Ubuntu', 'fixture', '/home/fixture/.codex'))
        self.assertFalse(self.entries.bridges)  # Registration doesn't start anything.

    def test_unknown_id_or_phone_path_cannot_register_an_entry(self):
        for identifier in ('wsl:unregistered', '/home/arbitrary', 'local'):
            with self.assertRaises(ValueError):
                self.entries.configure(identifier, True)
        with self.assertRaises(KeyError):
            self.entries.get('wsl:unknown')
        self.assertFalse(self.entries.path.exists())

    def test_same_windows_and_wsl_configuration_home_cannot_be_registered_twice(self):
        self.entries.desktop_home = Path(self.temp.name).resolve()
        identifier = entry_id('Ubuntu', 'fixture', '/mnt/c/shared')
        self.entries.candidates[identifier] = {'id': identifier, 'distribution': 'Ubuntu', 'user': 'fixture',
            'home': '/mnt/c/shared', 'windowsHome': str(self.entries.desktop_home), 'label': 'shared'}
        with self.assertRaisesRegex(ValueError, '共用同一'):
            self.entries.configure(identifier, True)
        self.assertFalse(self.entries.path.exists())

    def test_disabling_closes_only_selected_byte_connection(self):
        with patch.object(wsl, 'running_distributions', return_value=['Ubuntu']), patch.object(wsl, 'probe', return_value=self.info):
            row = self.entries.scan()['entries'][1]
            self.entries.configure(row['id'], True)
            connection = Mock()
            self.entries.bridges[row['id']] = connection
            self.entries.configure(row['id'], False)
            connection.close.assert_called_once_with()
            with self.assertRaises(KeyError):
                self.entries.get(row['id'])

    def test_stopped_distribution_never_invokes_python(self):
        with patch.object(wsl, 'running_distributions', return_value=[]), patch.object(wsl.subprocess, 'run') as run:
            with self.assertRaises(OSError):
                wsl.read('Stopped Ubuntu', 'print("unexpected")')
            run.assert_not_called()


class CliStoreTests(unittest.TestCase):
    def test_cli_source_is_explicit_and_subagents_remain_excluded(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            home = Path(folder)
            with closing(sqlite3.connect(home/'state_5.sqlite')) as db:
                db.execute('CREATE TABLE threads (id TEXT, originator TEXT, source TEXT, thread_source TEXT, archived INTEGER, updated_at INTEGER, cwd TEXT, title TEXT)')
                db.executemany('INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)', [
                    ('cli', 'codex-tui', 'cli', None, 0, 10, '/fixture', 'CLI'),
                    ('shared', 'codex-tui', 'vscode', None, 0, 11, '/fixture', 'Shared CLI'),
                    ('old', None, 'cli', None, 0, 12, '/fixture', 'Old'),
                    ('desktop', 'codex_work_desktop', 'vscode', None, 0, 13, '/fixture', 'Desktop'),
                    ('child', 'codex-tui', 'cli', 'subagent', 0, 14, '/fixture', 'Child'),
                    ('exec', 'codex_exec', 'exec', None, 0, 15, '/fixture', 'Exec')])
                db.commit()
            cli, desktop = SessionStore(home, source='cli'), SessionStore(home)
            self.assertEqual({r['id'] for r in cli.list()}, {'cli', 'shared', 'old'})
            self.assertEqual({r['id'] for r in desktop.list()}, {'desktop'})
            for identifier in ('desktop', 'child', 'exec'):
                with self.assertRaises(KeyError):
                    cli.get(identifier)
            self.assertEqual(cli.get('shared')['originator'], 'codex-tui')
            with self.assertRaises(KeyError):
                desktop.get('cli')


class Runtime:
    def __init__(self, identifier):
        self.closed = False
        self.calls = []
        self.responses = []
        self.fail_send = False
        self.thread = {'id': identifier, 'cwd': '/home/fixture/project', 'modelProvider': 'magpie',
                       'model': 'group/fixture', 'reasoningEffort': 'high', 'status': {'type': 'idle'},
                       'canAcceptDirectInput': True}
        self.turns = []

    def request(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == 'thread/read':
            return {'thread': copy.deepcopy(self.thread)}
        if method == 'thread/resume':
            return {'thread': copy.deepcopy(self.thread)}
        if method == 'thread/turns/list':
            return {'data': copy.deepcopy(self.turns), 'nextCursor': None}
        if method == 'turn/start':
            if self.fail_send:
                raise IPCError('Disconnected after bytes were sent')
            self.thread['status'] = {'type': 'active'}
            return {'turn': {'id': str(uuid.uuid4())}}
        if method == 'turn/interrupt':
            return {}
        if method == 'config/read':
            return {'config': {'model_provider': 'magpie', 'model': 'group/fixture', 'model_providers': {'magpie': {}}}}
        if method == 'model/list':
            return {'data': [{'model': 'group/fixture'}]}
        raise AssertionError('Unexpected operation: ' + method)

    def write(self, value):
        self.responses.append(copy.deepcopy(value))
        if hasattr(self, 'response_callback'):
            self.response_callback(value)

    def close(self):
        self.closed = True


class WslSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'.tmp')
        self.addCleanup(self.temp.cleanup)
        self.identifier = str(uuid.uuid4())
        self.row = {'id': entry_id('Ubuntu', 'fixture', '/home/fixture/.codex'), 'distribution': 'Ubuntu',
                    'user': 'fixture', 'home': '/home/fixture/.codex', 'label': 'WSL fixture'}
        self.entry = self.make_entry()
        self.addCleanup(self.entry.close)

    def make_entry(self):
        entry = WslEntry(self.row, self.temp.name)
        entry.server = Runtime(self.identifier)
        entry.generation = 'fixture-generation'
        entry.server.response_callback = lambda value: entry._event({'method': 'serverRequest/resolved',
            'params': {'threadId': self.identifier, 'requestId': value['id']}}, entry.generation)
        entry.store = SimpleNamespace(get=lambda identifier: {'id': identifier, 'cwd': '/home/fixture/project',
                                                              'model_provider': 'magpie'})
        return entry

    def test_reads_are_passive_and_explicit_send_subscribes_to_same_loaded_daemon(self):
        view = self.entry.view(self.identifier)
        self.assertTrue(view['connected'])
        self.assertEqual(view['provider'], 'magpie')
        self.assertFalse(view['capabilities']['permissions'])
        self.assertFalse(any(m == 'thread/resume' for m, _ in self.entry.server.calls))
        identifier = str(uuid.uuid4())
        result = self.entry.send(self.identifier, 'synthetic input', identifier, work_mode='default')
        self.assertEqual(result['status'], 'accepted')
        writes = [p for m, p in self.entry.server.calls if m == 'turn/start']
        self.assertEqual(writes, [{'threadId': self.identifier,
            'input': [{'type': 'text', 'text': 'synthetic input'}], 'clientUserMessageId': identifier}])
        self.assertFalse(any(m in ('thread/start', 'config/batchWrite') for m, _ in self.entry.server.calls))
        self.assertEqual([p for m, p in self.entry.server.calls if m == 'thread/resume'],
                         [{'threadId': self.identifier, 'excludeTurns': True}])
        self.assertEqual(self.entry.send(self.identifier, 'synthetic input', identifier), result)
        self.assertEqual(sum(m == 'turn/start' for m, _ in self.entry.server.calls), 1)

    def test_fresh_not_loaded_evidence_blocks_even_when_display_says_connected(self):
        session = self.entry.session(self.identifier)
        self.assertTrue(session.connected)
        self.entry.server.thread['status'] = {'type': 'notLoaded'}
        self.entry.server.thread['canAcceptDirectInput'] = None
        with self.assertRaises(IPCError):
            self.entry.send(self.identifier, 'do not send', str(uuid.uuid4()))
        self.assertFalse(any(m == 'turn/start' for m, _ in self.entry.server.calls))
        self.assertFalse(self.entry.receipts_path.exists())

    def test_uncertain_send_survives_restart_and_is_never_replayed(self):
        submission = str(uuid.uuid4())
        self.entry.server.fail_send = True
        with self.assertRaisesRegex(IPCError, '不会重复发送'):
            self.entry.send(self.identifier, 'synthetic input', submission)
        restarted = self.make_entry()
        self.addCleanup(restarted.close)
        result = restarted.send(self.identifier, 'synthetic input', submission)
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(any(m == 'turn/start' for m, _ in restarted.server.calls))
        with self.assertRaises(ValueError):
            restarted.send(self.identifier, 'changed input', submission)

    def test_subagent_and_noninteractive_owner_cannot_receive_input(self):
        for field, value in [('parentThreadId', str(uuid.uuid4())), ('canAcceptDirectInput', False)]:
            with self.subTest(field=field):
                self.entry.server.thread[field] = value
                with self.assertRaises(IPCError):
                    self.entry.send(self.identifier, 'do not send', str(uuid.uuid4()))
                self.entry.server.thread.pop(field)
        self.assertFalse(any(m == 'turn/start' for m, _ in self.entry.server.calls))

    def test_subscription_setting_change_aborts_before_sending_or_persisting_receipt(self):
        original = self.entry.server.request
        def changed(method, params):
            result = original(method, params)
            if method == 'thread/resume':
                result['thread']['modelProvider'] = 'different'
            return result
        self.entry.server.request = changed
        with self.assertRaisesRegex(IPCError, '尚未发送'):
            self.entry.send(self.identifier, 'do not send', str(uuid.uuid4()))
        self.assertFalse(self.entry.receipts_path.exists())
        self.assertFalse(any(m == 'turn/start' for m, _ in self.entry.server.calls))

    def test_approval_is_bound_to_thread_connection_and_original_scope(self):
        self.entry.session(self.identifier)
        request = {'id': 'approval-1', 'method': 'item/commandExecution/requestApproval',
                   'params': {'threadId': self.identifier, 'command': 'fixture', 'availableDecisions': ['decline']}}
        self.entry._event(request, self.entry.generation)
        with self.assertRaises(ValueError):
            self.entry.respond(self.identifier, 'approval-1', {'decision': 'accept'})
        self.assertFalse(self.entry.server.responses)
        result = self.entry.respond(self.identifier, 'approval-1', {'decision': 'decline'})
        self.assertEqual(result['status'], 'submitted')
        self.assertEqual(self.entry.server.responses, [{'id': 'approval-1', 'result': {'decision': 'decline'}}])
        with self.assertRaises(ValueError):
            self.entry.respond(self.identifier, 'approval-1', {'decision': 'decline'})
        self.assertEqual(len(self.entry.server.responses), 1)
        self.entry._event(request, self.entry.generation)
        self.entry.generation = 'new-daemon'
        with self.assertRaises(ValueError):
            self.entry.respond(self.identifier, 'approval-1', {'decision': 'decline'})

    def test_catalog_uses_original_runtime_models_without_exporting_config(self):
        result = self.entry.catalog(self.identifier, kind='models')
        self.assertEqual(result['models'], [{'model': 'group/fixture'}])
        self.assertNotIn('model_providers', result)
        self.assertFalse(any(m == 'turn/start' for m, _ in self.entry.server.calls))

    def test_wsl_access_summary_is_external_and_never_exposes_desktop_accounts(self):
        value = self.entry.access_summary()
        self.assertEqual(value['scope'], 'wsl')
        self.assertEqual(value['current']['name'], 'Magpie')
        self.assertFalse(value['canSwitch'])
        self.assertEqual(value['accounts'], [])
        self.assertNotIn('model_providers', json.dumps(value))

    def test_actual_injected_workspace_source_runs_without_bridge_imports_and_rejects_escape(self):
        root = Path(self.temp.name)/'project'
        root.mkdir()
        (root/'fixture.txt').write_bytes(b'fixture')
        (root.parent/'outside.txt').write_bytes(b'private')
        self.entry.store = SimpleNamespace(get=lambda _: {'cwd': str(root)})
        def remote(alias, source, timeout):
            self.assertNotIn('from bridge.', source)
            output = io.StringIO()
            with redirect_stdout(output):
                exec(source, {'__name__': 'wsl_fixture_payload'})
            return json.loads(output.getvalue())
        self.entry.read = remote
        self.assertEqual(self.entry.workspace(self.identifier, 'info', {'path': 'fixture.txt'})['size'], 7)
        with self.assertRaises(ValueError):
            self.entry.workspace(self.identifier, 'info', {'path': '../outside.txt'})


if __name__ == '__main__':
    unittest.main()
