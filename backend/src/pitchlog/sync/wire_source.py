"""E-1原イベント列の防御的不変値。実受付・認可・同writer資格ではない。

S-1全体の受付やS-2内容検査を代行しない。P3/旧DTOへ変換せず、原JSONの
欠落・registration・未知内容を保持する。HTTP/DB/PortとD5台帳は変更しない。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Self

from pitchlog.sync.model import _canonical_uuid
from pitchlog.sync.wire_fingerprint import (
    WireEventValue,
    freeze_wire_event,
    wire_event_fingerprint,
    wire_request_fingerprint,
)

_ERROR = "E-1原wire列の不変値が不正"
_VALUE_SEAL = object()


class WireSourceError(ValueError):
    """入力値・資格候補を含めないpure値の拒否。"""


@dataclass(frozen=True, slots=True, init=False, repr=False)
class WireSourceValue:
    """純粋な不変値。sealも真正受付/書込許可を意味しない。"""

    game_id: str
    d4: str
    codec_version: int
    events: tuple[WireEventValue, ...] = field(repr=False)
    event_fingerprints: tuple[str, ...] = field(repr=False)
    request_fingerprint: str = field(repr=False)
    positions_by_d1: tuple[int, ...] = field(repr=False)
    positions_by_d5: MappingProxyType[str, tuple[int, ...]] = field(repr=False)
    _seal: object = field(repr=False)

    def __new__(cls) -> Self:
        """直接生成で未検査値を配らない。"""
        raise TypeError(_ERROR)


def _indexes(
    events: tuple[WireEventValue, ...],
) -> tuple[tuple[int, ...], MappingProxyType[str, tuple[int, ...]]]:
    """原順を変更せず、一始まりの位置だけを索引へ写す。"""
    by_d5: dict[str, list[int]] = {}
    d1s: list[tuple[int, int]] = []
    for position, event in enumerate(events, 1):
        d5, d1 = event.wire_event.get("d5"), event.wire_event.get("d1")
        if not _canonical_uuid(d5) or type(d1) is not int:
            raise ValueError(_ERROR)
        # D5重複の意味判定は行わず、同D5の全位置を保持する。
        assert type(d5) is str
        by_d5.setdefault(d5, []).append(position)
        d1s.append((d1, position))
    return (
        tuple(position for _, position in sorted(d1s)),
        MappingProxyType({d5: tuple(positions) for d5, positions in by_d5.items()}),
    )


def freeze_wire_source(
    *, game_id: str, d4: str, raw_events: tuple[Mapping[str, object], ...]
) -> WireSourceValue:
    """未変換E-1列を既指紋部品へ一度渡し、不変の索引付き値にする。

    Args:
        game_id: URLに対応する正規形UUID。実URL受付の証明ではない。
        d4: 列に共通するD4。現世代との照合は行わない。
        raw_events: 受信時の原順tuple。S-2不正値も変更せず保持する。

    Returns:
        codec1の値。認証/受付/再送保持/同writerの資格にはならない。

    Raises:
        WireSourceError: JSON又はD1付き列の表現が不正な場合。
    """
    try:
        if type(raw_events) is not tuple or not raw_events:
            raise TypeError(_ERROR)
        events = tuple(freeze_wire_event(raw) for raw in raw_events)
        request = wire_request_fingerprint(game_id=game_id, d4=d4, events=events)
        positions_by_d1, positions_by_d5 = _indexes(events)
        value = object.__new__(WireSourceValue)
        for name, member in (
            ("game_id", game_id),
            ("d4", d4),
            ("codec_version", 1),
            ("events", events),
            ("event_fingerprints", tuple(wire_event_fingerprint(e) for e in events)),
            ("request_fingerprint", request),
            ("positions_by_d1", positions_by_d1),
            ("positions_by_d5", positions_by_d5),
            ("_seal", _VALUE_SEAL),
        ):
            object.__setattr__(value, name, member)
        return value
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise WireSourceError(_ERROR) from None


def checked_wire_source(value: WireSourceValue) -> WireSourceValue:
    """全値を再検査して改変を拒否する。真正受付へ昇格させない。

    Args:
        value: 本部品で不変化した値。

    Returns:
        再検査済みの同じpure値。

    Raises:
        WireSourceError: 偽型又は不変member/指紋/索引が一致しない場合。
    """
    try:
        if (
            type(value) is not WireSourceValue
            or value._seal is not _VALUE_SEAL
            or type(value.codec_version) is not int
            or value.codec_version != 1
            or type(value.events) is not tuple
            or type(value.event_fingerprints) is not tuple
            or any(type(digest) is not str for digest in value.event_fingerprints)
            or type(value.request_fingerprint) is not str
            or type(value.positions_by_d1) is not tuple
            or any(type(position) is not int for position in value.positions_by_d1)
            or type(value.positions_by_d5) is not MappingProxyType
            or any(
                type(d5) is not str
                or type(positions) is not tuple
                or any(type(position) is not int for position in positions)
                for d5, positions in value.positions_by_d5.items()
            )
        ):
            raise ValueError(_ERROR)
        request = wire_request_fingerprint(
            game_id=value.game_id, d4=value.d4, events=value.events
        )
        digests = tuple(wire_event_fingerprint(e) for e in value.events)
        by_d1, by_d5 = _indexes(value.events)
        if (
            request != value.request_fingerprint
            or digests != value.event_fingerprints
            or by_d1 != value.positions_by_d1
            or by_d5 != value.positions_by_d5
        ):
            raise ValueError(_ERROR)
        return value
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        raise WireSourceError(_ERROR) from None
