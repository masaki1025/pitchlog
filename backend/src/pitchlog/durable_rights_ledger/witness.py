"""保護済みの単一journalを開き、汎用frameを耐久追記する。"""

from __future__ import annotations

import array
import fcntl
import hashlib
import json
import math
import os
import stat
import struct
import sys
from _thread import RLock
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import UUID

_MAGIC = b"PLWIT001"
_VERSION = 1
_HEADER = struct.Struct(">8sBIQ32s")
_MAX_PAYLOAD = 65536
_ZERO = bytes(32)
_APPEND = 0x20
_IMMUTABLE = 0x10
_GETFLAGS = (2 << 30) | (struct.calcsize("l") << 16) | (ord("f") << 8) | 1
_NAMES = ("enrollment.json", "journal", "writer.lock")


class WitnessUnavailable(RuntimeError):
    """不正/破損/未提供のwitnessを成功へ写さない。"""


class WitnessProtectionUnavailable(WitnessUnavailable):
    """実UID・kernel保護・filesystem能力の不成立を表す。"""


class WitnessBusy(WitnessUnavailable):
    """期限内に単一writerを取得できなかったことを表す。"""


class WitnessOutcomeUnconfirmed(WitnessUnavailable):
    """追記/fsyncの結果不明。未記録と断定して再利用しない。"""


@dataclass(frozen=True, slots=True)
class Frame:
    """検証済みの汎用frame。業務上の成功証明ではない。"""

    ordinal: int
    payload: bytes
    digest: bytes


def _protection_error() -> WitnessProtectionUnavailable:
    return WitnessProtectionUnavailable("witness protection unavailable")


def _require_worker() -> None:
    if sys.platform != "linux" or os.geteuid() == 0 or os.getegid() == 0:
        raise _protection_error()
    if (
        os.getresuid() != (os.geteuid(),) * 3
        or os.getresgid() != (os.getegid(),) * 3
        or 0 in os.getgroups()
    ):
        raise _protection_error()
    try:
        rows = dict(
            line.split(":", 1)
            for line in Path("/proc/self/status").read_text().splitlines()
            if ":" in line
        )
        # effectiveだけでなく再取得可能なpermitted/bounding等も拒否する。
        if (
            any(
                int(rows[key].strip(), 16) != 0
                for key in ("CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd")
            )
            or rows["NoNewPrivs"].strip() != "1"
        ):
            raise _protection_error()
    except (OSError, ValueError, KeyError):
        raise _protection_error() from None


def _flags(fd: int) -> int:
    try:
        value = array.array("I", [0])
        fcntl.ioctl(fd, _GETFLAGS, value, True)
        return value[0]
    except OSError:
        raise _protection_error() from None


def _mount(fd: int) -> int:
    try:
        rows = dict(
            line.split(":", 1)
            for line in Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
            if ":" in line
        )
        return int(rows["mnt_id"].strip())
    except (OSError, ValueError, KeyError):
        raise _protection_error() from None


def _trusted_directory(path: Path) -> int:
    if not path.is_absolute() or ".." in path.parts or path == Path("/"):
        raise _protection_error()
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_fd
            metadata = os.fstat(descriptor)
            if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                raise _protection_error()
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _regular(fd: int, uid: int, gid: int, mode: int) -> os.stat_result:
    value = os.fstat(fd)
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid != uid
        or value.st_gid != gid
        or stat.S_IMODE(value.st_mode) != mode
    ):
        raise _protection_error()
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WitnessUnavailable("witness unavailable")
        value[key] = item
    return value


def _enrollment(fd: int) -> dict[str, Any]:
    if os.fstat(fd).st_size > 4096:
        raise WitnessUnavailable("witness unavailable")
    value = json.loads(os.pread(fd, 4097, 0), object_pairs_hook=_unique)
    expected = {
        "schema_version",
        "authority_id",
        "writer_uid",
        "writer_gid",
        "device",
        "filesystem_id",
        "directory_inode",
        "journal_inode",
        "lock_inode",
        "descriptor_inode",
    }
    if type(value) is not dict or set(value) != expected:
        raise WitnessUnavailable("witness unavailable")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise WitnessUnavailable("witness unavailable")
    if (
        type(value["authority_id"]) is not str
        or str(UUID(value["authority_id"])) != value["authority_id"]
    ):
        raise WitnessUnavailable("witness unavailable")
    for key in expected - {"schema_version", "authority_id"}:
        if type(value[key]) is not int or value[key] <= 0:
            raise WitnessUnavailable("witness unavailable")
    return value


def _read_exact(fd: int, count: int, offset: int) -> bytes:
    result = bytearray()
    while len(result) < count:
        chunk = os.pread(fd, count - len(result), offset + len(result))
        if not chunk:
            raise WitnessUnavailable("witness unavailable")
        result.extend(chunk)
    return bytes(result)


def _frames(fd: int, size: int) -> Iterator[Frame]:
    offset, ordinal, previous = 0, 0, _ZERO
    while offset < size:
        header = _read_exact(fd, _HEADER.size, offset)
        magic, version, count, index, linked = _HEADER.unpack(header)
        if (
            magic != _MAGIC
            or version != _VERSION
            or not 0 < count <= _MAX_PAYLOAD
            or index != ordinal + 1
            or linked != previous
            or offset + _HEADER.size + count + 32 > size
        ):
            raise WitnessUnavailable("witness unavailable")
        body = _read_exact(fd, count + 32, offset + _HEADER.size)
        payload, digest = body[:-32], body[-32:]
        if hashlib.sha256(header + payload).digest() != digest:
            raise WitnessUnavailable("witness unavailable")
        yield Frame(index, payload, digest)
        offset += _HEADER.size + count + 32
        ordinal, previous = index, digest


def _encoded(ordinal: int, previous: bytes, payload: bytes) -> tuple[bytes, bytes]:
    if (
        type(ordinal) is not int
        or not 0 < ordinal < 2**64
        or type(previous) is not bytes
        or len(previous) != 32
        or type(payload) is not bytes
        or not 0 < len(payload) <= _MAX_PAYLOAD
    ):
        raise WitnessUnavailable("witness unavailable")
    header = _HEADER.pack(_MAGIC, _VERSION, len(payload), ordinal, previous)
    digest = hashlib.sha256(header + payload).digest()
    return header + payload + digest, digest


def _acquire(fd: int, timeout: float) -> None:
    deadline = monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if monotonic() >= deadline:
                raise WitnessBusy("witness busy") from None
            sleep(min(0.01, max(0, deadline - monotonic())))


class ProtectedJournal:
    """実保護済みenrollmentを要求する単一writerの汎用journal。

    生成/再enroll/保護属性の設定は提供しない。業務復旧の証明やDB ACKの
    判定は後続authorityが担い、このclassへ任意の期待集合を渡して代用しない。
    """

    _fds: tuple[int, int, int, int]
    _enrollment: dict[str, Any]
    _timeout: float
    _pid: int
    _mutex: RLock
    _closed: bool
    _broken: bool
    _size: int
    _last: Frame

    @classmethod
    def open(cls, path: Path, *, timeout: float = 1.0) -> ProtectedJournal:
        """既存の保護descriptor/inodeを検査し、実排他取得後に開く。"""
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 30
        ):
            raise WitnessUnavailable("witness unavailable")
        if cls is not ProtectedJournal:
            raise WitnessUnavailable("witness unavailable")
        _require_worker()
        descriptors: list[int] = []
        try:
            root = _trusted_directory(path)
            descriptors.append(root)
            for name, access in zip(
                _NAMES, (os.O_RDONLY, os.O_RDWR | os.O_APPEND, os.O_RDWR), strict=True
            ):
                descriptors.append(
                    os.open(
                        name,
                        access | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                        dir_fd=root,
                    )
                )
            root, descriptor, journal, lock = descriptors
            # FIFO等を読まず、保護されたregular fileだけを解釈する。
            _regular(descriptor, 0, os.getegid(), 0o640)
            _regular(journal, os.geteuid(), os.getegid(), 0o600)
            _regular(lock, os.geteuid(), os.getegid(), 0o600)
            if not _flags(descriptor) & _IMMUTABLE:
                raise _protection_error()
            enrollment = _enrollment(descriptor)
            _acquire(lock, timeout)
            instance = object.__new__(cls)
            instance._fds = (root, descriptor, journal, lock)
            instance._enrollment = enrollment
            instance._timeout = timeout
            instance._pid = os.getpid()
            instance._mutex = RLock()
            instance._closed = False
            instance._broken = False
            instance._validate()
            # 既存enrollmentのfile metadataとdirectory entryも実耐久化する。
            for fd in (descriptor, journal, lock, root):
                os.fsync(fd)
            last = Frame(0, b"", _ZERO)
            size = os.fstat(journal).st_size
            for last in _frames(journal, size):
                pass
            instance._size, instance._last = size, last
            return instance
        except BaseException as error:
            for fd in reversed(descriptors):
                os.close(fd)
            if isinstance(error, WitnessUnavailable):
                raise error from None
            if not isinstance(error, Exception):
                raise
            raise WitnessUnavailable("witness unavailable") from None

    def _validate(self) -> None:
        _require_worker()
        root, descriptor, journal, lock = self._fds
        value = self._enrollment
        metadata = os.fstat(root)
        if (
            self._pid != os.getpid()
            or metadata.st_uid != 0
            or metadata.st_gid != os.getegid()
            or stat.S_IMODE(metadata.st_mode) != 0o750
            or value["writer_uid"] != os.geteuid()
            or value["writer_gid"] != os.getegid()
            or value["device"] != metadata.st_dev
            or value["filesystem_id"] != os.fstatvfs(root).f_fsid
            or value["directory_inode"] != metadata.st_ino
            or not _flags(root) & _APPEND
        ):
            raise _protection_error()
        entries = (
            (descriptor, 0, 0o640, "descriptor_inode", _IMMUTABLE),
            (journal, os.geteuid(), 0o600, "journal_inode", _APPEND),
            (lock, os.geteuid(), 0o600, "lock_inode", 0),
        )
        for name, (fd, uid, mode, key, required) in zip(_NAMES, entries, strict=True):
            current = _regular(fd, uid, os.getegid(), mode)
            bound = os.stat(name, dir_fd=root, follow_symlinks=False)
            if (
                current.st_ino != value[key]
                or current.st_dev != metadata.st_dev
                or (bound.st_dev, bound.st_ino) != (current.st_dev, current.st_ino)
                or _mount(fd) != _mount(root)
                or _flags(fd) & (_APPEND | _IMMUTABLE) != required
            ):
                raise _protection_error()

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        if not self._mutex.acquire(timeout=self._timeout):
            raise WitnessBusy("witness busy")
        try:
            if self._closed or self._broken or self._pid != os.getpid():
                raise WitnessUnavailable("witness unavailable")
            self._validate()
            if os.fstat(self._fds[2]).st_size != self._size:
                raise WitnessUnavailable("witness unavailable")
            yield
        except WitnessUnavailable:
            self._broken = True
            raise
        except OSError:
            self._broken = True
            raise WitnessUnavailable("witness unavailable") from None
        finally:
            self._mutex.release()

    @property
    def authority_id(self) -> UUID:
        """保護descriptorから得た識別値を返す。単独の復旧許可ではない。"""
        with self._exclusive():
            return UUID(self._enrollment["authority_id"])

    def records(self) -> Iterator[Frame]:
        """固定inodeの全frameをbounded memoryで再検証して流す。"""
        with self._exclusive():
            yield from _frames(self._fds[2], self._size)

    def append(self, payload: bytes) -> Frame:
        """完全追記とfile fsyncが完了した場合だけframeを返す。"""
        if type(payload) is not bytes or not 0 < len(payload) <= _MAX_PAYLOAD:
            raise WitnessUnavailable("witness unavailable")
        with self._exclusive():
            data, digest = _encoded(self._last.ordinal + 1, self._last.digest, payload)
            try:
                written = 0
                while written < len(data):
                    try:
                        count = os.write(self._fds[2], data[written:])
                    except InterruptedError:
                        continue
                    if count <= 0:
                        raise OSError("write failed")
                    written += count
                os.fsync(self._fds[2])
                self._validate()
                if os.fstat(self._fds[2]).st_size != self._size + len(data):
                    raise OSError("unexpected file size")
            except BaseException as error:
                self._broken = True
                if not isinstance(error, Exception):
                    raise
                raise WitnessOutcomeUnconfirmed("witness outcome unconfirmed") from None
            self._size += len(data)
            self._last = Frame(self._last.ordinal + 1, payload, digest)
            return self._last

    def close(self) -> None:
        """同じprocessのwriter leaseと全fdを解放する。"""
        if self._pid != os.getpid():
            raise WitnessUnavailable("witness unavailable")
        if not self._mutex.acquire(timeout=self._timeout):
            raise WitnessBusy("witness busy")
        try:
            if not self._closed:
                self._closed = True
                for fd in reversed(self._fds):
                    os.close(fd)
        finally:
            self._mutex.release()

    def __enter__(self) -> ProtectedJournal:
        """検証済みwriterをcontextへ渡す。"""
        with self._exclusive():
            return self

    def __exit__(self, *args: object) -> None:
        """例外時もwriterを解放し、成功へ写さない。"""
        self.close()
