"""制御 provider が検証する内部 binding と証拠参照の閉じた型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import get_args
from uuid import UUID

from pitchlog.sync.stop_contract import (
    AttemptIdentity,
    SyncStopReason,
    SyncStopResolution,
)


def _uuid(value: object) -> bool:
    """内部識別子の値型を確認する。"""
    return type(value) is UUID


def _ref(value: object) -> bool:
    """参照の外形だけを確認し、真正性は認定しない。"""
    return type(value) is str and bool(value)


def _positive(value: object) -> bool:
    """Bool を世代・位置へ混入させない。"""
    return type(value) is int and value > 0


def _expiry(value: object) -> bool:
    """比較可能な UTC 期限だけを受ける。"""
    if type(value) is not datetime or value.tzinfo is None:
        return False
    offset = value.utcoffset()
    return offset is not None and offset.total_seconds() == 0


@dataclass(frozen=True, slots=True)
class AuthorityBinding:
    """制御 instance と業務 instance、復元外 epoch の組。"""

    control_instance: UUID
    business_instance: UUID
    restore_epoch: UUID

    def __post_init__(self) -> None:
        """欠損した権威識別を拒否する。"""
        if not all(
            _uuid(value)
            for value in (
                self.control_instance,
                self.business_instance,
                self.restore_epoch,
            )
        ):
            raise ValueError("権威 binding が不正")


@dataclass(frozen=True, slots=True, repr=False)
class AttemptBinding:
    """認証主体・原 D4・内部世代・codec・要求全体 FP を固定する。"""

    authority: AuthorityBinding
    tenant_id: UUID
    device_id: UUID
    game_id: UUID
    wire_d4: str
    internal_generation: int
    attempt_id: UUID
    codec_version: int
    request_fingerprint: str
    event_count: int

    def __post_init__(self) -> None:
        """内部値の外形と C1 照会識別子の整合を検査する。"""
        if (
            type(self.authority) is not AuthorityBinding
            or not all(
                _uuid(value)
                for value in (
                    self.tenant_id,
                    self.device_id,
                    self.game_id,
                    self.attempt_id,
                )
            )
            or not _ref(self.wire_d4)
            or not _positive(self.internal_generation)
            or not _positive(self.codec_version)
            or not _ref(self.request_fingerprint)
            or not _positive(self.event_count)
        ):
            raise ValueError("試行 binding が不正")
        self.identity()

    def identity(self) -> AttemptIdentity:
        """既存 C1 の五値照会識別子を返す。"""
        return AttemptIdentity(
            str(self.attempt_id),
            str(self.game_id),
            self.wire_d4,
            self.codec_version,
            self.request_fingerprint,
        )


@dataclass(frozen=True, slots=True, repr=False)
class EventPhaseBinding:
    """D1 付き停止対象を試行内の一つの phase に固定する。"""

    attempt: AttemptBinding
    phase_id: UUID
    position: int
    d1: int
    d5: UUID
    event_fingerprint: str

    def __post_init__(self) -> None:
        """D1・D5・イベント FP と有限列内位置を確認する。"""
        if (
            type(self.attempt) is not AttemptBinding
            or not _uuid(self.phase_id)
            or not _positive(self.position)
            or self.position > self.attempt.event_count
            or not _positive(self.d1)
            or not _uuid(self.d5)
            or not _ref(self.event_fingerprint)
        ):
            raise ValueError("イベント phase binding が不正")


@dataclass(frozen=True, slots=True, repr=False)
class D1lessPhaseBinding:
    """P3 等の D1 なし phase。D1 付き停止記録へは渡せない。"""

    attempt: AttemptBinding
    phase_id: UUID
    position: int
    d5: UUID
    event_fingerprint: str

    def __post_init__(self) -> None:
        """D1 を持たない phase の境界を確認する。"""
        if (
            type(self.attempt) is not AttemptBinding
            or not _uuid(self.phase_id)
            or not _positive(self.position)
            or self.position > self.attempt.event_count
            or not _uuid(self.d5)
            or not _ref(self.event_fingerprint)
        ):
            raise ValueError("D1 なし phase binding が不正")


type PhaseBinding = EventPhaseBinding | D1lessPhaseBinding


@dataclass(frozen=True, slots=True, repr=False)
class AttemptResolutionBlock:
    """照会中の旧 attempt 進入禁止。永久の旧要求禁止とは別。"""

    attempt: AttemptBinding
    intent_ref: str

    def __post_init__(self) -> None:
        """試行と intent 参照の形だけを確認する。"""
        if type(self.attempt) is not AttemptBinding or not _ref(self.intent_ref):
            raise ValueError("照会 block が不正")


@dataclass(frozen=True, slots=True, repr=False)
class RetiredRequestBlock:
    """全 attempt 共通の旧 D5・FP・slot 禁止を表す。"""

    authority: AuthorityBinding
    tenant_id: UUID
    game_id: UUID
    wire_d4: str
    slot_d1: int
    old_d5: UUID
    old_wire_fingerprint: str
    codec_version: int
    decision_ref: str

    def __post_init__(self) -> None:
        """新 attempt を鍵に含めず、禁止対象の外形を確認する。"""
        if (
            type(self.authority) is not AuthorityBinding
            or not _uuid(self.tenant_id)
            or not _uuid(self.game_id)
            or not _ref(self.wire_d4)
            or not _positive(self.slot_d1)
            or not _uuid(self.old_d5)
            or not _ref(self.old_wire_fingerprint)
            or not _positive(self.codec_version)
            or not _ref(self.decision_ref)
        ):
            raise ValueError("旧要求 block が不正")


@dataclass(frozen=True, slots=True, repr=False)
class CompletionMarkerReference:
    """同じ業務取引の marker と結果を結ぶ参照。commit 証明ではない。"""

    phase: PhaseBinding
    transaction_ref: str
    marker_ref: str
    result_ref: str

    def __post_init__(self) -> None:
        """Marker と対象 phase の外形だけを確認する。"""
        if type(self.phase) not in (EventPhaseBinding, D1lessPhaseBinding) or not all(
            _ref(value)
            for value in (self.transaction_ref, self.marker_ref, self.result_ref)
        ):
            raise ValueError("marker 参照が不正")


@dataclass(frozen=True, slots=True, repr=False)
class StopRecord:
    """対象 phase/D1/D5/FP に不変結合する内部停止記録。"""

    target: EventPhaseBinding
    target_d1: int
    target_d5: UUID
    target_event_fingerprint: str
    stop_ref: str
    reason: SyncStopReason
    resolution: SyncStopResolution
    control_version: int
    evidence_ref: str
    prior_markers: tuple[CompletionMarkerReference, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """前方 phase の結果を停止対象へ誤結合させない。"""
        if (
            type(self.target) is not EventPhaseBinding
            or type(self.target_d1) is not int
            or self.target_d1 != self.target.d1
            or type(self.target_d5) is not UUID
            or self.target_d5 != self.target.d5
            or type(self.target_event_fingerprint) is not str
            or self.target_event_fingerprint != self.target.event_fingerprint
            or not _ref(self.stop_ref)
            or self.reason not in get_args(SyncStopReason.__value__)
            or self.resolution not in get_args(SyncStopResolution.__value__)
            or not _positive(self.control_version)
            or not _ref(self.evidence_ref)
            or type(self.prior_markers) is not tuple
            or not all(
                type(marker) is CompletionMarkerReference
                and marker.phase.attempt == self.target.attempt
                and marker.phase.position < self.target.position
                and marker.phase.phase_id != self.target.phase_id
                for marker in self.prior_markers
            )
        ):
            raise ValueError("停止対象 binding が不正")


@dataclass(frozen=True, slots=True, repr=False)
class LeaseEvidence:
    """issuer・対象・期限を持つ未検証の lease 証拠参照。"""

    issuer: UUID
    lease_id: UUID
    phase: PhaseBinding
    expires_at: datetime
    evidence_ref: str

    def __post_init__(self) -> None:
        """証拠値の型を確認する。真正性は検査口へ残す。"""
        if (
            not _uuid(self.issuer)
            or not _uuid(self.lease_id)
            or type(self.phase) not in (EventPhaseBinding, D1lessPhaseBinding)
            or not _expiry(self.expires_at)
            or not _ref(self.evidence_ref)
        ):
            raise ValueError("lease 証拠が不正")

    def is_current(self) -> bool:
        """期限を確認する。期限内であっても真正性は認定しない。"""
        return datetime.now(timezone.utc) < self.expires_at


@dataclass(frozen=True, slots=True, repr=False)
class ClosedTransactionEvidence:
    """同じ lease の業務終了を検証口へ渡す未検証参照。"""

    issuer: UUID
    lease_id: UUID
    phase: PhaseBinding
    transaction_ref: str
    termination_ref: str

    def __post_init__(self) -> None:
        """真偽値や任意 JSON を業務終了証拠として受けない。"""
        if (
            not _uuid(self.issuer)
            or not _uuid(self.lease_id)
            or type(self.phase) not in (EventPhaseBinding, D1lessPhaseBinding)
            or not _ref(self.transaction_ref)
            or not _ref(self.termination_ref)
        ):
            raise ValueError("業務終了証拠が不正")
