"""Private Tauri host contracts, isolated from real accounts and clients."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bridge.app.tauri import Host, checked_url

ROOT = Path(__file__).resolve().parents[1]


class HostTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.tmp').mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT/'.tmp')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.patch = patch('bridge.app.tauri.Desktop')
        factory = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.desktop = factory.return_value
        self.desktop.data_dir = self.root/'data'
        self.desktop.preferences.return_value = {'connections': [{'id':'server','accessMode':'server'}]}
        self.desktop.snapshot.return_value = {'urls':['http://127.0.0.1:8787/'], 'preferences': self.desktop.preferences.return_value}
        self.host = Host(self.desktop.data_dir, self.root/'desktop', '2.0.3')
        self.addCleanup(self.host.close)

    def test_memory_credentials_never_write_and_survive_start_in_same_owner(self):
        self.host.dispatch('connection-credentials', {'id':'server','secrets':{'password':'fixture-secret'}})
        self.desktop.connection_credentials.assert_not_called()
        self.assertEqual(self.host.dispatch('read-credentials', {'id':'server'}), {'password':'fixture-secret'})
        self.host.dispatch('start')
        self.desktop.start.assert_called_once_with({'connectionSecrets':{'server':{'password':'fixture-secret'}}})
        self.assertNotIn('fixture-secret', json.dumps(self.host.dispatch('snapshot')))

    def test_remember_and_clear_remove_memory_copy(self):
        self.host.dispatch('connection-credentials', {'id':'server','secrets':{'password':'first'}})
        self.host.dispatch('connection-credentials', {'id':'server','remember':True,'secrets':{'password':'second'}})
        self.assertNotIn('server', self.host.secrets)
        self.desktop.connection_credentials.assert_called_once()
        with self.assertRaises(ValueError):
            self.host.dispatch('connection-credentials', {'id':'server','secrets':{'clear':'true'}})

    def test_privileged_or_unknown_actions_are_not_forwarded(self):
        for action in ('exec', 'serve', 'management-stream', 'update-apply', 'update-prepare', 'install-update'):
            with self.assertRaises(ValueError):
                self.host.dispatch(action, {})
        self.desktop.start.assert_not_called()
        with self.assertRaises(ValueError):
            self.host.dispatch('server-setup', {'id':'server','action':'install'})

    def test_only_snapshot_urls_and_saved_local_paths_can_be_opened(self):
        self.assertEqual(self.host.dispatch('open','http://127.0.0.1:8787/')['kind'], 'url')
        self.assertEqual(self.host.dispatch('open','data')['value'], str(self.desktop.data_dir))
        for value in ('file:///C:/Windows/System32/cmd.exe','javascript:alert(1)','https://attacker.invalid'):
            with self.assertRaises(ValueError):
                self.host.dispatch('open',value)
        with self.assertRaises(ValueError):
            self.host.dispatch('copy','http://localhost:8787/')

    def test_language_persists_and_update_cannot_select_electron_archive(self):
        self.host.dispatch('set-language','en')
        self.assertEqual(json.loads((self.root/'desktop/language.json').read_text())['language'],'en')
        self.assertEqual(json.loads((self.desktop.data_dir/'ui-language.json').read_text())['language'],'en')
        self.assertEqual(self.host.dispatch('check-update')['state'],'unsupported')
        with self.assertRaises(ValueError):
            self.host.dispatch('set-language','invalid')

    def test_account_login_url_requires_current_enrollment_and_exact_https_host(self):
        self.desktop.accounts.return_value = {'enrollment':{'phase':'waiting','authUrl':'https://auth.openai.com/login'}}
        self.assertEqual(self.host.dispatch('accounts',{'action':'openLogin'})['url'],'https://auth.openai.com/login')
        self.desktop.accounts.return_value['enrollment']['authUrl'] = 'https://auth.openai.com.attacker.invalid/'
        with self.assertRaises(ValueError):
            self.host.dispatch('accounts',{'action':'openLogin'})

    def test_tailscale_does_not_accept_an_unconfigured_connection(self):
        with self.assertRaises(ValueError):
            self.host.dispatch('tailscale-authorize', {'id':'server'})
        self.desktop.tailscale_setup.assert_not_called()

    def test_switch_data_checks_local_owner_before_changing(self):
        self.desktop.close_local.side_effect = ValueError('busy')
        with self.assertRaisesRegex(ValueError,'busy'):
            self.host.dispatch('set-data-dir',str(self.root/'new'))
        self.assertIs(self.host.desktop,self.desktop)
        self.desktop.close_local.side_effect = None


class NativeUrlTests(unittest.TestCase):
    def test_login_and_tailnet_urls_fail_closed(self):
        for value in ('http://login.tailscale.com/', 'https://login.tailscale.com:444/',
                      'https://user@login.tailscale.com/', 'https://login.tailscale.com.evil/', None):
            with self.assertRaises(ValueError):
                checked_url(value, {'login.tailscale.com'})

    def test_real_private_stream_reads_unicode_and_remains_alive_after_rejection(self):
        (ROOT/'.tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as directory:
            root = Path(directory)
            request = '\n'.join(json.dumps(v) for v in [
                {'action':'set-language','payload':'zh-CN'},
                {'action':'exec','payload':{'command':'should-not-run'}},
                {'action':'language'}, {'action':'check-update'}])+'\n'
            result = subprocess.run([sys.executable,'-B',str(ROOT/'desktop.py'),'tauri-stream','--data-dir',str(root/'数据'),
                '--desktop-dir',str(root/'桌面')],input=request,text=True,encoding='utf-8',capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(replies),4)
            self.assertTrue(replies[0]['ok'])
            self.assertFalse(replies[1]['ok'])
            self.assertEqual(replies[2]['result'],'zh-CN')
            self.assertEqual(replies[3]['result']['state'],'unsupported')


if __name__ == '__main__':
    unittest.main()
