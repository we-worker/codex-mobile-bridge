"""Synthetic receipts for an idle Claude renderer handoff."""
import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from bridge.clients.claude.mailbox import CONNECTOR_REVISION, FileDesktop
from bridge.clients.errors import BridgeUnavailable

ROOT = Path(__file__).resolve().parents[1]


class ClaudeHandoff(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'.tmp')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.desktop = FileDesktop(self.directory, 'fixture-token')
        self.addCleanup(self.desktop.close)
        self.reply(seq=0)

    def reply(self, **fields):
        value = {'generation': self.desktop.generation, 'timestamp': time.time(),
                 'connected': True, 'connectorRevision': CONNECTOR_REVISION,
                 'surfaces': {'code': ['getAll', 'sendMessage']}, **fields}
        (self.directory/'response.json').write_text(self.desktop.pack(value), encoding='utf-8')

    def request(self):
        for _ in range(100):
            try:
                return json.loads(json.loads(
                    (self.directory/'request.json').read_text(encoding='utf-8'))['payload'])
            except (FileNotFoundError, PermissionError):
                time.sleep(.005)
        raise AssertionError('Claude request file remained unavailable')

    async def wait_request(self, kind):
        for _ in range(100):
            if self.request()['type'] == kind:
                return self.request()
            await asyncio.sleep(.01)
        self.fail('request type not observed: '+kind)

    async def test_confirmed_result_is_acknowledged_before_an_idle_handoff(self):
        call = asyncio.create_task(self.desktop.call('code', 'getAll', timeout=1))
        request = await self.wait_request('request')
        self.reply(seq=request['seq'], done=True, result=[])
        self.assertEqual(await call, [])
        self.assertEqual(self.request()['type'], 'idle')
        self.assertEqual(self.request()['seq'], request['seq'])
        self.reply(seq=request['seq'], done=True, result=[], connected=False,
                   handoffId='offer-1')
        acknowledgement = await self.wait_request('handoff-ack')
        self.assertEqual(acknowledgement['handoffId'], 'offer-1')
        self.assertTrue(self.desktop.stopped)
        with self.assertRaises(BridgeUnavailable):
            await self.desktop.call('code', 'sendMessage', 'session', 'text')
        self.assertEqual(self.request(), acknowledgement)
        self.desktop.close()
        self.assertEqual(self.request(), acknowledgement)

    async def test_uncertain_mutation_blocks_handoff_and_keeps_request(self):
        with self.assertRaisesRegex(BridgeUnavailable, '响应超时'):
            await self.desktop.call('code', 'sendMessage', 'session', 'text', timeout=.03)
        request = self.request()
        self.assertEqual(request['type'], 'request')
        self.assertEqual(self.desktop.unconfirmed_mutations, {request['seq']})
        self.reply(seq=request['seq'], done=True, error='结果待核对', connected=False,
                   handoffId='offer-2')
        await asyncio.sleep(.35)
        self.assertFalse(self.desktop.stopped)
        self.assertEqual(self.request(), request)

    async def test_late_success_acknowledges_only_the_matching_request(self):
        with self.assertRaisesRegex(BridgeUnavailable, '响应超时'):
            await self.desktop.call('code', 'sendMessage', 'session', 'text', timeout=.03)
        request = self.request()
        self.reply(seq=request['seq'], done=True, result=True)
        idle = await self.wait_request('idle')
        self.assertEqual(idle['seq'], request['seq'])
        self.assertEqual(self.desktop.unconfirmed_mutations, set())

    async def test_cancelling_during_idle_write_keeps_lock_until_write_finishes(self):
        original = self.desktop.write
        entered, release = threading.Event(), threading.Event()
        def held(value):
            if value.get('type') == 'idle' and value.get('seq') == 1:
                entered.set()
                release.wait(2)
            return original(value)
        with patch.object(self.desktop, 'write', side_effect=held):
            call = asyncio.create_task(self.desktop.call('code', 'getAll', timeout=1))
            request = await self.wait_request('request')
            self.reply(seq=request['seq'], done=True, result=[])
            for _ in range(100):
                if entered.is_set(): break
                await asyncio.sleep(.01)
            self.assertTrue(entered.is_set())
            call.cancel()
            self.reply(seq=request['seq'], done=True, result=[], connected=False,
                       handoffId='offer-3')
            await asyncio.sleep(.3)
            self.assertTrue(self.desktop.lock.locked())
            self.assertFalse(self.desktop.stopped)
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await call
            acknowledgement = await self.wait_request('handoff-ack')
            self.assertEqual(acknowledgement['handoffId'], 'offer-3')

    async def test_failed_idle_write_does_not_stop_the_monitor(self):
        original = self.desktop.write
        def failed(value):
            if value.get('type') == 'idle' and value.get('seq') == 1:
                raise OSError('fixture write failure')
            return original(value)
        with patch.object(self.desktop, 'write', side_effect=failed):
            call = asyncio.create_task(self.desktop.call('code', 'getAll', timeout=1))
            request = await self.wait_request('request')
            self.reply(seq=request['seq'], done=True, result=[])
            self.assertEqual(await call, [])
            self.reply(seq=request['seq'], done=True, result=[], connected=False,
                       handoffId='offer-4')
            await asyncio.sleep(.35)
            self.assertFalse(self.desktop.monitor.done())
            self.assertFalse(self.desktop.stopped)
            self.assertEqual(self.request()['type'], 'request')

    async def test_cancelling_request_write_preserves_uncertain_mutation(self):
        original = self.desktop.write
        entered, release = threading.Event(), threading.Event()
        def held(value):
            if value.get('type') == 'request':
                entered.set()
                release.wait(2)
            return original(value)
        with patch.object(self.desktop, 'write', side_effect=held):
            call = asyncio.create_task(self.desktop.call('code', 'sendMessage',
                                                         'session', 'text', timeout=1))
            for _ in range(100):
                if entered.is_set(): break
                await asyncio.sleep(.01)
            self.assertTrue(entered.is_set())
            call.cancel()
            self.reply(seq=0, connected=False, handoffId='offer-5')
            await asyncio.sleep(.3)
            self.assertTrue(self.desktop.lock.locked())
            self.assertFalse(self.desktop.stopped)
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await call
            await asyncio.sleep(.3)
            self.assertEqual(self.request()['type'], 'request')
            self.assertEqual(self.desktop.unconfirmed_mutations, {1})
            self.assertFalse(self.desktop.stopped)


if __name__ == '__main__':
    unittest.main()
