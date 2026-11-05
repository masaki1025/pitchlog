"""取消の純ABIを唯一artifactへ渡す閉じたJSON境界。

構造検査だけを行い、逆適用・履歴照合・成績効果をPythonで計算しない。
この型は認可・真正履歴・保存資格を発行しない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.protocols import Validator
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable

from pitchlog.domainrt.first_pitch import _invalid_constant, _unique_object
from pitchlog.domainrt.host import open_domain_host

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts/state-transition/undo_schema_v1.json"
)


def _reject_external_resource(uri: str) -> NoReturn:
    """外部schemaをHTTP/ファイル経由で取得せず必ず拒否する。"""
    raise NoSuchResource(ref=uri)


class UndoRequestError(ValueError):
    """呼出側が供給した要求の構造・JSON表現が閉ABIに違反する。"""


class UndoProtocolError(RuntimeError):
    """artifact応答または配置契約が不正で成功判定できない。"""


@lru_cache(maxsize=2)
def _validator(definition: str) -> Validator:
    """ネットワーク参照のない配置済み契約だけを読む。"""
    try:
        schema = json.loads(
            _SCHEMA_PATH.read_text(),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"},
            registry=Registry(retrieve=_reject_external_resource),
        )
    except (OSError, ValueError, KeyError, TypeError, SchemaError) as error:
        raise UndoProtocolError("取消の配置契約を読取できない") from error


def _read(raw: str, definition: str) -> dict[str, Any]:
    """重複memberと非JSON数値を拒否し、全入れ子を契約で検査する。"""
    if type(raw) is not str:
        raise ValueError("JSON文字列が必要")
    value = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )
    try:
        _validator(definition).validate(value)
    except Unresolvable as error:
        raise UndoProtocolError("取消の配置契約に解決不能な参照がある") from error
    return value


@dataclass(frozen=True, slots=True)
class UndoRequest:
    """検証済みwireを不変文字列で保持する要求。保存資格ではない。"""

    json: str

    def __post_init__(self) -> None:
        """直接構築でも閉要求の検査を必須にする。"""
        try:
            _read(self.json, "Request")
        except (ValueError, TypeError, ValidationError) as error:
            raise UndoRequestError("取消要求が閉ABIに一致しない") from error

    def to_wire(self) -> dict[str, Any]:
        """保存値と共有しない新しいwire objectを返す。"""
        return _read(self.json, "Request")


@dataclass(frozen=True, slots=True)
class UndoResponse:
    """成功5項目または既4エラーの全wireを保持する応答。"""

    json: str

    def __post_init__(self) -> None:
        """破損成功や未知エラーを技術故障として拒否する。"""
        try:
            _read(self.json, "Response")
        except (ValueError, TypeError, ValidationError) as error:
            raise UndoProtocolError("取消応答が閉ABIに一致しない") from error

    def to_wire(self) -> dict[str, Any]:
        """全応答値を欠落・補完なく新しいobjectへ復号する。"""
        return _read(self.json, "Response")


def decode_undo_response(raw: str) -> UndoResponse:
    """未知の応答を成功や内容拒否へ補完せず厳格に読む。

    Args:
        raw: 唯一artifactから返されたJSON文字列。

    Returns:
        閉ABIへ完全適合した応答。

    Raises:
        UndoProtocolError: 未知・欠落・余剰・型違い等の破損応答。
    """
    return UndoResponse(raw)


def apply_undo(request: UndoRequest) -> UndoResponse:
    """検証済み要求を製品artifactへ一回渡し全応答を読む。

    Args:
        request: 全状態と完全履歴を含む閉要求。

    Returns:
        artifactの成功または既定義の非成功。

    Raises:
        TypeError: 要求が専用の実型でない。
        UndoRequestError: 要求が閉ABIに適合しない。
        UndoProtocolError: 応答や配置契約が不正。
        DomainRuntimeError: 既hostの起動・実行・境界故障。
    """
    if type(request) is not UndoRequest:
        raise TypeError("UndoRequestの実型が必要")
    validated = UndoRequest(request.json)
    with open_domain_host() as host:
        # 技術故障をFalseやINVALID_REQUESTへ変換しない。
        return decode_undo_response(host.call("applyUndo", validated.json))
