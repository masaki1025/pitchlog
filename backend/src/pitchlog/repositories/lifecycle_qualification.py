"""終了再開device/rightを実phaseと一回の同writer貸与へ束縛する。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from uuid import UUID

from pitchlog.repositories.function_operations import FunctionOperationError
from pitchlog.repositories.tokens import TenantOperationToken


@dataclass(frozen=True, slots=True, init=False)
class BindLifecycleDeviceToken(TenantOperationToken):
    """実device phaseだけが発行する固定引数。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    credential_digest: bytes = field(repr=False)

    def __new__(cls, *args, **kwargs):
        """同値JSON/nonceから自由に資格を生成しない。"""
        raise FunctionOperationError("終了再開device tokenは私有phaseだけで発行します")

    @property
    def capability_id(self):
        """閉device能力を宣言する。"""
        return "CAP:sync_lifecycle:bind_device"


@dataclass(frozen=True, slots=True, init=False)
class CheckLifecycleRightToken(TenantOperationToken):
    """実rights phaseだけが発行する固定引数。"""

    attempt_id: UUID
    phase_id: UUID
    binding_nonce: bytes = field(repr=False)
    device_id: UUID
    game_id: UUID
    internal_generation: int
    recovery_generation: int
    proof_digest: bytes = field(repr=False)

    def __new__(cls, *args, **kwargs):
        """提示値だけの自由生成を拒否する。"""
        raise FunctionOperationError("終了再開right tokenは私有phaseだけで発行します")

    @property
    def capability_id(self):
        """閉rights能力を宣言する。"""
        return "CAP:sync_lifecycle:check_right"


_RIGHT_CALLS = {}
_RIGHT_TYPES = (BindLifecycleDeviceToken, CheckLifecycleRightToken)


def _right_live(handle, state):
    """既実E1 sourceとphase/Session/topTX/全lease引数を再確認する。"""
    from pitchlog.repositories import transaction
    from pitchlog.sync.lifecycle_execution import _lifecycle_qualification_active

    token, phase, runtime, lifetime, parameters, _used, snapshot, original_lease = state
    if (
        type(handle) is not transaction._TenantTransaction
        or _RIGHT_CALLS.get(handle._state_key) is not state
        or transaction._TRANSACTION_RUNTIMES.get(handle._state_key) is not runtime
        or transaction._port_phase(handle) is not phase
        or phase.handle is not handle
        or phase.runtime is not runtime
        or phase.context is not handle._context
        or phase.snapshot != snapshot
        or phase.bound._lease is not original_lease
        or phase.kind
        != ("device" if type(token) is BindLifecycleDeviceToken else "rights")
        or _lifecycle_qualification_active(handle) is not True
    ):
        raise FunctionOperationError("終了再開rightsの実scopeが失効又は不一致です")
    observed = handle._writer_lifetime()
    if observed[0] is not lifetime[0] or observed[1] is not lifetime[1]:
        raise FunctionOperationError("終了再開rightsの実topTXが不一致です")
    lease = phase.bound._lease
    for name, value in parameters.items():
        actual = (
            handle._bound_tenant_id
            if name == "tenant_id"
            else lease.nonce
            if name == "binding_nonce"
            else getattr(lease, name)
            if name in {"attempt_id", "phase_id", "device_id", "game_id"}
            else getattr(token, name)
        )
        if type(actual) is not type(value) or actual != value:
            raise FunctionOperationError("終了再開rightsの実引数が変更されました")
    for f in fields(token):
        value = getattr(token, f.name)
        if type(value) is not type(parameters[f.name]) or value != parameters[f.name]:
            raise FunctionOperationError("終了再開rights tokenの全値が変更されました")


@contextmanager
def _right_call(handle, token_type, extras):
    """実Port dispatcherの一呼出だけへtokenを貸与する。"""
    from pitchlog.repositories import transaction
    from pitchlog.sync.lifecycle_execution import _lifecycle_qualification_active

    if (
        type(handle) is not transaction._TenantTransaction
        or token_type not in _RIGHT_TYPES
        or handle._state_key in _RIGHT_CALLS
        or _lifecycle_qualification_active(handle) is not True
    ):
        raise FunctionOperationError("終了再開rightsの発行入口が不一致です")
    phase = transaction._port_phase(handle)
    expected_kind = "device" if token_type is BindLifecycleDeviceToken else "rights"
    if phase is None or phase.kind != expected_kind:
        raise FunctionOperationError("終了再開rightsの判定phaseが不一致です")
    lease = phase.bound._lease
    params = dict(
        tenant_id=handle._bound_tenant_id,
        attempt_id=lease.attempt_id,
        phase_id=lease.phase_id,
        binding_nonce=lease.nonce,
        device_id=lease.device_id,
        game_id=lease.game_id,
        **extras,
    )
    if any(
        type(params[n]) is not UUID
        for n in ("tenant_id", "attempt_id", "phase_id", "device_id", "game_id")
    ):
        raise FunctionOperationError("終了再開rightsのUUID実型が不一致です")
    for name in ("binding_nonce", "credential_digest", "proof_digest"):
        if name in params and (
            type(params[name]) is not bytes or len(params[name]) != 32
        ):
            raise FunctionOperationError("終了再開rightsの固定byte長が不一致です")
    for name in ("internal_generation", "recovery_generation"):
        if name in params and (
            type(params[name]) is not int or not 0 < params[name] < 2**63
        ):
            raise FunctionOperationError("終了再開rightsの正bigintが不一致です")
    token = object.__new__(token_type)
    if set(params) != {"tenant_id", *(f.name for f in fields(token_type))}:
        raise FunctionOperationError("終了再開rightsの閉引数が不一致です")
    for f in fields(token_type):
        object.__setattr__(token, f.name, params[f.name])
    state = [
        token,
        phase,
        transaction._TRANSACTION_RUNTIMES.get(handle._state_key),
        handle._writer_lifetime(),
        params,
        False,
        phase.snapshot,
        lease,
    ]
    key = handle._state_key
    _RIGHT_CALLS[key] = state
    try:
        _right_live(handle, state)
        yield token
        _right_live(handle, state)
        if state[5] is not True:
            raise FunctionOperationError("終了再開rightsの一回資格が消費されていません")
    finally:
        if _RIGHT_CALLS.get(key) is state:
            del _RIGHT_CALLS[key]


def _qualified_lifecycle_right_call(handle, operation):
    """実SQL前に同token/phaseの貸与を一回だけ消費する。"""
    state = _RIGHT_CALLS.get(handle._state_key)
    if state is None or state[0] is not operation or state[5] is not False:
        raise FunctionOperationError("終了再開rightsの一回資格が未発行又は消費済みです")
    _right_live(handle, state)
    state[5] = True
    return MappingProxyType(dict(state[4]))


def _assert_lifecycle_right_live(handle, operation):
    """SQL後も同じsource/phase/nonce/寿命を検査する。"""
    state = _RIGHT_CALLS.get(handle._state_key)
    if state is None or state[0] is not operation:
        raise FunctionOperationError("終了再開rightsの貸与が失効しています")
    _right_live(handle, state)


def run_lifecycle_device(handle, credential_digest):
    """既device Portから実固定関数へ接続し、偽成功を補わない。"""
    with _right_call(
        handle, BindLifecycleDeviceToken, {"credential_digest": credential_digest}
    ) as token:
        return handle.run_function(token)


def run_lifecycle_right(handle, recovery_generation, proof_digest):
    """既rights snapshotの実内部世代を使用し、target世代を流用しない。"""
    from pitchlog.repositories import transaction

    phase = transaction._port_phase(handle)
    if phase is None or phase.kind != "rights":
        raise FunctionOperationError("終了再開rights phaseがありません")
    raw = json.loads(phase.snapshot)["phase"]
    with _right_call(
        handle,
        CheckLifecycleRightToken,
        {
            "internal_generation": raw["internal_generation"],
            "recovery_generation": recovery_generation,
            "proof_digest": proof_digest,
        },
    ) as token:
        return handle.run_function(token)
