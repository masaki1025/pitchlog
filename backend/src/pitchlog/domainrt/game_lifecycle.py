"""終了・再開の閉ABI。状態変換は唯一artifactへ委譲する。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object

_ROOT = Path(__file__).resolve().parents[4] / "contracts/state-transition"


class LifecycleRequestError(ValueError):
    """利用者提案の閉形不一致。資格やDB不明とは区別する。"""


class LifecycleProtocolError(RuntimeError):
    """配置/実host応答が不明な技術故障。成功へ補完しない。"""


def _no_external(uri):
    """未登録参照をネットワークへ取りに行かない。"""
    raise NoSuchResource(ref=uri)


@lru_cache(maxsize=2)
def _validator(definition):
    """既current構造をコピーせず採用契約から参照する。"""
    try:
        registry = Registry(retrieve=_no_external)
        schema = None
        for name in (
            "game_lifecycle_schema_v1.json",
            "nonplay_prefix_bridge_schema_v1.json",
            "undo_schema_v1.json",
            "lineup_play_prefix_schema_v1.json",
        ):
            document = json.loads((_ROOT / name).read_text())
            Draft202012Validator.check_schema(document)
            registry = registry.with_resource(
                document["$id"], Resource.from_contents(document)
            )
            if name == "game_lifecycle_schema_v1.json":
                schema = document
        if schema is None:
            raise LifecycleProtocolError("終了再開の配置契約が欠落しています")
        return Draft202012Validator(
            {"$ref": schema["$id"] + "#/$defs/" + definition}, registry=registry
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LifecycleProtocolError("終了再開の配置契約を読取できません") from error


def _read(raw, definition):
    if type(raw) is not str:
        raise ValueError("JSON文字列が必要です")
    value = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    _validator(definition).validate(value)
    return value


@dataclass(frozen=True, slots=True)
class LifecycleRequest:
    """閉ABIの不変値。constructorだけでは保存資格にならない。"""

    json: str

    def __post_init__(self):
        """自由constructorでも余剰や型違いを拒否する。"""
        try:
            _read(self.json, "Request")
        except (ValueError, TypeError, ValidationError) as error:
            raise LifecycleRequestError("終了再開要求が閉ABIに不一致です") from error

    def to_wire(self):
        """共有参照を返さない。"""
        return _read(self.json, "Request")


@dataclass(frozen=True, slots=True)
class LifecycleResponse:
    """全応答。欠落を固定成功へ補修しない。"""

    json: str

    def __post_init__(self):
        """破損成功/未知結果は技術故障へ閉じる。"""
        try:
            _read(self.json, "Response")
        except (ValueError, TypeError, ValidationError) as error:
            raise LifecycleProtocolError("終了再開応答が閉ABIに不一致です") from error

    def to_wire(self):
        """全応答を新しいobjectへ復号する。"""
        return _read(self.json, "Response")


def decode_lifecycle_response(raw):
    """既実hostの応答を読む。評価や認可を追加しない。"""
    return LifecycleResponse(raw)


def evaluate_game_lifecycle(host, request):
    """実hostの単一操作へ閉要求を渡し、同じ応答codecを返す。"""
    from pitchlog.domainrt.host import NodeDomainHost

    if type(host) is not NodeDomainHost or type(request) is not LifecycleRequest:
        raise LifecycleProtocolError("終了再開の実host/要求が不一致です")
    return decode_lifecycle_response(host.call("applyGameLifecycle", request.json))
