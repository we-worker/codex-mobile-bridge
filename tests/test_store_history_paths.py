import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from bridge.features.sessions.store import SessionStore


ROOT = Path(__file__).resolve().parents[1]


class StoreHistoryPathTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp')
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.sessions = self.home / 'sessions'
        self.sessions.mkdir(parents=True)
        self.rollout = self.sessions / 'rollout.jsonl'
        self.rollout.write_text(json.dumps({'type': 'response_item', 'payload': {
            'type': 'message', 'role': 'assistant', 'content': [{'text': 'SAVED_REPLY'}]}}) + '\n')
        self.database = self.home / 'state_5.sqlite'
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE threads(id TEXT, originator TEXT, source TEXT, archived INT, cwd TEXT, rollout_path TEXT)')
            db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',
                       ('thread', 'codex-tui', 'vscode', 0, str(self.root), str(self.rollout)))
            db.commit()
        self.store = SessionStore(self.home)

    def tearDown(self):
        self.temp.cleanup()

    def set_rollout(self, path):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('UPDATE threads SET rollout_path=? WHERE id=?', (str(path), 'thread'))
            db.commit()

    def assert_readable(self):
        self.assertEqual(self.store.discovery_diagnostics('thread')['target']['reason'], 'readable')
        self.assertIn('SAVED_REPLY', str(self.store.history('thread')))

    def assert_outside(self):
        self.assertEqual(self.store.discovery_diagnostics('thread')['target']['reason'], 'rollout_outside_home')
        with self.assertRaises(ValueError):
            self.store.history('thread')

    def test_ordinary_path_remains_readable_without_identity_fallback(self):
        with patch.object(Path, 'samefile', side_effect=AssertionError('unneeded fallback')):
            self.assert_readable()

    @unittest.skipUnless(os.name == 'nt', 'Windows extended-length paths')
    def test_windows_extended_path_uses_same_existing_rollout(self):
        extended = Path('\\\\?\\' + str(self.rollout))
        self.set_rollout(extended)
        self.assert_readable()
        # Some Python versions remove the extended prefix during resolve().
        # Retain it here to exercise the identity fallback when it is needed.
        original_resolve = Path.resolve

        def retain_extended(path, *args, **kwargs):
            return path if path == extended else original_resolve(path, *args, **kwargs)

        self.assertNotIn(self.sessions.resolve(), extended.parents)
        with patch.object(Path, 'resolve', retain_extended), \
             patch.object(Path, 'samefile', side_effect=PermissionError('identity unavailable')) as samefile:
            self.assert_outside()
        samefile.assert_called()

    def test_outside_and_prefix_similar_directories_stay_rejected(self):
        outside = self.root / 'outside.jsonl'
        outside.write_bytes(self.rollout.read_bytes())
        near = self.home / 'sessions-other'
        near.mkdir()
        near_rollout = near / 'rollout.jsonl'
        near_rollout.write_bytes(self.rollout.read_bytes())
        for path in (outside, near_rollout):
            with self.subTest(path=path):
                self.set_rollout(path)
                self.assert_outside()
                if os.name == 'nt':
                    self.set_rollout('\\\\?\\' + str(path))
                    self.assert_outside()

    def test_symlink_to_outside_stays_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'rollout.jsonl').write_bytes(self.rollout.read_bytes())
        link = self.sessions / 'link'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'Directory symlink unavailable: {exc}')
        self.set_rollout(link / 'rollout.jsonl')
        self.assert_outside()
