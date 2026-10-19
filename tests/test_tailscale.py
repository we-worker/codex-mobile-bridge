import io
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bridge.features.network import access, tailscale
from bridge.features.notifications.addresses import entry_urls
from bridge.app.desktop import Desktop

ROOT = Path(__file__).resolve().parents[1]
ENTRY = {**access.DEFAULTS, 'id': 'ts', 'name': '', 'enabled': True, 'accessMode': 'tailscale',
         'publicUrl': 'https://computer.example.ts.net', 'tailscaleNodeId': 'n123'}
EMBEDDED = {**ENTRY, 'publicUrl': '', 'tailscaleNodeId': '', 'tailscaleRuntime': 'embedded',
            'tailscaleHostname': 'embedded-bridge', 'tailscaleAuthMode': 'interactive'}
STATUS = {'Version': '1.102.4', 'BackendState': 'Running',
          'Self': {'DNSName': 'computer.example.ts.net.', 'ID': 'n123'}}


class TailscaleTests(unittest.TestCase):
    def test_detect_is_read_only_and_returns_no_peer_or_account_details(self):
        raw = {**STATUS, 'Peer': {'secret': 'do not return'}, 'User': {'email': 'private@example.test'}}
        result = subprocess.CompletedProcess([], 0, json.dumps(raw), '')
        with patch.object(tailscale, 'executable', return_value='/tailscale'), patch.object(tailscale.subprocess, 'run', return_value=result) as run:
            state = tailscale.inspect(ENTRY)
        self.assertEqual(state['url'], ENTRY['publicUrl'])
        self.assertEqual(state['nodeId'], 'n123')
        self.assertNotIn('Peer', state)
        self.assertNotIn('User', state)
        self.assertEqual(run.call_args.args[0], ['/tailscale', 'status', '--json'])

    def test_missing_login_expiry_and_changed_identity(self):
        with patch.object(tailscale, 'executable', return_value=''):
            self.assertEqual(tailscale.inspect(ENTRY)['state'], 'missing')
        with patch.object(tailscale, 'executable', return_value='/tailscale'), patch.object(tailscale, 'command_json') as read:
            read.return_value = {**STATUS, 'BackendState': 'NeedsLogin', 'AuthURL': 'https://evil.test/login'}
            self.assertEqual(tailscale.inspect(ENTRY)['authUrl'], '')
            read.return_value = {**STATUS, 'Self': {**STATUS['Self'], 'KeyExpired': True}}
            with self.assertRaisesRegex(ValueError, '过期'):
                tailscale.inspect(ENTRY)
            read.return_value = {**STATUS, 'Self': {**STATUS['Self'], 'ID': 'nOther'}}
            with self.assertRaisesRegex(ValueError, '变化'):
                tailscale.require_identity(ENTRY)

    def test_validation_rejects_foreign_urls_bad_modes_ports_and_duplicate_entries(self):
        for change in ({'publicUrl': 'https://evil.test'}, {'publicUrl': 'https://example.ts.net.evil.test'},
                       {'tailscaleMode': 'reset'}, {'tailscalePort': True}, {'tailscalePort': 22},
                       {'tailscalePort': 8443}, {'tailscaleNodeId': 'one\ntwo'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                access.validate_connections({'connections': [{**ENTRY, **change}]})
        with self.assertRaisesRegex(ValueError, '一个 Tailscale'):
            access.validate_connections({'connections': [ENTRY, {**ENTRY, 'id': 'second', 'publicUrl': 'https://other.example.ts.net'}]})
        self.assertEqual(access.public_urls({'connections': [{**ENTRY, 'publicUrl': ''}]}), [])
        self.assertEqual(access.validate_connections({'connections': [{**ENTRY, 'publicUrl': '', 'tailscaleNodeId': ''}]})[0]['publicUrl'], '')

    def test_authorization_urls_are_exact_https_login_origin(self):
        good = 'https://login.tailscale.com/f/funnel?node=n123'
        self.assertEqual(tailscale.authorization_url(good), good)
        for bad in ('http://login.tailscale.com/a', 'https://login.tailscale.com.evil/a',
                    'https://user:pass@login.tailscale.com/a', 'https://login.tailscale.com:8443/a',
                    'https://login.tailscale.com/a\n', 'javascript:alert(1)'):
            self.assertEqual(tailscale.authorization_url(bad), '')

    def test_existing_foreground_and_background_ports_are_not_overwritten(self):
        for config in ({'TCP': {'443': {'HTTPS': True}}},
                       {'Foreground': {'another-owner': {'TCP': {'443': {'HTTPS': True}}}}},
                       {'Web': {'other.example.ts.net:443': {'Handlers': {'/': {'Text': 'hello'}}}}}):
            with self.subTest(config=config), tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
                tunnel = tailscale.TailscaleTunnel(ENTRY, 8787, folder)
                with patch.object(tailscale, 'require_identity'), patch.object(tailscale, 'executable', return_value='/tailscale'), \
                     patch.object(tailscale, 'command_json', return_value=config), patch.object(tailscale.subprocess, 'Popen') as spawn:
                    tunnel.start()
                    tunnel.thread.join(2)
                    self.assertFalse(tunnel.thread.is_alive())
                    spawn.assert_not_called()
                    self.assertEqual(tunnel.last_status['state'], 'blocked')
                    tunnel.close()
        self.assertFalse(tailscale.port_in_use({'TCP': {'8443': {'HTTPS': True}}}, 443))

    def test_foreground_process_and_only_owned_process_are_stopped(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            # Actual child lifecycle, no Tailscale/network/account changes.
            helper = Path(folder)/'client.py'
            helper.write_text('import time\nprint("Available on the internet:", flush=True)\ntime.sleep(60)\n')
            import sys
            launch = subprocess.Popen
            calls = []
            def spawn(argv, **kwargs):
                calls.append(argv)
                return launch([sys.executable, '-B', str(helper)], **kwargs)
            tunnel = tailscale.TailscaleTunnel(ENTRY, 8787, folder)
            connected = threading.Event()
            original = tunnel.status
            def status(state, message, auth_url=''):
                original(state, message, auth_url)
                if state == 'connected':
                    connected.set()
            tunnel.status = status
            with patch.object(tailscale, 'require_identity'), patch.object(tailscale, 'executable', return_value='/tailscale'), \
                 patch.object(tailscale, 'command_json', return_value={}), patch.object(tailscale.subprocess, 'Popen', side_effect=spawn):
                try:
                    tunnel.start()
                    self.assertTrue(connected.wait(3))
                    process = tunnel.process
                finally:
                    tunnel.close()
            self.assertFalse(tunnel.thread.is_alive())
            self.assertIsNotNone(process.poll())
            self.assertEqual(calls, [['/tailscale', 'funnel', '--https=443', 'http://127.0.0.1:8787']])
            self.assertEqual(tunnel.last_status['state'], 'stopped')

    def test_credentials_stay_required_and_origin_is_removed_on_disable(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            desktop = Desktop(folder)
            desktop.status = lambda: {'running': False}
            value = desktop.snapshot()
            value['preferences'].update(codexHome=folder, connections=[ENTRY])
            value['auth']['mode'] = 'none'
            with self.assertRaisesRegex(ValueError, '登录验证'):
                desktop.save(value)
            value['auth']['mode'] = 'password'
            desktop.save(value)
            self.assertIn(ENTRY['publicUrl'], desktop.config()['origins'])
            with patch.object(tailscale, 'inspect', return_value={'state': 'ready', 'url': ENTRY['publicUrl']}):
                self.assertEqual(desktop.tailscale_setup({'id': 'ts'})['state'], 'ready')
            value['preferences']['connections'] = [{**ENTRY, 'enabled': False}]
            desktop.save(value)
            self.assertNotIn(ENTRY['publicUrl'], desktop.config()['origins'])

    def test_address_notifications_only_offer_connected_tailscale_entry(self):
        preferences = {'connections': [ENTRY]}
        self.assertEqual(entry_urls(preferences, [], '', {'ts': {'state': 'connecting'}}), [])
        self.assertEqual(entry_urls(preferences, [], '', {'ts': {'state': 'connected'}}), [ENTRY['publicUrl']])
        live = 'https://actual-network.example.ts.net:8443'
        self.assertEqual(entry_urls(preferences, [], '',
                                    {'ts': {'state': 'connected', 'url': live}}), [live])

    def test_embedded_status_requires_the_current_gateway_runtime(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            directory = Path(folder)
            helper = directory/'codex-tsnet'
            helper.write_text('fixture')
            from bridge.features.notifications.channels import write_json
            write_json(tailscale.status_path(directory, EMBEDDED), {
                'pid': 41, 'state': 'connected', 'url': ENTRY['publicUrl'],
                'nodeId': 'n123', 'instanceId': 'gateway-instance',
            })
            with patch.object(tailscale, 'embedded_executable', return_value=str(helper)):
                current = tailscale.inspect(EMBEDDED, directory, 41, 'gateway-instance')
                stale = tailscale.inspect(EMBEDDED, directory, 42)
                other_instance = tailscale.inspect(EMBEDDED, directory, 41, 'another-instance')
                desktop = Desktop(directory)
                desktop.preferences = lambda: {
                    'connections': [ENTRY | {'tailscaleRuntime': 'embedded'}],
                    'lan': False, 'port': 8787,
                }
                desktop.status = lambda: {'running': False}
                stopped = desktop.tailscale_setup({'id': 'ts'})
            self.assertEqual(current['state'], 'ready')
            self.assertEqual(current['url'], ENTRY['publicUrl'])
            self.assertEqual(stale['state'], 'stopped')
            self.assertEqual(other_instance['state'], 'stopped')
            self.assertEqual(stopped['state'], 'stopped')

    def test_saved_embedded_address_is_not_a_persistent_trusted_origin(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            desktop = Desktop(folder)
            desktop.status = lambda: {'running': False}
            value = desktop.snapshot()
            value['preferences'].update(codexHome=folder, connections=[ENTRY | {
                'tailscaleRuntime': 'embedded',
            }])
            desktop.save(value)
            config = desktop.config()
            self.assertNotIn(ENTRY['publicUrl'], config['origins'])
            self.assertEqual(config['publicUrl'], '')
            self.assertNotIn(ENTRY['publicUrl'], desktop.snapshot()['urls'])

    def test_embedded_helper_receives_auth_key_only_on_private_stdin(self):
        secret = 'tskey-auth-fixture-private'
        live = 'https://embedded-bridge.example.ts.net'
        origins = []
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            process = MagicMock()
            process.pid = 123
            process.poll.return_value = 0
            entry = {**EMBEDDED, 'tailscaleAuthMode': 'authKey'}
            tunnel = tailscale.TailscaleTunnel(
                entry, 8787, folder, {'authKey': secret},
                allow_origin=lambda entry_id, origin, node_id:
                    origins.append((entry_id, origin, node_id)),
                instance_id='0123456789abcdef0123456789abcdef')
            class Output:
                def __iter__(self):
                    yield json.dumps({
                        'state': 'resolved', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                    }) + '\n'
                    yield json.dumps({
                        'state': 'listening', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                    }) + '\n'
                    yield json.dumps({
                        'state': 'connected', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                        'diagnostic': {
                            'backendState': 'Running',
                            'healthCount': 0,
                            'onlinePeers': 3,
                            'funnelCapability': True,
                            'httpsCapability': True,
                            'funnelPortsCapability': True,
                            'funnelRegistered': True,
                        },
                    }) + '\n'
                    tunnel.stopped.set()
                def close(self):
                    pass
            process.stdout = Output()
            with patch.object(tailscale, 'embedded_executable', return_value='/fixture/codex-tsnet'), \
                 patch.object(tailscale.subprocess, 'Popen', return_value=process) as spawn:
                tunnel.start()
                tunnel.thread.join(3)
            self.assertFalse(tunnel.thread.is_alive())
            argv = spawn.call_args.args[0]
            self.assertNotIn(secret, ' '.join(argv))
            self.assertIn(secret, process.stdin.write.call_args.args[0])
            persisted = (Path(folder)/'ssh-status-ts.json').read_text(encoding='utf-8')
            self.assertNotIn(secret, persisted)
            self.assertIn('"funnelRegistered": true', persisted)
            self.assertIn(('ts', live, 'n123'), origins)
            self.assertEqual(tunnel.last_status['state'], 'connected')

    def test_embedded_tailnet_listener_is_not_reported_as_publicly_connected(self):
        live = 'https://embedded-bridge.example.ts.net'
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            process = MagicMock()
            process.pid = 123
            process.poll.return_value = 0
            tunnel = tailscale.TailscaleTunnel(
                EMBEDDED, 8787, folder, {},
                instance_id='0123456789abcdef0123456789abcdef')

            class Output:
                def __iter__(self):
                    yield json.dumps({
                        'state': 'resolved', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                    }) + '\n'
                    yield json.dumps({
                        'state': 'listening', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                        'message': '正在验证公网 Funnel。',
                    }) + '\n'
                    yield json.dumps({
                        'state': 'publishing', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                        'message': '正在等待公网 DNS。',
                    }) + '\n'
                    tunnel.stopped.set()

                def close(self):
                    pass

            process.stdout = Output()
            with patch.object(tailscale, 'embedded_executable', return_value='/fixture/codex-tsnet'), \
                 patch.object(tailscale.subprocess, 'Popen', return_value=process):
                tunnel.start()
                tunnel.thread.join(3)
            self.assertFalse(tunnel.thread.is_alive())
            self.assertNotEqual(tunnel.last_status['state'], 'connected')
            self.assertIn('公网', tunnel.last_status['message'])

    def test_embedded_retry_withdraws_stale_origin_until_next_registration(self):
        live = 'https://embedded-bridge.example.ts.net'
        origins = []
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            process = MagicMock()
            process.pid = 123
            process.poll.return_value = 0
            tunnel = tailscale.TailscaleTunnel(
                EMBEDDED, 8787, folder, {},
                allow_origin=lambda entry_id, origin, node_id:
                    origins.append((entry_id, origin, node_id)),
                instance_id='0123456789abcdef0123456789abcdef')

            class Output:
                def __iter__(self):
                    yield json.dumps({
                        'state': 'resolved', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                    }) + '\n'
                    yield json.dumps({
                        'state': 'connected', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                    }) + '\n'
                    yield json.dumps({
                        'state': 'retrying', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                        'message': '公网入口在运行中失效，正在重新登记。',
                    }) + '\n'
                    self.cleared_on_retry = origins[-1] == ('ts', '', '')
                    tunnel.stopped.set()

                def close(self):
                    pass

            output = Output()
            process.stdout = output
            with patch.object(tailscale, 'embedded_executable', return_value='/fixture/codex-tsnet'), \
                 patch.object(tailscale.subprocess, 'Popen', return_value=process):
                tunnel.start()
                tunnel.thread.join(3)
            self.assertFalse(tunnel.thread.is_alive())
            self.assertTrue(output.cleared_on_retry)
            self.assertEqual(tunnel.last_status['state'], 'retrying')

    def test_embedded_resolved_origin_is_published_before_listening(self):
        live = 'https://embedded-bridge.example.ts.net'
        origins = []
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            process = MagicMock()
            process.pid = 123
            process.poll.return_value = 0
            tunnel = tailscale.TailscaleTunnel(
                EMBEDDED, 8787, folder, {},
                allow_origin=lambda entry_id, origin, node_id:
                    origins.append((entry_id, origin, node_id)),
                instance_id='0123456789abcdef0123456789abcdef')

            class Output:
                def __iter__(self):
                    yield json.dumps({
                        'state': 'resolved', 'url': live, 'nodeId': 'n123',
                        'instanceId': '0123456789abcdef0123456789abcdef',
                    }) + '\n'
                    self.published_before_listening = ('ts', live, 'n123') in origins
                    yield json.dumps({
                        'state': 'failed', 'code': 'verification_failed',
                    }) + '\n'
                    tunnel.stopped.set()

                def close(self):
                    pass

            output = Output()
            process.stdout = output
            with patch.object(tailscale, 'embedded_executable', return_value='/fixture/codex-tsnet'), \
                 patch.object(tailscale.subprocess, 'Popen', return_value=process):
                tunnel.start()
                tunnel.thread.join(3)
            self.assertTrue(output.published_before_listening)
            self.assertEqual(tunnel.last_status['state'], 'failed')
            self.assertEqual(origins[-1], ('ts', '', ''))

    def test_embedded_helper_reports_network_timeout_without_staying_in_starting_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            process = MagicMock()
            process.pid = 123
            process.poll.return_value = 0
            entry = {**EMBEDDED, 'tailscaleAuthMode': 'authKey'}
            tunnel = tailscale.TailscaleTunnel(entry, 8787, folder, {'authKey': 'fixture'})

            class Output:
                def __iter__(self):
                    yield json.dumps({
                        'state': 'starting',
                        'message': '正在探测 Tailscale 控制面网络…',
                    }) + '\n'
                    yield json.dumps({'state': 'failed', 'code': 'network_timeout'}) + '\n'
                    tunnel.stopped.set()

                def close(self):
                    pass

            process.stdout = Output()
            with patch.object(tailscale, 'embedded_executable', return_value='/fixture/codex-tsnet'), \
                 patch.object(tailscale.subprocess, 'Popen', return_value=process):
                tunnel.start()
                tunnel.thread.join(3)
            self.assertFalse(tunnel.thread.is_alive())
            self.assertEqual(tunnel.last_status['state'], 'failed')
            self.assertEqual(tunnel.last_status['message'],
                             tailscale.EMBEDDED_ERRORS['network_timeout'])

    def test_embedded_configuration_error_stops_without_automatic_restart(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            process = MagicMock()
            process.pid = 123
            process.poll.return_value = 0
            entry = {**EMBEDDED, 'tailscaleAuthMode': 'authKey'}
            tunnel = tailscale.TailscaleTunnel(entry, 8787, folder, {})

            class Output:
                def __iter__(self):
                    yield json.dumps({'state': 'failed', 'code': 'https_unavailable'}) + '\n'

                def close(self):
                    pass

            process.stdout = Output()
            with patch.object(tailscale, 'embedded_executable', return_value='/fixture/codex-tsnet'), \
                 patch.object(tailscale.subprocess, 'Popen', return_value=process) as spawn:
                tunnel.start()
                tunnel.thread.join(2)
            self.assertFalse(tunnel.thread.is_alive())
            spawn.assert_called_once()
            self.assertEqual(tunnel.last_status['state'], 'failed')
            self.assertEqual(tunnel.last_status['message'],
                             tailscale.EMBEDDED_ERRORS['https_unavailable'])

    def test_embedded_helper_requires_the_current_gateway_instance(self):
        live = 'https://embedded-bridge.example.ts.net'
        origins = []
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            process = MagicMock()
            process.pid = 123
            process.poll.return_value = 0
            tunnel = tailscale.TailscaleTunnel(
                EMBEDDED, 8787, folder, {},
                allow_origin=lambda entry_id, origin, node_id:
                    origins.append((entry_id, origin, node_id)),
                instance_id='0123456789abcdef0123456789abcdef')
            class Output:
                def __iter__(self):
                    yield json.dumps({
                        'state': 'listening', 'url': live, 'nodeId': 'n123',
                        'instanceId': 'ffffffffffffffffffffffffffffffff',
                    }) + '\n'
                    tunnel.stopped.set()
                def close(self):
                    pass
            process.stdout = Output()
            with patch.object(tailscale, 'embedded_executable', return_value='/fixture/codex-tsnet'), \
                 patch.object(tailscale.subprocess, 'Popen', return_value=process):
                tunnel.start()
                tunnel.thread.join(3)
            self.assertFalse(tunnel.thread.is_alive())
            self.assertNotIn(('ts', live, 'n123'), origins)
            self.assertNotEqual((tunnel.last_status or {}).get('state'), 'connected')

    def test_embedded_origin_is_published_only_after_exact_live_identity(self):
        import run
        old = ENTRY['publicUrl']
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            config_path = Path(folder)/'config.json'
            config_path.write_text(json.dumps({
                'auth': {'mode': 'password'}, 'origins': [old],
            }))
            main, private = MagicMock(), MagicMock()
            main.origins, main.hosts, main.secure_hosts = set(), set(), set()
            private.server_address = ('127.0.0.1', 45678)
            with patch.object(run.sys, 'argv', ['run.py', '--config', str(config_path)]), \
                 patch.object(run.sys, 'stdout', MagicMock()), patch.object(run, 'Bridge'), \
                 patch.object(run, 'Notifications'), patch.object(run, 'AddressNotifications'), \
                 patch.object(run, 'GatewayControl'), patch.object(run.signal, 'signal'), \
                 patch.object(run, 'GatewayServer', side_effect=[main, private]) as listeners, \
                 patch('bridge.features.network.discovery.ConnectionDiscovery'), \
                 patch('bridge.features.network.shared_relay.start', return_value=None), \
                 patch.object(tailscale, 'TailscaleTunnel') as tunnel:
                run.main(connections=[{**ENTRY, 'tailscaleRuntime': 'embedded'}])
            runtime_config = next(row.args[2] for row in listeners.call_args_list)
            self.assertNotIn(old, runtime_config['origins'])
            self.assertEqual(runtime_config['publicUrl'], '')
            allow = tunnel.call_args.kwargs['allow_origin']
            live = 'https://actual-network.example.ts.net'
            allow('ts', live, 'n123')
            self.assertIn(live, main.origins)
            self.assertIn('actual-network.example.ts.net', main.hosts)
            self.assertIn('actual-network.example.ts.net', main.secure_hosts)
            self.assertEqual(runtime_config['publicUrl'], live)
            allow('ts', 'https://actual-network.example.ts.net.evil.test', 'n123')
            self.assertNotIn(live, main.origins)
            self.assertNotIn('actual-network.example.ts.net', main.hosts)
            self.assertEqual(runtime_config['publicUrl'], '')
            allow('ts', live, 'n123')
            allow('ts', '', '')
            self.assertNotIn(live, main.origins)

    def test_fixed_entry_uses_verified_owner_when_loopback_port_is_shadowed(self):
        preferences = {**ENTRY, 'port': 8787}
        with patch.object(access, 'read_auth', return_value={'instanceId': 'actual'}) as read:
            access.check_entry(preferences, instance_id='actual')
            self.assertEqual(read.call_args.args, (ENTRY['publicUrl'],))
        with patch.object(access, 'read_auth', return_value={'instanceId': 'other'}), self.assertRaisesRegex(ValueError, '当前网关'):
            access.check_entry(preferences, instance_id='actual')

    def test_runtime_uses_private_listener_and_closes_owned_entry(self):
        import run
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            config = Path(folder)/'config.json'
            config.write_text(json.dumps({'auth': {'mode': 'password'}, 'origins': []}))
            main, private = MagicMock(), MagicMock()
            private.server_address = ('127.0.0.1', 45678)
            with patch.object(run.sys, 'argv', ['run.py', '--config', str(config)]), \
                 patch.object(run.sys, 'stdout', MagicMock()), patch.object(run, 'Bridge'), \
                 patch.object(run, 'Notifications'), patch.object(run, 'AddressNotifications'), \
                 patch.object(run, 'GatewayControl'), patch.object(run.signal, 'signal'), \
                 patch.object(run, 'GatewayServer', side_effect=[main, private]) as listeners, \
                 patch('bridge.features.network.discovery.ConnectionDiscovery') as discovery, \
                 patch('bridge.features.network.shared_relay.start', return_value=None), \
                 patch.object(tailscale, 'TailscaleTunnel') as tunnel:
                run.main(connections=[ENTRY])
            self.assertEqual(listeners.call_args_list[1].args[0], ('127.0.0.1', 0))
            self.assertIs(listeners.call_args_list[1].kwargs['shared'], main)
            self.assertEqual(tunnel.call_args.args[1], 45678)
            self.assertIs(private.connection_discovery, discovery.return_value)
            self.assertIs(private.notifications, main.notifications)
            tunnel.return_value.start.assert_called_once()
            tunnel.return_value.close.assert_called_once()
            private.shutdown.assert_called_once()
            private.server_close.assert_called_once()

    def test_shadowed_status_requires_a_live_private_control_response(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            desktop = Desktop(folder)
            record = {'pid': 42, 'instanceId': 'owner', 'notificationManagement': True}
            with patch('bridge.app.desktop.http.client.HTTPConnection', side_effect=OSError()), \
                 patch('bridge.app.desktop.read_record', return_value=record), \
                 patch('bridge.app.desktop.request_pairing', return_value={'states': {}}) as control:
                state = desktop.status()
                self.assertTrue(state['running'])
                self.assertEqual(state['instanceId'], 'owner')
                control.side_effect = ValueError('not alive')
                self.assertFalse(desktop.status()['running'])


if __name__ == '__main__':
    unittest.main()
