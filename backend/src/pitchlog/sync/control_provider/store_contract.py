"""制御保存原本と発行元に束縛する内部receiptを定義する。

receiptは保存済みphaseの相関であり、lease/終結/業務書込許可ではない。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import UUID

from pitchlog.sync.control_provider.evidence import (
    AttemptBinding,
    D1lessPhaseBinding,
    EventPhaseBinding,
    PhaseBinding,
)


class ControlStoreUnavailable(RuntimeError):
    """保存原本・接続主体・権威の照合を完了できない。"""


@dataclass(frozen=True, slots=True)
class StoredRequest:
    """F1の単一要求原本と完全phase列をそのまま保持する。"""

    attempt: AttemptBinding
    phases: tuple[PhaseBinding, ...]

    def __post_init__(self) -> None:
        """F1検査と有限列の欠落/位置/phase ID重複だけを検査する。"""
        if type(self.attempt) is not AttemptBinding:
            raise ValueError("要求原本はF1 AttemptBindingが必要")
        checked = replace(self.attempt, authority=replace(self.attempt.authority))
        if type(self.phases) is not tuple or len(self.phases) != checked.event_count:
            raise ValueError("要求の完全phase集合が必要")
        phase_ids: set[UUID] = set()
        for position, phase in enumerate(self.phases, 1):
            if type(phase) not in (EventPhaseBinding, D1lessPhaseBinding):
                raise ValueError("F1の閉じたphase型が必要")
            replace(phase, attempt=checked)
            if (
                phase.attempt != checked
                or phase.position != position
                or phase.phase_id in phase_ids
            ):
                raise ValueError("phaseの要求/有限位置/識別子が不一致")
            phase_ids.add(phase.phase_id)
        # D1/D5重複の結果優先やFP計算などP7の意味を追加しない。


_RECEIPT_CREATION = object()


@dataclass(frozen=True, slots=True, init=False)
class StoredPhaseReceipt:
    """制御storeが実照合した原本/phaseだけを参照する内部相関。"""

    request: StoredRequest
    phase: PhaseBinding
    authority_id: UUID
    control_version: int
    _issuer: object = field(repr=False, compare=False)

    def __init__(
        self,
        request: StoredRequest,
        phase: PhaseBinding,
        authority_id: UUID,
        control_version: int,
        issuer: object,
        creation: object,
    ) -> None:
        """私有発行口以外からのUUID/ref/boolによる発行を拒否する。"""
        if creation is not _RECEIPT_CREATION:
            raise ControlStoreUnavailable("phase receiptの発行元が不正")
        if (
            type(request) is not StoredRequest
            or phase not in request.phases
            or type(authority_id) is not UUID
            or type(control_version) is not int
            or control_version < 1
        ):
            raise ControlStoreUnavailable("phase receiptの束縛が不正")
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "authority_id", authority_id)
        object.__setattr__(self, "control_version", control_version)
        object.__setattr__(self, "_issuer", issuer)


def _issue_phase_receipt(
    request: StoredRequest,
    phase: PhaseBinding,
    authority_id: UUID,
    control_version: int,
    issuer: object,
) -> StoredPhaseReceipt:
    """実制御照会を所有するstoreだけが使う私有発行口。"""
    return StoredPhaseReceipt(
        request, phase, authority_id, control_version, issuer, _RECEIPT_CREATION
    )
