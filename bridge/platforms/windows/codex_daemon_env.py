"""Read only requested variables from a verified x64 Windows Codex daemon.

The PEB layout is an internal Windows interface. Fail closed when it differs.
"""

import ctypes
from ctypes import wintypes
import os
import struct
from pathlib import Path


QUERY = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
VM_READ = 0x0010
TOKEN_QUERY = 0x0008
MAX_ENV = 1_048_576


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(ctypes.c_uint64)] * 4)]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                   wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    return kernel


def _read(kernel, handle, address, size):
    if not address or size <= 0 or size > MAX_ENV:
        raise OSError('Codex daemon memory address invalid')
    buffer = ctypes.create_string_buffer(size)
    count = ctypes.c_size_t()
    if not kernel.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, size,
                                    ctypes.byref(count)) or count.value != size:
        raise OSError('Codex daemon launch data unavailable')
    return buffer.raw


def _owner_sid(handle):
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel = _kernel()
    target = wintypes.HANDLE()
    current = wintypes.HANDLE()
    if not advapi.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(target)):
        raise OSError('Codex daemon owner unavailable')
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(current)):
            raise OSError('Codex daemon owner unavailable')
        def token_sid(token):
            length = wintypes.DWORD()
            advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(length))  # TokenUser
            if not 0 < length.value <= 4096:
                raise OSError('Codex daemon owner invalid')
            data = ctypes.create_string_buffer(length.value)
            if not advapi.GetTokenInformation(token, 1, data, length, ctypes.byref(length)):
                raise OSError('Codex daemon owner unavailable')
            return data, ctypes.c_void_p.from_buffer(data).value
        target_data, target_sid = token_sid(target)
        current_data, current_sid = token_sid(current)
        if not advapi.EqualSid(target_sid, current_sid):
            raise OSError('Codex daemon belongs to another user')
    finally:
        kernel.CloseHandle(target)
        if current:
            kernel.CloseHandle(current)


def _identity(kernel, handle, expected):
    times = [ctypes.c_uint64() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
        raise OSError('Codex daemon start time unavailable')
    path = ctypes.create_unicode_buffer(32768)
    length = wintypes.DWORD(len(path))
    if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
        raise OSError('Codex daemon executable unavailable')
    def normalized(value):
        return os.path.normcase(os.path.normpath(str(value).removeprefix('\\\\?\\')))
    if normalized(path.value) != normalized(Path(expected).resolve()):
        raise OSError('Codex daemon executable mismatch')
    return times[0].value, normalized(path.value)


def _environment(kernel, handle, names):
    ntdll = ctypes.WinDLL('ntdll', use_last_error=True)
    ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    basic = ctypes.create_string_buffer(48)  # PROCESS_BASIC_INFORMATION, x64.
    returned = wintypes.ULONG()
    if ntdll.NtQueryInformationProcess(handle, 0, basic, len(basic), ctypes.byref(returned)) < 0:
        raise OSError('Codex daemon PEB unavailable')
    peb = struct.unpack_from('<Q', basic.raw, 8)[0]
    params = struct.unpack('<Q', _read(kernel, handle, peb + 0x20, 8))[0]
    address = struct.unpack('<Q', _read(kernel, handle, params + 0x80, 8))[0]
    if not address:
        raise OSError('Codex daemon environment unavailable')
    # The UTF-16 block ends in two NUL characters. Read only bounded pages.
    raw = bytearray()
    offset = 0
    while offset < MAX_ENV:
        size = min(4096 - ((address + offset) % 4096), MAX_ENV - offset)
        previous = len(raw)
        raw.extend(_read(kernel, handle, address + offset, size))
        end = next((index for index in range(max(0, previous - 2) // 2 * 2, len(raw) - 3, 2)
                    if raw[index:index + 4] == b'\0\0\0\0'), -1)
        if end >= 0:
            raw = raw[:end + 4]
            break
        offset += size
    else:
        raise OSError('Codex daemon environment exceeds limit')
    selected = {}
    wanted = {name.casefold(): name for name in names}
    for entry in bytes(raw).decode('utf-16-le').split('\0'):
        if not entry:
            break
        key, separator, value = entry.partition('=')
        if separator and key.casefold() in wanted:
            selected[wanted[key.casefold()]] = value
    return selected


def read_process_environment(pid, record, executable, names, record_path=None):
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise OSError('Codex daemon environment needs Windows x64')
    kernel = _kernel()
    handle = kernel.OpenProcess(QUERY | VM_READ, False, pid)
    if not handle:
        raise OSError('Codex daemon process read unavailable')
    try:
        _owner_sid(handle)
        before = _identity(kernel, handle, executable)
        if str(before[0]) != str(record.get('processStartTime')):
            raise OSError('Codex daemon PID record is stale')
        values = _environment(kernel, handle, names)
        if _identity(kernel, handle, executable) != before:
            raise OSError('Codex daemon process changed')
        return values, (pid, *before)
    finally:
        kernel.CloseHandle(handle)
