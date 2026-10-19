#!/usr/bin/env python3
"""Prepare and run the isolated Windows native acceptance in a normal token."""
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOME = ROOT / 'h'
CLI = HOME / 'packages/app-server-daemon/current/bin/codex.exe'
INSTALLED_COPY = Path.home() / '.tmp/cmb-accounts-platform-20261014/codex.exe'
ARCHIVE = ROOT / 'bridge-source.zip'
WORKER = ROOT / 'codex_cli_windows_native.py'
LOG = ROOT / 'run.log'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.digest()


def main():
    if os.name != 'nt':
        raise RuntimeError('This fixture requires Windows')
    if ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('Run from an ordinary non-administrator terminal; native Codex forbids an elevated shared daemon')
    for path in (CLI, INSTALLED_COPY, ARCHIVE, WORKER):
        if not path.is_file():
            raise RuntimeError(f'Missing isolated fixture prerequisite: {path}')
    if digest(CLI) != digest(INSTALLED_COPY):
        raise RuntimeError('Staged CLI differs from the already installed Codex executable')
    socket = HOME / 'app-server-control/app-server-control.sock'
    if len(str(socket)) >= 108:
        raise RuntimeError('Isolated Windows AF_UNIX socket path is too long')
    if socket.exists() or any((HOME / 'app-server-daemon' / name).exists()
                              for name in ('daemon.pid', 'app-server.pid')):
        raise RuntimeError('Isolated daemon artifacts already exist; inspect this test home before running')
    source = ROOT / 'src'
    source.mkdir(exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as archive:
        names = archive.namelist()
        if not names or any(not name.startswith('bridge/') or '..' in Path(name).parts for name in names):
            raise RuntimeError('Unexpected bridge source archive')
        archive.extractall(source)
    result = ROOT / 'result.json'
    result.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment['CODEX_HOME'] = str(HOME)
    environment['PYTHONUTF8'] = '1'
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        with LOG.open('w', encoding='utf-8') as output:
            completed = subprocess.run([sys.executable, '-B', str(WORKER)],
                                       cwd=ROOT, env=environment, stdout=output,
                                       stderr=subprocess.STDOUT, timeout=180)
    except subprocess.TimeoutExpired:
        subprocess.run([str(CLI), 'app-server', 'daemon', 'stop'], env=environment,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
        raise RuntimeError('Isolated acceptance timed out; see run.log')
    if result.is_file():
        print(result.read_text(encoding='utf-8'))
    else:
        print(json.dumps({'status': 'failed', 'stage': 'launcher',
                          'error': f'Worker did not write result.json; inspect {LOG}'}))
    print(f'Log: {LOG}')
    return completed.returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        failure = {'status': 'failed', 'stage': 'launcher',
                   'errorType': type(exc).__name__, 'error': str(exc)}
        (ROOT / 'result.json').write_text(json.dumps(failure, indent=2), encoding='utf-8')
        print(json.dumps(failure))
        sys.exit(1)
