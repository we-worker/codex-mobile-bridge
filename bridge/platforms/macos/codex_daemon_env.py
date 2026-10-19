"""Bounded macOS read of an existing same-user Codex daemon's launch data."""

import ctypes
import os
import struct
from pathlib import Path

from bridge.platforms.macos.force_exit import Native


def _environment(pid, names):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
                            ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                            ctypes.c_void_p, ctypes.c_size_t]
    libc.sysctl.restype = ctypes.c_int
    mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2, pid.
    size = ctypes.c_size_t()
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) or not 4 <= size.value <= 2_000_000:
        raise OSError('Codex daemon launch data unavailable')
    data = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, data, ctypes.byref(size), None, 0):
        raise OSError('Codex daemon launch data unavailable')
    raw = data.raw[:size.value]
    argc = struct.unpack_from('i', raw)[0]
    if not 0 <= argc <= 256:
        raise OSError('Codex daemon launch data invalid')
    position = raw.index(b'\0', 4) + 1  # executable path
    while position < len(raw) and raw[position] == 0:
        position += 1
    if position >= len(raw):
        raise OSError('Codex daemon launch data invalid')
    for _ in range(argc):
        position = raw.index(b'\0', position) + 1
    while position < len(raw) and raw[position] == 0:
        position += 1
    wanted = {name.encode(): name for name in names}
    selected = {}
    while position < len(raw):
        end = raw.find(b'\0', position)
        if end <= position:
            break
        entry = raw[position:end]
        key, separator, value = entry.partition(b'=')
        if separator and key in wanted:
            selected[wanted[key]] = os.fsdecode(value)
        position = end + 1
    return selected


def read_process_environment(pid, record, executable, names, record_path=None):
    native = Native()
    before = native.identity(pid)
    identity = record.get('processIdentity') or {}
    if (before['pid'] != pid or before['uid'] != os.getuid() or
            before['ruid'] != os.getuid() or
            before['image'] != str(Path(executable).resolve()) or before['zombie'] or
            before['birth'][0] != identity.get('uniqueId') or
            tuple(before['started']) != (identity.get('startSeconds'), identity.get('startMicroseconds'))):
        raise OSError('Codex daemon process identity mismatch')
    values = _environment(pid, names)
    after = native.identity(pid)
    if before != after:
        raise OSError('Codex daemon process changed')
    return values, (pid, before['birth'], before['started'], before['image'])
