"""見直しトリガーの評価記録を実測または PO 証拠へ束縛する。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Collection, Mapping
from datetime import date
from functools import cache
from pathlib import Path, PurePosixPath
from typing import cast

from pitchlog.domaincheck.cli import CheckerExecutionError

EVIDENCE_ASSET = Path("backend/domain/review-trigger-evidence.json")
_TOP_KEYS = frozenset(
    {
        "schemaVersion",
        "poEvaluationLimit",
        "machineEvaluationLimit",
        "machineEvaluations",
        "manualDecisions",
    }
)
_MACHINE_KEYS = frozenset({"triggerId", "testNodes"})
_MANUAL_KEYS = frozenset(
    {
        "triggerId",
        "judge",
        "decisionDate",
        "fired",
        "evidenceLocation",
        "evidenceDigest",
    }
)
_NODE_ID = re.compile(
    r"(?P<path>tests/(?:[A-Za-z0-9_-]+/)*test_[A-Za-z0-9_]+\.py)"
    r"::(?P<function>test_[A-Za-z0-9_]+)"
)
_MACHINE_TRIGGER_NODES: dict[int, tuple[str, ...]] = {
    3: (
        "tests/domain/gen/test_formatter.py::"
        "test_alpha_python_typescript_and_reference_return_same_display",
        "tests/domain/gen/test_formatter.py::"
        "test_beta_seven_enum_map_receiver_and_reference_agree",
        "tests/domain/gen/test_formatter.py::"
        "test_all_target_matrix_classes_are_actually_generated",
    ),
    4: (
        "tests/domain/test_path_match.py::"
        "test_allowed_lossless_normalizations_pass_all_trigger_four_axes",
        "tests/domain/test_path_match.py::"
        "test_display_string_variations_are_not_normalized",
    ),
    6: (
        "tests/domain/test_collect_fe.py::"
        "test_dynamic_worker_is_reported_as_indeterminate",
        "tests/domain/test_closure_be.py::"
        "test_unresolved_dynamic_import_is_fail_closed",
        "tests/domain/test_display_binding.py::"
        "test_unresolved_display_path_is_fail_closed",
    ),
    9: (
        "tests/domain/test_history_depth.py::"
        "test_history_depth_is_derived_from_cases_and_maximum",
    ),
    12: (
        "tests/domain/mut/test_cost_record.py::"
        "test_recorded_scopes_recompute_product_and_budget_decision",
    ),
    13: (
        "tests/domain/test_display_binding.py::"
        "test_schema_selector_addition_changes_target_closure_without_code_list",
        "tests/domain/test_display_binding.py::"
        "test_matching_target_callsite_and_generated_formatter_pass",
    ),
    14: (
        "tests/domain/test_collect_layers.py::"
        "test_collector_computes_chain_instead_of_accepting_adapter_claim",
        "tests/domain/test_collect_layers.py::"
        "test_real_pytest_junit_output_is_counted_with_provenance",
    ),
    16: (
        "tests/domain/test_step_authorities.py::"
        "test_all_authorities_exist_verbatim_in_canonical_sources",
        "tests/domain/test_step_authorities.py::"
        "test_registry_has_exactly_all_fifty_seven_steps",
    ),
}


class TriggerEvaluationError(CheckerExecutionError):
    """評価記録が独立実測または PO 証拠と一致しないことを表す。"""


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーの JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TriggerEvaluationError(f"{label} が JSON object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise TriggerEvaluationError(f"{label} が JSON array でない")
    return cast(list[object], value)


def _read_json(path: Path) -> dict[str, object]:
    """JSON 資産を object として読む。"""
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TriggerEvaluationError(f"評価証拠を読めない: {path}: {error}") from error


def _trigger_id(value: object, label: str) -> int:
    """Boolean でない正のトリガー ID を返す。"""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TriggerEvaluationError(f"{label} が正の整数でない")
    return value


def _digest_file(path: Path) -> str:
    """一ファイルの内容 digest を返す。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_digest(root: Path, location: str) -> str:
    """証拠ファイルまたは証拠木を順序付き digest へ閉じる。"""
    relative = PurePosixPath(location)
    if relative.is_absolute() or ".." in relative.parts:
        raise TriggerEvaluationError(f"証拠パスが閉域外: {location}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise TriggerEvaluationError(f"証拠パスがリポジトリ外: {location}") from error
    if path.is_file():
        return f"sha256:{_digest_file(path)}"
    if not path.is_dir():
        raise TriggerEvaluationError(f"証拠が実在しない: {location}")
    entries = [
        {
            "path": item.relative_to(path).as_posix(),
            "sha256": _digest_file(item),
        }
        for item in sorted(path.rglob("*"))
        if item.is_file() and "__pycache__" not in item.parts
    ]
    if not entries:
        raise TriggerEvaluationError(f"証拠ディレクトリが空: {location}")
    payload = json.dumps(
        entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@cache
def _run_test_nodes(root_text: str, nodes: tuple[str, ...]) -> bool:
    """Node を収集・実行し、assertion failure があれば発火とする。"""
    root = Path(root_text)
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *nodes],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    collected_count = sum(
        1 for line in collected.stdout.splitlines() if _NODE_ID.fullmatch(line.strip())
    )
    if collected.returncode != 0 or collected_count < 1:
        raise TriggerEvaluationError(
            "機械トリガーの pytest node を 1 件以上収集できない"
        )
    with tempfile.TemporaryDirectory(prefix="pitchlog-trigger-") as directory:
        junit_path = Path(directory) / "junit.xml"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                f"--junitxml={junit_path}",
                *nodes,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            junit = ET.parse(junit_path).getroot()
            suites = (
                [junit]
                if junit.tag == "testsuite"
                else list(junit.findall("testsuite"))
            )
            executed_count = sum(
                int(suite.attrib.get("tests", "0")) for suite in suites
            )
        except (OSError, ET.ParseError, ValueError) as error:
            raise TriggerEvaluationError(
                "機械トリガーの pytest 実行件数を読めない"
            ) from error
    if executed_count < 1:
        raise TriggerEvaluationError("機械トリガーを 1 件も実行していない")
    if result.returncode not in {0, 1}:
        raise TriggerEvaluationError(
            f"機械トリガーの pytest が判定不能: exit={result.returncode}"
        )
    return result.returncode == 1


def _validated_machine_nodes(
    root: Path,
    trigger_id: int,
    raw_nodes: object,
) -> tuple[str, ...]:
    """Node ID 文法・対象ファイル・関数実在を閉じて返す。"""
    nodes_raw = _array(raw_nodes, "machine.testNodes")
    if not nodes_raw or not all(isinstance(node, str) for node in nodes_raw):
        raise TriggerEvaluationError("machine.testNodes が空または文字列でない")
    nodes = tuple(cast(list[str], nodes_raw))
    matches = [_NODE_ID.fullmatch(node) for node in nodes]
    if any(match is None for match in matches):
        raise TriggerEvaluationError(
            "machine.testNodes は path::test_function 形式でなければならない"
        )
    expected_nodes = _MACHINE_TRIGGER_NODES.get(trigger_id)
    if expected_nodes is None or nodes != expected_nodes:
        raise TriggerEvaluationError(
            f"トリガー {trigger_id} の評価 node が固定対応と違う"
        )
    for node, match in zip(nodes, matches, strict=True):
        assert match is not None
        path = root / match.group("path")
        if not path.is_file():
            raise TriggerEvaluationError(f"pytest node のファイルが実在しない: {node}")
        source = path.read_text(encoding="utf-8")
        function_pattern = rf"^def {re.escape(match.group('function'))}\("
        if re.search(function_pattern, source, re.MULTILINE) is None:
            raise TriggerEvaluationError(f"pytest node の関数が実在しない: {node}")
    if len(nodes) != len(set(nodes)):
        raise TriggerEvaluationError("machine.testNodes が重複している")
    return nodes


def _evaluation_fired(row: Mapping[str, object]) -> bool | None:
    """厳密な評価レコードから発火値を返す。"""
    value = row.get("evaluation")
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"fired"}:
        raise TriggerEvaluationError("evaluation は fired だけを持たねばならない")
    fired = value["fired"]
    if not isinstance(fired, bool):
        raise TriggerEvaluationError("evaluation.fired は boolean でなければならない")
    return fired


def _judges(row: Mapping[str, object]) -> frozenset[str]:
    """トリガー行の判定者集合を返す。"""
    value = row.get("judge")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TriggerEvaluationError("judge が文字列 array でない")
    judges = frozenset(value)
    if not judges or judges - {"機械", "PO"}:
        raise TriggerEvaluationError(f"judge が閉じていない: {sorted(judges)!r}")
    return judges


def validate_recorded_evaluations(
    registry: Mapping[str, object],
    repository_root: Path,
    *,
    evidence_path: Path | None = None,
    trigger_ids: Collection[int] | None = None,
) -> None:
    """機械評価を実行し、PO 評価を日付・判定者・内容 digest へ束縛する。

    PO の判断内容そのものは機械に代行できない。本検査が保証するのは、判定者・
    判定日・発火値を持つ決定記録が存在し、指定された証拠内容がその後変わって
    いないことまでである。この限界は証拠資産にも逐語で保持する。
    """
    root = repository_root.resolve()
    evidence_file = evidence_path or root / EVIDENCE_ASSET
    evidence = _read_json(evidence_file)
    if set(evidence) != _TOP_KEYS or evidence.get("schemaVersion") != 2:
        raise TriggerEvaluationError("評価証拠のトップレベルが不正")
    limit = evidence.get("poEvaluationLimit")
    if not isinstance(limit, str) or "判断内容そのもの" not in limit:
        raise TriggerEvaluationError("PO 評価の機械保証限界が明記されていない")
    machine_limit = evidence.get("machineEvaluationLimit")
    if (
        not isinstance(machine_limit, str)
        or "テスト本体の意味" not in machine_limit
        or "保証範囲外" not in machine_limit
    ):
        raise TriggerEvaluationError("機械評価の意味保証限界が明記されていない")

    raw_rows = _array(registry.get("triggers"), "triggers")
    rows = [
        _object(value, f"triggers[{index}]") for index, value in enumerate(raw_rows)
    ]
    by_id = {_trigger_id(row.get("id"), "trigger.id"): row for row in rows}
    if len(by_id) != len(rows):
        raise TriggerEvaluationError("トリガー ID が重複している")
    selected = frozenset(by_id) if trigger_ids is None else frozenset(trigger_ids)
    unknown = selected - frozenset(by_id)
    if unknown:
        raise TriggerEvaluationError(f"未知のトリガー ID: {sorted(unknown)!r}")

    machine_rows = _array(evidence.get("machineEvaluations"), "machineEvaluations")
    machine_by_id: dict[int, tuple[str, ...]] = {}
    for index, raw in enumerate(machine_rows):
        item = _object(raw, f"machineEvaluations[{index}]")
        if set(item) != _MACHINE_KEYS:
            raise TriggerEvaluationError("machineEvaluations のキー集合が不正")
        identifier = _trigger_id(item.get("triggerId"), "machine.triggerId")
        if identifier in machine_by_id:
            raise TriggerEvaluationError(
                "machineEvaluations の triggerId が重複している"
            )
        machine_by_id[identifier] = _validated_machine_nodes(
            root,
            identifier,
            item.get("testNodes"),
        )
    expected_machine = {
        identifier for identifier, row in by_id.items() if "機械" in _judges(row)
    }
    if set(machine_by_id) != expected_machine:
        raise TriggerEvaluationError(
            "機械トリガーの実測経路が不一致: "
            f"不足={sorted(expected_machine - set(machine_by_id))!r}, "
            f"未知={sorted(set(machine_by_id) - expected_machine)!r}"
        )

    manual_rows = _array(evidence.get("manualDecisions"), "manualDecisions")
    manual_by_id: dict[int, dict[str, object]] = {}
    for index, raw in enumerate(manual_rows):
        item = _object(raw, f"manualDecisions[{index}]")
        if set(item) != _MANUAL_KEYS:
            raise TriggerEvaluationError("manualDecisions のキー集合が不正")
        identifier = _trigger_id(item.get("triggerId"), "manual.triggerId")
        if identifier in manual_by_id:
            raise TriggerEvaluationError("manualDecisions の triggerId が重複している")
        manual_by_id[identifier] = item
    expected_manual = {
        identifier for identifier, row in by_id.items() if "PO" in _judges(row)
    }
    if set(manual_by_id) != expected_manual:
        raise TriggerEvaluationError("PO トリガーの決定記録集合が不一致")

    for identifier in sorted(selected):
        row = by_id[identifier]
        recorded = _evaluation_fired(row)
        if recorded is None:
            continue
        judges = _judges(row)
        if "機械" in judges:
            measured = _run_test_nodes(str(root), machine_by_id[identifier])
            if recorded is not measured:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の記録 {recorded} が"
                    f"機械実測 {measured} と不一致"
                )
        if "PO" in judges:
            decision = manual_by_id[identifier]
            if decision.get("judge") != registry.get("poName"):
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 判定者が不正"
                )
            raw_date = decision.get("decisionDate")
            try:
                if not isinstance(raw_date, str):
                    raise ValueError
                date.fromisoformat(raw_date)
            except ValueError as error:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の判定日が不正"
                ) from error
            if decision.get("fired") is not recorded:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 決定と評価記録が不一致"
                )
            location = decision.get("evidenceLocation")
            if location != row.get("evidenceLocation") or not isinstance(location, str):
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 証拠パスが不一致"
                )
            actual_digest = evidence_digest(root, location)
            if decision.get("evidenceDigest") != actual_digest:
                raise TriggerEvaluationError(
                    f"トリガー {identifier} の PO 証拠 digest が不一致"
                )


__all__ = [
    "EVIDENCE_ASSET",
    "TriggerEvaluationError",
    "evidence_digest",
    "validate_recorded_evaluations",
]
