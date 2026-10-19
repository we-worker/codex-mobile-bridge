"""Read Windows process identity in Claude Code 2.1.168's native registry format."""

import ctypes
import re
import subprocess


_QUERY_LIMITED = 0x1000
_TERMINATE = 0x0001
_SYNCHRONIZE = 0x100000


def process_start_ticks(pid):
    """Return .NET ticks, None for a confirmed absent PID, or raise on uncertainty."""
    if type(pid) is not int or pid <= 0:
        raise OSError('invalid process identity')
    script = ("$ErrorActionPreference='Stop'; "
              f'$p=Get-CimInstance Win32_Process -Filter "ProcessId={pid}" -ErrorAction Stop; '
              "if ($null -eq $p) { 'missing' } else { $p.CreationDate.Ticks }")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError('process identity unavailable') from exc
    if result.returncode != 0:
        raise OSError('process identity unavailable')
    value = result.stdout.strip()
    if value == 'missing':
        return None
    if not re.fullmatch(r'[1-9][0-9]*', value):
        raise OSError('process identity unavailable')
    return value


def _process_filetime(kernel, handle):
    values = [ctypes.c_uint64() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
        raise OSError('process identity unavailable')
    return values[0].value


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p, *([ctypes.POINTER(ctypes.c_uint64)] * 4)]
    kernel.GetProcessTimes.restype = ctypes.c_int
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.TerminateProcess.restype = ctypes.c_int
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    return kernel


def process_start_filetime(pid):
    """Capture an owned native child's creation time for later same-handle cleanup."""
    if type(pid) is not int or pid <= 0:
        raise OSError('invalid process identity')
    kernel = _kernel()
    handle = kernel.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise OSError('process identity unavailable')
    try:
        return _process_filetime(kernel, handle)
    finally:
        kernel.CloseHandle(handle)


def _cim_parent_start(pid):
    script = ("$ErrorActionPreference='Stop'; "
              f'$p=Get-CimInstance Win32_Process -Filter "ProcessId={pid}" -ErrorAction Stop; '
              "if ($null -eq $p) { 'missing' } else { "
              "$p.ParentProcessId.ToString() + '|' + $p.CreationDate.Ticks.ToString() + '|' + $p.Name }")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError('process ancestry unavailable') from exc
    if result.returncode != 0:
        raise OSError('process ancestry unavailable')
    value = result.stdout.strip().split('|')
    if len(value) != 3 or not all(re.fullmatch(r'[1-9][0-9]*', part) for part in value[:2]):
        raise OSError('process ancestry unavailable')
    return int(value[0]), value[1], value[2]


def owned_child_start_filetime(pid, shim_pid):
    """Bind only a native Claude child of our live npm shim to its creation identity."""
    if type(pid) is not int or pid <= 0 or type(shim_pid) is not int or shim_pid <= 0:
        raise OSError('invalid process ancestry')
    first = _cim_parent_start(pid)
    if first[0] != shim_pid or first[2].lower() != 'claude.exe':
        raise OSError('process is not the owned Claude child')
    start = process_start_filetime(pid)
    if start is None or _cim_parent_start(pid) != first:
        raise OSError('process identity changed during ownership check')
    return start


def terminate_matching_process(pid, start_filetime):
    """Terminate only the original child, checking identity on the termination handle."""
    if type(pid) is not int or pid <= 0 or type(start_filetime) is not int or start_filetime <= 0:
        raise OSError('invalid process identity')
    kernel = _kernel()
    handle = kernel.OpenProcess(_QUERY_LIMITED | _TERMINATE | _SYNCHRONIZE, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return False
        raise OSError('process identity unavailable')
    try:
        if _process_filetime(kernel, handle) != start_filetime:
            return False
        state = kernel.WaitForSingleObject(handle, 0)
        if state == 0:
            return False
        if state != 0x102:
            raise OSError('owned process state unavailable')
        if not kernel.TerminateProcess(handle, 1):
            if kernel.WaitForSingleObject(handle, 0) == 0:
                return False
            raise OSError('owned process termination failed')
        if kernel.WaitForSingleObject(handle, 3000) != 0:
            raise OSError('owned process termination unconfirmed')
        return True
    finally:
        kernel.CloseHandle(handle)
