"""初球の私有frameの不透明な参照と、資格を持たない返却値。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class FirstBallFrameError(RuntimeError):
    """入力や資格を含めないframe境界拒否。"""

    def __init__(self) -> None:
        """生の入力・元例外を公開しない。"""
        super().__init__("初球の同一評価frameを利用できません")


class FirstBallBridge:
    """privileged核が私有registryへ束縛する参照。認可証明ではない。"""

    __slots__ = ()

    def __new__(cls) -> FirstBallBridge:
        """通常の構築だけで待機状態を発行しない。"""
        raise FirstBallFrameError


class FirstBallFrame:
    """bridge内の発行記録との同一性だけで検査する不透明な参照。"""

    __slots__ = ()

    def __new__(cls) -> FirstBallFrame:
        """同型の手作りobjectを私有frameへ昇格しない。"""
        raise FirstBallFrameError


@dataclass(frozen=True, slots=True, repr=False)
class FirstBallIntent:
    """wire写像確定前の既計算入力名。受信V7を解釈・変更しない。"""

    event_kind: str
    result_id: str
    pitch_event_kind: str

    def __post_init__(self) -> None:
        """文字列の強制変換や派生型を受け付けない。"""
        if any(
            type(value) is not str
            for value in (self.event_kind, self.result_id, self.pitch_event_kind)
        ):
            raise FirstBallFrameError


@dataclass(frozen=True, slots=True, repr=False)
class FirstBallFrameValue:
    """一度消費した全値。writer/権利/保存成功を証明しない。"""

    tenant_id: UUID
    game_id: UUID
    generation: int
    d1: int
    d5: UUID
    source_fingerprint: str
    artifact_sha256: str
    request_json: str
    response_json: str
    roster_json: str
