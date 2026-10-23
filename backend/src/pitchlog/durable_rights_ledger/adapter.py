"""固定制限関数だけで外部同期台帳を利用する候補adapter。"""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
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

_MAX = 2**63 - 1
_SYNC_NAMES = "FIRST 1 (ledger_standby)"
Operation = Literal[
    "identity", "business_identity", "fence", "reserve", "claim", "read", "advance"
]


class LedgerUnavailable(InitialGrantUnavailable):
    """未確認の接続・設定・入力・制限関数拒否を表す。"""


class LedgerOutcomeUnconfirmed(LedgerUnavailable):
    """耐久処理の結果が不明であり、未使用と断定できないことを表す。"""


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
        "identity": "SELECT pitchlog_ledger.identity()",
        "business_identity": (
            "SELECT system_identifier::text FROM pg_catalog.pg_control_system()"
        ),
        "fence": "SELECT pitchlog_ledger.epoch_fence()",
        "reserve": "SELECT * FROM pitchlog_ledger.reserve(%s, %s, %s, %s)",
        "claim": "SELECT * FROM pitchlog_ledger.claim(%s, %s, %s, %s)",
        "read": "SELECT * FROM pitchlog_ledger.reservation(%s, %s, %s, %s)",
        "advance": "SELECT pitchlog_ledger.advance_epoch(%s)",
    }
    # operationの未知値・引数数もDBへ到達させない。
    arities = {
        "identity": 0,
        "business_identity": 0,
        "fence": 0,
        "reserve": 4,
        "claim": 4,
        "read": 4,
        "advance": 1,
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
    value = _query(connection, "identity")[0]
    if type(value) is not dict:
        raise LedgerUnavailable("ledger unavailable")
    return value


class _Fence(RecoveryEpochFence):
    """生きた同一transactionだけに有効な共有epochロック。"""

    def __init__(
        self,
        ledger: DurableLedger,
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
        self._ledger._check_primary(_identity(self._connection))
        if _positive(_query(self._connection, "fence")[0]) != self._generation:
            raise LedgerUnavailable("ledger unavailable")


class DurableLedger(DurableGenerationSource):
    """正常pairの生存期間内に限定した同期台帳部品。

    新processのcold attachを認可する最新性proof Portは未提供である。
    この候補は初回の隔離pairを同定した後、再起動・昇格・再構成を拒否する。
    設定や二台の一致を、運用再開/古いbackup拒否の完了証明には使わない。
    """

    def __init__(self, endpoints: LedgerEndpoints) -> None:
        """隔離初回pairを同定し、その起動identityへ寿命を固定する。"""
        if type(endpoints) is not LedgerEndpoints:
            raise LedgerUnavailable("ledger unavailable")
        _require_client()
        self._endpoints = endpoints
        self._lock = RLock()
        self._closed = False
        self._primary: dict[str, Any] = {}
        self._standby: dict[str, Any] = {}
        with _connection(endpoints.business_dsn, endpoints.timeout) as connection:
            business_id = _query(connection, "business_identity")[0]
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
                        _lsn(standby.get("wal")) >= barrier
                        and _lsn(peer["peers"][0].get("flush")) >= barrier
                    ):
                        actual = (
                            _query(connection, "read", params)
                            if params is not None
                            else (standby.get("epoch"),)
                        )
                        if actual != expected:
                            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
                        return
                sleep(0.02)
        except Exception:
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed") from None
        raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")

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
    ) -> tuple[Any, ...]:
        with self._lock:
            connection = _connect(
                self._endpoints.control_dsn
                if operation == "advance"
                else self._endpoints.primary_dsn,
                self._endpoints.timeout,
            )
            try:
                self._check_primary(_identity(connection))
                row = _query(connection, operation, params)
                _commit(connection, self._endpoints.timeout)
                self._confirmed(
                    connection, None if operation == "advance" else params, row
                )
                return row
            finally:
                # 未確定の接続を再利用せず、消費取消/rollback成功を主張しない。
                connection.close()

    def reserve(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> ReservedGeneration:
        """同一ownerへだけ正のbigint予約を同期保全して返す。"""
        params = (attempt_id, tenant_id, game_id, start_request_id)
        _owner(params)
        row = self._mutate("reserve", params)
        if len(row) != 6 or row[2:5] != params[1:] or row[5] is not False:
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
        return ReservedGeneration(
            _positive(row[0]), _positive(row[1]), tenant_id, game_id, start_request_id
        )

    def claim(
        self, attempt_id: UUID, tenant_id: UUID, game_id: UUID, start_request_id: UUID
    ) -> None:
        """同じownerの予約を一度だけ同期耐久消費する。"""
        params = (attempt_id, tenant_id, game_id, start_request_id)
        _owner(params)
        row = self._mutate("claim", params)
        if len(row) != 6 or row[2:5] != params[1:] or row[5] is not True:
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")

    def advance_recovery_generation(self, previous: int) -> int:
        """RG1 close確定後にだけ呼ぶ制御roleの単調CAS。"""
        _positive(previous)
        if previous == _MAX:
            raise LedgerUnavailable("ledger unavailable")
        row = self._mutate("advance", (previous,))
        if row != (previous + 1,):
            raise LedgerOutcomeUnconfirmed("ledger outcome unconfirmed")
        return previous + 1

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
