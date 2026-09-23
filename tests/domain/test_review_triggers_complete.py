"""基準ステップ時点の見直しトリガー評価完了を検査する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend/src"
REGISTRY_PATH = ROOT / "backend/domain/review-triggers.json"
EVIDENCE_PATH = ROOT / "backend/domain/review-trigger-evidence.json"

sys.path.insert(0, str(BACKEND_SRC))
COMPLETION = importlib.import_module(
    "pitchlog.domaincheck.trigger_completion"
)
STOPGATE = importlib.import_module("pitchlog.domaincheck.stopgate")


@pytest.fixture(scope="module")
def registry() -> dict[str, Any]:
    """実資産の評価枠を読み込む。"""
    value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_registry(tmp_path: Path, registry: dict[str, Any]) -> Path:
    """変更した評価枠を一時 JSON へ書く。"""
    path = tmp_path / "review-triggers.json"
    path.write_text(
        json.dumps(registry, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _write_evidence(tmp_path: Path, evidence: dict[str, Any]) -> Path:
    """変更した評価証拠を一時 JSON へ書く。"""
    path = tmp_path / "review-trigger-evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    return path


def _trigger(registry: dict[str, Any], trigger_id: int) -> dict[str, Any]:
    """指定 ID のトリガー行を一意に返す。"""
    matches = [
        item for item in registry["triggers"] if item["id"] == trigger_id
    ]
    assert len(matches) == 1
    return matches[0]


def test_mother_set_is_exactly_sixteen() -> None:
    """停止ゲートが検査したトリガー母集合を16件に固定する。"""
    states = STOPGATE.load_trigger_states(REGISTRY_PATH)

    assert len(states) == 16
    assert {state.trigger_id for state in states} == set(range(1, 17))


def test_as_of_fifty_accepts_all_due_evaluations() -> None:
    """基準50で期限を迎えた評価だけが全件完了していれば通す。"""
    report = COMPLETION.validate_trigger_completion(
        REGISTRY_PATH,
        ROOT,
        as_of_step=50,
    )
    states = STOPGATE.load_trigger_states(REGISTRY_PATH)
    expected = {
        state.trigger_id for state in states if state.evaluation_deadline <= 50
    }

    assert report.trigger_count == len(states) == 16
    assert report.applicable_trigger_ids == expected
    assert report.evaluated_trigger_ids == expected


def test_as_of_fifty_seven_rejects_unevaluated_trigger_sixteen(
    registry: dict[str, Any], tmp_path: Path
) -> None:
    """期限57に達した未評価のトリガー16を拒否する。"""
    asset = copy.deepcopy(registry)
    _trigger(asset, 16)["evaluation"] = None

    with pytest.raises(COMPLETION.IncompleteEvaluationError, match="16"):
        COMPLETION.validate_trigger_completion(
            _write_registry(tmp_path, asset),
            ROOT,
            as_of_step=57,
        )


def test_one_due_trigger_returned_to_unevaluated_is_rejected(
    registry: dict[str, Any], tmp_path: Path
) -> None:
    """期限を迎えた評価を一件未評価へ戻す遷移を拒否する。"""
    asset = copy.deepcopy(registry)
    due = next(
        item
        for item in asset["triggers"]
        if item["evaluationDeadline"] <= 50
        and item["evaluation"] is not None
    )
    due["evaluation"] = None

    with pytest.raises(
        COMPLETION.IncompleteEvaluationError,
        match=str(due["id"]),
    ):
        COMPLETION.validate_trigger_completion(
            _write_registry(tmp_path, asset),
            ROOT,
            as_of_step=50,
        )


def test_nine_po_evidence_locations_are_allowed_and_exist() -> None:
    """PO を含む九判定の証拠が閉域内に実在する。"""
    report = COMPLETION.validate_trigger_completion(
        REGISTRY_PATH,
        ROOT,
        as_of_step=50,
    )

    assert len(report.manual_evidence) == 9
    assert all(item.resolved_path.exists() for item in report.manual_evidence)
    assert all(
        any(
            item.location.rstrip("/") == prefix
            or item.location.startswith(f"{prefix}/")
            for prefix in COMPLETION.MANUAL_EVIDENCE_PATH_ALLOWLIST
        )
        for item in report.manual_evidence
    )


def test_po_evidence_outside_allowlist_is_rejected(
    registry: dict[str, Any], tmp_path: Path
) -> None:
    """実在しても allowlist 外にある PO 証拠を拒否する。"""
    asset = copy.deepcopy(registry)
    po_trigger = next(
        item for item in asset["triggers"] if "PO" in item["judge"]
    )
    po_trigger["evidenceLocation"] = "frontend/package.json"

    with pytest.raises(COMPLETION.EvidenceLocationError, match="allowlist"):
        COMPLETION.validate_trigger_completion(
            _write_registry(tmp_path, asset),
            ROOT,
            as_of_step=50,
        )


def test_missing_po_evidence_is_rejected(
    registry: dict[str, Any], tmp_path: Path
) -> None:
    """Allowlist 内でも実在しない PO 証拠を拒否する。"""
    asset = copy.deepcopy(registry)
    po_trigger = next(
        item for item in asset["triggers"] if "PO" in item["judge"]
    )
    po_trigger["evidenceLocation"] = "backend/domain/not-present.json"

    with pytest.raises(COMPLETION.EvidenceLocationError, match="実在しない"):
        COMPLETION.validate_trigger_completion(
            _write_registry(tmp_path, asset),
            ROOT,
            as_of_step=50,
        )


def test_fired_record_is_rejected_by_existing_stopgate(
    registry: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """発火後の拒否を既存停止ゲートの判定へ委ねる。"""
    asset = copy.deepcopy(registry)
    due = next(
        item
        for item in asset["triggers"]
        if item["evaluationDeadline"] <= 50
    )
    due["evaluation"] = {"fired": True}
    called: list[int] = []
    original = STOPGATE.rejection_reasons

    def observing_rejection_reasons(states: Any, current_step: int) -> Any:
        """既存停止判定の呼び出しを観測して結果を委譲する。"""
        called.append(current_step)
        return original(states, current_step)

    monkeypatch.setattr(
        COMPLETION.stopgate,
        "rejection_reasons",
        observing_rejection_reasons,
    )
    monkeypatch.setattr(
        COMPLETION.trigger_evaluation,
        "validate_recorded_evaluations",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(COMPLETION.FiredTriggerError, match="発火済み"):
        COMPLETION.validate_trigger_completion(
            _write_registry(tmp_path, asset),
            ROOT,
            as_of_step=51,
        )
    assert called == [51]


def test_recorded_evaluations_match_machine_measurements_and_po_evidence() -> None:
    """実記録が機械の再実測と PO の日付付き証拠へ一致すれば通る。"""
    report = COMPLETION.validate_trigger_completion(
        REGISTRY_PATH,
        ROOT,
        as_of_step=57,
    )

    assert report.applicable_trigger_ids == report.evaluated_trigger_ids
    assert len(report.applicable_trigger_ids) == report.trigger_count == 16


def test_machine_trigger_cannot_be_marked_without_measured_condition(
    registry: dict[str, Any], tmp_path: Path
) -> None:
    """機械実測が非発火なのに発火と自己申告した記録を拒否する。"""
    asset = copy.deepcopy(registry)
    _trigger(asset, 3)["evaluation"] = {"fired": True}

    with pytest.raises(
        COMPLETION.trigger_evaluation.TriggerEvaluationError,
        match="機械実測",
    ):
        COMPLETION.validate_trigger_completion(
            _write_registry(tmp_path, asset),
            ROOT,
            as_of_step=57,
        )


def test_machine_trigger_rejects_pytest_option_instead_of_node_id(
    tmp_path: Path,
) -> None:
    """`--version` で 0 件評価のまま非発火にできない。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence["machineEvaluations"][0]["testNodes"] = ["--version"]

    with pytest.raises(
        COMPLETION.trigger_evaluation.TriggerEvaluationError,
        match="path::test_function",
    ):
        COMPLETION.validate_trigger_completion(
            REGISTRY_PATH,
            ROOT,
            as_of_step=57,
            evaluation_evidence_path=_write_evidence(tmp_path, evidence),
        )


def test_machine_trigger_rejects_unrelated_test_in_allowed_file(
    tmp_path: Path,
) -> None:
    """許可ファイル内でも固定した評価テスト以外への差し替えを拒否する。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence["machineEvaluations"][0]["testNodes"][0] = (
        "tests/domain/gen/test_formatter.py::"
        "test_reference_implementations_have_regenerable_provenance"
    )

    with pytest.raises(
        COMPLETION.trigger_evaluation.TriggerEvaluationError,
        match="評価 node が固定対応",
    ):
        COMPLETION.validate_trigger_completion(
            REGISTRY_PATH,
            ROOT,
            as_of_step=57,
            evaluation_evidence_path=_write_evidence(tmp_path, evidence),
        )


def test_machine_evaluation_semantic_limit_is_explicit() -> None:
    """固定 node のテスト本体の意味は機械保証外であると明記する。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert "テスト本体の意味" in evidence["machineEvaluationLimit"]
    assert "保証範囲外" in evidence["machineEvaluationLimit"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("judge", "別の判定者", "PO 判定者"),
        ("decisionDate", "not-a-date", "判定日"),
    ],
)
def test_po_decision_requires_named_judge_and_date(
    field: str,
    value: str,
    message: str,
    tmp_path: Path,
) -> None:
    """PO 判定の判定者・判定日をそれぞれ必須化する。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence["manualDecisions"][0][field] = value

    with pytest.raises(
        COMPLETION.trigger_evaluation.TriggerEvaluationError,
        match=message,
    ):
        COMPLETION.validate_trigger_completion(
            REGISTRY_PATH,
            ROOT,
            as_of_step=57,
            evaluation_evidence_path=_write_evidence(tmp_path, evidence),
        )


def test_duplicate_manual_decision_id_is_rejected(tmp_path: Path) -> None:
    """矛盾する PO 決定を前置きして後勝ちにする経路を拒否する。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(evidence["manualDecisions"][0])
    duplicate["fired"] = not duplicate["fired"]
    evidence["manualDecisions"].insert(0, duplicate)

    with pytest.raises(
        COMPLETION.trigger_evaluation.TriggerEvaluationError,
        match="manualDecisions.*重複",
    ):
        COMPLETION.validate_trigger_completion(
            REGISTRY_PATH,
            ROOT,
            as_of_step=57,
            evaluation_evidence_path=_write_evidence(tmp_path, evidence),
        )


def test_po_evidence_content_change_is_rejected(tmp_path: Path) -> None:
    """PO が見た証拠と異なる digest の自己申告を拒否する。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence["manualDecisions"][0]["evidenceDigest"] = "sha256:" + "0" * 64

    with pytest.raises(
        COMPLETION.trigger_evaluation.TriggerEvaluationError,
        match="digest",
    ):
        COMPLETION.validate_trigger_completion(
            REGISTRY_PATH,
            ROOT,
            as_of_step=57,
            evaluation_evidence_path=_write_evidence(tmp_path, evidence),
        )
