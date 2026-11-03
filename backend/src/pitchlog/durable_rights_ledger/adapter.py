"""固定制限関数だけで外部同期台帳を利用する候補adapter。"""

from __future__ import annotations

import json
import math
import socket
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, RLock, Timer
from time import monotonic, sleep
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
from psycopg import capabilities, pq

from pitchlog.recording_rights.initial_grant import (
    DurableGenerationSource,
    InitialGrantUnavailable,
    RecoveryEpochFence,
    ReservedGeneration,
)

from .witness import (
    ProtectedJournal,
    WitnessOutcomeUnconfirmed,
    WitnessUnavailable,
    _unique,
)

_MAX = 2**63 - 1
_SYNC_NAMES = "FIRST 1 (ledger_standby)"
Operation = Literal[
    "identity",
    "business_identity",
    "fence",
    "reserve",
    "claim",
    "read",
    "advance",
    "audit",
    "reconcile",
    "lookup",
    "confirm_state",
]


class LedgerUnavailable(InitialGrantUnavailable):
    """未確認の接続・設定・入力・制限関数拒否を表す。"""


class LedgerOutcomeUnconfirmed(LedgerUnavailable):
    """耐久処理の結果が不明であり、未使用と断定できないことを表す。"""


@dataclass(frozen=True, slots=True)
class FreshActivationAttestation:
    """実開始frameに束縛された初回時点のmetadata。単体では認可証明ではない。"""

    authority_id: UUID
    activation_ordinal: int
    business_system_id: str
    database: str
    postmaster_started_at: str
    pair_epoch: int
    highwater: int
    reservation_count: int

    def __post_init__(self) -> None:
        """JSON風の型や未知のfresh値を実証metadataへ変換しない。"""
        if (
            type(self.authority_id) is not UUID
            or type(self.activation_ordinal) is not int
            or not 0 < self.activation_ordinal < 2**64
            or any(
                type(v) is not str or not v
                for v in (
                    self.business_system_id,
                    self.database,
                    self.postmaster_started_at,
                )
            )
            or type(self.pair_epoch) is not int
            or self.pair_epoch != 1
            or type(self.highwater) is not int
            or self.highwater != 0
            or type(self.reservation_count) is not int
            or self.reservation_count != 0
        ):
            raise LedgerUnavailable("ledger unavailable")


def _activation_wire(value: FreshActivationAttestation) -> dict[str, Any]:
    return {
        "authority_id": str(value.authority_id),
        "activation_ordinal": value.activation_ordinal,
        "business_system_id": value.business_system_id,
        "database": value.database,
        "postmaster_started_at": value.postmaster_started_at,
        "pair_epoch": value.pair_epoch,
        "highwater": value.highwater,
        "reservation_count": value.reservation_count,
    }


def _activation_from(value: object) -> FreshActivationAttestation:
    try:
        if type(value) is not dict:
            raise ValueError
        data = cast(dict[str, Any], value)
        if (
            set(data)
            != {
                "authority_id",
                "activation_ordinal",
                "business_system_id",
                "database",
                "postmaster_started_at",
                "pair_epoch",
                "highwater",
                "reservation_count",
            }
            or type(data["authority_id"]) is not str
        ):
            raise ValueError
        authority_id = UUID(data["authority_id"])
        if str(authority_id) != data["authority_id"]:
            raise ValueError
        return FreshActivationAttestation(
            authority_id,
            data["activation_ordinal"],
            data["business_system_id"],
            data["database"],
            data["postmaster_started_at"],
            data["pair_epoch"],
            data["highwater"],
            data["reservation_count"],
        )
    except Exception:
        raise LedgerUnavailable("ledger unavailable") from None


def _activation_event(
    ordinal: int, value: dict[str, Any]
) -> FreshActivationAttestation:
    business = value["business"]
    if type(business) is not dict or set(business) != {
        "system_id",
        "database",
        "started_at",
    }:
        raise LedgerUnavailable("ledger unavailable")
    return _activation_from(
        {
            "authority_id": value["authority_id"],
            "activation_ordinal": ordinal,
            "business_system_id": business["system_id"],
            "database": business["database"],
            "postmaster_started_at": business["started_at"],
            "pair_epoch": value["epoch"],
            "highwater": value["highwater"],
            "reservation_count": value["reservation_count"],
        }
    )


@dataclass(frozen=True, slots=True)
class LedgerEndpoints:
    """独立した実接続先。資格はreprへ含めない。"""

    primary_dsn: str = field(repr=False)
    standby_dsn: str = field(repr=False)
    business_dsn: str = field(repr=False)
    control_dsn: str = field(repr=False)
    timeout: float = 3.0

    def __post_init__(self) -> None:
        """無限待機やboolを設定として受理しない。"""
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0.1 <= self.timeout <= 30
            or any(
                type(s) is not str or not s
                for s in (
                    self.primary_dsn,
                    self.standby_dsn,
                    self.business_dsn,
                    self.control_dsn,
                )
            )
        ):
            raise LedgerUnavailable("ledger unavailable")


def _require_client() -> None:
    """Legacy cancelへfallbackするclientを接続前に拒否する。"""
    try:
        valid = pq.version() >= 170000 and capabilities.has_cancel_safe()
    except Exception:
        valid = False
    if not valid:
        raise LedgerUnavailable("ledger unavailable")


def _connect(dsn: str, timeout: float) -> psycopg.Connection[Any]:
    """接続と各statement/lockの期限を固定する。"""
    _require_client()
    try:
        return psycopg.connect(
            dsn,
            connect_timeout=math.ceil(timeout),
            options=(
                f"-c statement_timeout={math.ceil(timeout * 1000)} "
                f"-c lock_timeout={math.ceil(timeout * 1000)} "
                "-c synchronous_commit=on"
            ),
        )
    except Exception:
        raise LedgerUnavailable("ledger unavailable") from None


@contextmanager
def _connection(dsn: str, timeout: float) -> Iterator[psycopg.Connection[Any]]:
    """読取transactionを暗黙commitせず、接続を毎回破棄する。"""
    connection = _connect(dsn, timeout)
    try:
        yield connection
    finally:
        connection.close()


def _query(
    connection: psycopg.Connection[Any],
    operation: Operation,
    params: tuple[object, ...] = (),
) -> tuple[Any, ...]:
    """閉じた操作集合を固定SQLへ写し、単一行だけ取得する。"""
    statements = {
        "identity": (
            "SELECT session_user::text, current_user::text, pitchlog_ledger.identity()"
        ),
        "business_identity": (
            "SELECT session_user::text, current_user::text, "
            "pitchlog_ledger_observer.identity()"
        ),
        "fence": "SELECT pitchlog_ledger.epoch_fence()",
        "reserve": "SELECT * FROM pitchlog_ledger.reserve(%s, %s, %s, %s)",
        "claim": "SELECT * FROM pitchlog_ledger.claim(%s, %s, %s, %s)",
        "read": "SELECT * FROM pitchlog_ledger.reservation(%s, %s, %s, %s)",
        "lookup": "SELECT CASE WHEN r.generation IS NULL THEN NULL ELSE "
        "jsonb_build_array(r.generation,r.recovery_generation,r.tenant_id,r.game_id,r.start_request_id,r.claimed,r.quarantined)"
        " END FROM (SELECT * FROM pitchlog_ledger.reservation(%s,%s,%s,%s))"
        " r RIGHT JOIN (SELECT 1) singleton ON true",
        "advance": "SELECT pitchlog_ledger.advance_epoch(%s)",
        "confirm_state": "SELECT pitchlog_ledger.confirm_state(%s,%s,%s)",
        "audit": "SELECT pitchlog_ledger.audit_page(%s, %s)",
        "reconcile": (
            "SELECT * FROM pitchlog_ledger.reconcile(%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        ),
    }
    # operationの未知値・引数数もDBへ到達させない。
    arities = {
        "identity": 0,
        "business_identity": 0,
        "fence": 0,
        "reserve": 4,
        "claim": 4,
        "read": 4,
        "lookup": 4,
        "advance": 1,
        "audit": 2,
        "reconcile": 9,
        "confirm_state": 3,
    }
    if operation not in statements or len(params) != arities[operation]:
        raise LedgerUnavailable("ledger unavailable")
    from typing import LiteralString

    try:
        row = connection.execute(
            cast(LiteralString, statements[operation]), params
        ).fetchone()
        if row is None:
            raise LedgerUnavailable("ledger unavailable")
        return row
    except Exception:
        raise LedgerUnavailable("ledger unavailable") from None


def _cancel_commit(connection: psycopg.Connection[Any], timeout: float) -> None:
    """期限付き取消だけを実行するexact私有境界。"""
    connection.cancel_safe(timeout=timeout)


def _commit(connection: psycopg.Connection[Any], timeout: float) -> None:
    """同期待機を有限にし、取消と競合した成功戻りも未確定にする。"""
    expired = Event()
    cancel_failed = Event()

    def cancel() -> None:
        expired.set()
        try:
            _cancel_commit(connection, timeout)
        except Exception:
            cancel_failed.set()

    deadline = monotonic() + timeout
    timer = Timer(timeout, cancel)
    timer.daemon = True
    timer.start()
    failed = False
    try:
        connection.commit()
    except Exception:
        failed = True
    finally:
        timer.cancel()
        timer.join(timeout + 0.5)
    if (
        monotonic() >= deadline
        or failed
        or expired.is_set()
        or cancel_failed.is_set()
        or timer.is_alive()
    ):
        # 呼出元は必ず接続を閉じる。別要求へ貸し戻さない。
        raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None


def _positive(value: object) -> int:
    if type(value) is not int or not 0 < value <= _MAX:
        raise LedgerUnavailable("ledger unavailable")
    return value


def _owner(values: tuple[object, ...]) -> None:
    if len(values) != 4 or any(type(v) is not UUID for v in values):
        raise LedgerUnavailable("ledger unavailable")


def _lsn(value: object) -> int:
    try:
        if type(value) is not str:
            raise ValueError
        parts = value.split("/")
        if len(parts) != 2:
            raise ValueError
        return (int(parts[0], 16) << 32) + int(parts[1], 16)
    except (ValueError, TypeError):
        raise LedgerUnavailable("ledger unavailable") from None


def _identity(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    received = _query(connection, "identity")
    if (
        len(received) != 3
        or received[0] != received[1]
        or received[0] not in ("pitchlog_ledger_app", "pitchlog_ledger_control")
    ):
        raise LedgerUnavailable("ledger unavailable")
    value = received[2]
    if type(value) is not dict:
        raise LedgerUnavailable("ledger unavailable")
    return value


class _Fence(RecoveryEpochFence):
    """生きた同一transactionだけに有効な共有epochロック。"""

    def __init__(
        self,
        ledger: _PgLedgerPair,
        connection: psycopg.Connection[Any],
        generation: int,
    ) -> None:
        self._ledger = ledger
        self._connection = connection
        self._generation = generation
        self._active = True

    @property
    def generation(self) -> int:
        """ロック取得時の世代を返す。"""
        self.assert_held()
        return self._generation

    def assert_held(self) -> None:
        """終了済み・失効・接続断は失敗閉鎖する。"""
        if (
            not self._active
            or self._connection.info.transaction_status != pq.TransactionStatus.INTRANS
        ):
            raise LedgerUnavailable("ledger unavailable")
        self._ledger._check_business()
        self._ledger._check_primary(_identity(self._connection))
        if _positive(_query(self._connection, "fence")[0]) != self._generation:
            raise LedgerUnavailable("ledger unavailable")


class _PgLedgerPair:
    """authorityがjournal照合に用いる私有の実同期PG部品。"""

    def __init__(
        self,
        endpoints: LedgerEndpoints,
        *,
        business_peer: tuple[int, int] | None = None,
    ) -> None:
        """隔離初回pairを同定し、その起動identityへ寿命を固定する。"""
        if type(endpoints) is not LedgerEndpoints:
            raise LedgerUnavailable("ledger unavailable")
        _require_client()
        self._endpoints = endpoints
        self._business_peer = business_peer
        self._lock = RLock()
        self._closed = False
        self._primary: dict[str, Any] = {}
        self._standby: dict[str, Any] = {}
        self._business = self._observe_business()
        business_id = self._business["system_id"]
        with _connection(endpoints.primary_dsn, endpoints.timeout) as connection:
            primary = _identity(connection)
        with _connection(endpoints.standby_dsn, endpoints.timeout) as connection:
            standby = _identity(connection)
        if (
            type(primary.get("system_id")) is not str
            or primary["system_id"] == business_id
            or primary["system_id"] != standby.get("system_id")
            or primary.get("timeline") != standby.get("timeline")
            or primary.get("timeline") != 1
        ):
            raise LedgerUnavailable("ledger unavailable")
        self._primary = primary
        self._standby = standby
        self._check_primary(primary)
        self._check_standby(standby)

    def _observe_business(self) -> dict[str, Any]:
        with _connection(
            self._endpoints.business_dsn, self._endpoints.timeout
        ) as connection:
            if self._business_peer is not None:
                # v2のroot固定値を、実接続のkernel主体とも毎回照合する。
                with socket.fromfd(
                    connection.fileno(), socket.AF_UNIX, socket.SOCK_STREAM
                ) as peer:
                    _, uid, gid = struct.unpack(
                        "3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                    )
                if (uid, gid) != self._business_peer:
                    raise LedgerUnavailable("ledger unavailable")
            role = _query(connection, "business_identity")
        if (
            len(role) != 3
            or role[:2] != ("pitchlog_ledger_identity_probe",) * 2
            or type(role[2]) is not dict
            or set(role[2])
            != {"system_id", "database", "started_at", "version", "recovery"}
            or any(
                type(role[2][key]) is not str or not role[2][key]
                for key in ("system_id", "database", "started_at")
            )
            or type(role[2]["version"]) is not int
            or role[2]["version"] != 170011
            or role[2]["recovery"] is not False
        ):
            raise LedgerUnavailable("ledger unavailable")
        return role[2]

    def _check_business(self) -> None:
        # 同じsystem_idでも業務DB再起動後は別のclose/drain証明なしに再開しない。
        if self._observe_business() != self._business:
            self._closed = True
            raise LedgerUnavailable("ledger unavailable")

    def _check_common(
        self, value: dict[str, Any], pinned: dict[str, Any], recovery: bool
    ) -> None:
        if (
            self._closed
            or value.get("recovery") is not recovery
            or value.get("version") != 170011
            or value.get("fsync") != "on"
            or value.get("full_page_writes") != "on"
            or any(
                value.get(k) != pinned.get(k) or value.get(k) is None
                for k in ("system_id", "timeline", "started_at")
            )
        ):
            self._closed = True
            raise LedgerUnavailable("ledger unavailable")
        _positive(value.get("epoch"))

    def _check_primary(self, value: dict[str, Any]) -> None:
        self._check_common(value, self._primary, False)
        peers = value.get("peers")
        if (
            value.get("synchronous_commit") != "on"
            or value.get("synchronous_standby_names") != _SYNC_NAMES
            or type(peers) is not list
            or len(peers) != 1
            or peers[0].get("name") != "ledger_standby"
            or peers[0].get("user") != "pitchlog_ledger_replicator"
            or peers[0].get("address") != self._standby.get("address")
            or peers[0].get("state") != "streaming"
            or peers[0].get("sync_state") != "sync"
        ):
            raise LedgerUnavailable("ledger unavailable")

    def _check_standby(self, value: dict[str, Any]) -> None:
        self._check_common(value, self._standby, True)

    def _confirmed(
        self,
        primary: psycopg.Connection[Any],
        params: tuple[object, ...] | None,
        expected: tuple[Any, ...],
    ) -> None:
        # COMMIT後のprimary flush位置以上を指定peerで確認し、実standbyで再読する。
        try:
            identity = _identity(primary)
            self._check_primary(identity)
            barrier = _lsn(identity.get("wal"))
            deadline = monotonic() + self._endpoints.timeout
            while monotonic() < deadline:
                with _connection(
                    self._endpoints.standby_dsn, self._endpoints.timeout
                ) as connection:
                    standby = _identity(connection)
                    self._check_standby(standby)
                    peer = _identity(primary)
                    self._check_primary(peer)
                    if (
                        _lsn(standby.get("received_wal")) >= barrier
                        and _lsn(peer["peers"][0].get("flush")) >= barrier
                    ):
                        if params is None:
                            actual = (standby.get("epoch"),)
                        else:
                            value = _query(connection, "lookup", params)[0]
                            actual = None if value is None else _row(value, params)
                        # durable receiveは実同期済み位置。
                        # 可視rowの再読でCOMMIT replayも確認する。
                        if actual == expected:
                            return
                sleep(0.02)
        except Exception:
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
        raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")

    def _confirm_state(self, highwater: int, count: int) -> None:
        # 一回enroll/attach専用。保護flockの下、未終端lease検査後か発行前にだけ呼ぶ。
        connection = _connect(self._endpoints.control_dsn, self._endpoints.timeout)
        try:
            self._check_primary(_identity(connection))
            if _query(connection, "confirm_state", (1, highwater, count)) != (1,):
                raise LedgerUnavailable("ledger unavailable")
            _commit(connection, self._endpoints.timeout)
            self._confirmed(connection, None, (1,))
        finally:
            connection.close()

    def current_recovery_generation(self) -> int:
        """primaryと実standbyの現epoch一致を返す。"""
        with (
            self._lock,
            _connection(
                self._endpoints.primary_dsn, self._endpoints.timeout
            ) as connection,
        ):
            value = _identity(connection)
            self._check_primary(value)
            epoch = _positive(value.get("epoch"))
            self._confirmed(connection, None, (epoch,))
            return epoch

    def _mutate(
        self,
        operation: Literal["reserve", "claim", "advance"],
        params: tuple[object, ...],
        journal: ProtectedJournal,
    ) -> tuple[Any, ...]:
        if type(journal) is not ProtectedJournal or operation == "advance":
            raise LedgerUnavailable("ledger unavailable")
        with self._lock:
            connection = _connect(
                self._endpoints.control_dsn
                if operation == "advance"
                else self._endpoints.primary_dsn,
                self._endpoints.timeout,
            )
            try:
                self._check_primary(_identity(connection))
                row = _checked_row(_query(connection, operation, params), params)
                if row[6] or row[5] is not (operation == "claim"):
                    raise LedgerUnavailable("ledger unavailable")
                intent = journal.append(
                    _encode_event(
                        {
                            "event": "intent",
                            "operation": operation,
                            "params": [str(value) for value in params],
                            "row": _wire_row(row),
                        }
                    )
                )
                _commit(connection, self._endpoints.timeout)
                self._confirmed(
                    connection, None if operation == "advance" else params, row
                )
                journal.append(
                    _encode_event({"event": "confirmed", "intent": intent.ordinal})
                )
                return row
            except WitnessOutcomeUnconfirmed:
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            except WitnessUnavailable:
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            finally:
                # 未確定の接続を再利用せず、消費取消/rollback成功を主張しない。
                connection.close()

    @contextmanager
    def recovery_fence(self) -> Iterator[RecoveryEpochFence]:
        """呼出元の業務commit終了まで共有epoch行ロックを借用する。"""
        connection = _connect(self._endpoints.primary_dsn, self._endpoints.timeout)
        fence: _Fence | None = None
        try:
            self._check_primary(_identity(connection))
            fence = _Fence(self, connection, _positive(_query(connection, "fence")[0]))
            fence.assert_held()
            yield fence
            fence.assert_held()
        finally:
            if fence is not None:
                fence._active = False
            connection.close()


def _checked_row(row: tuple[Any, ...], params: tuple[object, ...]) -> tuple[Any, ...]:
    if (
        len(row) != 7
        or row[2:5] != params[1:]
        or type(row[5]) is not bool
        or type(row[6]) is not bool
    ):
        raise LedgerUnavailable("ledger unavailable")
    _positive(row[0])
    _positive(row[1])
    return row


def _wire_row(row: tuple[Any, ...]) -> list[Any]:
    return [row[0], row[1], *(str(value) for value in row[2:5]), row[5], row[6]]


def _row(value: object, params: tuple[object, ...]) -> tuple[Any, ...]:
    if type(value) is not list or len(value) != 7:
        raise LedgerUnavailable("ledger unavailable")
    try:
        if any(type(v) is not str for v in value[2:5]):
            raise ValueError
        row = (
            value[0],
            value[1],
            *(UUID(cast(str, v)) for v in value[2:5]),
            value[5],
            value[6],
        )
        return _checked_row(row, params)
    except Exception:
        raise LedgerUnavailable("ledger unavailable") from None


def _encode_event(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _events(journal: ProtectedJournal) -> Iterator[tuple[int, dict[str, Any]]]:
    for frame in journal.records():
        try:
            value = json.loads(frame.payload, object_pairs_hook=_unique)
            if type(value) is not dict or type(value.get("event")) is not str:
                raise ValueError
            shapes = {
                "enrolled": {
                    "event",
                    "authority_id",
                    "primary",
                    "standby",
                    "business",
                    "epoch",
                },
                "attached": {"event", "primary", "standby", "business"},
                "intent": {"event", "operation", "params", "row"},
                "confirmed": {"event", "intent"},
                "quarantined": {"event", "intent", "row"},
                "lease_open": {"event", "epoch"},
                "activation_open": {
                    "event",
                    "authority_id",
                    "business",
                    "epoch",
                    "highwater",
                    "reservation_count",
                },
                "lease_close": {"event", "lease"},
                "binding_intent": {"event", "lease", "record"},
                "binding_rejected": {"event", "lease"},
                "binding_published": {"event", "lease"},
                "binding_quarantined": {"event", "lease"},
                "binding_close_requested": {"event", "lease"},
                "binding_terminal": {"event", "lease", "outcome"},
            }
            if value["event"] not in shapes or set(value) != shapes[value["event"]]:
                raise ValueError
            if value["event"] == "intent":
                _params(value["params"])
                _row(value["row"], _params(value["params"]))
                if value["operation"] not in ("reserve", "claim"):
                    raise ValueError
                if value["row"][6] is not False or value["row"][5] is not (
                    value["operation"] == "claim"
                ):
                    raise ValueError
            if value["event"] in ("confirmed", "quarantined"):
                if (
                    type(value["intent"]) is not int
                    or not 0 < value["intent"] < frame.ordinal
                ):
                    raise ValueError
            if value["event"] in {
                "lease_close",
                "binding_intent",
                "binding_rejected",
                "binding_quarantined",
                "binding_published",
                "binding_close_requested",
                "binding_terminal",
            }:
                if (
                    type(value["lease"]) is not int
                    or not 0 < value["lease"] < frame.ordinal
                ):
                    raise ValueError
            if value["event"] == "binding_intent":
                from pitchlog.sync.control_provider.binding_control import (
                    _writer_from_wire,
                )

                record = value["record"]
                if type(record) is not dict or set(record) != {
                    "tenant_id",
                    "attempt_id",
                    "phase_id",
                    "lease_id",
                    "recovery_generation",
                    "close_id",
                    "phase",
                    "writer",
                    "nonce_digest",
                    "expires_at",
                }:
                    raise ValueError
                for name in (
                    "tenant_id",
                    "attempt_id",
                    "phase_id",
                    "lease_id",
                    "close_id",
                ):
                    if str(UUID(record[name])) != record[name]:
                        raise ValueError
                if (
                    type(record["nonce_digest"]) is not str
                    or len(bytes.fromhex(record["nonce_digest"])) != 32
                ):
                    raise ValueError
                _positive(record["recovery_generation"])
                _writer_from_wire(record["writer"])
            if value["event"] == "binding_terminal" and value["outcome"] not in (
                "COMMITTED",
                "ROLLBACK_CONFIRMED",
            ):
                raise ValueError
            if value["event"] in ("enrolled", "lease_open"):
                _positive(value["epoch"])
            if value["event"] == "activation_open":
                _activation_event(frame.ordinal, value)
            yield frame.ordinal, value
        except Exception:
            raise LedgerUnavailable("ledger unavailable") from None


def _params(value: object) -> tuple[UUID, ...]:
    try:
        if type(value) is not list or len(value) != 4:
            raise ValueError
        if any(type(item) is not str for item in value):
            raise ValueError
        result = tuple(UUID(cast(str, item)) for item in value)
        if [str(item) for item in result] != value:
            raise ValueError
        _owner(result)
        return result
    except Exception:
        raise LedgerUnavailable("ledger unavailable") from None


def _resolved(
    journal: ProtectedJournal, ordinal: int, event: dict[str, Any]
) -> tuple[Any, ...] | None:
    found = None
    for _, current in _events(journal):
        if (
            current["event"] in ("confirmed", "quarantined")
            and current["intent"] == ordinal
        ):
            if found is not None:
                raise LedgerUnavailable("ledger unavailable")
            row = _row(event["row"], _params(event["params"]))
            if current["event"] == "quarantined":
                altered = _row(current["row"], _params(event["params"]))
                if (
                    altered[:5] != row[:5]
                    or altered[6] is not True
                    or (row[5] and not altered[5])
                ):
                    raise LedgerUnavailable("ledger unavailable")
                row = altered
            found = row
    return found


def _metadata(pair: _PgLedgerPair) -> dict[str, Any]:
    def projection(value: dict[str, Any]) -> dict[str, Any]:
        return {key: value[key] for key in ("system_id", "started_at")}

    return {
        "primary": projection(pair._primary),
        "standby": projection(pair._standby),
        "business": {
            **projection(pair._business),
            "database": pair._business["database"],
        },
    }


def _validate_binding_rejections(events: list[tuple[int, dict[str, Any]]]) -> None:
    """確定拒否の終結証拠を、未知leaseや別状態へ拡張しない。"""
    for ordinal, event in events:
        if event["event"] != "binding_rejected":
            continue
        lease = event["lease"]
        openings = [(i, v) for i, v in events if i == lease]
        same = [(i, v) for i, v in events if v.get("lease") == lease]
        intents = [(i, v) for i, v in same if v["event"] == "binding_intent"]
        rejected = [i for i, v in same if v["event"] == "binding_rejected"]
        closes = [i for i, v in same if v["event"] == "lease_close"]
        if (
            len(openings) != 1
            or openings[0][1]["event"] != "lease_open"
            or len(intents) != 1
            or not lease < intents[0][0] < ordinal
            or rejected != [ordinal]
            or len(closes) > 1
            or any(i <= ordinal for i in closes)
            or any(
                v["event"] not in {"binding_intent", "binding_rejected", "lease_close"}
                for _, v in same
            )
        ):
            raise LedgerUnavailable("ledger unavailable")


class _AuthorityRuntime:
    """保護journalと実PGを同じworkerで所有する実行器。"""

    def __init__(self, value: dict[str, Any], journal: ProtectedJournal) -> None:
        self._value, self._journal = value, journal
        self._mutex = RLock()
        self._blocked = False
        self._active: set[int] = set()
        self._pair = self._pair_from(value)
        metadata = self._verify_enrollment()
        self._verify_history(metadata)
        self._recover_binding_leases()
        self._verify_leases()
        self._recover()
        journal.append(_encode_event({"event": "attached", **metadata}))

    def _verify_enrollment(self) -> dict[str, Any]:
        records = _events(self._journal)
        try:
            ordinal, enrollment = next(records)
        except StopIteration:
            raise LedgerUnavailable("ledger unavailable") from None
        metadata = _metadata(self._pair)
        if (
            ordinal != 1
            or enrollment["event"] != "enrolled"
            or enrollment["authority_id"] != str(self._journal.authority_id)
            or enrollment["epoch"] != 1
        ):
            raise LedgerUnavailable("ledger unavailable")
        for key in metadata:
            if (
                type(enrollment[key]) is not dict
                or set(enrollment[key]) != set(metadata[key])
                or enrollment[key]["system_id"] != metadata[key]["system_id"]
                or (key == "business" and enrollment[key] != metadata[key])
            ):
                raise LedgerUnavailable("ledger unavailable")
        return metadata

    @staticmethod
    def _pair_from(value: dict[str, Any]) -> _PgLedgerPair:
        return _PgLedgerPair(
            LedgerEndpoints(
                value["primary_dsn"],
                value["standby_dsn"],
                value["business_dsn"],
                value["control_dsn"],
                value["timeout"],
            ),
            business_peer=(value["database_uid"], value["database_gid"])
            if value.get("schema_version") in (2, 3)
            else None,
        )

    @classmethod
    def enroll(cls, value: dict[str, Any], journal: ProtectedJournal) -> None:
        """実専用subjectと空の同期pairを観測して初回recordを耐久化する。"""
        if value["enrollment_state"] != "new" or any(True for _ in journal.records()):
            raise LedgerUnavailable("ledger unavailable")
        pair = cls._pair_from(value)
        with _connection(value["primary_dsn"], value["timeout"]) as connection:
            identity = _identity(connection)
            pair._check_primary(identity)
            if (
                identity.get("highwater") != 0
                or identity.get("reservation_count") != 0
                or identity.get("epoch") != 1
            ):
                raise LedgerUnavailable("ledger unavailable")
        pair._confirm_state(0, 0)
        journal.append(
            _encode_event(
                {
                    "event": "enrolled",
                    "authority_id": str(journal.authority_id),
                    **_metadata(pair),
                    "epoch": 1,
                }
            )
        )

    def _verify_history(self, metadata: dict[str, Any]) -> None:
        """実PGを修復する前にjournalのowner/世代/終端を検査する。"""
        highwater = 0
        unresolved = None
        activation_seen = False
        for ordinal, event in _events(self._journal):
            kind = event["event"]
            if kind == "enrolled" and ordinal != 1:
                raise LedgerUnavailable("ledger unavailable")
            if kind == "lease_open" and event["epoch"] != 1:
                raise LedgerUnavailable("ledger unavailable")
            if kind == "activation_open":
                if (
                    activation_seen
                    or highwater != 0
                    or event["authority_id"] != str(self._journal.authority_id)
                    or event["business"] != metadata["business"]
                ):
                    raise LedgerUnavailable("ledger unavailable")
                # 開始時に他のleaseが生きていた履歴を正常化しない。
                for start, opened in _events(self._journal):
                    if start >= ordinal:
                        break
                    if opened["event"] == "lease_open" and not any(
                        end < ordinal
                        and closed["event"] == "lease_close"
                        and closed["lease"] == start
                        for end, closed in _events(self._journal)
                    ):
                        raise LedgerUnavailable("ledger unavailable")
                activation_seen = True
            if kind == "attached":
                for key in metadata:
                    previous = event[key]
                    if (
                        type(previous) is not dict
                        or set(previous) != set(metadata[key])
                        or any(
                            type(previous[field]) is not str or not previous[field]
                            for field in metadata[key]
                        )
                        or previous["system_id"] != metadata[key]["system_id"]
                        or (key == "business" and previous != metadata[key])
                    ):
                        raise LedgerUnavailable("ledger unavailable")
            if kind != "intent":
                continue
            if unresolved is not None:
                raise LedgerUnavailable("ledger unavailable")
            params = _params(event["params"])
            row = _row(event["row"], params)
            previous = None
            for index, item in _events(self._journal):
                if index >= ordinal:
                    break
                if item["event"] == "intent" and item["params"][0] == str(params[0]):
                    if any(
                        end >= ordinal
                        and resolution["event"] in ("confirmed", "quarantined")
                        and resolution["intent"] == index
                        for end, resolution in _events(self._journal)
                    ):
                        raise LedgerUnavailable("ledger unavailable")
                    previous = _resolved(self._journal, index, item)
            if row[1] != 1:
                raise LedgerUnavailable("ledger unavailable")
            if previous is None:
                if event["operation"] != "reserve" or row[0] != highwater + 1:
                    raise LedgerUnavailable("ledger unavailable")
                highwater = row[0]
            elif row[:5] != previous[:5] or previous[5] or previous[6]:
                raise LedgerUnavailable("ledger unavailable")
            resolved = _resolved(self._journal, ordinal, event)
            if resolved is None:
                unresolved = ordinal
        self._maximum_witness_highwater = highwater

    def _recover_binding_leases(self) -> None:
        """再起動で残った専用leaseは実DB終結を観測できるまで閉じない。"""
        from pitchlog.sync.control_provider.binding_control import (
            BindingOutcome,
            _BindingAuthority,
        )

        events = list(_events(self._journal))
        _validate_binding_rejections(events)
        for _, event in events:
            if event["event"] != "binding_intent":
                continue
            lease = event["lease"]
            closed = any(
                v["event"] == "lease_close" and v["lease"] == lease for _, v in events
            )
            if closed:
                continue
            if any(
                v["event"] == "binding_rejected" and v["lease"] == lease
                for _, v in events
            ):
                self._journal.append(
                    _encode_event({"event": "lease_close", "lease": lease})
                )
                continue
            if self._value.get("schema_version") != 3:
                raise LedgerUnavailable("ledger unavailable")
            self._journal.append(
                _encode_event({"event": "binding_quarantined", "lease": lease})
            )
            self._journal.append(
                _encode_event({"event": "binding_close_requested", "lease": lease})
            )
            with self._pair.recovery_fence() as fence:
                if fence.generation != event["record"]["recovery_generation"]:
                    raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
                fence.assert_held()
                outcome = _BindingAuthority(
                    self._value, self._journal.authority_id
                ).resolve(event["record"])
                fence.assert_held()
                if outcome not in (
                    BindingOutcome.COMMITTED,
                    BindingOutcome.ROLLBACK_CONFIRMED,
                ):
                    raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
                self._journal.append(
                    _encode_event(
                        {
                            "event": "binding_terminal",
                            "lease": lease,
                            "outcome": str(outcome),
                        }
                    )
                )
                self._journal.append(
                    _encode_event({"event": "lease_close", "lease": lease})
                )

    def _verify_leases(self) -> None:
        _validate_binding_rejections(list(_events(self._journal)))
        for ordinal, event in _events(self._journal):
            if event["event"] in ("lease_open", "activation_open"):
                ends = sum(
                    1
                    for _, item in _events(self._journal)
                    if item["event"] == "lease_close" and item["lease"] == ordinal
                )
                if ends != 1 and ordinal not in self._active:
                    raise LedgerUnavailable("ledger unavailable")
            if event["event"] in ("confirmed", "quarantined", "lease_close"):
                reference = event.get("intent", event.get("lease"))
                matches = [
                    item["event"]
                    for index, item in _events(self._journal)
                    if index == reference
                ]
                expected = (
                    {"lease_open", "activation_open"}
                    if event["event"] == "lease_close"
                    else {"intent"}
                )
                if len(matches) != 1 or matches[0] not in expected:
                    raise LedgerUnavailable("ledger unavailable")

            if event["event"] in (
                "binding_intent",
                "binding_rejected",
                "binding_quarantined",
                "binding_published",
                "binding_close_requested",
                "binding_terminal",
            ):
                predecessors = [
                    (i, v) for i, v in _events(self._journal) if i == event["lease"]
                ]
                if (
                    len(predecessors) != 1
                    or predecessors[0][1]["event"] != "lease_open"
                ):
                    raise LedgerUnavailable("ledger unavailable")
            if event["event"] == "lease_close":
                bound = any(
                    v["event"] == "binding_intent" and v["lease"] == event["lease"]
                    for _, v in _events(self._journal)
                )
                if bound and not any(
                    i < ordinal
                    and v["event"] in ("binding_terminal", "binding_rejected")
                    and v["lease"] == event["lease"]
                    for i, v in _events(self._journal)
                ):
                    raise LedgerUnavailable("ledger unavailable")

    def _last_for(self, params: tuple[object, ...]) -> tuple[Any, ...] | None:
        latest = None
        for ordinal, event in _events(self._journal):
            if event["event"] != "intent" or event["params"][0] != str(params[0]):
                continue
            row = _resolved(self._journal, ordinal, event)
            if row is None:
                continue
            if row[2:5] != params[1:]:
                raise LedgerUnavailable("ledger unavailable")
            if latest is not None and (
                row[:5] != latest[:5]
                or (latest[5] and not row[5])
                or (latest[6] and not row[6])
            ):
                raise LedgerUnavailable("ledger unavailable")
            latest = row
        return latest

    def _reconcile(self, params: tuple[object, ...], row: tuple[Any, ...]) -> None:
        connection = _connect(self._value["control_dsn"], self._value["timeout"])
        try:
            identity = _identity(connection)
            self._pair._check_primary(identity)
            args = (*params, row[0], row[1], row[5], row[6], identity["highwater"])
            actual = _query(connection, "reconcile", args)
            if actual != row:
                raise LedgerUnavailable("ledger unavailable")
            _commit(connection, self._value["timeout"])
            self._pair._confirmed(connection, params, row)
        finally:
            connection.close()

    def _read_row(self, params: tuple[object, ...]) -> tuple[Any, ...] | None:
        with _connection(
            self._value["primary_dsn"], self._value["timeout"]
        ) as connection:
            self._pair._check_primary(_identity(connection))
            # readは不在を含む固定関数。singleton wrapperのNULL表現を使う。
            value = _query(connection, "lookup", params)[0]
            if value is None:
                return None
            return _row(value, params)

    def _recover(self) -> None:
        pending = []
        for ordinal, event in _events(self._journal):
            if (
                event["event"] == "intent"
                and _resolved(self._journal, ordinal, event) is None
            ):
                pending.append((ordinal, event))
                if len(pending) > 1:
                    raise LedgerUnavailable("ledger unavailable")
        with _connection(
            self._value["primary_dsn"], self._value["timeout"]
        ) as connection:
            identity = _identity(connection)
            self._pair._check_primary(identity)
            if (
                identity["epoch"] != 1
                or type(identity["highwater"]) is not int
                or not 0 <= identity["highwater"] <= self._maximum_witness_highwater
            ):
                raise LedgerUnavailable("ledger unavailable")
        # DB側を固定cursor/256件上限で検査する。未知行を削除して通さない。
        cursor = 0
        while True:
            with _connection(
                self._value["control_dsn"], self._value["timeout"]
            ) as connection:
                page = _query(connection, "audit", (cursor, 256))[0]
            if type(page) is not list or len(page) > 256:
                raise LedgerUnavailable("ledger unavailable")
            if not page:
                break
            for item in page:
                if type(item) is not dict or set(item) != {
                    "attempt_id",
                    "tenant_id",
                    "game_id",
                    "start_request_id",
                    "generation",
                    "recovery_generation",
                    "claimed",
                    "quarantined",
                }:
                    raise LedgerUnavailable("ledger unavailable")
                params = _params(
                    [
                        item[k]
                        for k in (
                            "attempt_id",
                            "tenant_id",
                            "game_id",
                            "start_request_id",
                        )
                    ]
                )
                actual = _row(
                    [
                        item["generation"],
                        item["recovery_generation"],
                        *(
                            item[k]
                            for k in ("tenant_id", "game_id", "start_request_id")
                        ),
                        item["claimed"],
                        item["quarantined"],
                    ],
                    params,
                )
                expected = self._last_for(params)
                if pending and pending[0][1]["params"][0] == str(params[0]):
                    expected = _row(pending[0][1]["row"], params)
                if (
                    expected is None
                    or actual[:5] != expected[:5]
                    or actual[0] <= cursor
                ):
                    raise LedgerUnavailable("ledger unavailable")
                if (actual[5] and not expected[5]) or (actual[6] and not expected[6]):
                    raise LedgerUnavailable("ledger unavailable")
                cursor = actual[0]
        for ordinal, event in pending:
            params = _params(event["params"])
            expected = _row(event["row"], params)
            actual = self._read_row(params)
            if actual == expected:
                with _connection(
                    self._value["primary_dsn"], self._value["timeout"]
                ) as connection:
                    self._pair._confirmed(connection, params, expected)
                self._journal.append(
                    _encode_event({"event": "confirmed", "intent": ordinal})
                )
            else:
                if actual is not None and (
                    actual[:5] != expected[:5] or actual[5] or actual[6]
                ):
                    raise LedgerUnavailable("ledger unavailable")
                quarantined = (*expected[:6], True)
                self._reconcile(params, quarantined)
                self._journal.append(
                    _encode_event(
                        {
                            "event": "quarantined",
                            "intent": ordinal,
                            "row": _wire_row(quarantined),
                        }
                    )
                )
        expected_highwater, expected_count = 0, 0
        for ordinal, event in _events(self._journal):
            if event["event"] != "intent" or event["operation"] != "reserve":
                continue
            params = _params(event["params"])
            earlier = any(
                index < ordinal
                and item["event"] == "intent"
                and item["operation"] == "reserve"
                and item["params"][0] == str(params[0])
                for index, item in _events(self._journal)
            )
            if earlier:
                continue
            expected = self._last_for(params)
            if expected is None:
                raise LedgerUnavailable("ledger unavailable")
            expected_count += 1
            expected_highwater = max(expected_highwater, expected[0])
            actual = self._read_row(params)
            if actual != expected:
                self._reconcile(params, expected)
        with _connection(
            self._value["primary_dsn"], self._value["timeout"]
        ) as connection:
            identity = _identity(connection)
            self._pair._check_primary(identity)
            if (
                identity["highwater"] != expected_highwater
                or identity["reservation_count"] != expected_count
                or identity["epoch"] != 1
            ):
                raise LedgerUnavailable("ledger unavailable")
        self._pair._confirm_state(expected_highwater, expected_count)
        # restart直後にも明示WALを届け、確定集合の全owner-bound行を実peerで照合する。
        for _, event in _events(self._journal):
            if event["event"] != "intent" or event["operation"] != "reserve":
                continue
            params = _params(event["params"])
            expected = self._last_for(params)
            if expected is None:
                raise LedgerUnavailable("ledger unavailable")
            with _connection(
                self._value["primary_dsn"], self._value["timeout"]
            ) as connection:
                self._pair._confirmed(connection, params, expected)
        self._expected_highwater = expected_highwater
        self._expected_count = expected_count

    def _live_matches(self) -> None:
        self._pair._check_business()
        # 再起動peerの発見をCOMMIT後へ遅らせず、INTENT/予約SQLより前にも照合する。
        with _connection(self._value["standby_dsn"], self._value["timeout"]) as standby:
            self._pair._check_standby(_identity(standby))
        with _connection(
            self._value["primary_dsn"], self._value["timeout"]
        ) as connection:
            value = _identity(connection)
            self._pair._check_primary(value)
            if (
                value["epoch"] != 1
                or value["highwater"] != self._expected_highwater
                or value["reservation_count"] != self._expected_count
            ):
                self._blocked = True
                raise LedgerUnavailable("ledger unavailable")

    def _dispatch(self, operation: str | None, request: dict[str, Any]) -> object:
        if self._blocked:
            raise LedgerUnavailable("ledger unavailable")
        if not self._mutex.acquire(timeout=self._value["timeout"]):
            raise LedgerUnavailable("ledger unavailable")
        try:
            if self._blocked:
                raise LedgerUnavailable("ledger unavailable")
            self._live_matches()
            if operation == "epoch" and set(request) == {"operation"}:
                return self._pair.current_recovery_generation()
            if operation not in ("reserve", "claim") or set(request) != {
                "operation",
                "params",
            }:
                raise LedgerUnavailable("ledger unavailable")
            params = _params(request["params"])
            previous = self._last_for(params)
            try:
                row = self._pair._mutate(operation, params, self._journal)
            except LedgerOutcomeUnconfirmed:
                self._blocked = True
                raise
            self._expected_highwater = max(self._expected_highwater, row[0])
            self._expected_count += int(previous is None)
            try:
                self._live_matches()
            except Exception:
                self._blocked = True
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            if operation == "reserve":
                return _wire_row(row)
            return None
        finally:
            self._mutex.release()

    def _start_lease(
        self, fence: RecoveryEpochFence, *, fresh: bool
    ) -> tuple[int, object]:
        if not self._mutex.acquire(timeout=self._value["timeout"]):
            raise LedgerUnavailable("ledger unavailable")
        try:
            if self._blocked:
                raise LedgerUnavailable("ledger unavailable")
            self._live_matches()
            epoch = fence.generation
            if fresh:
                metadata = self._verify_enrollment()
                self._verify_history(metadata)
                self._verify_leases()
                if (
                    self._active
                    or self._expected_highwater != 0
                    or self._expected_count != 0
                    or any(
                        event["event"] in ("intent", "activation_open")
                        for _, event in _events(self._journal)
                    )
                ):
                    raise LedgerUnavailable("ledger unavailable")
                event = {
                    "event": "activation_open",
                    "authority_id": str(self._journal.authority_id),
                    "business": metadata["business"],
                    "epoch": epoch,
                    "highwater": 0,
                    "reservation_count": 0,
                }
            else:
                event = {"event": "lease_open", "epoch": epoch}
            try:
                opened = self._journal.append(_encode_event(event))
            except WitnessUnavailable:
                self._blocked = True
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            try:
                self._active.add(opened.ordinal)
                response = (
                    _activation_wire(_activation_event(opened.ordinal, event))
                    if fresh
                    else epoch
                )
            except Exception:
                self._active.discard(opened.ordinal)
                self._blocked = True
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            return opened.ordinal, response
        finally:
            # open期間全体では保持しない。通常D4 mutationは同じmutexで直列化できる。
            self._mutex.release()

    def _close_lease(self, lease: int) -> None:
        if not self._mutex.acquire(timeout=self._value["timeout"]):
            raise LedgerUnavailable("ledger unavailable")
        try:
            if self._blocked:
                raise LedgerUnavailable("ledger unavailable")
            try:
                self._journal.append(
                    _encode_event({"event": "lease_close", "lease": lease})
                )
            except WitnessUnavailable:
                self._blocked = True
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            self._active.remove(lease)
        finally:
            self._mutex.release()

    def _handle_binding(self, channel: socket.socket, request: dict[str, Any]) -> None:
        """専用peerにだけnonce/照合/権威実観測終結を供給する。"""
        from pitchlog.sync.control_provider.binding_control import (
            BindingOutcome,
            _BindingAuthority,
            _ConfirmedBindingRejection,
        )

        if self._value.get("schema_version") != 3 or self._blocked:
            raise LedgerUnavailable("ledger unavailable")
        lease = None
        record = None
        binding_intent_recorded = False
        authority = _BindingAuthority(self._value, self._journal.authority_id)
        authority.validate_request(request)
        try:
            with self._pair.recovery_fence() as fence:
                lease, _ = self._start_lease(fence, fresh=False)
                record, binding, nonce = authority.prepare_writer_binding(
                    request, fence.generation
                )
                self._journal.append(
                    _encode_event(
                        {"event": "binding_intent", "lease": lease, "record": record}
                    )
                )
                binding_intent_recorded = True
                authority.publish_prepared(record, binding, nonce)
                self._journal.append(
                    _encode_event({"event": "binding_published", "lease": lease})
                )
                fence.assert_held()
                _send(
                    channel,
                    {
                        "status": "ok",
                        "result": {
                            "nonce": nonce.hex(),
                            "lease_id": record["lease_id"],
                            "expires_at": record["expires_at"],
                        },
                    },
                )
                del nonce
                while True:
                    current = _receive(channel)
                    if (
                        set(current) != {"operation"}
                        or current["operation"]
                        not in ("binding_check", "binding_close")
                        or self._blocked
                    ):
                        raise LedgerUnavailable("ledger unavailable")
                    fence.assert_held()
                    if current["operation"] == "binding_check":
                        from datetime import datetime, timezone

                        if datetime.now(timezone.utc) >= datetime.fromisoformat(
                            cast(str, record["expires_at"])
                        ):
                            raise LedgerUnavailable("ledger unavailable")
                        self._live_matches()
                        authority.check(record, fence.generation)
                        _send(channel, {"status": "ok", "result": None})
                        continue
                    self._journal.append(
                        _encode_event({"event": "binding_quarantined", "lease": lease})
                    )
                    self._journal.append(
                        _encode_event(
                            {"event": "binding_close_requested", "lease": lease}
                        )
                    )
                    outcome = authority.resolve(record)
                    if outcome not in (
                        BindingOutcome.COMMITTED,
                        BindingOutcome.ROLLBACK_CONFIRMED,
                    ):
                        raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
                    self._journal.append(
                        _encode_event(
                            {
                                "event": "binding_terminal",
                                "lease": lease,
                                "outcome": str(outcome),
                            }
                        )
                    )
                    self._close_lease(lease)
                    lease = None
                    _send(channel, {"status": "ok", "result": str(outcome)})
                    return
        except _ConfirmedBindingRejection:
            if lease is None:
                raise LedgerUnavailable("ledger unavailable") from None
            try:
                if binding_intent_recorded:
                    self._journal.append(
                        _encode_event({"event": "binding_rejected", "lease": lease})
                    )
                self._close_lease(lease)
            except BaseException:
                self._active.discard(lease)
                self._blocked = True
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            raise LedgerUnavailable("ledger unavailable") from None
        except BaseException:
            if lease is not None:
                try:
                    self._journal.append(
                        _encode_event({"event": "binding_quarantined", "lease": lease})
                    )
                finally:
                    self._active.discard(lease)
                    self._blocked = True
            raise

    def handle(self, channel: socket.socket, *, role: str | None = None) -> None:
        """実peer認証済みchannel上で閉じた要求と実fenceだけを実行する。"""
        lease = None
        try:
            request = _receive(channel)
            operation = request.get("operation")
            # roleはroot固定listenerからだけ受け、要求本文では選択しない。
            # PG/fence/journalに触れる前に能力外の操作を拒否する。
            _authorize_operation(role, operation)
            if role == "sync_binding":
                self._handle_binding(channel, request)
                return
            if role is not None:
                keys = (
                    {"operation", "params"}
                    if operation in ("reserve", "claim")
                    else {"operation"}
                )
                if set(request) != keys:
                    raise LedgerUnavailable("ledger unavailable")
                if operation in ("reserve", "claim"):
                    _params(request["params"])
            if operation not in ("fence_open", "fresh_activation_open"):
                result = self._dispatch(operation, request)
                _send(channel, {"status": "ok", "result": result})
                return
            if set(request) != {"operation"} or self._blocked:
                raise LedgerUnavailable("ledger unavailable")
            with self._pair.recovery_fence() as fence:
                try:
                    lease, response = self._start_lease(
                        fence, fresh=operation == "fresh_activation_open"
                    )
                    fence.assert_held()
                    _send(channel, {"status": "ok", "result": response})
                    while True:
                        current = _receive(channel)
                        if (
                            self._blocked
                            or set(current) != {"operation"}
                            or current["operation"]
                            not in ("fence_check", "fence_close")
                        ):
                            raise LedgerUnavailable("ledger unavailable")
                        fence.assert_held()
                        if current["operation"] == "fence_close":
                            self._close_lease(lease)
                            lease = None
                            _send(channel, {"status": "ok", "result": None})
                            return
                        _send(channel, {"status": "ok", "result": None})
                except BaseException:
                    if lease is not None:
                        self._blocked = True
                        raise LedgerOutcomeUnconfirmed(
                            "ledger outcome unconfirmed"
                        ) from None
                    raise
        except LedgerOutcomeUnconfirmed:
            _send_error(channel, "unconfirmed")
        except Exception:
            _send_error(channel, "unavailable")
        finally:
            if lease is not None:
                self._active.discard(lease)
                self._blocked = True


def _authorize_operation(role: str | None, operation: object) -> None:
    """v1の既存閉集合を保ち、v2だけを固定された二つの能力へ分離する。"""
    if role is None:
        return
    allowed = {
        "generation": frozenset({"epoch", "reserve", "claim", "fence_open"}),
        "fresh_controller": frozenset({"fresh_activation_open"}),
        "sync_binding": frozenset({"binding_open"}),
    }
    if (
        type(role) is not str
        or type(operation) is not str
        or operation not in allowed.get(role, ())
    ):
        raise LedgerUnavailable("ledger unavailable")


def _receive(channel: socket.socket) -> dict[str, Any]:
    data = bytearray()
    while True:
        chunk = channel.recv(1)
        if not chunk:
            raise LedgerUnavailable("ledger unavailable")
        if chunk == b"\n":
            break
        data.extend(chunk)
        if len(data) > 65536:
            raise LedgerUnavailable("ledger unavailable")
    try:
        value = json.loads(data, object_pairs_hook=_unique)
        if type(value) is not dict:
            raise ValueError
        return value
    except Exception:
        raise LedgerUnavailable("ledger unavailable") from None


def _send(channel: socket.socket, value: dict[str, Any]) -> None:
    channel.sendall(_encode_event(value) + b"\n")


def _send_error(channel: socket.socket, status: str) -> None:
    try:
        _send(channel, {"status": status})
    except OSError:
        pass


def _request(
    channel: socket.socket, value: dict[str, Any], *, mutation: bool = False
) -> Any:
    try:
        _send(channel, value)
        response = _receive(channel)
    except (OSError, LedgerUnavailable):
        if mutation:
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
        raise LedgerUnavailable("ledger unavailable") from None
    if set(response) == {"status"} and response["status"] == "unconfirmed":
        raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
    if set(response) == {"status"} and response["status"] == "unavailable":
        raise LedgerUnavailable("ledger unavailable")
    if set(response) != {"status", "result"} or response["status"] != "ok":
        if mutation:
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
        raise LedgerUnavailable("ledger unavailable")
    return response["result"]


class _RemoteFence(RecoveryEpochFence):
    def __init__(self, channel: socket.socket, value: int) -> None:
        self._channel, self._value, self._active = channel, _positive(value), True

    @property
    def generation(self) -> int:
        """同じ実channel/共有lockの生存を確認して世代を返す。"""
        self.assert_held()
        return self._value

    def assert_held(self) -> None:
        """切れたchannelや終了leaseをheldとして再構築しない。"""
        if (
            not self._active
            or _request(self._channel, {"operation": "fence_check"}) is not None
        ):
            raise LedgerUnavailable("ledger unavailable")


class DurableLedger(DurableGenerationSource):
    """root保護endpointと実Unix peerで接続する製品source候補。"""

    def __init__(self, endpoint: Path) -> None:
        """DSN/fresh pairの直接構築を公開入口から拒否する。"""
        if not isinstance(endpoint, Path):
            raise LedgerUnavailable("ledger unavailable")
        from .authority import _endpoint

        try:
            self._endpoint, self._target = endpoint, _endpoint(endpoint)
        except Exception:
            raise LedgerUnavailable("ledger unavailable") from None

    @contextmanager
    def _channel(self) -> Iterator[socket.socket]:
        from .authority import _endpoint

        channel: socket.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            if _endpoint(self._endpoint) != self._target:
                raise LedgerUnavailable("ledger unavailable")
            channel.settimeout(self._target["timeout"])
            channel.connect(self._target["socket_path"])
            _, uid, gid = struct.unpack(
                "3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            if uid != self._target["authority_uid"] or (
                self._target["schema_version"] in (2, 3)
                and gid != self._target["authority_gid"]
            ):
                raise LedgerUnavailable("ledger unavailable")
            yield channel
        except OSError:
            raise LedgerUnavailable("ledger unavailable") from None
        finally:
            channel.close()

    def current_recovery_generation(self) -> int:
        """実authorityが照合した現在epochだけを返す。"""
        _authorize_operation(self._target.get("role"), "epoch")
        with self._channel() as channel:
            return _positive(_request(channel, {"operation": "epoch"}))

    def reserve(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> ReservedGeneration:
        """journal/実同期PGの両耐久化後にだけ単一ProtocolのDTOを返す。"""
        _authorize_operation(self._target.get("role"), "reserve")
        params = (attempt_id, tenant_id, game_id, start_request_id)
        _owner(params)
        with self._channel() as channel:
            value = _request(
                channel,
                {"operation": "reserve", "params": [str(v) for v in params]},
                mutation=True,
            )
        try:
            row = _row(value, params)
            if row[5] or row[6]:
                raise LedgerUnavailable("ledger unavailable")
        except Exception:
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
        return ReservedGeneration(row[0], row[1], tenant_id, game_id, start_request_id)

    def claim(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> None:
        """一度のclaimとCONFIRMED fsyncを実authorityへ要求する。"""
        _authorize_operation(self._target.get("role"), "claim")
        params = (attempt_id, tenant_id, game_id, start_request_id)
        _owner(params)
        with self._channel() as channel:
            if (
                _request(
                    channel,
                    {"operation": "claim", "params": [str(v) for v in params]},
                    mutation=True,
                )
                is not None
            ):
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")

    def advance_recovery_generation(self, previous: int) -> int:
        """実RG1 close証明の接合前にはepoch更新を開かない。"""
        _positive(previous)
        raise LedgerUnavailable("ledger unavailable")

    @contextmanager
    def recovery_fence(self) -> Iterator[RecoveryEpochFence]:
        """実共有epoch lockを同じ認証済みchannelで業務commitまで借用する。"""
        _authorize_operation(self._target.get("role"), "fence_open")
        with self._channel() as channel:
            fence = _RemoteFence(
                channel, _request(channel, {"operation": "fence_open"})
            )
            try:
                yield fence
            finally:
                try:
                    if _request(channel, {"operation": "fence_close"}) is not None:
                        raise LedgerUnavailable("ledger unavailable")
                finally:
                    fence._active = False

    @contextmanager
    def fresh_activation(
        self,
    ) -> Iterator[tuple[FreshActivationAttestation, RecoveryEpochFence]]:
        """一度限り開始の不変metadataと同channelの実共有fenceを借用する。"""
        _authorize_operation(self._target.get("role"), "fresh_activation_open")
        with self._channel() as channel:
            value = _request(
                channel, {"operation": "fresh_activation_open"}, mutation=True
            )
            try:
                attestation = _activation_from(value)
                fence = _RemoteFence(channel, attestation.pair_epoch)
                fence.assert_held()
            except Exception:
                raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
            try:
                yield attestation, fence
            except BaseException:
                # 業務結果不明/例外を正常closeへ補完しない。切断は実未終端として残る。
                raise
            else:
                if (
                    _request(channel, {"operation": "fence_close"}, mutation=True)
                    is not None
                ):
                    raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
            finally:
                fence._active = False
