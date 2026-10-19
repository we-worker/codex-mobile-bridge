"""Current-turn selection in the installed gateway's loopback model fixture."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from packaged_cli_e2e import GatewayHTTP, MockHandler, ready_clients, wait_for_history_marker


class FixtureTurnSelectionTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.handler = MockHandler.__new__(MockHandler)
        self.handler.server = SimpleNamespace(
            markers={'deny': Path('/tmp/deny'), 'allow': Path('/tmp/allow')},
            record=lambda **row: self.calls.append(row))

    def test_codex_uses_latest_user_not_seed_history(self):
        events = self.handler._codex_events({'model': 'fixture', 'input': [
            {'role': 'user', 'content': 'CODEX_SEED'},
            {'role': 'assistant', 'content': 'CODEX_SEED_REPLY'},
            {'role': 'user', 'content': 'CODEX_HTTP_SEND'},
        ]})
        self.assertIn('CODEX_HTTP_REPLY', str(events))
        self.assertNotIn('CODEX_SEED_REPLY', str(events))

    def test_claude_uses_latest_user_before_trailing_system(self):
        events = self.handler._claude_events({'model': 'fixture', 'messages': [
            {'role': 'user', 'content': 'CLAUDE_SEED'},
            {'role': 'assistant', 'content': 'CLAUDE_SEED_REPLY'},
            {'role': 'user', 'content': 'CLAUDE_HTTP_SEND'},
            {'role': 'system', 'content': 'Native context suffix'},
        ]})
        self.assertIn('CLAUDE_HTTP_REPLY', str(events))
        self.assertNotIn('CLAUDE_SEED_REPLY', str(events))

    def test_claude_approval_matches_latest_tool_result_id(self):
        events = self.handler._claude_events({'model': 'fixture', 'messages': [
            {'role': 'user', 'content': 'CLAUDE_SEED'},
            {'role': 'user', 'content': 'REQUEST_DENY_WRITE'},
            {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'toolu_deny_fixture'}]},
            {'role': 'user', 'content': [{'type': 'tool_result',
                'tool_use_id': 'toolu_deny_fixture', 'is_error': True}]},
            {'role': 'system', 'content': 'Native context suffix'},
        ]})
        self.assertIn('CLAUDE_DENIED_REPLY', str(events))
        self.assertNotIn('toolu_allow_fixture', str(self.calls))
        self.assertEqual(self.calls[-1]['toolId'], 'toolu_deny_fixture')
        self.assertTrue(self.calls[-1]['denied'])

    def test_claude_rejects_unrelated_tool_result_id(self):
        with self.assertRaisesRegex(ValueError, 'Unknown tool result'):
            self.handler._claude_events({'model': 'fixture', 'messages': [
                {'role': 'user', 'content': 'CLAUDE_SEED'},
                {'role': 'user', 'content': [{'type': 'tool_result',
                    'tool_use_id': 'toolu_unrelated', 'is_error': True}]},
            ]})


class HttpTraceTests(unittest.TestCase):
    def test_records_route_status_and_closes_connection(self):
        connection = Mock()
        connection.getresponse.return_value = SimpleNamespace(
            status=200, read=lambda: b'{"ok":true}', getheader=lambda _: None)
        with patch('packaged_cli_e2e.http.client.HTTPConnection', return_value=connection) as connect:
            client = GatewayHTTP(12345)
            self.assertEqual(client.request('GET', '/api/clients?detail=1')[0], 200)
        self.assertEqual(connect.call_args.kwargs['timeout'], 10)
        self.assertEqual(client.trace[0]['method'], 'GET')
        self.assertEqual(client.trace[0]['route'], '/api/clients')
        self.assertEqual(client.trace[0]['status'], 200)
        self.assertGreaterEqual(client.trace[0]['durationMs'], 0)
        connection.close.assert_called_once()

    def test_timeout_identifies_route_and_closes_connection(self):
        connection = Mock()
        connection.getresponse.side_effect = TimeoutError('timed out')
        with patch('packaged_cli_e2e.http.client.HTTPConnection', return_value=connection) as connect:
            client = GatewayHTTP(12345)
            with self.assertRaisesRegex(TimeoutError, 'GET /api/clients timed out'):
                client.request('GET', '/api/clients')
        self.assertEqual(connect.call_args.kwargs['timeout'], 10)
        self.assertEqual(client.trace[0]['status'], 'timeout')
        self.assertEqual(client.trace[0]['route'], '/api/clients')
        connection.close.assert_called_once()

    def test_client_write_uses_ui_lifecycle_deadline_without_retry(self):
        connection = Mock()
        connection.getresponse.side_effect = TimeoutError('timed out')
        with patch('packaged_cli_e2e.http.client.HTTPConnection', return_value=connection) as connect:
            client = GatewayHTTP(12345)
            with self.assertRaisesRegex(TimeoutError, 'POST /api/clients timed out'):
                client.request('POST', '/api/clients', {'provider': 'claude', 'enabled': True})
        self.assertEqual(connect.call_args.kwargs['timeout'], 45)
        self.assertEqual(connection.request.call_count, 1)
        self.assertEqual(client.trace[0]['status'], 'timeout')

    def test_pending_client_list_is_not_treated_as_ready(self):
        rows = iter([
            {'pending': True, 'clients': [{'id': 'claude', 'cliAuthReady': True}]},
            {'pending': False, 'clients': [{'id': 'claude', 'cliAuthReady': False}]},
        ])
        client = SimpleNamespace(trace=[], checked=lambda method, route: (
            client.trace.append({'durationMs': 4}) or next(rows)))
        self.assertFalse(ready_clients(client)[0]['cliAuthReady'])
        self.assertEqual(len(client.trace), 2)

    def test_ready_client_list_over_ui_deadline_fails(self):
        client = SimpleNamespace(trace=[], checked=lambda method, route: (
            client.trace.append({'durationMs': 10_000}) or
            {'pending': False, 'clients': [{'id': 'claude'}]}))
        with self.assertRaisesRegex(AssertionError, 'UI status deadline'):
            ready_clients(client)

    def test_missing_pending_contract_fails(self):
        client = SimpleNamespace(trace=[], checked=lambda method, route: (
            client.trace.append({'durationMs': 4}) or {'clients': []}))
        with self.assertRaisesRegex(AssertionError, 'pending state'):
            ready_clients(client)

    def test_failed_refresh_does_not_accept_old_complete_snapshot(self):
        client = SimpleNamespace(trace=[], checked=lambda method, route: (
            client.trace.append({'durationMs': 4}) or
            {'pending': False, 'refreshError': 'scan failed',
             'clients': [{'id': 'claude', 'cliAuthReady': True}]}))
        with self.assertRaisesRegex(AssertionError, 'refresh failed'):
            ready_clients(client)

    def test_ready_after_discovery_window_still_fails(self):
        client = SimpleNamespace(trace=[], checked=lambda method, route: (
            client.trace.append({'durationMs': 4}) or {'pending': False, 'clients': []}))
        with patch('packaged_cli_e2e.time.monotonic', side_effect=[0, 0, 46]):
            with self.assertRaisesRegex(AssertionError, '45-second discovery window'):
                ready_clients(client)


class RestartHistoryTests(unittest.TestCase):
    def test_empty_initial_history_can_fill_without_another_write(self):
        request = Mock(side_effect=[
            (200, {'loadingHistory': True, 'turns': []}, None),
            (200, {'loadingHistory': False, 'turns': [{'text': 'CODEX_HTTP_REPLY'}]}, None),
        ])
        state = wait_for_history_marker(SimpleNamespace(request=request), '/api/sessions/id',
                                        'CODEX_HTTP_REPLY', 'Codex history', seconds=1)
        self.assertFalse(state['loadingHistory'])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args, ('GET', '/api/sessions/id'))

    def test_missing_history_still_fails(self):
        request = Mock(return_value=(200, {'loadingHistory': False, 'turns': []}, None))
        with self.assertRaisesRegex(AssertionError, 'Codex history timed out'):
            wait_for_history_marker(SimpleNamespace(request=request), '/api/sessions/id',
                                    'CODEX_HTTP_REPLY', 'Codex history', seconds=.01)
        self.assertGreaterEqual(request.call_count, 1)

    def test_http_error_fails_immediately(self):
        request = Mock(return_value=(503, {'error': 'unavailable'}, None))
        with self.assertRaisesRegex(RuntimeError, 'GET /api/sessions/id returned HTTP 503'):
            wait_for_history_marker(SimpleNamespace(request=request), '/api/sessions/id',
                                    'CODEX_HTTP_REPLY', 'Codex history', seconds=1)
        self.assertEqual(request.call_count, 1)

    def test_transport_timeout_fails_immediately(self):
        request = Mock(side_effect=TimeoutError('read timed out'))
        with self.assertRaisesRegex(RuntimeError, 'GET /api/sessions/id failed'):
            wait_for_history_marker(SimpleNamespace(request=request), '/api/sessions/id',
                                    'CODEX_HTTP_REPLY', 'Codex history', seconds=1)
        self.assertEqual(request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
