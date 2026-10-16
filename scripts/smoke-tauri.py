#!/usr/bin/env python3
"""Convenient CI entry for the native Tauri smoke test."""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['node', str(root/'scripts/smoke-tauri.cjs'), *sys.argv[1:]], cwd=root, check=True)
