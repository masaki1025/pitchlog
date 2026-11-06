"""終了再開の閉私有token。実同Session/nonce/raw参照だけをdispatcherへ貸す。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.repositories import transaction
from pitchlog.repositories.nonplay_prefix import NonplaySourceUnavailable, _live
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken
from pitchlog.sync.undo_payload import _load


@dataclass(frozen=True, slots=True)
class _ReadLifecycleState(TenantOperationToken):
    """最新head一点read。callerのJSONは資格ではない。"""

    request_json: str

    @property
    def capability_id(self):
        return "CAP:sync_lifecycle:read_state"


@dataclass(frozen=True, slots=True)
class _PrepareLifecycle(TenantOperationToken):
    """実評価の同frame prepare。"""

    request_json: str

    @property
    def capability_id(self):
        return "CAP:sync_lifecycle:prepare"


@dataclass(frozen=True, slots=True)
class _ConsumeLifecycle(TenantOperationToken):
    """実評価の同frame consume。"""

    request_json: str

    @property
    def capability_id(self):
        return "CAP:sync_lifecycle:consume"


_FUNCTIONS = MappingProxyType(
    {
        _ReadLifecycleState: "read_lifecycle_state",
        _PrepareLifecycle: "prepare_game_lifecycle",
        _ConsumeLifecycle: "consume_game_lifecycle",
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class QualifiedLifecycleCall:
    """核が消費済み資格からだけ得る固定関数選択と全bind。"""

    operation: TenantOperationToken
    function_name: str
    parameters: object


_CALLS = {}
_READS = {}
_PAGE_ITEMS = {}


@contextmanager
def _call_scope(handle, source, event, operation):
    """呼出区間とexacttoken/全値を結びSQL直実行の偽造を閉じる。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or type(operation) not in _FUNCTIONS
    ):
        raise NonplaySourceUnavailable("終了再開の固定関数型が不一致です")
    key = handle._state_key
    if key in _CALLS:
        raise NonplaySourceUnavailable("終了再開関数資格の再入です")
    lifetime = handle._writer_lifetime()
    runtime = transaction._TRANSACTION_RUNTIMES.get(key)
    _live(handle, source, event, lifetime, runtime)
    if type(operation) in {_PrepareLifecycle, _ConsumeLifecycle}:
        from pitchlog.sync.lifecycle_prefix_bridge import _assert_lifecycle_write_call

        _assert_lifecycle_write_call(handle, operation)
    lease = source.bound._lease
    parameters = {
        "tenant_id": handle._bound_tenant_id,
        "attempt_id": lease.attempt_id,
        "phase_id": lease.phase_id,
        "binding_nonce": lease.nonce,
        "device_id": lease.device_id,
        "game_id": UUID(event.game_id),
        "request_json": operation.request_json,
    }
    if (
        any(
            type(parameters[name]) is not UUID
            for name in ("tenant_id", "attempt_id", "phase_id", "device_id", "game_id")
        )
        or type(parameters["binding_nonce"]) is not bytes
        or len(parameters["binding_nonce"]) != 32
    ):
        raise NonplaySourceUnavailable("終了再開の型付き実bindが不一致です")
    snapshot = (
        operation,
        operation.request_json,
        parameters,
        source,
        event,
        lifetime,
        runtime,
    )
    state = [snapshot, False]
    _CALLS[key] = state
    try:
        yield
        _live(handle, source, event, lifetime, runtime)
        if state[1] is not True:
            raise NonplaySourceUnavailable("終了再開の固定関数が資格を消費していません")
    finally:
        if _CALLS.get(key) is state:
            del _CALLS[key]


def _qualified_lifecycle_call(handle, operation):
    """Root dispatcherがSQL0の前に一回消費する唯一getter。"""
    if type(handle) is not transaction._TenantTransaction:
        raise NonplaySourceUnavailable("終了再開の実handleが必要です")
    state = _CALLS.get(handle._state_key)
    if state is None or state[1] is not False:
        raise NonplaySourceUnavailable("終了再開の関数資格が未発行又は消費済みです")
    token, raw, params, source, event, lifetime, runtime = state[0]
    _live(handle, source, event, lifetime, runtime)
    if (
        operation is not token
        or type(operation) not in _FUNCTIONS
        or type(operation.request_json) is not str
        or operation.request_json != raw
    ):
        raise NonplaySourceUnavailable("終了再開のtoken identity/値が不一致です")
    lease = source.bound._lease
    actual_parameters = {
        "tenant_id": handle._bound_tenant_id,
        "attempt_id": lease.attempt_id,
        "phase_id": lease.phase_id,
        "binding_nonce": lease.nonce,
        "device_id": lease.device_id,
        "game_id": UUID(event.game_id),
        "request_json": operation.request_json,
    }
    if any(
        type(value) is not type(params[name]) or value != params[name]
        for name, value in actual_parameters.items()
    ):
        raise NonplaySourceUnavailable("終了再開の実bind全値/型が変更されました")
    if (
        params["binding_nonce"] != lease.nonce
        or params["attempt_id"] != lease.attempt_id
        or params["phase_id"] != lease.phase_id
        or params["device_id"] != lease.device_id
        or params["game_id"] != UUID(event.game_id)
    ):
        raise NonplaySourceUnavailable("終了再開の実leaseが差し替わりました")
    if type(operation) in {_PrepareLifecycle, _ConsumeLifecycle}:
        from pitchlog.sync.lifecycle_prefix_bridge import _consume_lifecycle_write_call

        _consume_lifecycle_write_call(handle, operation)
    state[1] = True
    return QualifiedLifecycleCall(
        operation, _FUNCTIONS[type(operation)], MappingProxyType(dict(params))
    )


def _run(handle, source, event, token):
    """既同Session実行器へ渡す。未登録はそのまま技術故障となる。"""
    with _call_scope(handle, source, event, token):
        from pitchlog.repositories.function_operations import FunctionOperationError
        from pitchlog.sync.lifecycle_execution import LifecycleExecutionError

        try:
            result = handle.run_function(token)
        except FunctionOperationError as error:
            raise LifecycleExecutionError(
                "終了再開の固定関数資格が不成立です"
            ) from error
        if type(result) is not TenantOperationResult or type(result.rows) is not tuple:
            raise NonplaySourceUnavailable("終了再開の固定関数応答型が不一致です")
        return result.rows


def _read_lifecycle_state(handle, source, event):
    """同writer lock下の一点headを読み、実不在だけ版0/NULLにする。"""
    rows = _run(handle, source, event, _ReadLifecycleState("null"))
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not str:
        raise NonplaySourceUnavailable("終了再開のheadが一点ではありません")
    value = _load(rows[0][0])
    if type(value) is not dict or set(value) != {"status", "lastVersion", "active"}:
        raise NonplaySourceUnavailable("終了再開のhead全値が不一致です")
    from pitchlog.sync.lifecycle_payload import _positive

    version = value["lastVersion"]
    if value["status"] == "in_progress":
        if value["active"] is not None or not (version == "0" or _positive(version)):
            raise NonplaySourceUnavailable("進行中の終了版形が不一致です")
    elif value["status"] == "finished":
        a = value["active"]
        if (
            type(a) is not dict
            or set(a) != {"version", "eventId", "receiptId"}
            or not _positive(version)
            or a["version"] != version
        ):
            raise NonplaySourceUnavailable("終了済みの最新確定版が不一致です")
        if any(
            type(a[k]) is not str or str(UUID(a[k])) != a[k]
            for k in ("eventId", "receiptId")
        ):
            raise NonplaySourceUnavailable("終了pointer UUIDが不一致です")
    else:
        raise NonplaySourceUnavailable("終了再開の現在状態が不明です")
    return value


def _read_lifecycle_display(handle, game_id):
    """実同handleからだけ表示を取得し、別tenantは0行のまま隠す。"""
    if type(handle) is not transaction._TenantTransaction or type(game_id) is not UUID:
        raise NonplaySourceUnavailable("終了表示は真正tenant handleが必要です")
    runtime = transaction._TRANSACTION_RUNTIMES.get(handle._state_key)
    if runtime is None:
        raise NonplaySourceUnavailable("終了表示のscopeが失効しています")
    from pitchlog.repositories.lifecycle_function_operations import (
        LifecycleDisplayToken,
        _display_decode,
    )

    result = handle.run_function(LifecycleDisplayToken(game_id))
    result = _display_decode(result)
    if transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not runtime:
        raise NonplaySourceUnavailable("終了表示の実Sessionが変更されました")
    return _load(result.rows[0][0]) if result.rows else None


_DISPLAY_READS = {}


@contextmanager
def lifecycle_display_scope(handle, game_id):
    """実DB表示を得た同TXだけをfinished metadataの閉読取へ貸与する。"""
    from pitchlog.sync.tokens import GameLockToken

    # 既readerと同じ試合行を先に固定し、表示とprefixの観測を同TXに束縛する。
    handle.run(GameLockToken(game_id))
    value = _read_lifecycle_display(handle, game_id)
    key = handle._state_key
    runtime = transaction._TRANSACTION_RUNTIMES.get(key)
    if key in _DISPLAY_READS or runtime is None:
        raise NonplaySourceUnavailable("終了表示scopeの再入です")
    session = runtime[0]
    tx = session.get_transaction()
    if tx is None or not tx.is_active or session.get_nested_transaction() is not None:
        raise NonplaySourceUnavailable("終了表示のtop TXが不明です")
    raw = _canonical_json(value)
    state = (handle, game_id, runtime, tx, raw)
    _DISPLAY_READS[key] = state
    try:
        yield _load(raw)
        _assert_display_read(handle, game_id)
    finally:
        if _DISPLAY_READS.get(key) is state:
            del _DISPLAY_READS[key]


def _assert_display_read(handle, game_id):
    state = _DISPLAY_READS.get(handle._state_key)
    if (
        state is None
        or state[0] is not handle
        or state[1] != game_id
        or transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not state[2]
        or state[2][0].get_transaction() is not state[3]
        or not state[3].is_active
    ):
        raise NonplaySourceUnavailable("終了表示の同TX貸与が失効しています")
    return _load(state[4])


def _finished_lifecycle_read_allowed(handle, game_id):
    """Caller boolやstatus文字列だけではfinishedを不可視境界から開かない。"""
    if (
        type(handle) is not transaction._TenantTransaction
        or handle._state_key not in _DISPLAY_READS
    ):
        return False
    value = _assert_display_read(handle, game_id)
    return type(value) is dict and value["status"] == "finished"
