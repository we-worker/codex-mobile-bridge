"""Read selected launch variables from the verified local Codex daemon."""

import json
import os
import stat
import sys
from pathlib import Path


class DaemonEnvironmentUnavailable(OSError):
    pass


def read_daemon_environment(home, executable, names):
    """Return (selected values, process generation); never export a full environment."""
    home = Path(home).resolve()
    expected = Path(executable).resolve()
    names = frozenset(names) | {'CODEX_HOME'}
    if (not names.issubset({name for name in names if isinstance(name, str) and
                             name and '=' not in name and '\0' not in name}) or len(names) > 32):
        raise DaemonEnvironmentUnavailable('Invalid daemon environment request')
    state = home / 'app-server-daemon'
    record = next((state / name for name in ('daemon.pid', 'app-server.pid')
                   if (state / name).is_file()), None)
    if record is None or record.is_symlink():
        raise DaemonEnvironmentUnavailable('Codex daemon PID record is unavailable')
    try:
        info = record.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_size > 4096 or
                os.name != 'nt' and info.st_uid != os.getuid()):
            raise DaemonEnvironmentUnavailable('Codex daemon PID record is untrusted')
        with record.open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise DaemonEnvironmentUnavailable('Codex daemon PID record is too large')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise DaemonEnvironmentUnavailable('Codex daemon PID record is invalid')
        pid = payload.get('pid')
        if type(pid) is not int or pid <= 0:
            raise DaemonEnvironmentUnavailable('Codex daemon PID record is invalid')
        if sys.platform == 'darwin':
            from bridge.platforms.macos.codex_daemon_env import read_process_environment
        elif sys.platform == 'linux':
            from bridge.platforms.linux.codex_daemon_env import read_process_environment
        elif os.name == 'nt':
            from bridge.platforms.windows.codex_daemon_env import read_process_environment
        else:
            raise DaemonEnvironmentUnavailable('Codex daemon environment is unsupported')
        values, identity = read_process_environment(pid, payload, expected, names, record)
        daemon_home = values.pop('CODEX_HOME', None)
        if daemon_home is not None and Path(daemon_home).resolve() != home:
            raise DaemonEnvironmentUnavailable('Codex daemon belongs to another home')
        after = record.stat()
        if (after.st_mtime_ns, after.st_ino, after.st_size) != (
                info.st_mtime_ns, info.st_ino, info.st_size):
            raise DaemonEnvironmentUnavailable('Codex daemon PID record changed')
        return values, identity
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        if isinstance(exc, DaemonEnvironmentUnavailable):
            raise
        raise DaemonEnvironmentUnavailable('Codex daemon environment could not be verified') from exc
