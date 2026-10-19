"""Draft keys follow verified owners, not login or model cache generations."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bridge.app.service import Bridge
from bridge.clients.manager import DesktopSessions
from bridge.clients.claude.remote_worker import draft_account_identity as claude_account_identity
from bridge.features.accounts.draft_identity import codex_account_identity
from bridge.features.auth.auth import Auth


class DraftIdentityTests(unittest.TestCase):
    def test_gateway_scope_survives_restart_and_password_rotation(self):
        with tempfile.TemporaryDirectory() as root:
            config = {'mode': 'password', 'username': 'alice', 'salt': 'one', 'hash': 'old'}
            first = Auth(config, root)
            expected = first.draft_identity
            token, _ = first.new_session('127.0.0.1')
            first.logout(token)
            self.assertEqual(Auth(config, root).draft_identity, expected)
            rotated = Auth({**config, 'salt': 'two', 'hash': 'new'}, root)
            self.assertEqual(rotated.draft_identity, expected)
            self.assertNotEqual(Auth({**config, 'username': 'bob'}, root).draft_identity, expected)
            with tempfile.TemporaryDirectory() as other:
                self.assertNotEqual(Auth(config, other).draft_identity, expected)
            for secret in ('old', 'new', first.cookie_name):
                self.assertNotIn(secret, expected)

    def test_codex_owner_is_stable_across_token_and_model_changes(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            bridge = Bridge.__new__(Bridge)
            bridge.host = 'local'
            bridge.codex_home = home
            bridge.accounts = SimpleNamespace(lock=threading.RLock(), active_matches=lambda: False)
            (home/'auth.json').write_text(json.dumps({'tokens': {'account_id': 'account-a', 'access_token': 'old'}}))
            first = bridge._draft_account_identity({'provider': 'openai', 'model': 'first'})
            (home/'auth.json').write_text(json.dumps({'tokens': {'account_id': 'account-a', 'access_token': 'renewed'}}))
            self.assertEqual(bridge._draft_account_identity({'provider': 'openai', 'model': 'second'}), first)
            (home/'auth.json').write_text(json.dumps({'tokens': {'account_id': 'account-b'}}))
            self.assertNotEqual(bridge._draft_account_identity({'provider': 'openai'}), first)
            bridge.host = 'ssh-host'
            bridge.cli_sessions = SimpleNamespace(alias=None)
            self.assertEqual(bridge._draft_account_identity({'provider': 'openai'}), '')
            bridge.host = 'local'
            self.assertEqual(bridge._draft_account_identity({'provider': 'custom'}), '')

    def test_codex_api_credential_fallback_excludes_model(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            (home/'auth.json').write_text(json.dumps({'OPENAI_API_KEY': 'key-one'}))
            bridge = Bridge.__new__(Bridge)
            bridge.host = 'local'
            bridge.codex_home = home
            bridge.accounts = SimpleNamespace(lock=threading.RLock(), active_matches=lambda: False)
            first = bridge._draft_account_identity({'provider': 'openai', 'model': 'a'})
            self.assertEqual(first, bridge._draft_account_identity({'provider': 'openai', 'model': 'b'}))
            (home/'auth.json').write_text(json.dumps({'OPENAI_API_KEY': 'key-two'}))
            self.assertNotEqual(first, bridge._draft_account_identity({'provider': 'openai'}))

    def test_codex_never_uses_gateway_ambient_key_for_joined_home(self):
        with tempfile.TemporaryDirectory() as root, patch.dict('os.environ', {'OPENAI_API_KEY': 'wrong-shell-key'}):
            self.assertEqual(codex_account_identity(root, 'openai'), '')
            (Path(root)/'auth.json').write_text(json.dumps({'auth_mode': 'apikey',
                                                            'OPENAI_API_KEY': 'actual-home-key'}))
            self.assertEqual(codex_account_identity(root, 'openai'),
                             codex_account_identity(root, 'openai', {'OPENAI_API_KEY': 'wrong-shell-key'}))

    def test_saved_codex_api_provider_uses_saved_key_and_endpoint(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            saved = home/'saved'
            saved.mkdir()
            secret = saved/'api.json'
            secret.write_text(json.dumps({'key': 'first-key'}))
            row = {'id': 'saved-id', 'kind': 'api', 'baseUrl': 'https://api.example/v1'}
            accounts = SimpleNamespace(lock=threading.RLock(), active_matches=lambda: True,
                index={'activeId': 'saved-id'}, row=lambda identifier: row,
                directory=lambda identifier: saved)
            bridge = Bridge.__new__(Bridge)
            bridge.host = 'local'
            bridge.codex_home = home
            bridge.accounts = accounts
            first = bridge._draft_account_identity({'provider': 'bridge_api', 'model': 'model-a'})
            self.assertEqual(first, bridge._draft_account_identity({'provider': 'bridge_api', 'model': 'model-b'}))
            secret.write_text(json.dumps({'key': 'second-key'}))
            self.assertNotEqual(first, bridge._draft_account_identity({'provider': 'bridge_api'}))
            row['baseUrl'] = 'https://other.example/v1'
            self.assertNotEqual(first, bridge._draft_account_identity({'provider': 'bridge_api'}))

    def test_codex_ssh_owner_comes_from_selected_remote(self):
        bridge = Bridge.__new__(Bridge)
        bridge.host = 'remote-one'
        bridge.cli_sessions = SimpleNamespace(alias='ssh-one', remote_home=Path('/remote/codex'))
        bridge._draft_remote_lock = threading.Lock()
        bridge._draft_remote_cache = {}
        bridge._draft_remote_pending = set()
        started = threading.Event()
        release = threading.Event()
        def slow_remote(alias, source, timeout):
            started.set()
            release.wait(2)
            return {'identity': 'remote-account'}
        with patch('bridge.app.service.ssh_read', side_effect=slow_remote) as read:
            begin = time.monotonic()
            self.assertEqual(bridge._draft_account_identity({'provider': 'openai'}), '')
            self.assertLess(time.monotonic() - begin, 0.2)
            self.assertTrue(started.wait(1))
            self.assertEqual(bridge._draft_account_identity({'provider': 'openai'}), '')
            read.assert_called_once()
            release.set()
            for _ in range(100):
                first = bridge._draft_account_identity({'provider': 'openai'})
                if first:
                    break
                time.sleep(0.01)
            self.assertEqual(len(first), 64)
            read.assert_called_once()
        self.assertEqual(read.call_args.args[0], 'ssh-one')
        self.assertIn('request["home"]', read.call_args.args[1])
        bridge.host = 'remote-two'
        with patch('bridge.app.service.ssh_read', return_value={'identity': 'remote-account'}):
            self.assertEqual(bridge._draft_account_identity({'provider': 'openai'}), '')
            for _ in range(100):
                second = bridge._draft_account_identity({'provider': 'openai'})
                if second:
                    break
                time.sleep(0.01)
            self.assertNotEqual(second, first)

    def test_remote_refresh_keeps_known_scope_until_probe_finishes(self):
        bridge = Bridge.__new__(Bridge)
        bridge.host = 'remote-one'
        bridge.cli_sessions = SimpleNamespace(alias='ssh-one', remote_home=Path('/remote/codex'))
        bridge._draft_remote_lock = threading.Lock()
        key = ('remote-one', 'ssh-one', str(bridge.cli_sessions.remote_home), 'openai')
        bridge._draft_remote_cache = {key: (time.monotonic() - 31, 'known-owner')}
        bridge._draft_remote_pending = set()
        with patch('bridge.app.service.threading.Thread') as worker:
            self.assertEqual(bridge._draft_account_identity({'provider': 'openai'}), 'known-owner')
            self.assertEqual(bridge._draft_account_identity({'provider': 'openai'}), 'known-owner')
            worker.return_value.start.assert_called_once()

    def test_claude_native_metadata_survives_credential_refresh(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)/'.claude'
            directory.mkdir()
            metadata = {'oauthAccount': {'accountUuid': 'account-one', 'organizationUuid': 'org-one'}}
            (directory/'.claude.json').write_text(json.dumps(metadata))
            first = claude_account_identity(directory)
            self.assertEqual(len(first), 64)
            (directory/'.credentials.json').write_text('{"accessToken":"renewed"}')
            self.assertEqual(claude_account_identity(directory), first)
            metadata['oauthAccount']['accountUuid'] = 'account-two'
            (directory/'.claude.json').write_text(json.dumps(metadata))
            self.assertNotEqual(claude_account_identity(directory), first)

    def test_claude_selected_project_env_overrides_ambient_and_user_settings(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)/'.claude'
            directory.mkdir()
            cwd = Path(root)/'project'
            (cwd/'.claude').mkdir(parents=True)
            (directory/'settings.json').write_text(json.dumps({'env': {'ANTHROPIC_API_KEY': 'user-key'}}))
            (cwd/'.claude/settings.json').write_text(json.dumps({'env': {'ANTHROPIC_API_KEY': 'project-key'}}))
            first = claude_account_identity(directory, cwd, {'ANTHROPIC_API_KEY': 'ambient-key'})
            self.assertEqual(first, claude_account_identity(directory, cwd, {'ANTHROPIC_API_KEY': 'another-ambient-key'}))
            (cwd/'.claude/settings.json').write_text(json.dumps({'env': {'ANTHROPIC_API_KEY': 'second-project-key'}}))
            self.assertNotEqual(first, claude_account_identity(directory, cwd))

    def test_desktop_uses_verified_deepseek_account_and_fails_closed(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        credential = Path(temp.name)/'deepseek.json'
        credential.write_text(json.dumps({'version': 1, 'refs': {'DEEPSEEK_API_KEY': 'api-key'}, 'records': {}}))
        credential.chmod(0o600)
        manager = DesktopSessions.__new__(DesktopSessions)
        manager.adapters = {'deepseek': SimpleNamespace()}
        snapshot = {'accounts': [{'id': 'saved-api', 'kind': 'api', 'saved': True}],
                    'activeIds': ['saved-api']}
        manager._account_store = lambda provider: SimpleNamespace(lock=threading.RLock(), public=lambda: snapshot,
                                                                  path=credential)
        detail = {'session': {'model': 'deepseek-official/model-a'}}
        first = manager._draft_account_identity('deepseek', 'session', detail)
        self.assertEqual(len(first), 64)
        detail['session']['model'] = 'deepseek-official/model-b'
        self.assertEqual(manager._draft_account_identity('deepseek', 'session', detail), first)
        credential.write_text(json.dumps({'version': 1, 'refs': {'DEEPSEEK_API_KEY': 'new-key'}, 'records': {}}))
        self.assertNotEqual(manager._draft_account_identity('deepseek', 'session', detail), first)
        snapshot['activeIds'] = []
        self.assertEqual(manager._draft_account_identity('deepseek', 'session', detail), '')
        snapshot['activeIds'] = ['saved-api']
        self.assertEqual(manager._draft_account_identity('deepseek', 'session', {'session': {'model': 'other/model'}}), '')

    def test_unsaved_deepseek_official_uses_current_fingerprint(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        credential = Path(temp.name)/'deepseek.json'
        def set_grant(token):
            credential.write_text(json.dumps({'version': 1, 'refs': {}, 'records': {
                'deepseek-account-platform/default': {'kind': 'grant', 'payload': {
                    'version': 1, 'issuer': 'https://platform.deepseek.com', 'token': token}}}}))
            credential.chmod(0o600)
        set_grant('token-one')
        manager = DesktopSessions.__new__(DesktopSessions)
        manager.adapters = {'deepseek': SimpleNamespace()}
        row = {'id': 'current-official', 'kind': 'official', 'saved': False}
        snapshot = {'accounts': [row], 'activeIds': ['current-official']}
        manager._account_store = lambda provider: SimpleNamespace(lock=threading.RLock(), public=lambda: snapshot,
                                                                  path=credential)
        detail = {'session': {'model': 'deepseek-account/model'}}
        first = manager._draft_account_identity('deepseek', 'session', detail)
        self.assertEqual(len(first), 64)
        set_grant('token-two')
        self.assertNotEqual(manager._draft_account_identity('deepseek', 'session', detail), first)
        row['accountId'] = 'known-account'
        stable = manager._draft_account_identity('deepseek', 'session', detail)
        set_grant('token-three')
        self.assertEqual(manager._draft_account_identity('deepseek', 'session', detail), stable)

    def test_claude_cli_requires_matching_managed_profile(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        credential = Path(temp.name)/'api.json'
        credential.write_text(json.dumps({'key': 'api-key'}))
        manager = DesktopSessions.__new__(DesktopSessions)
        profile = {'origin': 'gateway:saved-api:/profile:settings-a', 'directory': '/profile'}
        cli = SimpleNamespace(lock=threading.RLock(), index={'session': {'origin': profile['origin']}},
                              profile_resolver=lambda: profile)
        remote = SimpleNamespace(lock=threading.RLock(), index={})
        manager.adapters = {'claude': SimpleNamespace(cli=cli, remote_cli=remote, index={})}
        access = SimpleNamespace(lock=threading.RLock(), index={'activeClaude': 'saved-api',
            'claude': [{'id': 'saved-api', 'kind': 'api', 'originBase': 'gateway:saved-api:/profile',
                        'secretPath': str(credential), 'baseUrl': 'https://api.example/v1',
                        'authScheme': 'bearer'}]})
        manager.bridge = SimpleNamespace(cli_access=access)
        first = manager._draft_account_identity('claude', 'session', {'session': {}})
        self.assertEqual(len(first), 64)
        profile['origin'] = 'gateway:saved-api:/profile:settings-b'
        cli.index['session']['origin'] = profile['origin']
        self.assertEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), first)
        credential.write_text(json.dumps({'key': 'other-account-key'}))
        self.assertNotEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), first)
        credential.write_text(json.dumps({'key': 'api-key'}))
        access.index['claude'][0]['baseUrl'] = 'https://other.example/v1'
        self.assertNotEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), first)
        remote.index['session'] = {'host': 'remote'}
        self.assertEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), '')
        remote.index.clear()
        access.index['activeClaude'] = 'different'
        self.assertEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), '')

    def test_unsaved_claude_desktop_uses_current_fingerprint(self):
        manager = DesktopSessions.__new__(DesktopSessions)
        cli = SimpleNamespace(lock=threading.RLock(), index={})
        remote = SimpleNamespace(lock=threading.RLock(), index={})
        manager.adapters = {'claude': SimpleNamespace(cli=cli, remote_cli=remote,
                                                     index={'session': {'backend': 'desktop'}})}
        current = ['official', 'token-fingerprint-one', None]
        manager._account_store = lambda provider: SimpleNamespace(lock=threading.RLock(),
            _current=lambda: current, _index=lambda: {'accounts': []})
        first = manager._draft_account_identity('claude', 'session', {'session': {}})
        self.assertEqual(len(first), 64)
        current[1] = 'token-fingerprint-two'
        self.assertNotEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), first)
        current[1] = ''
        self.assertEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), '')

    def test_claude_desktop_api_identity_excludes_model_list(self):
        manager = DesktopSessions.__new__(DesktopSessions)
        cli = SimpleNamespace(lock=threading.RLock(), index={})
        remote = SimpleNamespace(lock=threading.RLock(), index={})
        manager.adapters = {'claude': SimpleNamespace(cli=cli, remote_cli=remote,
                                                     index={'session': {'backend': 'desktop'}})}
        config = {'inferenceGatewayBaseUrl': 'https://api.example/v1',
                  'inferenceGatewayApiKey': 'first-key',
                  'inferenceGatewayAuthScheme': 'bearer', 'inferenceModels': ['model-a']}
        gateway = {'id': 'profile-id', 'config': config}
        manager._account_store = lambda provider: SimpleNamespace(lock=threading.RLock(),
            _current=lambda: ('api', 'whole-config-fingerprint', gateway))
        first = manager._draft_account_identity('claude', 'session', {'session': {}})
        config['inferenceModels'] = ['model-b']
        self.assertEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), first)
        config['inferenceGatewayApiKey'] = 'second-key'
        self.assertNotEqual(manager._draft_account_identity('claude', 'session', {'session': {}}), first)


if __name__ == '__main__':
    unittest.main()
