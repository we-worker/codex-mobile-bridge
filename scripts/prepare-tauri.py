#!/usr/bin/env python3
"""Stage only local UI resources, preserving the Electron page's relative URLs."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    target = ROOT/'.tmp/tauri-web'
    # This fixed, verified staging directory never contains user data.
    if target.resolve() != (ROOT/'.tmp/tauri-web').absolute():
        raise ValueError('Unsafe Tauri staging directory')
    if target.exists():
        shutil.rmtree(target)
    package = json.loads((ROOT/'package.json').read_text(encoding='utf-8'))
    files = set()
    for pattern in package['build']['files']:
        if pattern.endswith('/**'):
            files.update(p for p in (ROOT/pattern[:-3]).rglob('*') if p.is_file())
        elif (ROOT/pattern).is_file():
            files.add(ROOT/pattern)
    extensions = {'.html', '.js', '.css', '.png', '.ico', '.svg', '.woff', '.woff2'}
    for source in sorted(files):
        if source.suffix not in extensions:
            continue
        relative = source.relative_to(ROOT)
        output = target/relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if relative.as_posix() == 'desktop/index.html':
            html = source.read_text(encoding='utf-8')
            # The Electron page intentionally disallows all connections. Tauri's
            # own IPC is the only extra origin; no backend HTTP access is granted.
            html = html.replace("connect-src 'none'", "connect-src ipc: http://ipc.localhost; frame-src 'none'; form-action 'none'")
            output.write_text(html, encoding='utf-8')
        else:
            shutil.copyfile(source, output)
    print('Tauri UI staged:', target)
    return target


if __name__ == '__main__':
    prepare()
