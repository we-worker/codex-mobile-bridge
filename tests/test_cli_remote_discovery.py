import unittest
from pathlib import Path
from unittest.mock import patch

from bridge.clients.codex.remote import AppHosts, RemoteStore, RemoteUnavailable, ssh_command


class RemoteDiscoveryTests(unittest.TestCase):
    def test_managed_aliases_do_not_require_project_references(self):
        hosts = AppHosts(Path('/unused'))
        hosts.state = lambda: {'remote-projects': [{'hostId': 'remote:project'}],
                               'thread-project-membership-host-ids': {'thread': 'remote:member'},
                               'codex-managed-remote-connections': [
            {'hostId': 'remote:one', 'alias': 'saved-host', 'displayName': 'Saved'},
            {'hostId': 'remote:project', 'alias': 'project-host'},
            {'hostId': 'remote:member', 'alias': 'member-host'},
            {'hostId': 'remote:bad', 'alias': '-bad'},
            {'hostId': 'remote:spaces', 'alias': 'host ; command'},
        ]}
        self.assertEqual(set(hosts.hosts()), {'remote:one', 'remote:project', 'remote:member'})
        self.assertEqual(set(hosts.lifecycle_hosts()), {'remote:project', 'remote:member'})

    def test_ssh_login_shell_keeps_strict_options_and_alias_as_argument(self):
        command = ssh_command('saved-host')
        self.assertEqual(command[-2], 'saved-host')
        self.assertIn('"$SHELL" -lc', command[-1])
        self.assertIn('python3 -', command[-1])
        self.assertIn('StrictHostKeyChecking=yes', command)
        self.assertIn('BatchMode=yes', command)
        for alias in ('-bad', 'bad host', 'bad\ncommand', ''):
            with self.assertRaises(RemoteUnavailable):
                ssh_command(alias)

    def test_remote_diagnostics_carries_home_provenance_without_paths(self):
        store = RemoteStore('saved-host')
        with patch('bridge.clients.codex.remote.ssh_read', return_value={'status': 'ok'}) as read:
            result = store.discovery_diagnostics('thread-id')
        self.assertEqual(result, {'status': 'ok'})
        source = read.call_args.args[1]
        self.assertIn('discovery_diagnostics', source)
        self.assertIn('result["homeSource"] = home_source', source)
        self.assertNotIn('saved-host', source)


if __name__ == '__main__':
    unittest.main()
