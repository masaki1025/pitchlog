"""別UIDのUnix authorityを起動し、root管理の配置とworkerを分離する。"""

from __future__ import annotations

import argparse
import array
import fcntl
import json
import os
import select
import signal
import socket
import stat
import struct
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from .witness import _flags, _trusted_directory

_SETFLAGS = (1 << 30) | (struct.calcsize("l") << 16) | (ord("f") << 8) | 2
_CONFIG_KEYS = {
    "schema_version",
    "authority_uid",
    "authority_gid",
    "client_uid",
    "client_gid",
    "socket_path",
    "endpoint_path",
    "witness_path",
    "timeout",
    "primary_dsn",
    "standby_dsn",
    "business_dsn",
    "control_dsn",
    "enrollment_state",
}
_ENDPOINT_KEYS = {
    "schema_version",
    "authority_uid",
    "client_uid",
    "client_gid",
    "socket_path",
    "timeout",
}


class AuthorityUnavailable(RuntimeError):
    """配置/主体/起動の不成立を固定例外へ写す。"""


def _read_root_json(path: Path, mode: int) -> dict[str, Any]:
    parent = _trusted_directory(path.parent)
    descriptor = -1
    try:
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_nlink != 1
            or metadata.st_size > 16384
            or not _flags(descriptor) & 0x10
        ):
            raise AuthorityUnavailable("authority unavailable")
        from .witness import _unique

        value = json.loads(os.read(descriptor, 16385), object_pairs_hook=_unique)
        if type(value) is not dict:
            raise AuthorityUnavailable("authority unavailable")
        return value
    except Exception:
        raise AuthorityUnavailable("authority unavailable") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _config(path: Path) -> dict[str, Any]:
    value = _read_root_json(path, 0o640)
    if (
        set(value) != _CONFIG_KEYS
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise AuthorityUnavailable("authority unavailable")
    for key in ("authority_uid", "authority_gid", "client_uid", "client_gid"):
        if type(value[key]) is not int or value[key] <= 0:
            raise AuthorityUnavailable("authority unavailable")
    if (
        value["authority_uid"] == value["client_uid"]
        or value["authority_gid"] == value["client_gid"]
    ):
        raise AuthorityUnavailable("authority unavailable")
    if os.stat(path, follow_symlinks=False).st_gid != value["authority_gid"]:
        raise AuthorityUnavailable("authority unavailable")
    if value["enrollment_state"] not in ("new", "enrolled"):
        raise AuthorityUnavailable("authority unavailable")
    for key in ("socket_path", "endpoint_path", "witness_path"):
        if type(value[key]) is not str or not Path(value[key]).is_absolute():
            raise AuthorityUnavailable("authority unavailable")
    from .adapter import LedgerEndpoints

    LedgerEndpoints(
        value["primary_dsn"],
        value["standby_dsn"],
        value["business_dsn"],
        value["control_dsn"],
        value["timeout"],
    )
    return value


def _endpoint(path: Path) -> dict[str, Any]:
    value = _read_root_json(path, 0o644)
    if (
        set(value) != _ENDPOINT_KEYS
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise AuthorityUnavailable("authority unavailable")
    for key in ("authority_uid", "client_uid", "client_gid"):
        if type(value[key]) is not int or value[key] <= 0:
            raise AuthorityUnavailable("authority unavailable")
    if (
        value["client_uid"] != os.geteuid()
        or value["authority_uid"] == value["client_uid"]
    ):
        raise AuthorityUnavailable("authority unavailable")
    import math

    if (
        type(value["timeout"]) not in (int, float)
        or not math.isfinite(value["timeout"])
        or not 0.1 <= value["timeout"] <= 30
    ):
        raise AuthorityUnavailable("authority unavailable")
    target = Path(value["socket_path"])
    parent = _trusted_directory(target.parent)
    try:
        metadata = os.stat(target.name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISSOCK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != value["client_gid"]
            or stat.S_IMODE(metadata.st_mode) != 0o660
        ):
            raise AuthorityUnavailable("authority unavailable")
    finally:
        os.close(parent)
    return value


def _set_flags(fd: int, flags: int) -> None:
    fcntl.ioctl(fd, _SETFLAGS, array.array("I", [flags]), True)


def _write_root_json(path: Path, value: dict[str, Any], mode: int, gid: int) -> None:
    parent = _trusted_directory(path.parent)
    descriptor = -1
    try:
        if path.exists():
            old = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                _set_flags(old, _flags(old) & ~0x10)
            finally:
                os.close(old)
        descriptor = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            mode,
            dir_fd=parent,
        )
        os.fchown(descriptor, 0, gid)
        os.fchmod(descriptor, mode)
        data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise OSError("write failed")
            offset += written
        os.fsync(descriptor)
        _set_flags(descriptor, _flags(descriptor) | 0x10)
        os.fsync(descriptor)
        os.fsync(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _create_store(value: dict[str, Any]) -> None:
    path = Path(value["witness_path"])
    parent = _trusted_directory(path.parent)
    descriptors: list[int] = []
    try:
        os.mkdir(path.name, mode=0o750, dir_fd=parent)
        root = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        descriptors.append(root)
        os.fchown(root, 0, value["authority_gid"])
        os.fchmod(root, 0o750)
        for name in ("enrollment.json", "journal", "writer.lock"):
            descriptors.append(
                os.open(
                    name,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root,
                )
            )
        _, descriptor, journal, lock = descriptors
        os.fchown(descriptor, 0, value["authority_gid"])
        os.fchmod(descriptor, 0o640)
        for fd in (journal, lock):
            os.fchown(fd, value["authority_uid"], value["authority_gid"])
        metadata = dict(
            schema_version=1,
            authority_id=str(uuid4()),
            writer_uid=value["authority_uid"],
            writer_gid=value["authority_gid"],
            device=os.fstat(root).st_dev,
            filesystem_id=os.fstatvfs(root).f_fsid,
            directory_inode=os.fstat(root).st_ino,
            journal_inode=os.fstat(journal).st_ino,
            lock_inode=os.fstat(lock).st_ino,
            descriptor_inode=os.fstat(descriptor).st_ino,
        )
        data = json.dumps(metadata).encode()
        offset = 0
        while offset < len(data):
            count = os.write(descriptor, data[offset:])
            if count <= 0:
                raise OSError("write failed")
            offset += count
        _set_flags(descriptor, _flags(descriptor) | 0x10)
        _set_flags(journal, _flags(journal) | 0x20)
        _set_flags(root, _flags(root) | 0x20)
        for fd in (*descriptors, parent):
            os.fsync(fd)
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
        os.close(parent)


def _worker(mode: str, config_path: Path, status_fd: int, release_fd: int) -> None:
    value = _config(config_path)
    if os.geteuid() != value["authority_uid"] or os.getegid() != value["authority_gid"]:
        raise AuthorityUnavailable("authority unavailable")
    from .adapter import _AuthorityRuntime
    from .witness import ProtectedJournal

    with ProtectedJournal.open(
        Path(value["witness_path"]), timeout=value["timeout"]
    ) as journal:
        if mode == "enroll":
            _AuthorityRuntime.enroll(value, journal)
            os.write(status_fd, b"enrolled\n")
            return
        if value["enrollment_state"] != "enrolled":
            raise AuthorityUnavailable("authority unavailable")
        runtime = _AuthorityRuntime(value, journal)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(value["socket_path"])
            listener.listen(16)
            os.write(status_fd, b"bound\n")
            if os.read(release_fd, 1) != b"G":
                raise AuthorityUnavailable("authority unavailable")
            from threading import BoundedSemaphore, Thread

            admitted = BoundedSemaphore(16)
            while True:
                channel, _ = listener.accept()
                if not admitted.acquire(blocking=False):
                    channel.close()
                    continue

                def handle(accepted: socket.socket) -> None:
                    try:
                        accepted.settimeout(value["timeout"])
                        _, uid, gid = struct.unpack(
                            "3i",
                            accepted.getsockopt(
                                socket.SOL_SOCKET, socket.SO_PEERCRED, 12
                            ),
                        )
                        if (uid, gid) == (value["client_uid"], value["client_gid"]):
                            runtime.handle(accepted)
                    finally:
                        accepted.close()
                        admitted.release()

                Thread(target=handle, args=(channel,), daemon=True).start()
        finally:
            listener.close()


def _launch(mode: str, config_path: Path) -> None:
    if os.geteuid() != 0:
        raise AuthorityUnavailable("authority unavailable")
    value = _config(config_path)
    if mode == "enroll":
        if value["enrollment_state"] != "new":
            raise AuthorityUnavailable("authority unavailable")
        _create_store(value)
    else:
        if value["enrollment_state"] != "enrolled":
            raise AuthorityUnavailable("authority unavailable")
        lock = os.open(
            Path(value["witness_path"]) / "writer.lock", os.O_RDWR | os.O_NOFOLLOW
        )
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            target = Path(value["socket_path"])
            if target.exists():
                if not stat.S_ISSOCK(target.lstat().st_mode):
                    raise AuthorityUnavailable("authority unavailable")
                target.unlink()
        finally:
            os.close(lock)
    if mode == "serve":
        run_path = Path(value["socket_path"]).parent
        if run_path in (config_path.parent, Path(value["endpoint_path"]).parent):
            raise AuthorityUnavailable("authority unavailable")
        run_fd = _trusted_directory(run_path)
        try:
            os.fchown(run_fd, 0, value["authority_gid"])
            os.fchmod(run_fd, 0o770)
        finally:
            os.close(run_fd)
    status_r, status_w = os.pipe()
    release_r, release_w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(status_r)
        os.close(release_w)
        os.set_inheritable(status_w, True)
        os.set_inheritable(release_r, True)
        paths = [str(Path(p)) for p in sys.path if p and Path(p) != Path.cwd()]
        args = [
            "/usr/bin/setpriv",
            "--reuid=" + str(value["authority_uid"]),
            "--regid=" + str(value["authority_gid"]),
            "--clear-groups",
            "--bounding-set=-all",
            "--inh-caps=-all",
            "--ambient-caps=-all",
            "--no-new-privs",
            sys.executable,
            "-m",
            "pitchlog.durable_rights_ledger.authority",
            "_worker",
            "--config",
            str(config_path),
            "--mode",
            mode,
            "--status-fd",
            str(status_w),
            "--release-fd",
            str(release_r),
        ]
        os.execve(
            args[0],
            args,
            {
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": os.pathsep.join(paths),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        os._exit(1)
    os.close(status_w)
    os.close(release_r)
    reaped = False
    stopping = False
    try:
        ready, _, _ = select.select([status_r], [], [], 60)
        message = os.read(status_r, 64) if ready else b""
        if mode == "enroll":
            if message != b"enrolled\n":
                raise AuthorityUnavailable("authority unavailable")
            _, status_code = os.waitpid(pid, 0)
            reaped = True
            if status_code != 0:
                raise AuthorityUnavailable("authority unavailable")
            value["enrollment_state"] = "enrolled"
            _write_root_json(config_path, value, 0o640, value["authority_gid"])
            return
        if message != b"bound\n":
            raise AuthorityUnavailable("authority unavailable")
        target = Path(value["socket_path"])
        observed = target.lstat()
        if (
            not stat.S_ISSOCK(observed.st_mode)
            or observed.st_uid != value["authority_uid"]
        ):
            raise AuthorityUnavailable("authority unavailable")
        os.chown(target, 0, value["client_gid"])
        os.chmod(target, 0o660)
        os.chmod(target.parent, 0o755)
        endpoint = {key: value[key] for key in _ENDPOINT_KEYS}
        _write_root_json(
            Path(value["endpoint_path"]), endpoint, 0o644, value["client_gid"]
        )
        os.write(release_w, b"G")

        def stop(signum: int, frame: Any) -> None:
            nonlocal stopping
            stopping = True
            if not reaped:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        _, status_code = os.waitpid(pid, 0)
        reaped = True
        if status_code != 0 and not stopping:
            raise AuthorityUnavailable("authority unavailable")
    finally:
        for fd in (status_r, release_w):
            os.close(fd)
        # reaped済みPIDを再利用された別processへ送信しない。
        if not reaped:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        if mode == "serve":
            # 起動拒否でもbind用の一時group-writeを残さず、次回の安全な再試行を保つ。
            run_fd = os.open(
                Path(value["socket_path"]).parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            try:
                if os.fstat(run_fd).st_uid != 0:
                    raise AuthorityUnavailable("authority unavailable")
                os.fchmod(run_fd, 0o755)
                os.fsync(run_fd)
            finally:
                os.close(run_fd)


def main() -> int:
    """root配置とcapabilityを落としたworkerを明示modeで起動する。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("enroll", "serve", "_worker"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("enroll", "serve"))
    parser.add_argument("--status-fd", type=int, default=-1)
    parser.add_argument("--release-fd", type=int, default=-1)
    args = parser.parse_args()
    try:
        if args.operation == "_worker":
            _worker(args.mode, args.config, args.status_fd, args.release_fd)
        else:
            _launch(args.operation, args.config)
        return 0
    except Exception:
        print("authority unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
