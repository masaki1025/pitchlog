"""停止制御の純粋型だけの限定供給。公開停止操作・Port実装は未供給。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from re import fullmatch
from typing import Any, Literal, cast

type SyncStopReason = Literal[
    "ORIGINAL_UNAVAILABLE",
    "ORIGINAL_INCONSISTENT",
    "ORIGINAL_READ_FAILED",
    "ORIGINAL_PERMISSION_FAILED",
    "TOMBSTONE_NOT_PROVIDED",
]


type SyncStopResolution = Literal["rollback_confirmed", "commit_unknown"]


_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _opaque(value: object) -> bool:
    """不透明な文字列の外形だけを確認する。"""
    return type(value) is str and bool(value)


def _uuid(value: object) -> bool:
    """UUID の wire 正規形だけを確認する。"""
    return type(value) is str and fullmatch(_UUID_PATTERN, value) is not None


def _request_version(value: object) -> bool:
    """元要求の codec 版の型だけを確認し、対応版は確定しない。"""
    return type(value) is int


def _exact_mapping(value: object, keys: frozenset[str]) -> Mapping[str, object]:
    """辞書の欠落・余剰・非文字列キーを拒否する。"""
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("同期停止契約の項目が不正")
    return value


@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    """送信前バリアだけで照会できる試行の5値。"""

    attempt_id: str = field(repr=False)
    game_id: str
    d4: str
    codec_version: int
    wire_fingerprint: str = field(repr=False)

    def __post_init__(self) -> None:
        """識別子の外形を検査する。所有と耐久束縛は検査しない。"""
        if not (
            _uuid(self.attempt_id)
            and _uuid(self.game_id)
            and _opaque(self.d4)
            and _request_version(self.codec_version)
            and _opaque(self.wire_fingerprint)
        ):
            raise ValueError("試行識別子の値が不正")

    @classmethod
    def from_mapping(cls, value: object) -> AttemptIdentity:
        """stop_ref を含む余剰項目を拒否する。"""
        fields = _exact_mapping(value, frozenset(cls.__dataclass_fields__))
        return cast(Any, cls)(**fields)
