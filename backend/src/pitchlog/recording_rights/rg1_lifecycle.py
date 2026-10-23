"""RG1実controllerへの接続と、同じ業務DBに束縛した借用を提供する。

このclientはfreshの判定を行わない。rootが配置した設定と実Unix peerを検証し、
controllerが実authorityから取得した借用だけを消費する。controller未提供・
設定欠落・接続断を成功へ補完する経路は持たない。
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, LiteralString, cast
from uuid import UUID

_MAX_FRAME_BYTES = 8192
_SOCKET_TIMEOUT_SECONDS = 2.0
_LOAN_KEY = object()


class RG1ControlUnavailable(RuntimeError):
    """実controllerの入場・保持・解放を確認できないことを表す。"""


def _unavailable() -> RG1ControlUnavailable:
    """接続設定・資格・内部応答を外形へ含めない。"""
    return RG1ControlUnavailable("RG1 control unavailable")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """重複keyを上書きして有効な応答へ変えない。"""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _unavailable()
        result[key] = value
    return result


def _invalid_constant(_value: str) -> Any:
    """JSON外のNaN/Infinityを受理しない。"""
    raise _unavailable()


def _decode_object(body: bytes) -> dict[str, Any]:
    """有限のUTF-8 objectだけを読み取る。"""
    try:
        if not 0 < len(body) <= _MAX_FRAME_BYTES:
            raise _unavailable()
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_invalid_constant,
        )
        if type(value) is not dict:
            raise _unavailable()
        return value
    except (UnicodeError, ValueError, RecursionError) as error:
        raise _unavailable() from error


def _positive_integer(value: object, maximum: int) -> int:
    """boolや浮動小数を識別値にしない。"""
    if type(value) is not int or not 0 < value <= maximum:
        raise _unavailable()
    return value


@dataclass(frozen=True, slots=True)
class BusinessBinding:
    """実Sessionの固定読取が観測したDBとbackendの識別。"""

    system_identifier: str
    database_oid: int
    database_name: str
    postmaster_started_at: datetime
    backend_pid: int

    @classmethod
    def from_text(cls, body: str) -> BusinessBinding:
        """固定関数のtext戻り値を、補完せず閉じた構造へする。"""
        if type(body) is not str:
            raise _unavailable()
        try:
            return cls._from_mapping(_decode_object(body.encode("utf-8")))
        except (UnicodeError, ValueError) as error:
            raise _unavailable() from error

    @classmethod
    def _from_mapping(cls, value: object) -> BusinessBinding:
        """SQL観測とpeer観測で同じ形を要求する。"""
        keys = {
            "system_identifier",
            "database_oid",
            "database_name",
            "postmaster_started_at",
            "backend_pid",
        }
        if type(value) is not dict or set(value) != keys:
            raise _unavailable()
        value = cast("dict[str, object]", value)
        system_id = value["system_identifier"]
        database = value["database_name"]
        started = value["postmaster_started_at"]
        if (
            type(system_id) is not str
            or not 1 <= len(system_id) <= 20
            or not system_id.isascii()
            or not system_id.isdecimal()
            or not 0 < int(system_id) < 2**64
            or str(int(system_id)) != system_id
            or type(database) is not str
            or not database
            or "\0" in database
            or type(started) is not str
            or len(started) > 128
        ):
            raise _unavailable()
        try:
            instant = datetime.fromisoformat(started.replace("Z", "+00:00"))
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise _unavailable()
            instant = instant.astimezone(timezone.utc)
        except (ValueError, OverflowError) as error:
            raise _unavailable() from error
        return cls(
            system_identifier=system_id,
            database_oid=_positive_integer(value["database_oid"], 2**32 - 1),
            database_name=database,
            postmaster_started_at=instant,
            backend_pid=_positive_integer(value["backend_pid"], 2**31 - 1),
        )

    def same_database(self, other: BusinessBinding) -> bool:
        """別接続のPIDは一致条件にせず、DB四要素はすべて一致させる。"""
        return (
            self.system_identifier,
            self.database_oid,
            self.database_name,
            self.postmaster_started_at,
        ) == (
            other.system_identifier,
            other.database_oid,
            other.database_name,
            other.postmaster_started_at,
        )


def _trusted_directory(descriptor: int) -> None:
    """root管理で、非rootが既存entryを置換できない親を要求する。"""
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0:
        raise _unavailable()
    writable = info.st_mode & 0o022
    if writable and not info.st_mode & stat.S_ISVTX:
        raise _unavailable()


def _parent_descriptor(path: Path) -> tuple[int, str]:
    """rootから各階層をNOFOLLOWで開き、symlink・相対参照を拒否する。"""
    if not path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise _unavailable()
    if len(path.parts) < 2 or not path.name:
        raise _unavailable()
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        _trusted_directory(descriptor)
        for part in path.parts[1:-1]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
            _trusted_directory(descriptor)
        return descriptor, path.name
    except BaseException:
        os.close(descriptor)
        raise


def _configuration_bytes(path: Path) -> tuple[bytes, tuple[int, int, str]]:
    """root所有設定を同じFDから有限読取し、差替え検出値も返す。"""
    parent, name = _parent_descriptor(path)
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
    finally:
        os.close(parent)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or info.st_size > _MAX_FRAME_BYTES
        ):
            raise _unavailable()
        body = bytearray()
        while len(body) <= _MAX_FRAME_BYTES:
            part = os.read(descriptor, _MAX_FRAME_BYTES + 1 - len(body))
            if not part:
                break
            body.extend(part)
        if len(body) > _MAX_FRAME_BYTES:
            raise _unavailable()
        content = bytes(body)
        return content, (info.st_dev, info.st_ino, hashlib.sha256(content).hexdigest())
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class _Configuration:
    """検証した設定と読み取ったinodeを固定する。"""

    path: Path
    fingerprint: tuple[int, int, str]
    socket_path: Path
    controller_uid: int
    application_uid: int


def _load_configuration(path: Path) -> _Configuration:
    """設定そのものを接続の成功証拠にせず、peer照合の期待値に限定する。"""
    body, fingerprint = _configuration_bytes(path)
    value = _decode_object(body)
    if set(value) != {
        "schema_version",
        "socket_path",
        "controller_uid",
        "application_uid",
    }:
        raise _unavailable()
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise _unavailable()
    uid = _positive_integer(value["controller_uid"], 2**32 - 1)
    app_uid = _positive_integer(value["application_uid"], 2**32 - 1)
    socket_name = value["socket_path"]
    if (
        app_uid != os.geteuid()
        or uid == app_uid
        or type(socket_name) is not str
        or "\0" in socket_name
        or not 0 < len(os.fsencode(socket_name)) < 108
    ):
        raise _unavailable()
    socket_path = Path(socket_name)
    parent, _name = _parent_descriptor(socket_path)
    os.close(parent)
    return _Configuration(path, fingerprint, socket_path, uid, app_uid)


def _send(sock: socket.socket, message: dict[str, object]) -> None:
    """固定operationを有限frameとして送る。"""
    body = json.dumps(
        message, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()
    if not 0 < len(body) <= _MAX_FRAME_BYTES:
        raise _unavailable()
    sock.sendall(struct.pack("!I", len(body)) + body)


def _receive(sock: socket.socket) -> dict[str, Any]:
    """切断・部分frameを成功応答へ補完しない。"""

    def exact(size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            part = sock.recv(size - len(result))
            if not part:
                raise _unavailable()
            result.extend(part)
        return bytes(result)

    size = struct.unpack("!I", exact(4))[0]
    if not 0 < size <= _MAX_FRAME_BYTES:
        raise _unavailable()
    return _decode_object(exact(size))


@dataclass(frozen=True, slots=True)
class _Activation:
    authority_id: UUID
    ordinal: int
    epoch: int

    @classmethod
    def parse(cls, value: object) -> _Activation:
        """未知fieldと非正規UUIDを受理しない。"""
        if type(value) is not dict or set(value) != {
            "authority_id",
            "ordinal",
            "epoch",
        }:
            raise _unavailable()
        value = cast("dict[str, object]", value)
        identifier = value["authority_id"]
        try:
            parsed = UUID(identifier) if type(identifier) is str else None
        except ValueError as error:
            raise _unavailable() from error
        if parsed is None or str(parsed) != identifier:
            raise _unavailable()
        return cls(
            parsed,
            _positive_integer(value["ordinal"], 2**63 - 1),
            _positive_integer(value["epoch"], 2**63 - 1),
        )


class _GateLoan:
    """実peerの同一channelにだけ結ぶ、不透明なscope用借用。"""

    def __init__(
        self,
        sock: socket.socket,
        config: _Configuration,
        loan_id: int,
        activation: _Activation,
        local_binding: BusinessBinding,
        *,
        key: object,
    ) -> None:
        if key is not _LOAN_KEY:
            raise _unavailable()
        self._socket: socket.socket | None = sock
        self._config = config
        self._loan_id = loan_id
        self._activation = activation
        self.binding = local_binding

    def _exchange(self, operation: str, expected: str) -> None:
        sock = self._socket
        if sock is None:
            raise _unavailable()
        try:
            if _configuration_bytes(self._config.path)[1] != self._config.fingerprint:
                raise _unavailable()
            _send(sock, {"op": operation, "loan_id": self._loan_id})
            response = _receive(sock)
            if (
                set(response) != {"status", "loan_id", "activation"}
                or response["status"] != expected
                or _positive_integer(response["loan_id"], 2**63 - 1) != self._loan_id
                or _Activation.parse(response["activation"]) != self._activation
            ):
                raise _unavailable()
        except (OSError, ValueError, RG1ControlUnavailable) as error:
            self._socket = None
            sock.close()
            raise _unavailable() from error

    def assert_held(self) -> None:
        """controllerが実fenceを確認した同じ借用だけを保持済みとする。"""
        self._exchange("assert-held", "held")

    def release(self) -> None:
        """PGの確定/取消の後にだけ呼び、解放不明も成功にしない。"""
        sock = self._socket
        try:
            self._exchange("release", "released")
        finally:
            self._socket = None
            if sock is not None:
                sock.close()

    def abandon(self) -> None:
        """PG終結不明時は正常解放を送らず、実channelの未終端を残す。"""
        sock = self._socket
        self._socket = None
        if sock is not None:
            sock.close()


class _RuntimeClient:
    """root設定を固定し、入場時に毎回実peerを確認する。"""

    def __init__(self, config: _Configuration) -> None:
        self._config = config

    def borrow(self, binding: BusinessBinding) -> _GateLoan:
        """callerからproofを受け取らず、実DB識別とpeerの実証を照合する。"""
        sock: socket.socket | None = None
        try:
            config = self._config
            if _configuration_bytes(config.path)[1] != config.fingerprint:
                raise _unavailable()
            parent, name = _parent_descriptor(config.socket_path)
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0:
                    raise _unavailable()
            finally:
                os.close(parent)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(_SOCKET_TIMEOUT_SECONDS)
            sock.connect(str(config.socket_path))
            _pid, uid, _gid = struct.unpack(
                "3i",
                sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12),
            )
            if uid != config.controller_uid:
                raise _unavailable()
            _send(sock, {"op": "borrow"})
            response = _receive(sock)
            if set(response) != {"status", "loan_id", "binding", "activation"}:
                raise _unavailable()
            if response["status"] != "active":
                raise _unavailable()
            remote = BusinessBinding._from_mapping(response["binding"])
            if not binding.same_database(remote):
                raise _unavailable()
            loan = _GateLoan(
                sock,
                config,
                _positive_integer(response["loan_id"], 2**63 - 1),
                _Activation.parse(response["activation"]),
                binding,
                key=_LOAN_KEY,
            )
            loan.assert_held()
            return loan
        except (OSError, ValueError, RG1ControlUnavailable) as error:
            if sock is not None:
                sock.close()
            raise _unavailable() from error


_runtime_client: _RuntimeClient | None = None


def configure_runtime(config_path: Path | None) -> None:
    """startupでroot設定を検査し、未設定/不正なら書込を閉じる。"""
    global _runtime_client
    _runtime_client = None
    if config_path is not None:
        try:
            _runtime_client = _RuntimeClient(_load_configuration(config_path))
        except (OSError, ValueError, RG1ControlUnavailable) as error:
            raise _unavailable() from error


def borrow_gate(binding: BusinessBinding) -> _GateLoan:
    """未設定を実行許可にせず、実clientへだけ借用を委譲する。"""
    client = _runtime_client
    if client is None:
        raise _unavailable()
    return client.borrow(binding)


def serve_fresh_controller(config_path: Path) -> None:
    """root配置と実authorityだけで一度限りのfresh controllerを起動する。

    設定は接続先・UIDの非秘密値だけで、fresh証明の入力ではない。
    通常再起動・旧DB復元・非zero復旧の自動解除はこの入口に含めない。
    """
    import ctypes
    import importlib
    import select
    import threading

    import psycopg

    if os.geteuid() != 0:
        raise _unavailable()
    body, fingerprint = _configuration_bytes(config_path)
    config = _decode_object(body)
    if (
        set(config)
        != {
            "schema_version",
            "socket_path",
            "controller_uid",
            "application_uid",
            "business_socket_directory",
            "business_port",
            "business_database",
            "business_server_uid",
            "ledger_endpoint",
        }
        or type(config["schema_version"]) is not int
        or config["schema_version"] != 1
    ):
        raise _unavailable()
    controller_uid = _positive_integer(config["controller_uid"], 2**32 - 1)
    app_uid = _positive_integer(config["application_uid"], 2**32 - 1)
    server_uid = _positive_integer(config["business_server_uid"], 2**32 - 1)
    port = _positive_integer(config["business_port"], 65535)
    if len({controller_uid, app_uid, server_uid}) != 3:
        raise _unavailable()
    for name in ("socket_path", "business_socket_directory", "ledger_endpoint"):
        value = config[name]
        if type(value) is not str or "\0" in value or not Path(value).is_absolute():
            raise _unavailable()
    database = config["business_database"]
    if type(database) is not str or not database or "\0" in database:
        raise _unavailable()
    socket_path = Path(config["socket_path"])
    if not 0 < len(os.fsencode(socket_path)) < 108:
        raise _unavailable()
    parent, _name = _parent_descriptor(socket_path)
    os.close(parent)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        # 既存entryをunlinkして再起動・別controllerを乗っ取らない。
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o666)
        listener.listen(64)
        listener.settimeout(0.2)
        os.setgroups([])
        os.setgid(controller_uid)
        os.setuid(controller_uid)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(38, 1, 0, 0, 0) != 0 or os.geteuid() != controller_uid:
            raise _unavailable()
        # 動的解決先はこの固定製品packageだけ。未供給を代替実装で補完しない。
        package = importlib.import_module("pitchlog.durable_rights_ledger")
        ledger = package.DurableLedger(Path(config["ledger_endpoint"]))
        with psycopg.connect(
            host=config["business_socket_directory"],
            port=port,
            dbname=database,
            user="pitchlog_rg1_control_actor",
            passfile="/dev/null",
            connect_timeout=3,
            autocommit=True,
        ) as connection:
            with socket.fromfd(
                connection.fileno(), socket.AF_UNIX, socket.SOCK_STREAM
            ) as peer:
                _pid, peer_uid, _gid = struct.unpack(
                    "3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )
                if peer_uid != server_uid:
                    raise _unavailable()
            row = connection.execute("SELECT session_user, current_user").fetchone()
            if row != ("pitchlog_rg1_control_actor", "pitchlog_rg1_control_actor"):
                raise _unavailable()
            connection.execute("SET statement_timeout = '3s'")

            def control(name: str) -> object:
                # callerのSQLや引数は受け取らない有限の制御面。
                statements: dict[str, LiteralString] = {
                    "take": "SELECT rg1_control.try_controller_lease()",
                    "close": "SELECT rg1_control.close_gate()",
                    "closed": "SELECT rg1_control.read_closed_gate()",
                    "open": "SELECT rg1_control.open_fresh_gate()",
                    "alive": "SELECT rg1_control.controller_lease_alive()",
                    "release": "SELECT rg1_control.release_controller_lease()",
                }
                result = connection.execute(statements[name]).fetchone()
                if result is None or len(result) != 1:
                    raise _unavailable()
                return result[0]

            if control("take") is not True or control("close") is not True:
                raise _unavailable()
            closed = control("closed")
            if type(closed) is not dict or closed.get("gate_state") != "closed":
                raise _unavailable()
            binding = BusinessBinding._from_mapping(
                {key: value for key, value in closed.items() if key != "gate_state"}
            )
            if binding.database_name != database:
                raise _unavailable()
            with ledger.fresh_activation() as (attestation, fence):
                if (
                    attestation.business_system_id != binding.system_identifier
                    or attestation.database != binding.database_name
                    or datetime.fromisoformat(
                        attestation.postmaster_started_at
                    ).astimezone(timezone.utc)
                    != binding.postmaster_started_at
                    or type(attestation.highwater) is not int
                    or attestation.highwater != 0
                    or type(attestation.reservation_count) is not int
                    or attestation.reservation_count != 0
                ):
                    raise _unavailable()
                activation = _Activation.parse(
                    {
                        "authority_id": str(attestation.authority_id),
                        "ordinal": attestation.activation_ordinal,
                        "epoch": attestation.pair_epoch,
                    }
                )
                fence.assert_held()
                if control("open") is not True:
                    raise _unavailable()
                mutex = threading.RLock()
                stop = threading.Event()
                loans: dict[int, socket.socket] = {}
                workers: list[threading.Thread] = []
                sequence = 0

                def assert_live() -> None:
                    if (
                        stop.is_set()
                        or _configuration_bytes(config_path)[1] != fingerprint
                    ):
                        raise _unavailable()
                    fence.assert_held()
                    if control("alive") is not True:
                        raise _unavailable()

                def reply(status: str, loan_id: int) -> dict[str, object]:
                    return {
                        "status": status,
                        "loan_id": loan_id,
                        "activation": {
                            "authority_id": str(activation.authority_id),
                            "ordinal": activation.ordinal,
                            "epoch": activation.epoch,
                        },
                    }

                def session(channel: socket.socket) -> None:
                    nonlocal sequence
                    loan_id: int | None = None
                    released = False
                    try:
                        channel.settimeout(_SOCKET_TIMEOUT_SECONDS)
                        _pid, uid, _gid = struct.unpack(
                            "3i",
                            channel.getsockopt(
                                socket.SOL_SOCKET, socket.SO_PEERCRED, 12
                            ),
                        )
                        if uid != app_uid:
                            return
                        if _receive(channel) != {"op": "borrow"}:
                            raise _unavailable()
                        with mutex:
                            assert_live()
                            if len(loans) >= 128:
                                raise _unavailable()
                            sequence += 1
                            loan_id = sequence
                            loans[loan_id] = channel
                            response = reply("active", loan_id)
                            response["binding"] = {
                                "system_identifier": binding.system_identifier,
                                "database_oid": binding.database_oid,
                                "database_name": binding.database_name,
                                "postmaster_started_at": (
                                    binding.postmaster_started_at.isoformat()
                                ),
                                "backend_pid": binding.backend_pid,
                            }
                            _send(channel, response)
                        while not stop.is_set():
                            if not select.select([channel], [], [], 0.2)[0]:
                                continue
                            request = _receive(channel)
                            if (
                                set(request) != {"op", "loan_id"}
                                or _positive_integer(request["loan_id"], 2**63 - 1)
                                != loan_id
                            ):
                                raise _unavailable()
                            with mutex:
                                assert_live()
                                if loans.get(loan_id) is not channel:
                                    raise _unavailable()
                                if request["op"] == "assert-held":
                                    _send(channel, reply("held", loan_id))
                                elif request["op"] == "release":
                                    loans.pop(loan_id)
                                    released = True
                                    _send(channel, reply("released", loan_id))
                                    return
                                else:
                                    raise _unavailable()
                    except Exception:
                        # 内部応答・SQL・資格をログ/外形へ漏らさない。
                        stop.set()
                    finally:
                        with mutex:
                            if loan_id is not None:
                                loans.pop(loan_id, None)
                                if not released:
                                    stop.set()
                        channel.close()

                try:
                    while not stop.is_set():
                        with mutex:
                            assert_live()
                        try:
                            channel, _address = listener.accept()
                        except TimeoutError:
                            continue
                        workers[:] = [worker for worker in workers if worker.is_alive()]
                        if len(workers) >= 128:
                            channel.close()
                            continue
                        worker = threading.Thread(
                            target=session, args=(channel,), daemon=True
                        )
                        workers.append(worker)
                        worker.start()
                finally:
                    stop.set()
                    # closeは同PG sessionで確定。途中故障時はfresh ENDへ補完しない。
                    with mutex:
                        if control("close") is not True:
                            raise _unavailable()
                    for worker in workers:
                        worker.join(timeout=3)
                # この最初小単位は再起動を解除しない。異常停止の未終端を残す。
                raise _unavailable()
    finally:
        listener.close()
