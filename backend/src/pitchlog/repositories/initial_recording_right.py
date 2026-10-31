"""初期記録権の固定9操作と、真正なactor scopeだけを接ぐ。"""

from __future__ import annotations

import hashlib
import hmac
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast, final
from uuid import UUID

from pitchlog.recording_rights.initial_grant import (
    InitialGrantConflict,
    InitialGrantRecord,
    InitialGrantUnavailable,
    ProofEnvelope,
)
from pitchlog.repositories.context import TenantContext
from pitchlog.repositories.function_operations import (
    _INITIAL_ENROLL_FUNCTION_TYPES,
    _INITIAL_FUNCTION_TYPES,
    _INITIAL_RESOLVE_FUNCTION_TYPES,
    _INITIAL_START_FUNCTION_TYPES,
    FunctionOperationRegistration,
    _build_fixed_function_statement,
    build_function_registry,
)
from pitchlog.repositories.rg1 import assert_rg1_open_before_commit, read_rg1_open
from pitchlog.repositories.tokens import TenantOperationResult, TenantOperationToken

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pitchlog.repositories.game_start import (
        BoundInitialStartPayload,
        InitialStartReceipt,
    )
    from pitchlog.repositories.transaction import _TenantTransaction

__all__ = ("InitialRecordingRightScope",)
_SCOPE_CREATION = object()
_SCOPE_BINDINGS: dict[
    InitialRecordingRightScope, tuple[object, object, object, tuple[object, ...]]
] = {}


def _positive_generation(value: object) -> bool:
    """boolを整数へ混ぜず、PostgreSQL bigintの正域へ閉じる。"""
    return type(value) is int and 0 < value < 2**63


def _credential_digest(credential: str) -> bytes:
    """opaque資格を正規化せずUTF-8として単一digestへ写す。"""
    if type(credential) is not str or not credential:
        raise InitialGrantUnavailable("端末資格を確認できない")
    try:
        return hashlib.sha256(credential.encode("utf-8")).digest()
    except UnicodeError as error:
        raise InitialGrantUnavailable("端末資格を確認できない") from error


@dataclass(frozen=True, slots=True)
class _StartOwner:
    """brokerだけが構築し、要求と耐久attemptへ束縛する固定owner。"""

    tenant_id: UUID
    game_id: UUID
    start_request_id: UUID
    device_id: UUID
    attempt_id: UUID
    request_digest: bytes = field(repr=False)

    def __post_init__(self) -> None:
        """曖昧なUUIDとcallerの不定長digestを拒否する。"""
        if (
            any(
                type(v) is not UUID
                for v in (
                    self.tenant_id,
                    self.game_id,
                    self.start_request_id,
                    self.device_id,
                    self.attempt_id,
                )
            )
            or type(self.request_digest) is not bytes
            or len(self.request_digest) != 32
        ):
            raise InitialGrantUnavailable("開始ownerの束縛値が不正")


@dataclass(frozen=True, slots=True)
class _LockDeviceToken(TenantOperationToken):
    """端末資格を共有lockして読む。"""

    device_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:lock_device"


@dataclass(frozen=True, slots=True)
class _ReadExistingStartToken(TenantOperationToken):
    """同一確定要求の現権利だけを読む。"""

    game_id: UUID
    start_request_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:read_existing_start"


@dataclass(frozen=True, slots=True)
class _ReadStartGameToken(TenantOperationToken):
    """対象試合の状態だけを読む。"""

    game_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:read_start_game"


@dataclass(frozen=True, slots=True)
class _LockPreparingGameToken(TenantOperationToken):
    """preparingの試合だけをlockする。"""

    game_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:lock_preparing_game"


@dataclass(frozen=True, slots=True)
class _LockCurrentStartToken(TenantOperationToken):
    """game→現世代→配達を順にlockする。"""

    game_id: UUID
    start_request_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:lock_current_start"


@dataclass(frozen=True, slots=True)
class _CheckBusinessEpochToken(TenantOperationToken):
    """同businessの復旧世代を照合する。"""

    recovery_generation: int

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:check_business_epoch"


@dataclass(frozen=True, slots=True)
class _InsertInitialGrantToken(TenantOperationToken):
    """世代・暗号文・attempt確定を一つの固定関数へ渡す。"""

    game_id: UUID
    start_request_id: UUID
    device_id: UUID
    attempt_id: UUID
    generation: int
    recovery_generation: int
    proof_digest: bytes = field(repr=False)
    key_id: str
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:insert_initial_grant"


@dataclass(frozen=True, slots=True)
class _BeginStartAttemptToken(TenantOperationToken):
    """業務scopeより前の短intentを耐久化する。"""

    game_id: UUID
    start_request_id: UUID
    device_id: UUID
    request_digest: bytes = field(repr=False)
    attempt_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:begin_start_attempt"


@dataclass(frozen=True, slots=True)
class _ResolveStartAttemptToken(TenantOperationToken):
    """同businessでrequest→attemptをlockする。"""

    game_id: UUID
    start_request_id: UUID
    attempt_id: UUID

    @property
    def capability_id(self) -> str:
        """固定能力だけを返す。"""
        return "CAP:initial_right:resolve_start_attempt"


@dataclass(frozen=True, slots=True)
class _ReadInitialStartContextToken(TenantOperationToken):
    """真正scopeが固定する開始contextの6引数操作。"""

    game_id: UUID
    start_request_id: UUID
    attempt_id: UUID
    request_digest: bytes
    typed_payload_json: str

    @property
    def capability_id(self) -> str:
        """私有開始能力だけを返す。"""
        return "CAP:initial_right:read_initial_start_context"


@dataclass(frozen=True, slots=True)
class _PersistInitialStartToken(_ReadInitialStartContextToken):
    """同じownerと全payloadだけを保存する閉操作。"""

    @property
    def capability_id(self) -> str:
        """私有開始能力だけを返す。"""
        return "CAP:initial_right:persist_initial_start"


_INITIAL_TOKEN_TYPES = (
    _LockDeviceToken,
    _ReadExistingStartToken,
    _ReadStartGameToken,
    _LockPreparingGameToken,
    _LockCurrentStartToken,
    _CheckBusinessEpochToken,
    _InsertInitialGrantToken,
    _BeginStartAttemptToken,
    _ResolveStartAttemptToken,
    _ReadInitialStartContextToken,
    _PersistInitialStartToken,
)


def _decode_initial_result(result: TenantOperationResult) -> TenantOperationResult:
    """10列record・暗号長・outcomeを固定契約へ閉じる。"""
    for row in result.rows:
        if len(row) == 10:
            if (
                any(type(v) is not UUID for v in row[:4])
                or not all(_positive_generation(v) for v in row[4:6])
                or type(row[6]) is not bytes
                or len(row[6]) != 32
                or type(row[7]) is not str
                or not row[7]
                or type(row[8]) is not bytes
                or len(row[8]) != 12
                or type(row[9]) is not bytes
                or len(row[9]) != 48
            ):
                raise InitialGrantUnavailable("初期権の保存recordが不正")
        elif len(row) == 2 and type(row[0]) is str:
            outcome, generation = row
            if not (
                (outcome == "pending" and generation is None)
                or (outcome == "committed" and _positive_generation(generation))
            ):
                raise InitialGrantUnavailable("開始attemptの結果を確定できない")
        elif len(row) == 2 and type(row[0]) is UUID:
            if row[1] not in ("pending", "committed"):
                raise InitialGrantUnavailable("開始attemptを進められない")
        elif len(row) == 2 and type(row[0]) is bytes:
            if len(row[0]) != 32:
                raise InitialGrantUnavailable("端末資格を確認できない")
    return result


def _initial_registrations() -> tuple[FunctionOperationRegistration, ...]:
    """旧9と開始2署名の単一宣言から、任意SQLを許さない登録を構成する。"""
    result = []
    for token_type, (function_id, contract) in zip(
        _INITIAL_TOKEN_TYPES,
        (*_INITIAL_FUNCTION_TYPES.items(), *_INITIAL_START_FUNCTION_TYPES.items()),
        strict=True,
    ):
        inputs, outputs, nullable, aware = contract
        schema, name = function_id.split(".")
        scalar = name in (
            "lock_preparing_game",
            "check_business_epoch",
            "insert_initial_grant",
        )
        result.append(
            FunctionOperationRegistration(
                operation_id=f"INITIAL_RIGHT:{name}",
                token_type=token_type,
                capability_id=f"CAP:initial_right:{name}",
                function_id=function_id,
                statement=_build_fixed_function_statement(
                    schema, name, inputs, tuple(k for k, _ in outputs), not scalar
                ),
                input_fields=inputs,
                result_fields=outputs,
                min_rows=1 if scalar else 0,
                max_rows=1,
                decoder=_decode_initial_result,
                nullable_results=nullable,
                aware_datetime_results=aware,
            )
        )
    return tuple(result)


_ALL_INITIAL_REGISTRATIONS = _initial_registrations()
INITIAL_FUNCTION_OPERATIONS = _ALL_INITIAL_REGISTRATIONS[:-2]
_INITIAL_START_FUNCTION_OPERATIONS = _ALL_INITIAL_REGISTRATIONS[-2:]


@dataclass(frozen=True, slots=True)
class _EnrollDeviceToken(TenantOperationToken):
    """短命enroll scopeだけで使う固定INSERT引数。"""

    device_id: UUID
    credential_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """端末登録一件だけの能力を返す。"""
        return "CAP:initial_right:enroll_device"


def _enrollment_registrations() -> tuple[FunctionOperationRegistration, ...]:
    """旧9/開始2の反復を変えず新1登録だけを構築する。"""
    contract = _INITIAL_ENROLL_FUNCTION_TYPES["initial_right_api.enroll_device"]
    inputs, outputs, nullable, aware = contract
    return (
        FunctionOperationRegistration(
            operation_id="INITIAL_RIGHT:enroll_device",
            token_type=_EnrollDeviceToken,
            capability_id="CAP:initial_right:enroll_device",
            function_id="initial_right_api.enroll_device",
            statement=_build_fixed_function_statement(
                "initial_right_api", "enroll_device", inputs, ("device_id",), False
            ),
            input_fields=inputs,
            result_fields=outputs,
            min_rows=1,
            max_rows=1,
            decoder=_decode_initial_result,
            nullable_results=nullable,
            aware_datetime_results=aware,
        ),
    )


@dataclass(frozen=True, slots=True)
class _LookupExistingStartAttemptToken(TenantOperationToken):
    """新規intentを作らず、同ownerの既attemptだけをlockする。"""

    game_id: UUID
    start_request_id: UUID
    device_id: UUID
    request_digest: bytes = field(repr=False)

    @property
    def capability_id(self) -> str:
        """非作成lookupだけの能力を返す。"""
        return "CAP:initial_right:lookup_existing_start_attempt"


def _resolution_registrations() -> tuple[FunctionOperationRegistration, ...]:
    """旧12登録とは独立した新lookup1だけを構築する。"""
    inputs, outputs, nullable, aware = _INITIAL_RESOLVE_FUNCTION_TYPES[
        "initial_right_api.lookup_existing_start_attempt"
    ]
    return (
        FunctionOperationRegistration(
            operation_id="INITIAL_RIGHT:lookup_existing_start_attempt",
            token_type=_LookupExistingStartAttemptToken,
            capability_id="CAP:initial_right:lookup_existing_start_attempt",
            function_id="initial_right_api.lookup_existing_start_attempt",
            statement=_build_fixed_function_statement(
                "initial_right_api",
                "lookup_existing_start_attempt",
                inputs,
                ("attempt_id", "outcome"),
                True,
            ),
            input_fields=inputs,
            result_fields=outputs,
            min_rows=0,
            max_rows=1,
            decoder=_decode_initial_result,
            nullable_results=nullable,
            aware_datetime_results=aware,
        ),
    )


_INITIAL_ENROLL_FUNCTION_OPERATIONS = _enrollment_registrations()
_INITIAL_RESOLVE_FUNCTION_OPERATIONS = _resolution_registrations()
_INITIAL_FUNCTION_REGISTRY = build_function_registry(
    (
        *INITIAL_FUNCTION_OPERATIONS,
        *_INITIAL_START_FUNCTION_OPERATIONS,
        *_INITIAL_ENROLL_FUNCTION_OPERATIONS,
        *_INITIAL_RESOLVE_FUNCTION_OPERATIONS,
    ),
    frozenset(),
)
_INITIAL_INTENT_TOKENS = frozenset({_LockDeviceToken, _BeginStartAttemptToken})
_INITIAL_BUSINESS_TOKENS = frozenset(
    set(_INITIAL_TOKEN_TYPES) - {_BeginStartAttemptToken}
)


@final
class InitialRecordingRightScope:
    """実actorハンドルの生存と固定ownerを毎回再照合する9method adapter。"""

    __slots__ = (
        "_context",
        "_transaction",
        "_owner",
        "_device_valid",
        "_outcome",
        "_resolved_generation",
        "_game_locked",
        "_start_payload",
        "_start_context",
        "_start_receipt",
        "_start_um2_saved",
    )

    def __init_subclass__(cls, **kwargs: object) -> None:
        """派生した偽scopeを拒否する。"""
        raise TypeError("初期権scopeを派生できない")

    def __init__(
        self,
        context: TenantContext,
        transaction: _TenantTransaction,
        owner: _StartOwner,
        creation: object,
        start_payload: BoundInitialStartPayload | None = None,
    ) -> None:
        """私有factoryからのみ生成し、未検証資格から操作を進めない。"""
        if creation is not _SCOPE_CREATION or type(owner) is not _StartOwner:
            raise InitialGrantUnavailable("初期権scopeは私有factoryだけが生成できる")
        self._context, self._transaction, self._owner = context, transaction, owner
        self._device_valid = False
        self._outcome: str | None = None
        self._resolved_generation: int | None = None
        self._game_locked = False
        from pitchlog.repositories.game_start import BoundInitialStartPayload

        if start_payload is not None:
            if type(start_payload) is not BoundInitialStartPayload:
                raise InitialGrantUnavailable("開始payloadの閉型が不正")
            start_payload.assert_owner(owner)
        self._start_payload = start_payload
        self._start_um2_saved = False
        self._start_context: dict[str, Any] | None = None
        self._start_receipt: InitialStartReceipt | None = None
        snapshot = (
            owner.tenant_id,
            owner.game_id,
            owner.start_request_id,
            owner.device_id,
            owner.attempt_id,
            owner.request_digest,
            start_payload,
        )
        _SCOPE_BINDINGS[self] = (context, transaction, owner, snapshot)
        try:
            self.assert_bound_tenant(owner.tenant_id)
        except BaseException:
            _SCOPE_BINDINGS.pop(self, None)
            raise

    def _check(self) -> None:
        """同じ真正scope/tenant/phaseが今も有効であることを検査する。"""
        from pitchlog.repositories.transaction import _assert_initial_actor_transaction

        binding = _SCOPE_BINDINGS.get(self)
        if (
            type(self) is not InitialRecordingRightScope
            or binding is None
            or binding[:3] != (self._context, self._transaction, self._owner)
            or binding[0] is not self._context
            or binding[1] is not self._transaction
            or binding[2] is not self._owner
            or binding[3][-1] is not self._start_payload
            or binding[3]
            != (
                self._owner.tenant_id,
                self._owner.game_id,
                self._owner.start_request_id,
                self._owner.device_id,
                self._owner.attempt_id,
                self._owner.request_digest,
                self._start_payload,
            )
        ):
            raise InitialGrantUnavailable("初期権scopeのowner束縛が失効又は不一致")
        _assert_initial_actor_transaction(self._transaction, self._context, "business")
        if self._start_payload is not None:
            self._start_payload.assert_owner(self._owner)
        if self._context.tenant_id != self._owner.tenant_id:
            raise InitialGrantUnavailable("開始ownerとtenantが一致しない")

    def _require_device(self) -> None:
        """同Sessionの資格確認とrequest/attempt排他が完了したことを要求する。"""
        self._check()
        if not self._device_valid or self._outcome not in ("pending", "committed"):
            raise InitialGrantUnavailable("端末資格を確認できない")

    def assert_bound_tenant(self, tenant_id: UUID) -> None:
        """固定tenantと発行証跡を実照合する。"""
        self._check()
        if type(tenant_id) is not UUID or tenant_id != self._owner.tenant_id:
            raise InitialGrantUnavailable("初期権のtenantが一致しない")

    def lock_valid_device(self, device_id: UUID, credential: str) -> bool:
        """資格共有lockの真照合後に同Sessionでrequest→attemptを排他lockする。"""
        self._check()
        if type(device_id) is not UUID or device_id != self._owner.device_id:
            return False
        self._device_valid = False
        rows = self._transaction.run_function(_LockDeviceToken(device_id)).rows
        if not rows or rows[0][1] is not None:
            return False
        if not hmac.compare_digest(
            cast(bytes, rows[0][0]), _credential_digest(credential)
        ):
            return False
        owner = self._owner
        rows = self._transaction.run_function(
            _ResolveStartAttemptToken(
                owner.game_id, owner.start_request_id, owner.attempt_id
            )
        ).rows
        if not rows:
            raise InitialGrantUnavailable("開始attemptのownerを確認できない")
        self._outcome = cast(str, rows[0][0])
        self._resolved_generation = cast(int | None, rows[0][1])
        self._device_valid = True
        return True

    def _same_request(self, game_id: UUID, request_id: UUID) -> None:
        """別game/requestへのハンドル転用を拒否する。"""
        self._require_device()
        if (
            type(game_id) is not UUID
            or type(request_id) is not UUID
            or (game_id, request_id)
            != (self._owner.game_id, self._owner.start_request_id)
        ):
            raise InitialGrantConflict("開始要求のownerが一致しない")

    def _record(
        self, rows: tuple[tuple[object, ...], ...]
    ) -> InitialGrantRecord | None:
        """既decoderで閉じたrecordをowner/確定結果と再照合する。"""
        if not rows:
            if self._outcome == "committed":
                raise InitialGrantConflict("同一開始の現権利がない")
            return None
        if self._outcome != "committed":
            raise InitialGrantConflict("未確定attemptに既存権利を結び付けられない")
        row = rows[0]
        if (
            tuple(row[:4])
            != (
                self._owner.tenant_id,
                self._owner.game_id,
                self._owner.start_request_id,
                self._owner.device_id,
            )
            or row[4] != self._resolved_generation
        ):
            raise InitialGrantConflict("保存済み初期権のownerが一致しない")
        return InitialGrantRecord(
            cast(UUID, row[0]),
            cast(UUID, row[1]),
            cast(UUID, row[2]),
            cast(UUID, row[3]),
            cast(int, row[4]),
            cast(int, row[5]),
            cast(bytes, row[6]),
            ProofEnvelope(cast(str, row[7]), cast(bytes, row[8]), cast(bytes, row[9])),
        )

    def existing_start(
        self, game_id: UUID, start_request_id: UUID
    ) -> InitialGrantRecord | None:
        """同一現権利だけを返し、欠損から新規予約へ進めない。"""
        self._same_request(game_id, start_request_id)
        return self._record(
            self._transaction.run_function(
                _ReadExistingStartToken(game_id, start_request_id)
            ).rows
        )

    def precheck_open_and_game(self, game_id: UUID) -> None:
        """既RG1非lock読取と新規/同一再交付の状態を検査する。"""
        self._same_request(game_id, self._owner.start_request_id)
        read_rg1_open(self._transaction)
        rows = self._transaction.run_function(_ReadStartGameToken(game_id)).rows
        valid = (
            {"preparing"}
            if self._outcome == "pending"
            else {"preparing", "in_progress", "finished"}
        )
        if not rows or rows[0][0] not in valid:
            raise InitialGrantConflict("試合を開始できない")

    def lock_preparing_game(self, game_id: UUID) -> None:
        """preparingを同Sessionでlockする。開始service接続は後続へ残す。"""
        self._same_request(game_id, self._owner.start_request_id)
        if self._outcome != "pending" or self._transaction.run_function(
            _LockPreparingGameToken(game_id)
        ).rows != ((True,),):
            raise InitialGrantConflict("試合を開始できない")
        self._game_locked = True
        if self._start_payload is not None:
            from pitchlog.repositories.game_start import _initialize_start

            self._start_receipt = _initialize_start(self, self._start_payload)

    def lock_current_start(
        self, game_id: UUID, start_request_id: UUID
    ) -> InitialGrantRecord | None:
        """同一確定要求のgame→現世代→配達を再照合する。"""
        self._same_request(game_id, start_request_id)
        record = self._record(
            self._transaction.run_function(
                _LockCurrentStartToken(game_id, start_request_id)
            ).rows
        )
        if self._start_payload is not None:
            from pitchlog.repositories.game_start import (
                _read_start_context,
                _receipt_from_context,
            )

            context = _read_start_context(self._transaction, self._start_payload)
            if context["outcome"] != "committed":
                raise InitialGrantConflict("開始済み原本がない")
            self._start_receipt = _receipt_from_context(self._start_payload, context)
        return record

    def assert_recovery_generation(self, value: int) -> None:
        """実business epochと外部fence値が一致することを固定readで確認する。"""
        self._require_device()
        if not _positive_generation(value) or self._transaction.run_function(
            _CheckBusinessEpochToken(value)
        ).rows != ((True,),):
            raise InitialGrantUnavailable("復旧世代が一致しない")

    def insert_initial_grant(self, record: InitialGrantRecord) -> None:
        """単一issuerの世代/暗号文を固定ownerの同businessへ保存する。"""
        self._require_device()
        owner = self._owner
        if (
            type(record) is not InitialGrantRecord
            or type(record.envelope) is not ProofEnvelope
            or not self._game_locked
            or self._outcome != "pending"
            or (
                record.tenant_id,
                record.game_id,
                record.start_request_id,
                record.device_id,
            )
            != (owner.tenant_id, owner.game_id, owner.start_request_id, owner.device_id)
        ):
            raise InitialGrantConflict("初期付与のownerが一致しない")
        _decode_initial_result(
            TenantOperationResult(
                (
                    (
                        record.tenant_id,
                        record.game_id,
                        record.start_request_id,
                        record.device_id,
                        record.generation,
                        record.recovery_generation,
                        record.proof_digest,
                        record.envelope.key_id,
                        record.envelope.nonce,
                        record.envelope.ciphertext,
                    ),
                )
            )
        )
        token = _InsertInitialGrantToken(
            record.game_id,
            record.start_request_id,
            record.device_id,
            owner.attempt_id,
            record.generation,
            record.recovery_generation,
            record.proof_digest,
            record.envelope.key_id,
            record.envelope.nonce,
            record.envelope.ciphertext,
        )
        if self._transaction.run_function(token).rows != ((True,),):
            raise InitialGrantConflict("初期付与を確定できない")
        self._outcome = "committed"
        self._resolved_generation = record.generation

    def assert_open_before_commit(self) -> None:
        """既RG1の実共有lockを同一scopeでcommitまで保持する。"""
        self._require_device()
        assert_rg1_open_before_commit(self._transaction)


@contextmanager
def _initial_recording_right_scope(
    context: TenantContext,
    owner: _StartOwner,
    actor_runtime: object,
    start_payload: BoundInitialStartPayload | None = None,
) -> Iterator[InitialRecordingRightScope]:
    """登録済みactorの同一businessを私有factoryとして生成する。"""
    from pitchlog.repositories.transaction import _initial_actor_transaction_scope

    with _initial_actor_transaction_scope(
        context, actor_runtime, "business"
    ) as transaction:
        with _bound_initial_adapter(
            context, transaction, owner, start_payload
        ) as scope:
            yield scope


@contextmanager
def _existing_start_scope_on_handle(
    context: TenantContext,
    owner: _StartOwner,
    actor_runtime: object,
    transaction: _TenantTransaction,
    bound: BoundInitialStartPayload,
) -> Iterator[InitialRecordingRightScope]:
    """真正resolve登録のcommitted lookupと同じSessionでだけadapterを作る。"""
    from pitchlog.repositories.transaction import _assert_existing_resolution_owner

    _assert_existing_resolution_owner(transaction, context, actor_runtime, owner, bound)
    with _bound_initial_adapter(context, transaction, owner, bound) as scope:
        yield scope


@contextmanager
def _bound_initial_adapter(
    context: TenantContext,
    transaction: _TenantTransaction,
    owner: _StartOwner,
    payload: BoundInitialStartPayload | None,
) -> Iterator[InitialRecordingRightScope]:
    """旧factoryと同一の生成/失効処理を共有し、Session生成や再束縛をしない。"""
    scope = InitialRecordingRightScope(
        context, transaction, owner, _SCOPE_CREATION, payload
    )
    try:
        yield scope
    finally:
        _SCOPE_BINDINGS.pop(scope, None)
