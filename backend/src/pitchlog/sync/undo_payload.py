"""取消V7/イベントの閉codec。計算・認可・保存資格を発行しない。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object
from pitchlog.sync.idempotency import _json_value, event_source
from pitchlog.sync.model import SyncEvent

_ROOT = Path(__file__).resolve().parents[4] / "contracts/state-transition"


class UndoPayloadError(ValueError):
    """入力の閉形不一致。原本や秘密を表示しない。"""


class UndoContractUnavailable(RuntimeError):
    """配置契約が不明な技術故障。内容拒否へ変換しない。"""


def _no_resource(uri):
    """登録していないschemaを取得しない。"""
    raise NoSuchResource(ref=uri)


@lru_cache(maxsize=1)
def _contract():
    """採用済み3schemaを明示登録し、外部参照を閉じる。"""
    try:
        documents = [
            json.loads(
                (_ROOT / name).read_text(),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
            for name in (
                "nonplay_prefix_bridge_schema_v1.json",
                "undo_schema_v1.json",
                "lineup_play_prefix_schema_v1.json",
            )
        ]
        registry = Registry(retrieve=_no_resource)
        for document in documents:
            Draft202012Validator.check_schema(document)
            registry = registry.with_resource(
                document["$id"], Resource.from_contents(document)
            )
        return documents[0], registry
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise UndoContractUnavailable("取消橋の配置契約を確認できません") from error


def _load(raw):
    """重複key/非有限値/JSON外の入力を補修しない。"""
    if type(raw) is not str:
        raise UndoPayloadError("取消JSON文字列が必要です")
    return json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )


def _validate_value(value, definition):
    """型と全memberを保持し、shapeだけの検査結果を返す。"""
    schema, registry = _contract()
    Draft202012Validator(
        {"$ref": schema["$id"] + "#/$defs/" + definition}, registry=registry
    ).validate(value)
    return value


def _read(raw, definition):
    """参照解決/配置故障を内容不正に潰さない。"""
    try:
        return _validate_value(_load(raw), definition)
    except (ValueError, TypeError, ValidationError) as error:
        raise UndoPayloadError("取消の閉値が不一致です") from error


@dataclass(frozen=True, slots=True)
class UndoPayload:
    """不変JSONで保持する純payload。真正frameではない。"""

    json: str

    def __post_init__(self):
        """自由constructorでも再検査する。"""
        _read(self.json, "UndoPayload")

    def to_wire(self):
        """毎回独立した全値を返す。"""
        return _read(self.json, "UndoPayload")


def read_undo_payload(raw):
    """V7の閉版だけを読取し、型を不変に保つ。"""
    return UndoPayload(_canonical_json(_read(raw, "UndoPayload")))


def read_undo_event(event):
    """V5/ownD2/V8/対象を既実eventと全値照合する。"""
    if type(event) is not SyncEvent or type(event.d1) is not int:
        raise UndoPayloadError("取消イベントの実型が不一致です")
    value = _load(_canonical_json(_json_value(event_source(event))))
    _read(_canonical_json(value), "UndoEvent")
    if type(value["target_reference"]["d1"]) is not int:
        raise UndoPayloadError("取消対象連番の実型が不一致です")
    return read_undo_payload(_canonical_json(value["payload"]))
