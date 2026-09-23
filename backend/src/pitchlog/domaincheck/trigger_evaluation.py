"""見直しトリガーの評価記録を実測または PO 証拠へ束縛する。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Collection, Mapping
from datetime import date
from functools import cache
from pathlib import Path, PurePosixPath
from typing import cast

from pitchlog.domaincheck.cli import CheckerExecutionError

EVIDENCE_ASSET = Path("backend/domain/review-trigger-evidence.json")
_TOP_KEYS = frozenset(
    {"schemaVersion", "poEvaluationLimit", "machineEvaluations", "manualDecisions"}
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
    """発火条件に対応する独立テストを実行し、失敗があれば発火とする。"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *nodes],
        cwd=Path(root_text),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode != 0


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
    if set(evidence) != _TOP_KEYS or evidence.get("schemaVersion") != 1:
        raise TriggerEvaluationError("評価証拠のトップレベルが不正")
    limit = evidence.get("poEvaluationLimit")
    if not isinstance(limit, str) or "判断内容そのもの" not in limit:
        raise TriggerEvaluationError("PO 評価の機械保証限界が明記されていない")

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
        nodes_raw = _array(item.get("testNodes"), "machine.testNodes")
        if not nodes_raw or not all(
            isinstance(node, str) and node for node in nodes_raw
        ):
            raise TriggerEvaluationError("machine.testNodes が空または不正")
        machine_by_id[identifier] = tuple(cast(list[str], nodes_raw))
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
