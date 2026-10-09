"""既存のベクタ runner を JSON Lines で呼び出すブリッジ。"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import TextIO, cast

from pitchlog.domaincheck.path_match import ComparisonContract, FieldContract
from pitchlog.domaincheck.runners import vectors


class ProtocolError(Exception):
    """入出力の通信規約違反を表す。"""


class AdapterError(Exception):
    """ホスト側 adapter が通知した例外を表す。"""


def _object(value: object, label: str) -> dict[str, object]:
    """JSON object として受け取った値を確認する。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ProtocolError(f"{label} が object でない")
    return cast(dict[str, object], value)


def _keys(value: object, label: str, required: set[str]) -> dict[str, object]:
    """メッセージに必要なキーだけがあることを確認する。"""
    item = _object(value, label)
    missing = required - item.keys()
    unexpected = item.keys() - required
    if missing or unexpected:
        detail = f"不足={sorted(missing)!r}, 未知={sorted(unexpected)!r}"
        raise ProtocolError(f"{label} のキーが不正: {detail}")
    return item


def _string(value: object, label: str) -> str:
    """文字列の属性を返す。"""
    if not isinstance(value, str):
        raise ProtocolError(f"{label} が文字列でない")
    return value


def _strings(value: object, label: str) -> frozenset[str]:
    """文字列配列を既存契約向けの集合へ変換する。"""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProtocolError(f"{label} が文字列 array でない")
    return frozenset(value)


def _comparison(value: object, label: str) -> ComparisonContract:
    """通信上の比較面を既存の契約オブジェクトへ変換する。"""
    config = _keys(value, label, {"surface", "fields", "normalizations"})
    fields_value = config["fields"]
    if not isinstance(fields_value, list):
        raise ProtocolError(f"{label}.fields が array でない")
    fields: list[FieldContract] = []
    for index, raw_field in enumerate(fields_value):
        field_label = f"{label}.fields[{index}]"
        field = _keys(
            raw_field,
            field_label,
            {"field", "role", "valueType", "nullable", "scale"},
        )
        nullable = field["nullable"]
        scale = field["scale"]
        if not isinstance(nullable, bool):
            raise ProtocolError(f"{field_label}.nullable が boolean でない")
        if scale is not None and (
            not isinstance(scale, int) or isinstance(scale, bool)
        ):
            raise ProtocolError(f"{field_label}.scale が integer または null でない")
        try:
            fields.append(
                FieldContract(
                    field=_string(field["field"], f"{field_label}.field"),
                    role=_string(field["role"], f"{field_label}.role"),
                    value_type=_string(field["valueType"], f"{field_label}.valueType"),
                    nullable=nullable,
                    scale=scale,
                )
            )
        except ValueError as error:
            raise ProtocolError(f"{field_label} が不正: {error}") from error
    try:
        return ComparisonContract(
            surface=_string(config["surface"], f"{label}.surface"),
            fields=tuple(fields),
            normalizations=_strings(
                config["normalizations"], f"{label}.normalizations"
            ),
        )
    except ValueError as error:
        raise ProtocolError(f"{label} が不正: {error}") from error


def _contract(value: object) -> vectors.VectorContract:
    """開始メッセージの契約を既存 runner の契約へ変換する。"""
    config = _keys(
        value,
        "contract",
        {
            "calculation",
            "vector",
            "runner",
            "entrypointId",
            "directTargetId",
            "caseSchema",
            "normalizationComparison",
            "outputComparison",
        },
    )
    return vectors.VectorContract(
        calculation=_string(config["calculation"], "contract.calculation"),
        vector=_string(config["vector"], "contract.vector"),
        runner=_string(config["runner"], "contract.runner"),
        entrypoint_id=_string(config["entrypointId"], "contract.entrypointId"),
        direct_target_id=_string(config["directTargetId"], "contract.directTargetId"),
        case_schema=_object(config["caseSchema"], "contract.caseSchema"),
        normalization_comparison=_comparison(
            config["normalizationComparison"], "contract.normalizationComparison"
        ),
        output_comparison=_comparison(
            config["outputComparison"], "contract.outputComparison"
        ),
    )


def _read(stdin: TextIO) -> dict[str, object]:
    """次の JSON 行を読み、規約違反を例外にする。"""
    line = stdin.readline()
    if not line:
        raise ProtocolError("応答前に EOF になった")
    try:
        value: object = json.loads(
            line,
            parse_constant=lambda constant: _invalid_constant(constant),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ProtocolError(f"JSON でない行: {error}") from error
    return _object(value, "メッセージ")


def _invalid_constant(constant: str) -> object:
    """JSON でない非有限数を拒否する。"""
    raise ValueError(f"JSON にない定数: {constant}")


def _send(stdout: TextIO, message: Mapping[str, object]) -> None:
    """JSON Lines の一行を送って直ちに flush する。"""
    stdout.write(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")
    stdout.flush()


class _Exchange:
    """ブリッジとホストの一往復を扱う。"""

    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        """入出力ストリームを保持する。"""
        self.stdin = stdin
        self.stdout = stdout

    def request(
        self,
        message: Mapping[str, object],
        expected_type: str,
        *,
        allow_unsupported: bool = False,
    ) -> object:
        """要求を送り、対応する応答値か adapter の例外を返す。"""
        _send(self.stdout, message)
        response = _read(self.stdin)
        response_type = _string(response.get("type"), "応答.type")
        if response_type == "adapter-error":
            item = _keys(response, "adapter-error", {"type", "message"})
            raise AdapterError(_string(item["message"], "adapter-error.message"))
        if response_type == "unsupported" and allow_unsupported:
            _keys(response, "unsupported", {"type"})
            raise vectors.UnsupportedVectorCase()
        if response_type != expected_type:
            raise ProtocolError(
                f"応答 type の順序違反: {expected_type} を期待し {response_type} を受信"
            )
        item = _keys(response, expected_type, {"type", "value"})
        return item["value"]


class _Normalizer:
    """ホストへ正規化を委譲する proxy。"""

    def __init__(self, config: object, exchange: _Exchange) -> None:
        """生成物の属性と通信先を保持する。"""
        item = _keys(config, "normalizer", {"generatedId", "sourceHash"})
        self.generated_id = _string(item["generatedId"], "normalizer.generatedId")
        self.source_hash = _string(item["sourceHash"], "normalizer.sourceHash")
        self.exchange = exchange

    def normalize(self, raw: object) -> object:
        """正規化要求を送って戻り値を受け取る。"""
        return self.exchange.request({"type": "normalize", "raw": raw}, "normalized")


class _Calculation:
    """ホストへ計算を委譲する proxy。"""

    def __init__(self, exchange: _Exchange) -> None:
        """通信先を保持する。"""
        self.exchange = exchange

    def execute(self, case_id: str, normalized: object) -> object:
        """計算要求を送って戻り値を受け取る。"""
        return self.exchange.request(
            {"type": "execute", "caseId": case_id, "normalized": normalized},
            "executed",
            allow_unsupported=True,
        )


def _report(report: vectors.VectorRunReport) -> dict[str, object]:
    """既存 runner の報告を通信上の表現へ変換する。"""
    return {
        "type": "report",
        "declaredCaseIds": list(report.declared_case_ids),
        "consumedCaseIds": list(report.consumed_case_ids),
        "executions": [
            {
                "caseId": item.case_id,
                "generatedId": item.generated_id,
                "sourceHash": item.source_hash,
                "normalizationMatched": item.normalization_matched,
                "outputMatched": item.output_matched,
            }
            for item in report.executions
        ],
        "complete": report.complete,
    }


def serve(stdin: TextIO, stdout: TextIO) -> int:
    """一回のベクタ実行を処理し、終端メッセージを送る。

    Args:
        stdin: ホストから JSON Lines を読むテキストストリーム。
        stdout: ホストへ JSON Lines を書くテキストストリーム。

    Returns:
        終端メッセージ送信後の終了コード 0。
    """
    exchange = _Exchange(stdin, stdout)
    try:
        start = _keys(
            _read(stdin), "start", {"type", "cases", "contract", "normalizer"}
        )
        if start["type"] != "start":
            raise ProtocolError("最初の行が start でない")
        contract = _contract(start["contract"])
        normalizer = _Normalizer(start["normalizer"], exchange)
        report = vectors.run_vectors(
            start["cases"], contract, normalizer, _Calculation(exchange)
        )
        terminal = _report(report)
    except ProtocolError as error:
        terminal = {"type": "protocol-error", "message": str(error)}
    except AdapterError:
        terminal = {"type": "adapter-error"}
    except vectors.VectorRunError as error:
        terminal = {"type": "vector-run-error", "message": str(error)}
    _send(stdout, terminal)
    return 0


def main() -> int:
    """標準入出力でブリッジを一回起動する。"""
    return serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
