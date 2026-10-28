"""原wireの型保持JSON codec。DB真正性・受付・保存の資格は発行しない。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, NoReturn

from pitchlog.sync.idempotency import _json_value
from pitchlog.sync.model import _MAX_SAFE_INTEGER, _canonical_uuid, _opaque_string
from pitchlog.sync.wire_fingerprint import (
    WireEventValue,
    freeze_wire_event,
    wire_event_fingerprint,
)

_ERROR = "E-1原本の閉形式又は期待値が一致しません"
_KEYS = frozenset(
    {"format_version", "codec_version", "event_fingerprint", "wire_event_json"}
)


class WireOriginalError(ValueError):
    """原入力・元例外・台帳期待値を表示しない固定拒否。"""


def _canonical(value: object) -> str:
    """既指紋と同じJSON規則を使い、別のhashを導入しない。"""
    result = json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    result.encode("utf-8")
    return result


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """重複keyを最後の値で補修しない。"""
    value: dict[str, object] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(_ERROR)
        value[key] = member
    return value


def _constant(_: str) -> NoReturn:
    """非有限をJSON値へ通さない。"""
    raise ValueError(_ERROR)


def encode_wire_original(event: WireEventValue) -> str:
    """既pure全値を版付き原本へ直列化する。DB保存成功を意味しない。"""
    try:
        fingerprint = wire_event_fingerprint(event)
        return _canonical(
            {
                "format_version": "e1-original-v1",
                "codec_version": 1,
                "event_fingerprint": fingerprint,
                "wire_event_json": _canonical(event.wire_event),
            }
        )
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise WireOriginalError(_ERROR) from None


def decode_wire_original(
    original: Mapping[str, object],
    *,
    expected_event_fingerprint: str,
    game_id: str,
    d4: str,
    d1: int,
    d5: str,
) -> WireEventValue:
    """独立に渡された台帳/scope全値と照合する。真正性は呼出側の責務。"""
    try:
        if (
            not isinstance(original, Mapping)
            or set(original) != _KEYS
            or any(type(key) is not str for key in original)
            or type(original["format_version"]) is not str
            or original["format_version"] != "e1-original-v1"
            or type(original["codec_version"]) is not int
            or original["codec_version"] != 1
            or type(original["event_fingerprint"]) is not str
            or type(original["wire_event_json"]) is not str
            or type(expected_event_fingerprint) is not str
            or not _canonical_uuid(game_id)
            or not _opaque_string(d4)
            or type(d1) is not int
            or not 1 <= d1 <= _MAX_SAFE_INTEGER
            or not _canonical_uuid(d5)
        ):
            raise ValueError(_ERROR)
        raw = json.loads(
            original["wire_event_json"],
            object_pairs_hook=_object,
            parse_constant=_constant,
        )
        if type(raw) is not dict or _canonical(raw) != original["wire_event_json"]:
            raise ValueError(_ERROR)
        if any(
            type(raw.get(key)) is not type(expected) or raw[key] != expected
            for key, expected in (
                ("game_id", game_id),
                ("d4", d4),
                ("d1", d1),
                ("d5", d5),
            )
        ):
            raise ValueError(_ERROR)
        value = freeze_wire_event(raw)
        digest = wire_event_fingerprint(value)
        if (
            digest != original["event_fingerprint"]
            or digest != expected_event_fingerprint
        ):
            raise ValueError(_ERROR)
        return value
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise WireOriginalError(_ERROR) from None


@dataclass(frozen=True, slots=True)
class RejectedOriginalView:
    """W2用の純値。原本の真正性やwriter資格は発行しない。"""

    origin: Literal["wire", "legacy"]
    payload: Mapping[str, object]
    event_fingerprint: str


def rejected_original_view(
    original: Mapping[str, object],
    *,
    ledger_fingerprint: str,
    game_id: str,
    d4: str,
    d1: int,
    d5: str,
) -> RejectedOriginalView:
    """台帳domainと原本形式を両方確認し、W2の同名fieldを返す。

    legacyは既指紋helperを再利用し、未知形式をlegacyへ降格させない。
    各fieldのW2意味判定は従来の呼出側へ残す。
    """
    try:
        if type(ledger_fingerprint) is not str or not ledger_fingerprint:
            raise ValueError(_ERROR)
        if not isinstance(original, Mapping):
            raise ValueError(_ERROR)
        if ledger_fingerprint.startswith("wire-v1:"):
            value = decode_wire_original(
                original,
                expected_event_fingerprint=ledger_fingerprint,
                game_id=game_id,
                d4=d4,
                d1=d1,
                d5=d5,
            )
            return RejectedOriginalView("wire", value.wire_event, ledger_fingerprint)
        if ":" in ledger_fingerprint or set(original).intersection(_KEYS):
            raise ValueError(_ERROR)
        # prefix_pathは3Bで本moduleを参照するため遅延importし、旧算式をコピーしない。
        from pitchlog.sync.prefix_path import _original_fingerprint

        if _original_fingerprint(original) != ledger_fingerprint:
            raise ValueError(_ERROR)
        return RejectedOriginalView("legacy", original, ledger_fingerprint)
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise WireOriginalError(_ERROR) from None
