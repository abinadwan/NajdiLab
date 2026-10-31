"""Bounded local filesystem metadata only; never opens application contents."""
from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path


def local_filesystem(path: Path) -> bool:
    """Prove locality before stat, refusing remote/unknown drive or mount types."""
    if os.name == "nt":
        import ctypes
        try:
            get_type = ctypes.windll.kernel32.GetDriveTypeW
            get_type.argtypes = [ctypes.c_wchar_p]
            get_type.restype = ctypes.c_uint
            return get_type(path.anchor) == 3  # DRIVE_FIXED
        except (OSError, AttributeError):
            return False
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/mountinfo", "rb") as stream:
                raw = stream.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                return False
            matches = []
            for line in raw.decode("utf-8").splitlines():
                left, _, right = line.partition(" - ")
                mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), left.split()[4])
                parent = Path(mount)
                if path.is_relative_to(parent):
                    matches.append((len(parent.parts), right.split()[0]))
            if not matches:
                return False
            depth = max(entry[0] for entry in matches)
            local_types = {"ext2", "ext3", "ext4", "xfs", "btrfs", "tmpfs", "ramfs", "overlay", "aufs", "zfs", "f2fs", "squashfs"}
            return all(kind in local_types for size, kind in matches if size == depth)
        except (OSError, ValueError, IndexError):
            return False
    return False


def valid_local_path(path: Path) -> bool:
    value = str(path)
    return (path.is_absolute() and len(value) <= 4096 and len(path.parts) <= 64
            and not value.startswith(("\\\\", "//")) and ".." not in path.parts
            and not any(ord(char) < 32 for char in value)
            and ":" not in value[len(path.drive):])


def _windows_metadata(path: Path, kind: str) -> str:
    from .local_sources_windows import metadata
    return metadata(path, kind)


def _posix_metadata(path: Path, kind: str) -> str:
    if not hasattr(os, "O_PATH") or os.open not in os.supports_dir_fd:
        return "UNSAFE_PATH"
    import ctypes as ct
    import errno
    import platform
    if not sys.platform.startswith("linux") or platform.machine().lower() not in {"x86_64", "aarch64"}:
        return "UNSAFE_PATH"

    class OpenHow(ct.Structure):
        _fields_ = [("flags", ct.c_uint64), ("mode", ct.c_uint64), ("resolve", ct.c_uint64)]

    # Kernel-enforced BENEATH | NO_SYMLINKS | NO_MAGICLINKS | NO_XDEV. No
    # separate path/mount check can authorize crossing a mount during lookup.
    how = OpenHow(os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, 0, 0x08 | 0x04 | 0x02 | 0x01)
    root = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    handle = -1
    try:
        libc = ct.CDLL(None, use_errno=True)
        libc.syscall.restype = ct.c_long
        relative = "/".join(path.parts[1:]) or "."
        # openat2 is 437 on the explicitly supported Linux ABIs. Unsupported
        # kernels return ENOSYS; never fall back to a weaker traversal.
        handle = libc.syscall(ct.c_long(437), ct.c_int(root), ct.c_char_p(os.fsencode(relative)), ct.byref(how), ct.c_size_t(ct.sizeof(how)))
        if handle < 0:
            error = ct.get_errno()
            if error in {errno.ENOENT, errno.ENOTDIR}:
                return "MISSING"
            return "INACCESSIBLE" if error in {errno.EACCES, errno.EPERM} else "UNSAFE_PATH"
        info = os.fstat(handle)
        if stat.S_ISLNK(info.st_mode):
            return "UNSAFE_PATH"
        if kind == "directory":
            return "DETECTED" if stat.S_ISDIR(info.st_mode) else "WRONG_TYPE"
        return "DETECTED" if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 else "WRONG_TYPE"
    finally:
        if handle >= 0:
            os.close(handle)
        os.close(root)


def source_metadata(path: Path, kind: str) -> str:
    """No-follow metadata lookup, with no content/SQL access or stat fallback."""
    if not valid_local_path(path) or not local_filesystem(path):
        return "UNSAFE_PATH"
    try:
        if os.name == "nt":
            return _windows_metadata(path, kind)
        if os.name == "posix":
            return _posix_metadata(path, kind)
        return "UNSAFE_PATH"
    except FileNotFoundError:
        return "MISSING"
    except (OSError, AttributeError, NotImplementedError):
        return "INACCESSIBLE"


def marker_present(home: Path, marker: str) -> bool:
    return source_metadata(home / marker, "directory") == "DETECTED"
