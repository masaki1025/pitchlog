"""複数のテナント operation を束ねるトランザクション単位を提供する。"""

from __future__ import annotations

import hmac
from collections.abc import Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from itertools import islice
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, cast, final
from uuid import UUID

from sqlalchemy.orm import Session

from pitchlog.db.engine import create_database_engine
from pitchlog.recording_rights.rg1_lifecycle import (
    BusinessBinding,
    RG1ControlUnavailable,
    _GateLoan,
    borrow_gate,
)
from pitchlog.repositories.base import (
    _materialize_execution_result,
    _materialize_rows,
    _operation_spec,
    _prepare_operation,
)
from pitchlog.repositories.binding import TenantBindingError, _tenant_transaction
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.function_operations import (
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.tokens import (
    TenantOperationResult,
    TenantOperationToken,
)

if TYPE_CHECKING:
    from pitchlog.repositories.game_start import BoundInitialStartPayload
    from pitchlog.repositories.initial_recording_right import InitialRecordingRightScope

__all__ = ("tenant_transaction_scope",)

_HANDLE_CREATION_TOKEN = object()
_TransactionRuntime = tuple[Session, ExitStack]
_TRANSACTION_RUNTIMES: dict[object, _TransactionRuntime] = {}
_INITIAL_ACTOR_STATES: dict[
    object, tuple[object, Literal["intent", "business", "enroll"]]
] = {}
_RG1_LOANS: dict[object, _GateLoan] = {}


@dataclass(slots=True)
class _EnrollmentBinding:
    """一回の実scopeと生成資格digestにだけ対応する短命記録。"""

    context: TenantContext
    runtime: object = field(repr=False)
    device_id: UUID
    credential_digest: bytes = field(repr=False)
    consumed: bool = False
    operation_used: bool = False
    commit_attempted: bool = False
    commit_completed: bool = False


_ENROLL_BINDINGS: dict[object, _EnrollmentBinding] = {}


@dataclass(slots=True)
class _ResolutionBinding:
    """一回の同Session lookupと再交付へだけ束縛する閉記録。"""

    context: TenantContext
    runtime: object = field(repr=False)
    game_id: UUID
    start_request_id: UUID
    device_id: UUID
    request_digest: bytes = field(repr=False)
    credential_digest: bytes = field(repr=False)
    consumed: bool = False
    device_checked: bool = False
    looked_up: bool = False
    attempt_id: UUID | None = None
    outcome: str | None = None


_RESOLVE_BINDINGS: dict[object, _ResolutionBinding] = {}
_START_MEMORY_BINDINGS: dict[
    object,
    tuple[
        InitialRecordingRightScope,
        BoundInitialStartPayload,
        UUID,
        tuple[dict[str, Any], ...],
    ],
] = {}
_SYNC_APPLY_ACTIVE: ContextVar[bool] = ContextVar("sync_apply_active", default=False)


@contextmanager
def _sync_apply_active() -> Iterator[None]:
    """既存の適用トランザクション内で、別スコープの開始を禁止する。"""
    if _SYNC_APPLY_ACTIVE.get():
        raise RuntimeError("同期適用中の印へ再入できない")
    token = _SYNC_APPLY_ACTIVE.set(True)
    try:
        yield
    finally:
        _SYNC_APPLY_ACTIVE.reset(token)


@final
class _TenantTransaction:
    """束縛済み Session 上で閉じた operation token だけを実行する。"""

    __slots__ = (
        "_state_key",
        "_context",
        "_bound_tenant_id",
        "_bound_integrity_proof",
    )

    def __init__(
        self,
        context: TenantContext,
        state_key: object,
        bound_tenant_id: UUID,
        bound_integrity_proof: bytes,
        creation_token: object,
    ) -> None:
        """Scope が発行した実行状態への不透明キーと文脈を保持する。

        Args:
            context: スコープ生成時に受け取ったテナント文脈。
            state_key: モジュール私有レジストリ上の実行状態キー。
            bound_tenant_id: 束縛時点で固定したテナント ID。
            bound_integrity_proof: 束縛時点で固定した発行証跡。
            creation_token: Scope だけが渡すモジュール私有センチネル。

        Raises:
            RuntimeError: Scope 外からの生成、または未登録状態を検出した場合。
        """
        if creation_token is not _HANDLE_CREATION_TOKEN:
            raise RuntimeError("トランザクションハンドルは scope だけが生成できる")
        if state_key not in _TRANSACTION_RUNTIMES:
            raise RuntimeError("scope が登録していない実行状態から生成できない")
        self._state_key: object | None = state_key
        self._context = context
        self._bound_tenant_id = bound_tenant_id
        self._bound_integrity_proof = bound_integrity_proof

    def _expire(self) -> object | None:
        """実行状態との対応を破棄し、ハンドルを永久に失効させる。"""
        state_key = self._state_key
        self._state_key = None
        _PORT_PHASES.pop(state_key, None)
        _PORT_DEVICE_BIND_USED.discard(state_key)
        return state_key

    def run(self, operation: TenantOperationToken) -> TenantOperationResult:
        """登録済み operation を実行して不変な行集合を返す。

        Args:
            operation: 生成済み registry が認識する operation token。

        Returns:
            トランザクション内で完全実体化した immutable な結果。

        Raises:
            RuntimeError: ハンドルが失効済み、token が registry に無い、または
                結果契約に違反する場合。
        """
        state_key = self._state_key
        if state_key is None:
            raise RuntimeError("トランザクションハンドルは失効している")
        runtime = _TRANSACTION_RUNTIMES.get(state_key)
        if runtime is None:
            self._state_key = None
            raise RuntimeError("トランザクションハンドルは失効している")
        if (
            type(self._context) is not TenantContext
            or self._context.tenant_id != self._bound_tenant_id
            or self._context._integrity_proof != self._bound_integrity_proof
            or not self._context._has_valid_integrity_proof()
        ):
            raise TenantBindingError(
                "TenantContext の発行証跡が不一致のため業務 SQL を開始できない"
            )

        session, _ = runtime
        if _is_port_command(operation):
            return _execute_port_command(self, operation)
        phase = _port_phase(self)
        if phase is not None:
            _require_port_read_token(phase, operation)
        if state_key in _INITIAL_ACTOR_STATES:
            _validate_initial_memory_operation(self, operation)
        spec = _operation_spec(operation)
        statement, parameters = _prepare_operation(operation, self._bound_tenant_id)
        if phase is not None:
            _require_plain_port_select(spec.statement)
            _require_plain_port_select(statement)
        if spec.preflight is not None:
            preflight = spec.preflight(operation, parameters)
            if any(
                _operation_spec(check).preflight is not None
                for check in preflight.operations
            ):
                raise RuntimeError("実行前検証の再帰は許可されない")
            preflight.validate(tuple(self.run(check) for check in preflight.operations))
        execution_result = session.execute(
            statement.execution_options(preserve_rowcount=True), parameters
        )
        return _materialize_execution_result(statement, execution_result)

    def run_function(self, operation: TenantOperationToken) -> TenantOperationResult:
        """同一scopeで登録済み固定関数だけを実行し、結果を閉じる。"""
        state_key = self._state_key
        if state_key is None:
            raise RuntimeError("トランザクションハンドルは失効している")
        runtime = _TRANSACTION_RUNTIMES.get(state_key)
        if runtime is None:
            self._state_key = None
            raise RuntimeError("トランザクションハンドルは失効している")
        if (
            type(self._context) is not TenantContext
            or self._context.tenant_id != self._bound_tenant_id
            or self._context._integrity_proof != self._bound_integrity_proof
            or not self._context._has_valid_integrity_proof()
        ):
            raise TenantBindingError(
                "TenantContext の発行証跡が不一致のため業務 SQL を開始できない"
            )
        from pitchlog.repositories.initial_recording_right import (
            _INITIAL_BUSINESS_TOKENS,
            _INITIAL_FUNCTION_REGISTRY,
            _INITIAL_INTENT_TOKENS,
            _CheckBusinessEpochToken,
            _EnrollDeviceToken,
            _LockCurrentStartToken,
            _LockDeviceToken,
            _LookupExistingStartAttemptToken,
            _ReadExistingStartToken,
            _ReadInitialStartContextToken,
            _ReadStartGameToken,
            _ResolveStartAttemptToken,
        )

        actor = _INITIAL_ACTOR_STATES.get(state_key)
        registry = FUNCTION_OPERATION_REGISTRY
        if actor is not None:
            _assert_initial_actor_transaction(self, self._context, actor[1])
            if actor[1] == "enroll":
                binding = _ENROLL_BINDINGS.get(state_key)
                if binding is None or (
                    binding.context is not self._context
                    or binding.runtime is not actor[0]
                    or type(binding.device_id) is not UUID
                    or type(binding.credential_digest) is not bytes
                    or len(binding.credential_digest) != 32
                ):
                    raise TenantBindingError("enroll能力が失効又は別owner")
                if type(operation) is _EnrollDeviceToken and (
                    binding.operation_used
                    or type(operation.device_id) is not UUID
                    or type(operation.credential_digest) is not bytes
                    or operation.device_id != binding.device_id
                    or operation.credential_digest != binding.credential_digest
                ):
                    raise TenantBindingError("enroll能力の生成資格が不一致")
            allowed = (
                frozenset({_EnrollDeviceToken})
                if actor[1] == "enroll"
                else _INITIAL_INTENT_TOKENS
                if actor[1] == "intent"
                else _INITIAL_BUSINESS_TOKENS
            )
            resolution = _RESOLVE_BINDINGS.get(state_key)
            if resolution is not None:
                if actor[1] != "business" or (
                    resolution.context is not self._context
                    or resolution.runtime is not actor[0]
                    or any(
                        type(v) is not UUID
                        for v in (
                            resolution.game_id,
                            resolution.start_request_id,
                            resolution.device_id,
                        )
                    )
                    or any(
                        type(v) is not bytes or len(v) != 32
                        for v in (
                            resolution.request_digest,
                            resolution.credential_digest,
                        )
                    )
                ):
                    raise TenantBindingError("resolve束縛が不一致")
                allowed = frozenset(
                    {
                        _LockDeviceToken,
                        _LookupExistingStartAttemptToken,
                        _ReadExistingStartToken,
                        _ReadStartGameToken,
                        _ResolveStartAttemptToken,
                        _LockCurrentStartToken,
                        _CheckBusinessEpochToken,
                        _ReadInitialStartContextToken,
                    }
                )
                if (
                    type(operation) is _LockDeviceToken
                    and operation.device_id != resolution.device_id
                ):
                    raise TenantBindingError("resolve端末が不一致")
                if type(operation) is _LookupExistingStartAttemptToken:
                    expected = _LookupExistingStartAttemptToken(
                        resolution.game_id,
                        resolution.start_request_id,
                        resolution.device_id,
                        resolution.request_digest,
                    )
                    loan = _RG1_LOANS.get(state_key)
                    if (
                        operation != expected
                        or not resolution.device_checked
                        or resolution.looked_up
                        or loan is None
                    ):
                        raise TenantBindingError("非作成lookupの短命能力が不一致")
                    loan.assert_held()
                    resolution.looked_up = True
            if type(operation) in allowed:
                from pitchlog.repositories.initial_recording_right import (
                    _SCOPE_BINDINGS,
                    _PersistInitialStartToken,
                    _ReadInitialStartContextToken,
                )

                if type(operation) in {
                    _ReadInitialStartContextToken,
                    _PersistInitialStartToken,
                }:
                    from pitchlog.repositories.game_start import _start_token

                    matches = [
                        scope
                        for scope in _SCOPE_BINDINGS
                        if scope._transaction is self
                        and scope._start_payload is not None
                    ]
                    if len(matches) != 1:
                        raise TenantBindingError("開始専用scopeがない")
                    scope = matches[0]
                    scope._require_device()
                    bound = scope._start_payload
                    if bound is None:
                        raise TenantBindingError("開始payloadがない")
                    expected = _start_token(
                        bound,
                        save=type(operation) is _PersistInitialStartToken,
                    )
                    if operation != expected or (
                        type(operation) is _PersistInitialStartToken
                        and (not scope._game_locked or not scope._start_um2_saved)
                    ):
                        raise TenantBindingError("開始操作のowner/payloadが不一致")
                if actor[1] == "enroll":
                    loan = _RG1_LOANS.get(state_key)
                    if loan is None:
                        raise TenantBindingError("enrollは実RG1借用が必要")
                    loan.assert_held()
                    binding.operation_used = True
                registry = _INITIAL_FUNCTION_REGISTRY
            else:
                spec = registry.get(type(operation))
                if spec is None or (spec.operation_id, spec.function_id) not in {
                    ("RG1:precheck", "rg1_api.rg1_read_open"),
                    ("RG1:commit_check", "rg1_api.rg1_assert_open_before_commit"),
                    ("RG1:scope_binding", "rg1_control.scope_binding"),
                }:
                    raise TenantBindingError("初期権actorのphaseに未登録の操作")
        elif type(operation) in _INITIAL_FUNCTION_REGISTRY:
            raise TenantBindingError("app scopeは初期権関数を実行できない")
        spec, parameters = prepare_function_operation(
            operation, self._bound_tenant_id, registry
        )
        phase = _port_phase(self)
        if phase is not None:
            _require_port_function(phase, operation, spec.function_id)
        from pitchlog.repositories.ordinary_pitch_qualification import (
            PrepareOrdinaryProjectionToken,
        )
        from pitchlog.sync.terminal_pitch_tokens import PreparePlayPrefixProjectionToken

        if type(operation) in {
            PrepareOrdinaryProjectionToken,
            PreparePlayPrefixProjectionToken,
        }:
            from pitchlog.sync.ordinary_pitch_execution import (
                _consume_ordinary_preparation,
            )

            _consume_ordinary_preparation(self, operation)
        session, _ = runtime
        execution_result = session.execute(spec.statement, parameters)
        rows = tuple(tuple(row) for row in islice(execution_result, spec.max_rows + 1))
        decoded = decode_function_result(spec, _materialize_rows(rows))
        resolution = _RESOLVE_BINDINGS.get(state_key)
        if resolution is not None:
            if type(operation) is _LockDeviceToken:
                resolution.device_checked = bool(
                    len(decoded.rows) == 1
                    and decoded.rows[0][1] is None
                    and type(decoded.rows[0][0]) is bytes
                    and hmac.compare_digest(
                        decoded.rows[0][0], resolution.credential_digest
                    )
                )
                if not resolution.device_checked:
                    raise TenantBindingError("resolve端末資格が不一致")
            elif type(operation) is _LookupExistingStartAttemptToken and decoded.rows:
                attempt_id, outcome = decoded.rows[0]
                if type(attempt_id) is not UUID or type(outcome) is not str:
                    raise TenantBindingError("lookup実戻り型が不正")
                resolution.attempt_id = attempt_id
                resolution.outcome = outcome
        return _materialize_rows(decoded.rows)

    def _ensure_rg1_lease(self) -> None:
        """実Sessionの固定観測だけを使い、scopeが終わるまで借用を所有する。"""
        from pitchlog.repositories.rg1 import RG1ScopeBindingToken, RG1Unavailable

        key = self._state_key
        if key is None or key not in _TRANSACTION_RUNTIMES:
            raise RuntimeError("トランザクションハンドルは失効している")
        existing = _RG1_LOANS.get(key)
        try:
            if existing is not None:
                existing.assert_held()
                return
            result = self.run_function(RG1ScopeBindingToken())
            if len(result.rows) != 1 or len(result.rows[0]) != 1:
                raise RG1Unavailable("復元ゲートの実識別を確認できない")
            value = result.rows[0][0]
            if not isinstance(value, str):
                raise RG1Unavailable("復元ゲートの実識別型が不正")
            binding = BusinessBinding.from_text(value)
            _RG1_LOANS[key] = borrow_gate(binding)
        except RG1ControlUnavailable as error:
            raise RG1Unavailable("復元ゲートの実保持を確認できない") from error

    def _assert_rg1_lease(self) -> None:
        """未借用や切断を、直前照合の成功へ昇格しない。"""
        from pitchlog.repositories.rg1 import RG1Unavailable

        key = self._state_key
        loan = None if key is None else _RG1_LOANS.get(key)
        if loan is None:
            raise RG1Unavailable("復元ゲートが借用されていない")
        try:
            loan.assert_held()
        except RG1ControlUnavailable as error:
            raise RG1Unavailable("復元ゲートの実保持を確認できない") from error

    def _writer_lifetime(self) -> tuple[object, object]:
        """所有するtop-level TXの不透明な寿命だけを返す。"""
        key = self._state_key
        if (
            key is None
            or key not in _TRANSACTION_RUNTIMES
            or key in _INITIAL_ACTOR_STATES
        ):
            raise TenantBindingError("通常writerの実scopeが必要")
        session, _ = _TRANSACTION_RUNTIMES[key]
        tx = session.get_transaction()
        if tx is None or not tx.is_active or session.in_nested_transaction():
            raise TenantBindingError("生存したtop-level writerが必要")
        return key, tx

    def _assert_writer_lifetime(self, owner: tuple[object, object]) -> None:
        """別scope/別TX/失効/savepointへのwriter資格転用を拒否する。"""
        if self._writer_lifetime() != owner:
            raise TenantBindingError("writer資格の寿命が不一致")

    def run_in_savepoint(
        self, operation: TenantOperationToken
    ) -> TenantOperationResult:
        """単一 operation の失敗だけを取り消せるように実行する。

        Args:
            operation: 既存の登録済み operation token。

        Returns:
            SAVEPOINT 内で実体化した結果。
        """
        state_key = self._state_key
        if state_key is None or state_key not in _TRANSACTION_RUNTIMES:
            raise RuntimeError("トランザクションハンドルは失効している")
        session, _ = _TRANSACTION_RUNTIMES[state_key]
        if _port_phase(self) is not None:
            raise TenantBindingError("Port判定phaseでsavepointを作れない")
        if state_key in _INITIAL_ACTOR_STATES:
            raise TenantBindingError("初期権actorへ汎用savepointを公開できない")
        from pitchlog.sync.control_provider.writer_binding import _LIVE_BINDINGS

        bound = _LIVE_BINDINGS.get(state_key)
        if bound is not None:
            bound.assert_current()
        with session.begin_nested():
            result = self.run(operation)
        if bound is not None:
            bound.assert_current()
        return result


class _TenantTransactionScope(AbstractContextManager[_TenantTransaction]):
    """Session の生成から close までを所有する内部 context manager。"""

    __slots__ = ("_context", "_handle", "_actor_runtime", "_actor_phase")

    def __init__(
        self,
        context: TenantContext,
        *,
        _actor_runtime: object | None = None,
        _actor_phase: Literal["intent", "business", "enroll"] | None = None,
    ) -> None:
        """スコープへ一度だけ渡されたテナント文脈を保持する。

        Args:
            context: API 層から引き渡されたテナント文脈。
        """
        self._context = context
        self._handle: _TenantTransaction | None = None
        self._actor_runtime = _actor_runtime
        self._actor_phase = _actor_phase

    def __enter__(self) -> _TenantTransaction:
        """Session を生成し、トランザクション先頭で文脈を束縛する。

        Returns:
            Session を公開せず、束縛済み実行状態だけを参照する操作ハンドル。
        """
        if self._handle is not None:
            raise RuntimeError("同じトランザクションスコープへ再入できない")
        if _SYNC_APPLY_ACTIVE.get():
            raise RuntimeError("同期適用中に新しいテナントスコープを開けない")
        if type(self._context) is not TenantContext:
            raise TenantBindingError("TenantContext が無いため業務 SQL を開始できない")
        if not self._context._has_valid_integrity_proof():
            raise TenantBindingError(
                "TenantContext の発行証跡が不一致のため業務 SQL を開始できない"
            )

        bound_tenant_id = self._context.tenant_id
        bound_integrity_proof = self._context._integrity_proof

        if self._actor_runtime is None:
            if self._actor_phase is not None:
                raise TenantBindingError("actor phaseとruntimeが不一致")
            engine = create_database_engine()
        else:
            from pitchlog.recording_rights.initial_grant_broker import (
                _initial_actor_engine,
            )

            if self._actor_phase not in ("intent", "business", "enroll"):
                raise TenantBindingError("actor phaseが未登録")
            engine = _initial_actor_engine(self._actor_runtime)
        session = Session(engine)
        exit_stack = ExitStack()
        state_key = object()
        _TRANSACTION_RUNTIMES[state_key] = (session, exit_stack)
        if self._actor_runtime is not None and self._actor_phase is not None:
            _INITIAL_ACTOR_STATES[state_key] = (self._actor_runtime, self._actor_phase)
        handle: _TenantTransaction | None = None
        try:
            handle = _TenantTransaction(
                self._context,
                state_key,
                bound_tenant_id,
                bound_integrity_proof,
                _HANDLE_CREATION_TOKEN,
            )
            self._handle = handle
            ExitStack.enter_context(
                exit_stack,
                _tenant_transaction(session, self._context),
            )
        except BaseException as primary_error:
            expired_key = state_key if handle is None else handle._expire()
            runtime = _TRANSACTION_RUNTIMES.pop(expired_key, None)
            _INITIAL_ACTOR_STATES.pop(expired_key, None)
            self._handle = None
            runtime_session = session if runtime is None else runtime[0]
            try:
                runtime_session.close()
            except BaseException as close_error:
                raise primary_error from close_error
            raise
        if handle is None:
            raise RuntimeError("トランザクションハンドルを生成できない")
        return handle

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """終了理由を既存境界へ渡し、成否にかかわらず Session を閉じる。

        Args:
            exception_type: スコープ内で発生した例外の型。
            exception: スコープ内で発生した例外。
            traceback: スコープ内で発生した例外の traceback。

        Returns:
            既存トランザクション境界の例外伝播判定。
        """
        handle = self._handle
        key = None if handle is None else handle._state_key
        from pitchlog.sync.control_provider.writer_binding import _before_writer_finish

        if exception is None and handle is not None:
            try:
                _before_writer_finish(handle)
            except BaseException as precommit_error:
                self.__exit__(
                    type(precommit_error),
                    precommit_error,
                    precommit_error.__traceback__,
                )
                raise
        loan = None if key is None else _RG1_LOANS.get(key)
        if exception is None and loan is not None:
            from pitchlog.repositories.rg1 import assert_rg1_open_before_commit

            if handle is None:
                raise RuntimeError("終了前にscopeが失効している")
            try:
                assert_rg1_open_before_commit(handle)
            except BaseException as precommit_error:
                try:
                    self.__exit__(
                        type(precommit_error),
                        precommit_error,
                        precommit_error.__traceback__,
                    )
                except BaseException as cleanup_error:
                    raise precommit_error from cleanup_error
                raise
        if key is not None:
            _RG1_LOANS.pop(key, None)
        try:
            result = self._exit_after_rg1_check(exception_type, exception, traceback)
        except BaseException as primary_error:
            if loan is not None:
                try:
                    loan.abandon()
                except BaseException as abandon_error:
                    raise primary_error from abandon_error
            raise
        if loan is not None:
            try:
                loan.release()
            except BaseException as release_error:
                if exception is not None and not result:
                    raise exception.with_traceback(traceback) from release_error
                raise
        return result

    def _exit_after_rg1_check(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """旧PG確定/取消/closeの順序を保ち、その完了を借用解放より先にする。"""
        handle = self._handle
        if handle is None:
            raise RuntimeError("開始していないトランザクションスコープを終了できない")

        expired_key = handle._expire()
        self._handle = None
        runtime = _TRANSACTION_RUNTIMES.pop(expired_key, None)
        _INITIAL_ACTOR_STATES.pop(expired_key, None)
        if runtime is None:
            raise RuntimeError("トランザクションハンドルの実行状態が既に失効している")
        session, exit_stack = runtime
        binding = _ENROLL_BINDINGS.get(expired_key)
        if binding is not None and exception is None:
            binding.commit_attempted = True
        try:
            exit_result = ExitStack.__exit__(
                exit_stack,
                exception_type,
                exception,
                traceback,
            )
        except BaseException as primary_error:
            try:
                session.close()
            finally:
                from pitchlog.sync.control_provider.writer_binding import (
                    _after_writer_finish,
                )

                try:
                    _after_writer_finish(expired_key)
                except BaseException as binding_error:
                    raise primary_error from binding_error
            raise

        from pitchlog.sync.control_provider.writer_binding import _after_writer_finish

        try:
            _after_writer_finish(expired_key)
        except BaseException:
            session.close()
            raise
        if binding is not None and exception is None:
            binding.commit_completed = True
        try:
            session.close()
        except BaseException as close_error:
            if exception is not None and not exit_result:
                raise exception.with_traceback(traceback) from close_error
            raise
        return exit_result


def tenant_transaction_scope(
    context: TenantContext,
) -> AbstractContextManager[_TenantTransaction]:
    """テナント文脈を一度だけ受け取るトランザクション単位を返す。

    Args:
        context: API 層から引き渡されたテナント文脈。

    Returns:
        Session の生成・束縛・確定・取消・close を所有するスコープ。
    """
    return _TenantTransactionScope(context)


def _assert_initial_actor_transaction(
    handle: _TenantTransaction,
    context: TenantContext,
    phase: Literal["intent", "business", "enroll"],
) -> None:
    """真正な実登録actorハンドルと同一tenant/phaseを毎回照合する。"""
    from pitchlog.recording_rights.initial_grant_broker import _initial_actor_engine

    if type(handle) is not _TenantTransaction or type(context) is not TenantContext:
        raise TenantBindingError("初期権scopeの型が不正")
    key = handle._state_key
    actor = _INITIAL_ACTOR_STATES.get(key)
    if (
        key is None
        or key not in _TRANSACTION_RUNTIMES
        or actor is None
        or actor[1] != phase
        or handle._context is not context
        or handle._bound_tenant_id != context.tenant_id
        or handle._bound_integrity_proof != context._integrity_proof
        or not context._has_valid_integrity_proof()
    ):
        raise TenantBindingError("初期権scopeは失効又は別文脈")
    _initial_actor_engine(actor[0])


def _initial_actor_transaction_scope(
    context: TenantContext,
    actor_runtime: object,
    phase: Literal["intent", "business", "enroll"],
) -> AbstractContextManager[_TenantTransaction]:
    """登録済みactorの閉scopeを作り、既tenant境界/commit処理を再利用する。"""
    if phase not in ("intent", "business", "enroll"):
        raise TenantBindingError("初期権scopeのphaseが不正")
    return _TenantTransactionScope(
        context, _actor_runtime=actor_runtime, _actor_phase=phase
    )


def _validate_initial_memory_operation(
    handle: _TenantTransaction, operation: TenantOperationToken
) -> None:
    """開始で検証済みの自チームexact5操作だけを同handleに限定する。"""
    from pitchlog.repositories.initial_recording_right import _SCOPE_BINDINGS
    from pitchlog.repositories.lineup_memory import (
        LineupMemoryReadToken,
        _ActiveLineupPlayerLockToken,
        _LineupMemoryInsertToken,
        _LineupMemoryUpdateToken,
        _SelfTeamLockToken,
    )

    binding = _START_MEMORY_BINDINGS.get(handle._state_key)
    if binding is None:
        raise TenantBindingError("初期権actorへ汎用DMLを公開できない")
    scope, bound, team, lineup = binding
    if (
        scope not in _SCOPE_BINDINGS
        or scope._transaction is not handle
        or scope._start_payload is not bound
    ):
        raise TenantBindingError("開始UM2束縛が失効")
    scope._require_device()
    if not scope._game_locked or scope._outcome != "pending":
        raise TenantBindingError("開始UM2のphaseが不正")
    _assert_initial_actor_transaction(handle, handle._context, "business")
    if type(operation) not in {
        _SelfTeamLockToken,
        _ActiveLineupPlayerLockToken,
        LineupMemoryReadToken,
        _LineupMemoryInsertToken,
        _LineupMemoryUpdateToken,
    }:
        raise TenantBindingError("開始UM2のexact操作でない")
    if type(operation) is _LineupMemoryUpdateToken:
        # 既UM2のread直後に選んだ同一memoryだけを更新できる。
        expected_id = handle.run(LineupMemoryReadToken(team)).rows
        if len(expected_id) != 1 or operation.id != expected_id[0][0]:
            raise TenantBindingError("開始UM2の更新対象が不一致")
    elif getattr(operation, "team_record_id", None) != team:
        raise TenantBindingError("開始UM2の自チームが不一致")
    if type(operation) is _ActiveLineupPlayerLockToken:
        if operation.player_id not in {UUID(e["player_id"]) for e in lineup}:
            raise TenantBindingError("開始UM2の選手が不一致")
    if type(operation) in {_LineupMemoryInsertToken, _LineupMemoryUpdateToken}:
        import json

        from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object

        try:
            actual = json.loads(
                getattr(operation, "lineup_json"),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
        except ValueError:
            raise TenantBindingError("開始UM2のpayloadが不正") from None
        if actual != list(lineup):
            raise TenantBindingError("開始UM2のpayloadが不一致")


def _save_initial_lineup_memory(
    scope: InitialRecordingRightScope,
    bound: BoundInitialStartPayload,
    team: UUID,
    lineup: tuple[dict[str, Any], ...],
) -> None:
    """閉start hookから既UM2を短命登録内で直接呼ぶ。callbackを渡さない。"""
    from pitchlog.repositories.initial_recording_right import _SCOPE_BINDINGS
    from pitchlog.repositories.lineup_memory import save_lineup_memory

    if scope not in _SCOPE_BINDINGS or scope._start_payload is not bound:
        raise TenantBindingError("開始UM2の真正scopeがない")
    scope._require_device()
    bound.assert_owner(scope._owner)
    context = scope._start_context
    if (
        context is None
        or str(team) != context["self_team_id"]
        or not scope._game_locked
        or scope._outcome != "pending"
    ):
        raise TenantBindingError("開始UM2の検証済contextがない")
    side = "away" if str(team) == context["away_team_id"] else "home"
    expected = tuple(
        {k: v for k, v in e.items() if k != "uniform_number_snapshot"}
        for e in context[side]
    )
    if lineup != expected:
        raise TenantBindingError("開始UM2の確定payloadが不一致")
    handle = scope._transaction
    _assert_initial_actor_transaction(handle, handle._context, "business")
    key = handle._state_key
    if key in _START_MEMORY_BINDINGS:
        raise TenantBindingError("開始UM2へ再入できない")
    _START_MEMORY_BINDINGS[key] = (scope, bound, team, lineup)
    try:
        save_lineup_memory(handle, team, lineup)
    finally:
        _START_MEMORY_BINDINGS.pop(key, None)


@contextmanager
def _initial_enrollment_transaction_scope(
    binding: _EnrollmentBinding,
) -> Iterator[_TenantTransaction]:
    """新1関数だけを真正な同Sessionへ束縛し、確定後も登録を残さない。"""
    if type(binding) is not _EnrollmentBinding or (
        type(binding.device_id) is not UUID
        or type(binding.credential_digest) is not bytes
        or len(binding.credential_digest) != 32
        or binding.consumed
        or binding.commit_attempted
        or binding.commit_completed
    ):
        raise TenantBindingError("enroll束縛値が不正")
    binding.consumed = True
    key = None
    try:
        with _initial_actor_transaction_scope(
            binding.context, binding.runtime, "enroll"
        ) as handle:
            key = handle._state_key
            if key is None or key in _ENROLL_BINDINGS:
                raise TenantBindingError("enroll scopeが不正")
            _ENROLL_BINDINGS[key] = binding
            yield handle
    finally:
        if key is not None:
            _ENROLL_BINDINGS.pop(key, None)


@contextmanager
def _initial_resolution_transaction_scope(
    binding: _ResolutionBinding,
) -> Iterator[_TenantTransaction]:
    """新規作成を許さない、同Sessionのlookup/既存再交付登録。"""
    if type(binding) is not _ResolutionBinding or binding.consumed:
        raise TenantBindingError("resolve登録が不正又は再使用")
    binding.consumed = True
    key = None
    try:
        with _initial_actor_transaction_scope(
            binding.context, binding.runtime, "business"
        ) as handle:
            key = handle._state_key
            if key is None or key in _RESOLVE_BINDINGS:
                raise TenantBindingError("resolve実scopeが不正")
            _RESOLVE_BINDINGS[key] = binding
            yield handle
    finally:
        if key is not None:
            _RESOLVE_BINDINGS.pop(key, None)


def _assert_existing_resolution_owner(handle, context, runtime, owner, bound) -> None:
    """lookupの実結果とowner全値を照合し、別Sessionへadapterを移さない。"""
    from pitchlog.repositories.game_start import BoundInitialStartPayload
    from pitchlog.repositories.initial_recording_right import _StartOwner

    _assert_initial_actor_transaction(handle, context, "business")
    binding = _RESOLVE_BINDINGS.get(handle._state_key)
    if (
        binding is None
        or binding.runtime is not runtime
        or binding.context is not context
        or not binding.looked_up
        or not binding.device_checked
        or binding.outcome != "committed"
        or type(owner) is not _StartOwner
        or type(bound) is not BoundInitialStartPayload
    ):
        raise TenantBindingError("committed resolve登録がない")
    owner.__post_init__()
    bound.assert_owner(owner)
    if (
        owner.game_id,
        owner.start_request_id,
        owner.device_id,
        owner.attempt_id,
        owner.request_digest,
        bound.credential_digest,
    ) != (
        binding.game_id,
        binding.start_request_id,
        binding.device_id,
        binding.attempt_id,
        binding.request_digest,
        binding.credential_digest,
    ):
        raise TenantBindingError("committed resolveの実ownerが不一致")


@dataclass(frozen=True, slots=True)
class _PortDecisionPhase:
    """実scopeへ束縛した判定中制約。新しい認可資格ではない。"""

    handle: _TenantTransaction
    runtime: object
    lifetime: tuple[object, object]
    context: TenantContext
    bound: Any
    snapshot: str
    kind: Literal["rg1-precheck", "rg1-commit", "device", "rights", "content"]


_PORT_PHASES: dict[object, _PortDecisionPhase] = {}
_PORT_DEVICE_BIND_USED: set[object] = set()


@contextmanager
def _port_predecision_phase(handle: _TenantTransaction, kind: str):
    """同じrunを保持したまま、Port判定中の業務DMLを閉じる。"""
    from pitchlog.sync.control_provider.writer_binding import (
        _LIVE_BINDINGS,
        _LiveWriterBinding,
    )

    if (
        type(handle) is not _TenantTransaction
        or type(kind) is not str
        or kind
        not in (
            "rg1-precheck",
            "rg1-commit",
            "device",
            "rights",
            "content",
        )
    ):
        raise TenantBindingError("Port判定phaseが不正")
    lifetime = handle._writer_lifetime()
    key = handle._state_key
    bound = _LIVE_BINDINGS.get(key)
    if (
        key in _PORT_PHASES
        or key in _INITIAL_ACTOR_STATES
        or type(bound) is not _LiveWriterBinding
        or bound._handle is not handle
        or bound._used
        or _TRANSACTION_RUNTIMES.get(key) is None
        or type(bound._phase_snapshot) is not str
        or bound._lease._phase_snapshot != bound._phase_snapshot
    ):
        raise TenantBindingError("Port判定phaseのwriterが不一致")
    bound.assert_current()
    phase = _PortDecisionPhase(
        handle,
        _TRANSACTION_RUNTIMES[key],
        lifetime,
        handle._context,
        bound,
        bound._phase_snapshot,
        cast(Any, kind),
    )
    _PORT_PHASES[key] = phase
    try:
        yield
    finally:
        # writer失効の経路でも自分の短命制約だけを除去する。
        if _PORT_PHASES.get(key) is phase:
            del _PORT_PHASES[key]


def _port_phase(handle: _TenantTransaction) -> _PortDecisionPhase | None:
    """再束縛/別runtimeへphaseを貸与しない。SQL発行前だけで確認する。"""
    phase = _PORT_PHASES.get(handle._state_key)
    if phase is None:
        return None
    from pitchlog.sync.control_provider.writer_binding import _LIVE_BINDINGS

    if (
        type(phase) is not _PortDecisionPhase
        or phase.handle is not handle
        or _TRANSACTION_RUNTIMES.get(handle._state_key) is not phase.runtime
        or handle._context is not phase.context
        or _LIVE_BINDINGS.get(handle._state_key) is not phase.bound
        or phase.bound._used
        or phase.bound._phase_snapshot != phase.snapshot
        or phase.bound._lease._phase_snapshot != phase.snapshot
    ):
        raise TenantBindingError("Port判定phaseが失効又は不一致")
    handle._assert_writer_lifetime(phase.lifetime)
    return phase


def _port_read_types(kind: str):
    """phaseごとの必要read exact型だけを許す。未知Selectを許可しない。"""
    from pitchlog.repositories.roster import PlayerReadToken
    from pitchlog.sync.tokens import (
        GameReadToken,
        RecordingGenerationByNumberReadToken,
        RecordingGenerationReadToken,
        TemporaryPlayerMappingReadToken,
    )

    return {
        "rg1-precheck": frozenset(),
        "rg1-commit": frozenset(),
        "device": frozenset(),
        "rights": frozenset(
            {RecordingGenerationReadToken, RecordingGenerationByNumberReadToken}
        ),
        "content": frozenset(
            {PlayerReadToken, TemporaryPlayerMappingReadToken, GameReadToken}
        ),
    }[kind]


def _require_port_read_token(phase, operation):
    if type(operation) not in _port_read_types(phase.kind):
        raise TenantBindingError("Port判定phaseの業務書込又は未知readを拒否")


def _require_plain_port_select(statement):
    """既登録readでも、DML/行lock/副作用関数へ差し替えた文を拒否する。"""
    from sqlalchemy.sql import visitors
    from sqlalchemy.sql.functions import FunctionElement
    from sqlalchemy.sql.selectable import Select

    if (
        not isinstance(statement, Select)
        or statement._for_update_arg is not None
        or any(
            isinstance(node, FunctionElement) for node in visitors.iterate(statement)
        )
    ):
        raise TenantBindingError("Port判定phaseの読取文が不正")


def _require_port_function(phase, operation, function_id):
    """正規qualification/stampとRG1だけを有限照合。汎用関数は禁止。"""
    allowed = {
        "rg1-precheck": {"rg1_api.rg1_read_open", "rg1_control.scope_binding"},
        "rg1-commit": {
            "rg1_api.rg1_assert_open_before_commit",
            "rg1_control.scope_binding",
        },
        "device": {"sync_right_api.bind_device", "sync_right_api.bind_ordinary_device"},
        "rights": {
            "sync_right_api.check_current_right",
            "sync_right_api.check_ordinary_right",
        },
        "content": set(),
    }[phase.kind] | {
        "sync_fence_api.assert_writer_binding",
        "sync_fence_api.read_writer_identity",
    }
    if function_id not in allowed:
        raise TenantBindingError("Port判定phaseの固定関数が未許可")
    if function_id in {
        "sync_right_api.bind_device",
        "sync_right_api.check_current_right",
        "sync_right_api.bind_ordinary_device",
        "sync_right_api.check_ordinary_right",
        "sync_fence_api.assert_writer_binding",
    }:
        lease = phase.bound._lease
        for field_name, expected in (
            ("attempt_id", lease.attempt_id),
            ("phase_id", lease.phase_id),
            ("binding_nonce", lease.nonce),
            ("device_id", lease.device_id),
            ("game_id", lease.game_id),
        ):
            if getattr(operation, field_name, None) != expected:
                raise TenantBindingError("Port判定phaseの固定関数入力が別binding")


def _is_port_command(operation):
    from pitchlog.sync.ordinary_pitch_tokens import (
        ProjectOrdinaryPitchToken,
        ValidateOrdinaryPitchToken,
    )
    from pitchlog.sync.terminal_pitch_tokens import (
        ProjectPlayPrefixToken,
        ValidatePlayPrefixToken,
    )
    from pitchlog.sync.tokens import (
        PortBindCurrentDeviceToken,
        PortCheckCurrentRightToken,
        PortCheckPresentedRightToken,
        PortProjectFirstBallToken,
        PortRG1CommitCheckToken,
        PortRG1PrecheckToken,
        PortValidateFirstBallToken,
    )

    return isinstance(
        operation,
        (
            ValidateOrdinaryPitchToken,
            ProjectOrdinaryPitchToken,
            ValidatePlayPrefixToken,
            ProjectPlayPrefixToken,
            PortBindCurrentDeviceToken,
            PortCheckCurrentRightToken,
            PortCheckPresentedRightToken,
            PortProjectFirstBallToken,
            PortRG1PrecheckToken,
            PortRG1CommitCheckToken,
            PortValidateFirstBallToken,
        ),
    )


def _verified_recovery_epoch(handle, phase) -> int:
    """同scopeの実借用だけを照合し、epochをPortへ公開せず核で使う。"""
    from pitchlog.recording_rights.rg1_lifecycle import _Activation

    if (
        _port_phase(handle) is not phase
        or phase.kind not in {"rg1-precheck", "rg1-commit", "rights"}
        or _TRANSACTION_RUNTIMES.get(handle._state_key) is not phase.runtime
    ):
        raise TenantBindingError("記録権の復旧世代scopeが不一致")
    handle._assert_writer_lifetime(phase.lifetime)
    key = handle._state_key
    loan = _RG1_LOANS.get(key)
    if type(loan) is not _GateLoan:
        raise TenantBindingError("記録権の実RG1借用がない")
    from pitchlog.sync.control_provider.writer_binding import WriterIdentity

    identity = phase.bound._identity
    binding = loan.binding
    if (
        type(identity) is not WriterIdentity
        or type(binding) is not BusinessBinding
        or (
            type(binding.database_oid) is not int
            or type(binding.backend_pid) is not int
            or binding.system_identifier != identity.system_identifier
            or str(binding.database_oid) != identity.database_oid
            or binding.postmaster_started_at != identity.postmaster_started_at
            or binding.backend_pid != identity.backend_pid
        )
    ):
        raise TenantBindingError("記録権のRG1借用が別DB/backend")
    loan.assert_held()
    if loan.binding is not binding or phase.bound._identity is not identity:
        raise TenantBindingError("記録権のRG1借用が差し替えられた")
    if _RG1_LOANS.get(key) is not loan or _port_phase(handle) is not phase:
        raise TenantBindingError("記録権の実RG1借用が失効")
    activation = loan._activation
    if type(activation) is not _Activation or (
        type(activation.epoch) is not int or not 0 < activation.epoch < 2**63
    ):
        raise TenantBindingError("記録権の復旧世代が不正")
    return activation.epoch


def _execute_port_command(handle, operation):
    """値命令へactual lease/nonceを核だけが補い、既固定関数へ渡す。"""
    import json

    from pitchlog.repositories.first_ball import (
        _BindFirstBallDeviceToken,
        _CheckFirstBallRightToken,
    )
    from pitchlog.repositories.rg1 import RG1CommitCheckToken, RG1PrecheckToken
    from pitchlog.sync.ordinary_pitch_tokens import (
        ProjectOrdinaryPitchToken,
        ValidateOrdinaryPitchToken,
    )
    from pitchlog.sync.terminal_pitch_tokens import (
        ProjectPlayPrefixToken,
        ValidatePlayPrefixToken,
    )
    from pitchlog.sync.tokens import (
        PortBindCurrentDeviceToken,
        PortCheckCurrentRightToken,
        PortCheckPresentedRightToken,
        PortProjectFirstBallToken,
        PortRG1CommitCheckToken,
        PortRG1PrecheckToken,
        PortValidateFirstBallToken,
    )

    phase = _port_phase(handle)
    if type(operation) is ProjectPlayPrefixToken:
        if phase is not None:
            raise TenantBindingError("v2投影命令は判定phase外だけで使う")
        operation.__post_init__()
        from pitchlog.sync.terminal_pitch_projection import apply_play_prefix_projection

        return apply_play_prefix_projection(handle, operation)
    if type(operation) is ValidatePlayPrefixToken:
        operation.__post_init__()
        from pitchlog.sync.ordinary_pitch_execution import _ordinary_content_result

        accepted = _ordinary_content_result(
            handle, operation.event, operation.writer, mode="play-prefix-play-v2"
        )
        return TenantOperationResult(
            ((accepted, None if accepted else "v2投球の実評価値と不一致"),)
        )
    if type(operation) is ProjectOrdinaryPitchToken:
        if phase is not None:
            raise TenantBindingError("通常投影命令は判定phase外だけで使う")
        operation.__post_init__()
        from pitchlog.sync.ordinary_pitch_projection import (
            apply_ordinary_pitch_projection,
        )

        return apply_ordinary_pitch_projection(handle, operation)
    if type(operation) is ValidateOrdinaryPitchToken:
        operation.__post_init__()
        from pitchlog.sync.ordinary_pitch_execution import _ordinary_content_result

        accepted = _ordinary_content_result(handle, operation.event, operation.writer)
        return TenantOperationResult(
            ((accepted, None if accepted else "通常投球の実評価値と不一致"),)
        )
    if type(operation) is PortProjectFirstBallToken:
        if phase is not None:
            raise TenantBindingError("投影命令は判定phaseの外だけで使う")
        from pitchlog.sync.first_ball_execution import _apply_first_ball_projection

        return _apply_first_ball_projection(handle, operation)
    if phase is None:
        raise TenantBindingError("Port値命令は実判定phaseを必要とする")
    phase.bound.assert_current()
    if type(operation) is PortValidateFirstBallToken and phase.kind == "content":
        from pitchlog.sync.first_ball_execution import _validate_first_ball_command

        return _validate_first_ball_command(handle, operation)
    lease = phase.bound._lease
    if type(operation) is PortCheckPresentedRightToken and phase.kind == "rights":
        from pitchlog.sync.first_ball_proof import FirstBallProofError, proof_digest

        raw = json.loads(phase.snapshot)["phase"]
        if (
            type(operation.game_id) is not UUID
            or operation.game_id != lease.game_id
            or type(operation.wire_d4) is not str
            or operation.wire_d4 != raw["wire_d4"]
        ):
            raise TenantBindingError("提示記録権命令がactual bindingと不一致")
        try:
            digest = proof_digest(operation.raw_v12)
        except FirstBallProofError:
            return TenantOperationResult(((False,),))
        epoch = _verified_recovery_epoch(handle, phase)
        result = handle.run(
            PortCheckCurrentRightToken(
                operation.game_id, operation.wire_d4, epoch, digest
            )
        )
        if type(result) is not TenantOperationResult or (
            type(result.rows) is not tuple
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 2
            or any(type(value) is not bool for value in result.rows[0])
        ):
            raise TenantBindingError("現権利命令の結果が不正")
        recovery, right = result.rows[0]
        if recovery is not True:
            raise TenantBindingError("実RG1借用と業務復旧世代が不一致")
        if right is True:
            from pitchlog.sync.ordinary_pitch_execution import (
                _ordinary_qualification_active,
                _record_ordinary_right_epoch,
            )

            if _ordinary_qualification_active(handle):
                _record_ordinary_right_epoch(handle, phase, epoch)
        return TenantOperationResult(((right,),))
    if type(operation) is PortRG1PrecheckToken and phase.kind == "rg1-precheck":
        token = RG1PrecheckToken()
    elif type(operation) is PortRG1CommitCheckToken and phase.kind == "rg1-commit":
        token = RG1CommitCheckToken()
    elif type(operation) is PortBindCurrentDeviceToken and phase.kind == "device":
        if handle._state_key in _PORT_DEVICE_BIND_USED:
            raise TenantBindingError("同writerの端末bindは一度だけ")
        if (
            type(operation.credential_digest) is not bytes
            or len(operation.credential_digest) != 32
        ):
            raise TenantBindingError("端末資格digestの型が不正")
        _PORT_DEVICE_BIND_USED.add(handle._state_key)
        from pitchlog.repositories.ordinary_pitch_qualification import (
            BindOrdinaryDeviceToken,
        )
        from pitchlog.sync.ordinary_pitch_execution import (
            _ordinary_qualification_active,
        )

        if _ordinary_qualification_active(handle):
            token = BindOrdinaryDeviceToken(
                lease.attempt_id,
                lease.phase_id,
                lease.nonce,
                lease.device_id,
                lease.game_id,
                operation.credential_digest,
            )
        else:
            token = _BindFirstBallDeviceToken(
                lease.attempt_id,
                lease.phase_id,
                lease.nonce,
                lease.device_id,
                lease.game_id,
                operation.credential_digest,
            )
    elif type(operation) is PortCheckCurrentRightToken and phase.kind == "rights":
        raw = json.loads(phase.snapshot)["phase"]
        if (
            type(operation.game_id) is not UUID
            or operation.game_id != lease.game_id
            or type(operation.wire_d4) is not str
            or operation.wire_d4 != raw["wire_d4"]
            or type(operation.recovery_generation) is not int
            or not 0 < operation.recovery_generation < 2**63
            or type(operation.proof_digest) is not bytes
            or len(operation.proof_digest) != 32
        ):
            raise TenantBindingError("現権利命令がactual bindingと不一致")
        from pitchlog.repositories.ordinary_pitch_qualification import (
            CheckOrdinaryRightToken,
        )
        from pitchlog.sync.ordinary_pitch_execution import (
            _ordinary_qualification_active,
        )

        if _ordinary_qualification_active(handle):
            token = CheckOrdinaryRightToken(
                lease.attempt_id,
                lease.phase_id,
                lease.nonce,
                lease.device_id,
                lease.game_id,
                raw["internal_generation"],
                operation.recovery_generation,
                operation.proof_digest,
            )
        else:
            token = _CheckFirstBallRightToken(
                lease.attempt_id,
                lease.phase_id,
                lease.nonce,
                lease.device_id,
                lease.game_id,
                raw["internal_generation"],
                operation.recovery_generation,
                operation.proof_digest,
            )
    else:
        raise TenantBindingError("Port値命令の型又はphaseが不一致")
    result = handle.run_function(token)
    if type(operation) in {PortRG1PrecheckToken, PortRG1CommitCheckToken}:
        if type(result) is not TenantOperationResult or (
            type(result.rows) is not tuple
            or len(result.rows) != 1
            or type(result.rows[0]) is not tuple
            or len(result.rows[0]) != 1
            or type(result.rows[0][0]) is not bool
        ):
            raise TenantBindingError("RG1命令の結果が不正")
        if result.rows[0][0] is True:
            _verified_recovery_epoch(handle, phase)
    return result
