"""Windows metadata-only lookup with kernel-enforced reparse refusal.

No data-read/write access, SQLite connection, content copy or denying share lock.
Unknown device mappings/API behavior fail closed; no path-based stat fallback.
"""
from pathlib import Path
import ctypes as ct
from ctypes import wintypes as wt
import re


def metadata(path: Path, kind: str) -> str:
    kernel = ct.WinDLL("kernel32", use_last_error=True)
    native = ct.WinDLL("ntdll")
    query_device = kernel.QueryDosDeviceW
    query_device.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD]
    query_device.restype = wt.DWORD
    mapping = ct.create_unicode_buffer(4096)
    if not query_device(path.drive, mapping, len(mapping)):
        return "UNSAFE_PATH"
    # Resolve only the DOS drive alias, without filesystem/SMB access. Do not
    # reopen C: after checking it; use the pinned local volume object instead.
    if not re.fullmatch(r"\\Device\\HarddiskVolume[0-9]+", mapping.value):
        return "UNSAFE_PATH"
    name = mapping.value + "\\" + "\\".join(path.parts[1:])
    buffer = ct.create_unicode_buffer(name)

    class UnicodeString(ct.Structure):
        _fields_ = [("Length", wt.USHORT), ("MaximumLength", wt.USHORT), ("Buffer", wt.LPWSTR)]

    class ObjectAttributes(ct.Structure):
        _fields_ = [("Length", wt.ULONG), ("RootDirectory", wt.HANDLE), ("ObjectName", ct.POINTER(UnicodeString)), ("Attributes", wt.ULONG), ("SecurityDescriptor", ct.c_void_p), ("SecurityQualityOfService", ct.c_void_p)]

    class IoStatus(ct.Structure):
        _fields_ = [("StatusOrPointer", ct.c_void_p), ("Information", ct.c_size_t)]

    class FileInformation(ct.Structure):
        _fields_ = [("attributes", wt.DWORD), ("created", wt.FILETIME), ("accessed", wt.FILETIME), ("written", wt.FILETIME), ("volume", wt.DWORD), ("size_high", wt.DWORD), ("size_low", wt.DWORD), ("links", wt.DWORD), ("index_high", wt.DWORD), ("index_low", wt.DWORD)]

    length = len(name.encode("utf-16-le"))
    text = UnicodeString(length, length + 2, ct.cast(buffer, wt.LPWSTR))
    # OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE: reject a reparse at ANY component,
    # including an ancestor exchanged while this call resolves the name.
    attributes = ObjectAttributes(ct.sizeof(ObjectAttributes), None, ct.pointer(text), 0x40 | 0x1000, None, None)
    handle = wt.HANDLE()
    io = IoStatus()
    open_existing = native.NtCreateFile
    open_existing.argtypes = [ct.POINTER(wt.HANDLE), wt.ULONG, ct.POINTER(ObjectAttributes), ct.POINTER(IoStatus), ct.c_void_p, wt.ULONG, wt.ULONG, wt.ULONG, wt.ULONG, ct.c_void_p, wt.ULONG]
    open_existing.restype = ct.c_int32
    # READ_ATTRIBUTES | SYNCHRONIZE; share read/write/delete; FILE_OPEN only;
    # synchronous non-alert + OPEN_REPARSE_POINT (still reject its attributes).
    status = open_existing(ct.byref(handle), 0x80 | 0x100000, ct.byref(attributes), ct.byref(io), None, 0, 7, 1, 0x20 | 0x200000, None, 0) & 0xffffffff
    if status:
        if status in {0xc000000f, 0xc0000034, 0xc000003a}:
            return "MISSING"
        return "UNSAFE_PATH" if status in {0xc000050b, 0xc0000279, 0xc00000bb, 0xc000000d} else "INACCESSIBLE"
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wt.HANDLE], wt.BOOL
    try:
        info = FileInformation()
        get_info = kernel.GetFileInformationByHandle
        get_info.argtypes, get_info.restype = [wt.HANDLE, ct.POINTER(FileInformation)], wt.BOOL
        if not get_info(handle, ct.byref(info)):
            return "INACCESSIBLE"
        if info.attributes & (0x400 | 0x40):  # REPARSE_POINT or DEVICE
            return "UNSAFE_PATH"
        directory = bool(info.attributes & 0x10)
        if kind == "directory":
            return "DETECTED" if directory else "WRONG_TYPE"
        return "DETECTED" if not directory and info.links == 1 else "WRONG_TYPE"
    finally:
        close(handle)
