"""原wireの型保持JSON codec。DB真正性・受付・保存の資格は発行しない。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import NoReturn

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
