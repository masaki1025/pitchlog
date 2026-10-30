"""未変換E-1 wireを不変化し、既規範の専用指紋だけを生成する。

S-1受付/認可/数学/nonce/真正原本/保存の証明ではない。既DTO指紋やD5台帳、
HTTP/端末の読取・数値表現・耐久保持は変更しない。登録Port向けではない。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from pitchlog.sync.idempotency import source_fingerprint
from pitchlog.sync.model import (
    _MAX_SAFE_INTEGER,
    FrozenJson,
    _canonical_uuid,
    _opaque_string,
    freeze_json,
)

_ERROR = "E-1原wire指紋の入力又は不変値が不正"
_VALUE_SEAL = object()


class WireFingerprintError(ValueError):
    """原入力/資格を含めない固定のpure値拒否。"""


@dataclass(frozen=True, slots=True, init=False, repr=False)
class WireEventValue:
    """防御的snapshot。真正性やS-1成立を認定する資格ではない。"""

    _wire_event: MappingProxyType[str, FrozenJson] = field(repr=False)
    _fingerprint: str = field(repr=False)
    _seal: object = field(repr=False)

    @property
    def wire_event(self) -> MappingProxyType[str, FrozenJson]:
        """元入力とaliasを持たない再帰不変snapshotを返す。"""
        return self._wire_event


def _raw_json(value: object) -> None:
    """未変換JSONにないPython値を修復せず拒否する。"""
    if value is None or type(value) in (bool, int, float, str):
        return
    if type(value) is list:
        for member in value:
            _raw_json(member)
        return
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("JSON keyの型が不正")
        for member in value.values():
            _raw_json(member)
        return
    raise TypeError("JSON外の値")


def _frozen_json(value: object) -> None:
    """強制差替えによる可変container/未知型を再利用させない。"""
    if value is None or type(value) in (bool, int, float, str):
        return
    if type(value) is tuple:
        for member in value:
            _frozen_json(member)
        return
    if type(value) is MappingProxyType:
        if any(type(key) is not str for key in value):
            raise TypeError("不変JSON keyの型が不正")
        for member in value.values():
            _frozen_json(member)
        return
    raise TypeError("不変JSON外の値")


def _fingerprint(wire: Mapping[str, object]) -> str:
    """全原値/registrationを既単一正規化器へ渡す。"""
    return "wire-v1:" + source_fingerprint(
        {
            "codec_version": 1,
            "wire_event": wire,
            "registration": wire.get("registration"),
        }
    )


def _checked(event: WireEventValue) -> WireEventValue:
    """実型/構造/発行時digestで強制差替えと偽instanceを拒否する。"""
    if type(event) is not WireEventValue or event._seal is not _VALUE_SEAL:
        raise TypeError("不変値の型が不正")
    if type(event._wire_event) is not MappingProxyType:
        raise TypeError("原eventは不変objectが必要")
    _frozen_json(event._wire_event)
    actual = _fingerprint(event._wire_event)
    if type(event._fingerprint) is not str or actual != event._fingerprint:
        raise ValueError("発行後の値が不一致")
    return event


def freeze_wire_event(raw_event: Mapping[str, object]) -> WireEventValue:
    """原event全値を保持し、JSON外/非有限/UTF8不能を拒否する。

    Args:
        raw_event: 受信直後の意味変換していないJSON object。

    Returns:
        原入力の変更が混入しない不変snapshot。S-1成立証明ではない。

    Raises:
        WireFingerprintError: JSON表現又は入力型が不正な場合。
    """
    try:
        if not isinstance(raw_event, Mapping):
            raise TypeError("原eventはobjectが必要")
        _raw_json(raw_event)
        wire = freeze_json(raw_event)
        if type(wire) is not MappingProxyType:
            raise TypeError("不変eventの型が不正")
        digest = _fingerprint(wire)
        value = object.__new__(WireEventValue)
        object.__setattr__(value, "_wire_event", wire)
        object.__setattr__(value, "_fingerprint", digest)
        object.__setattr__(value, "_seal", _VALUE_SEAL)
        return value
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise WireFingerprintError(_ERROR) from None


def wire_event_fingerprint(event: WireEventValue) -> str:
    """当該不変原eventの専用指紋を返す。

    Args:
        event: 本部品で不変化した原event。

    Returns:
        wire-v1専用指紋。旧DTO/要求全体の指紋ではない。

    Raises:
        WireFingerprintError: 偽値又は発行後の強制変更の場合。
    """
    try:
        return _checked(event)._fingerprint
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise WireFingerprintError(_ERROR) from None


def wire_request_fingerprint(
    *, game_id: str, d4: str, events: tuple[WireEventValue, ...]
) -> str:
    """S-1成立済みE-1列をD1昇順に写し、要求専用指紋を返す。

    Args:
        game_id: URLへ束縛した正規形UUID。
        d4: 当該要求のD4文字列。
        events: 原events順を保持した不変event列。S-2は意味検査しない。

    Returns:
        wire-request-v1専用指紋。認可/原body耐久保持の証明ではない。

    Raises:
        WireFingerprintError: 要求scope/D1外形や不変値が不正な場合。
    """
    try:
        if not _canonical_uuid(game_id) or not _opaque_string(d4):
            raise ValueError("要求scopeの外形が不正")
        if type(events) is not tuple or not events:
            raise TypeError("空でない不変event列が必要")
        ordered: list[tuple[int, str]] = []
        for event in events:
            checked = _checked(event)
            wire = checked._wire_event
            d1 = wire.get("d1")
            if (
                type(d1) is not int
                or not 1 <= d1 <= _MAX_SAFE_INTEGER
                or wire.get("game_id") != game_id
                or wire.get("d4") != d4
            ):
                raise ValueError("eventのD1/scopeが不正")
            ordered.append((d1, checked._fingerprint))
        if len({d1 for d1, _ in ordered}) != len(ordered):
            raise ValueError("D1が重複")
        ordered.sort(key=lambda entry: entry[0])
        return "wire-request-v1:" + source_fingerprint(
            {
                "codec_version": 1,
                "game_id": game_id,
                "d4": d4,
                "events": [digest for _, digest in ordered],
            }
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise WireFingerprintError(_ERROR) from None
