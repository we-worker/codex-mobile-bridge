#!/usr/bin/env python3
"""Report individual installer sizes; never compare combined artifact downloads."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def measure(release):
    runtime = ROOT/'dist/gateway'
    executable = release/'codex-mobile-bridge-tauri.exe'
    if not executable.is_file():
        raise ValueError('Tauri executable not found')
    files = [p for p in runtime.rglob('*') if p.is_file()]
    cloudflared = sum(p.stat().st_size for p in files if p.name == 'cloudflared.exe')
    runtime_size = sum(p.stat().st_size for p in files)
    loader_size = sum(p.stat().st_size for p in release.glob('*.dll'))
    result = {'nativeExecutableBytes': executable.stat().st_size, 'gatewayBytes': runtime_size,
              'cloudflaredBytes': cloudflared, 'nativeLoaderBytes': loader_size, 'applicationPayloadBytes': runtime_size+executable.stat().st_size+loader_size,
              'installers': [{'name':p.name,'bytes':p.stat().st_size} for p in sorted((release/'bundle/nsis').glob('*.exe'))],
              'excludes': 'WebView2 shared runtime, user data, installer/uninstaller metadata'}
    (ROOT/'.tmp').mkdir(exist_ok=True)
    (ROOT/'.tmp/tauri-size.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    text = json.dumps(result,indent=2)
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
            out.write('### Tauri package sizes\n```json\n'+text+'\n```\n')
    return result


if __name__ == '__main__':
    measure(Path(sys.argv[1] if len(sys.argv)>1 else ROOT/'src-tauri/target/release').resolve())
