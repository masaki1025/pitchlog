"""JSON Lines ブリッジの通信規約と共通適合ベクタを検証する。"""

from __future__ import annotations

import ast
import importlib
import io
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
FIXTURE = (
    Path(__file__).parent
    / "fixtures/vector-conformance/vector_conformance_v1.json"
)
BRIDGE_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/runners/vector_bridge.py"

sys.path.insert(0, str(BACKEND_SRC))
BRIDGE = importlib.import_module("pitchlog.domaincheck.runners.vector_bridge")
VECTORS = importlib.import_module("pitchlog.domaincheck.runners.vectors")
PATH_MATCH = importlib.import_module("pitchlog.domaincheck.path_match")


def _scenarios() -> list[dict[str, Any]]:
    """ステップ 1 の共通シナリオを読み込む。"""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return fixture["scenarios"]


def _start(scenario: dict[str, Any]) -> dict[str, object]:
    """シナリオから開始メッセージを作る。"""
    normalizer = scenario["normalizer"]
    return {
        "type": "start",
        "cases": scenario["cases"],
        "contract": {**scenario["contract"], "runner": "vitest"},
        "normalizer": {
            "generatedId": normalizer["generatedId"],
            "sourceHash": normalizer["sourceHash"],
        },
    }


class _DirectNormalizer:
    """直接実行で fixture の正規化表だけを参照する。"""

    def __init__(self, config: dict[str, Any]) -> None:
        """生成物属性と表を保持する。"""
        self.generated_id: str = config["generatedId"]
        self.source_hash: str = config["sourceHash"]
        self.mode: str = config["mode"]
        self.table: list[dict[str, object]] = config["table"]
        self.calls = 0

    def normalize(self, raw: object) -> object:
        """呼び出し順の表の値、または入力値を返す。"""
        if self.mode == "passthrough":
            return raw
        entry = self.table[self.calls]
        self.calls += 1
        assert raw == entry["raw"]
        return entry["normalized"]


class _DirectCalculation:
    """直接実行で fixture の対応 ID と出力表だけを参照する。"""

    def __init__(self, config: dict[str, Any]) -> None:
        """対応 ID と出力表を保持する。"""
        self.supported_case_ids: set[str] = set(config["supportedCaseIds"])
        self.outputs: dict[str, object] = config.get("outputs", {})

    def execute(self, case_id: str, normalized: object) -> object:
        """未対応を送出し、対応 ID は表の値か入力値を返す。"""
        if case_id not in self.supported_case_ids:
            raise VECTORS.UnsupportedVectorCase(case_id)
        return self.outputs.get(case_id, normalized)


def _direct_comparison(config: dict[str, Any]) -> Any:
    """fixture の比較面を直接実行用の契約へ変換する。"""
    return PATH_MATCH.ComparisonContract(
        surface=config["surface"],
        fields=tuple(
            PATH_MATCH.FieldContract(
                field=field["field"],
                role=field["role"],
                value_type=field["valueType"],
                nullable=field["nullable"],
                scale=field["scale"],
            )
            for field in config["fields"]
        ),
        normalizations=frozenset(config["normalizations"]),
    )


def _direct_report(scenario: dict[str, Any]) -> dict[str, object]:
    """同じシナリオの直接実行報告を通信上の名前へ写す。"""
    config = scenario["contract"]
    contract = VECTORS.VectorContract(
        calculation=config["calculation"],
        vector=config["vector"],
        runner="vitest",
        entrypoint_id=config["entrypointId"],
        direct_target_id=config["directTargetId"],
        case_schema=config["caseSchema"],
        normalization_comparison=_direct_comparison(
            config["normalizationComparison"]
        ),
        output_comparison=_direct_comparison(config["outputComparison"]),
    )
    report = VECTORS.run_vectors(
        scenario["cases"],
        contract,
        _DirectNormalizer(scenario["normalizer"]),
        _DirectCalculation(scenario["calculation"]),
    )
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


class _HostInput(io.TextIOBase):
    """ホストが開始行と各応答行を供給する入力ストリーム。"""

    def __init__(self, start: dict[str, object]) -> None:
        """開始行をキューへ積む。"""
        self.lines = deque([json.dumps(start, ensure_ascii=False) + "\n"])

    def readline(self, size: int = -1) -> str:
        """次の応答行を返す。"""
        return self.lines.popleft() if self.lines else ""


class _HostOutput(io.TextIOBase):
    """flush ごとに要求を読み、ホストの応答を作る出力ストリーム。"""

    def __init__(self, host: _Host) -> None:
        """ホストと出力行を保持する。"""
        self.host = host
        self.buffer = ""
        self.messages: list[dict[str, Any]] = []
        self.flush_count = 0

    def write(self, text: str) -> int:
        """送信中の一行を蓄える。"""
        self.buffer += text
        return len(text)

    def flush(self) -> None:
        """一行を確定し、ホストからの返答をキューへ積む。"""
        assert self.buffer.endswith("\n")
        assert self.buffer.count("\n") == 1
        message = json.loads(self.buffer)
        self.buffer = ""
        self.flush_count += 1
        self.messages.append(message)
        self.host.on_message(message)


class _Host:
    """fixture の表だけを使ってホストの adapter 応答を作る。"""

    def __init__(self, scenario: dict[str, Any]) -> None:
        """シナリオと通信の痕跡を保持する。"""
        self.scenario = scenario
        self.stdin = _HostInput(_start(scenario))
        self.stdout = _HostOutput(self)
        self.normalize_calls = 0
        self.executed_case_ids: list[str] = []
        self.transcript: list[str] = []

    def _reply(self, message: dict[str, object]) -> None:
        """adapter 応答を次の入力行として積む。"""
        self.transcript.append(str(message["type"]))
        self.stdin.lines.append(json.dumps(message, ensure_ascii=False) + "\n")

    def on_message(self, message: dict[str, Any]) -> None:
        """要求に応じて表引きし、次の応答を返す。"""
        self.transcript.append(message["type"])
        if message["type"] == "normalize":
            config = self.scenario["normalizer"]
            if config["mode"] == "passthrough":
                normalized = message["raw"]
            else:
                entry = config["table"][self.normalize_calls]
                assert message["raw"] == entry["raw"]
                normalized = entry["normalized"]
            self.normalize_calls += 1
            self._reply({"type": "normalized", "value": normalized})
        elif message["type"] == "execute":
            config = self.scenario["calculation"]
            case_id = message["caseId"]
            if case_id not in config["supportedCaseIds"]:
                self._reply({"type": "unsupported"})
            else:
                self.executed_case_ids.append(case_id)
                output = config.get("outputs", {}).get(case_id, message["normalized"])
                self._reply({"type": "executed", "value": output})


def _serve_lines(lines: list[str]) -> tuple[int, list[dict[str, Any]]]:
    """固定入力を in-process で渡し、出力行を返す。"""
    stdin = io.StringIO("".join(lines))
    stdout = io.StringIO()
    result = BRIDGE.serve(stdin, stdout)
    return result, [json.loads(line) for line in stdout.getvalue().splitlines()]


def _line(message: dict[str, object]) -> str:
    """一つの通信メッセージを JSON 行にする。"""
    return json.dumps(message, ensure_ascii=False) + "\n"


def test_complete_message_order_and_report() -> None:
    """完走時の交互の要求と応答、flush、報告を確認する。"""
    scenario = _scenarios()[0]
    host = _Host(scenario)

    assert BRIDGE.serve(host.stdin, host.stdout) == 0
    assert host.transcript == [
        "normalize",
        "normalized",
        "execute",
        "executed",
        "normalize",
        "normalized",
        "execute",
        "executed",
        "report",
    ]
    assert host.stdout.flush_count == len(host.stdout.messages)
    report = host.stdout.messages[-1]
    assert report == _direct_report(scenario)


def test_unsupported_becomes_vector_run_error() -> None:
    """計算側の未対応だけを既存 runner が包むことを確認する。"""
    scenario = next(item for item in _scenarios() if item["id"] == "unsupported-case")
    host = _Host(scenario)

    assert BRIDGE.serve(host.stdin, host.stdout) == 0
    assert host.stdout.messages[-1] == {
        "type": "vector-run-error",
        "message": "未対応 case: caseTwo",
    }


@pytest.mark.parametrize("phase", ["normalize", "execute"])
def test_adapter_error_is_not_wrapped(phase: str) -> None:
    """両 adapter の例外を vector-run-error に包まない。"""
    scenario = _scenarios()[0]
    responses: list[dict[str, object]] = [
        {"type": "adapter-error", "message": "host failed"}
    ]
    if phase == "execute":
        responses.insert(
            0,
            {
                "type": "normalized",
                "value": scenario["normalizer"]["table"][0]["normalized"],
            },
        )
    code, messages = _serve_lines([_line(_start(scenario)), *map(_line, responses)])

    assert code == 0
    assert messages[-1] == {"type": "adapter-error"}
    assert [message["type"] for message in messages[:-1]] == (
        ["normalize"] if phase == "normalize" else ["normalize", "execute"]
    )


def test_first_message_must_be_start() -> None:
    """必要な属性を備えた別 type の初回メッセージを拒否する。"""
    start = _start(_scenarios()[0])
    start["type"] = "normalize"

    code, messages = _serve_lines([_line(start)])

    assert code == 0
    assert messages == [
        {"type": "protocol-error", "message": "最初の行が start でない"}
    ]


@pytest.mark.parametrize(
    ("first_line", "response"),
    [
        ("not json\n", None),
        (_line({"type": "executed"}), None),
        (_line({"type": "start"}), None),
        (None, _line({"type": "mystery", "value": None})),
        (None, _line({"type": "executed", "value": None})),
        (None, _line({"type": "unsupported"})),
        (None, "not json\n"),
        (None, _line({"type": "normalized"})),
        (None, ""),
    ],
)
def test_protocol_errors(first_line: str | None, response: str | None) -> None:
    """不正 JSON、型、順序、必須キー欠落、EOF を拒否する。"""
    scenario = _scenarios()[0]
    lines = [first_line or _line(_start(scenario))]
    if response is not None:
        lines.append(response)
    code, messages = _serve_lines(lines)

    assert code == 0
    assert messages[-1]["type"] == "protocol-error"
    assert isinstance(messages[-1]["message"], str)
    assert len(messages[-1]["message"]) > 0
    assert [item["type"] for item in messages[:-1]] in ([], ["normalize"])


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda item: item["id"])
def test_shared_conformance_via_bridge(scenario: dict[str, Any]) -> None:
    """九シナリオの期待値と呼び出し痕跡を直接実行と揃える。"""
    host = _Host(scenario)

    assert BRIDGE.serve(host.stdin, host.stdout) == 0
    terminal = host.stdout.messages[-1]
    expected = scenario["expected"]
    if expected["outcome"] == "complete":
        assert terminal["type"] == "report"
        assert terminal == _direct_report(scenario)
        assert terminal["complete"] is True
        assert terminal["declaredCaseIds"] == expected["declaredCaseIds"]
        assert terminal["consumedCaseIds"] == expected["consumedCaseIds"]
    else:
        assert terminal["type"] == "vector-run-error"
        assert terminal["message"].startswith(expected["messagePrefix"])
    assert host.normalize_calls == scenario["trace"]["normalizeCalls"]
    assert host.executed_case_ids == scenario["trace"]["executedCaseIds"]


def test_bridge_delegates_validation_and_comparison() -> None:
    """ブリッジが既存 runner 以外の判定機構を import しない。"""
    tree = ast.parse(BRIDGE_SOURCE.read_text(encoding="utf-8"))
    nodes = list(ast.walk(tree))
    symbols = {
        node.id for node in nodes if isinstance(node, ast.Name)
    } | {node.attr for node in nodes if isinstance(node, ast.Attribute)}
    imported_modules: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
            symbols.update(alias.name for alias in node.names)
            symbols.update(alias.asname for alias in node.names if alias.asname)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.add(module)
            symbols.add(module)
            for alias in node.names:
                imported_modules.add(f"{module}.{alias.name}")
                symbols.add(alias.name)
                if alias.asname:
                    symbols.add(alias.asname)

    assert {"validate_asset", "compare_path_set"}.isdisjoint(symbols)
    assert "pitchlog.domaincheck.cli" not in imported_modules
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "pitchlog.domaincheck.runners"
        and any(alias.name == "vectors" and alias.asname is None for alias in node.names)
        for node in nodes
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "vectors"
        and node.func.attr == "run_vectors"
        for node in nodes
    )
