#!/usr/bin/env python3
"""Build the userspace Tailscale helper for the current desktop target."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tsnet'
OUTPUT = ROOT / 'dist' / 'tsnet'


def build():
    go = os.environ.get('CMB_GO') or shutil.which('go')
    if not go:
        raise SystemExit('Go is required to build the embedded Tailscale helper; install Go or set CMB_GO.')
    name = 'codex-tsnet.exe' if sys.platform == 'win32' else 'codex-tsnet'
    OUTPUT.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, 'CGO_ENABLED': '0'}
    subprocess.run([go, 'mod', 'download'], cwd=SOURCE, env=environment, check=True)
    subprocess.run([
        go, 'build', '-trimpath', '-buildvcs=false', '-ldflags=-s -w',
        '-o', str(OUTPUT / name), '.',
    ], cwd=SOURCE, env=environment, check=True)
    print('Embedded Tailscale helper ready:', OUTPUT / name)


if __name__ == '__main__':
    build()
