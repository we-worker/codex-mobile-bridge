#!/usr/bin/env python3
"""Verify mobile Tailscale credential parsing without running Android UI code."""
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
work = root / '.tmp/mobile-tailnet-credential-tests'
work.mkdir(parents=True, exist_ok=True)

java_home = os.environ.get('JAVA_HOME')
android_home = os.environ.get('ANDROID_HOME')
if not java_home or not android_home:
    raise SystemExit('JAVA_HOME and ANDROID_HOME are required')


def java_tool(name):
    return Path(java_home) / 'bin' / name


android = next((Path(android_home) / 'platforms').glob('*/android.jar'), None)
if android is None:
    raise SystemExit('Android platform jar is missing')

subprocess.run([
    str(java_tool('javac')),
    '--release',
    '8',
    '-encoding',
    'UTF-8',
    '-classpath',
    str(android),
    '-d',
    str(work),
    str(root / 'mobile/android/src/io/github/try2love/codexbridge/TailnetCredentialStore.java'),
    str(root / 'mobile/tests/TailnetCredentialKeyTests.java'),
], check=True)

subprocess.run([
    str(java_tool('java')),
    '-classpath',
    os.pathsep.join((str(work), str(android))),
    'io.github.try2love.codexbridge.TailnetCredentialKeyTests',
], check=True)
