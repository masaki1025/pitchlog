"""descriptorParity の射影・履歴深さ・失敗時の規則 ID を検証する。"""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from pitchlog.domaincheck.descriptor_parity import (
    DescriptorParityError,
    check_descriptor_parity,
)
from pitchlog.domaincheck.runners.handoff import LoadedHandoff, load_handoff

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTOR = "contracts/state-transition/input_axes_descriptor_v1.json"
STATE_SCHEMA = "contracts/state-transition/state_transition_contract_schema_v1.json"
GAME_SCHEMA = "contracts/state-transition/game_end_contract_schema_v1.json"
HISTORY = "backend/domain/history-depth.json"
HANDOFF = "contracts/state-transition/appendix_e_consumer_handoff_v1.json"


@pytest.fixture(scope="module")
def loaded() -> LoadedHandoff:
    """版検査済みの実 handoff を返す。"""
    return load_handoff(ROOT)


def _copy_assets(tmp_path: Path) -> None:
    """実ファイルを変えず、検査対象だけを一時領域へ複製する。"""
    for name in (DESCRIPTOR, STATE_SCHEMA, GAME_SCHEMA, HISTORY, HANDOFF):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)


def _change(path: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    """一時コピーの JSON だけを書き換える。"""
    data = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _mutated_descriptor(root: Path, loaded: LoadedHandoff) -> LoadedHandoff:
    """一時コピーの descriptor を下位検査口へ渡す。"""
    descriptor = cast(
        dict[str, object], json.loads((root / DESCRIPTOR).read_text(encoding="utf-8"))
    )
    return LoadedHandoff(loaded.by_calculation, descriptor)


def _rules(descriptor: dict[str, object]) -> list[dict[str, object]]:
    """試験のため射影規則配列を取得する。"""
    return cast(list[dict[str, object]], descriptor["projectionRules"])


def _game_axis(schema: dict[str, object], name: str) -> dict[str, object]:
    """終了判定 schema の明示的な軸を取得する。"""
    defs = cast(dict[str, object], schema["$defs"])
    snapshot = cast(dict[str, object], defs["ruleSnapshot"])
    properties = cast(dict[str, object], snapshot["properties"])
    return cast(dict[str, object], properties[name])


def _reject(
    tmp_path: Path,
    loaded: LoadedHandoff,
    path: str,
    mutate: Callable[[dict[str, object]], None],
    code: str,
) -> None:
    """一時コピーだけを変え、期待した規則 ID で拒否されることを調べる。"""
    _copy_assets(tmp_path)
    _change(tmp_path / path, mutate)
    with pytest.raises(DescriptorParityError) as caught:
        check_descriptor_parity(
            tmp_path,
            _mutated_descriptor(tmp_path, loaded),
        )
    assert caught.value.code == code


def test_repository_projection_rules_and_d_are_resolved(loaded: LoadedHandoff) -> None:
    """現行の8規則を通し、D=4 と D+1=5 を実値で得る。"""
    result = check_descriptor_parity(ROOT, loaded)

    assert (
        len(result.rule_ids)
        == len(cast(list[object], loaded.descriptor["projectionRules"]))
        == 8
    )
    assert set(result.rule_ids) == {
        "projection.finiteEnumerable",
        "projection.boundaryPartition",
        "projection.structuredBoundaryPartition",
        "projection.deferredStructuredBoundaryPartition",
        "projection.boundedBoundaryPartition",
        "projection.nonFinite",
        "projection.nonCoverageField",
        "projection.descriptorIdentity",
    }
    assert result.history_depth == 4
    assert result.resolved_history_boundaries["history.depth"] == (0, 1, 2, 4)
    assert result.resolved_history_boundaries["history.scenarioLength"] == (
        1,
        2,
        4,
        5,
    )


def test_added_axis_is_rejected(tmp_path: Path, loaded: LoadedHandoff) -> None:
    """規則へ帰属しない軸を足すと exact-set 不一致になる。"""

    def mutate(descriptor: dict[str, object]) -> None:
        axes = cast(list[object], descriptor["stateTransitionAxes"])
        added = copy.deepcopy(cast(dict[str, object], axes[0]))
        added["axisId"] = "state.extra"
        axes.append(added)

    _reject(tmp_path, loaded, DESCRIPTOR, mutate, "AXIS_SET")


def test_removed_axis_is_rejected(tmp_path: Path, loaded: LoadedHandoff) -> None:
    """規則に残った軸を descriptor から消すと拒否する。"""

    def mutate(descriptor: dict[str, object]) -> None:
        axes = cast(list[object], descriptor["stateTransitionAxes"])
        axes.pop(0)

    _reject(tmp_path, loaded, DESCRIPTOR, mutate, "AXIS_SET")


def test_schema_axis_loss_is_rejected(tmp_path: Path, loaded: LoadedHandoff) -> None:
    """終了判定 schema の注釈から軸を消しても exact-set 不一致になる。"""

    def mutate(schema: dict[str, object]) -> None:
        _game_axis(schema, "regulationInnings").pop("x-pitchlog-axis-id")

    _reject(tmp_path, loaded, GAME_SCHEMA, mutate, "AXIS_SET")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda schema: _game_axis(schema, "regulationInnings").update(
            {"x-pitchlog-boundary-values": [1, 7, 9, 99]}
        ),
        lambda schema: _game_axis(schema, "regulationInnings").update({"maximum": 98}),
    ],
)
def test_value_range_drift_is_rejected(
    tmp_path: Path,
    loaded: LoadedHandoff,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    """境界集合と JSON Schema の実制約のずれを拒否する。"""
    _reject(tmp_path, loaded, GAME_SCHEMA, mutate, "VALUE_RANGE")


def test_descriptor_digest_drift_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """派生 schema の descriptor digest のずれを拒否する。"""

    def mutate(schema: dict[str, object]) -> None:
        defs = cast(dict[str, object], schema["$defs"])
        binding = cast(dict[str, object], defs["inputAxesDescriptorBinding"])
        properties = cast(dict[str, object], binding["properties"])
        digest = cast(dict[str, object], properties["digest"])
        digest["const"] = "sha256:" + "0" * 64

    _reject(tmp_path, loaded, STATE_SCHEMA, mutate, "DESCRIPTOR_IDENTITY")


def test_derived_schema_version_drift_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """派生 schema の版が違えば射影を判定しない。"""

    def mutate(schema: dict[str, object]) -> None:
        schema["version"] = "unknown"

    _reject(tmp_path, loaded, STATE_SCHEMA, mutate, "SCHEMA_VERSION")


def test_history_depth_drift_is_rejected(tmp_path: Path, loaded: LoadedHandoff) -> None:
    """履歴資産の導出元を変えると固定された依存 digest と不一致になる。"""

    def mutate(history: dict[str, object]) -> None:
        derivation = cast(dict[str, object], history["derivation"])
        scenarios = cast(list[dict[str, object]], derivation["requiredScenarioCases"])
        first = scenarios[0]
        events = cast(list[str], first["events"])
        events.append("confirmed-play-c")
        first["length"] = len(events)

    _reject(tmp_path, loaded, HISTORY, mutate, "HISTORY_DEPTH")


def test_history_symbolic_value_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """未知の D 表記を実値へ解決できない場合は判定不能とする。"""

    def mutate(descriptor: dict[str, object]) -> None:
        axes = cast(list[dict[str, object]], descriptor["stateTransitionAxes"])
        axis = next(axis for axis in axes if axis["axisId"] == "history.depth")
        axis["boundaryValues"] = [0, 1, 2, "D+unknown"]

    _reject(tmp_path, loaded, DESCRIPTOR, mutate, "PARITY_UNDECIDABLE")


def test_non_coverage_field_loss_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """非 coverage field の schema 注釈が欠けたら拒否する。"""

    def mutate(schema: dict[str, object]) -> None:
        _game_axis(schema, "dh").pop("x-pitchlog-non-coverage-field")

    _reject(tmp_path, loaded, GAME_SCHEMA, mutate, "NON_COVERAGE")


def test_non_coverage_required_loss_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """非 coverage field が required から落ちても拒否する。"""

    def mutate(schema: dict[str, object]) -> None:
        defs = cast(dict[str, object], schema["$defs"])
        snapshot = cast(dict[str, object], defs["ruleSnapshot"])
        cast(list[str], snapshot["required"]).remove("dh")

    _reject(tmp_path, loaded, GAME_SCHEMA, mutate, "NON_COVERAGE")


@pytest.mark.parametrize(
    ("rule_id", "axis_id", "field", "code"),
    [
        ("projection.finiteEnumerable", "state.half", "values", "PARITY_UNDECIDABLE"),
        (
            "projection.structuredBoundaryPartition",
            "event.perPitch.thirdOutTimingByRunner",
            "valueSchema",
            "PARITY_UNDECIDABLE",
        ),
        (
            "projection.deferredStructuredBoundaryPartition",
            "event.operationPayload",
            "representationCapability",
            "PARITY_UNDECIDABLE",
        ),
    ],
)
def test_projection_source_field_loss_is_rejected(
    tmp_path: Path,
    loaded: LoadedHandoff,
    rule_id: str,
    axis_id: str,
    field: str,
    code: str,
) -> None:
    """個別規則が必要とする値域情報の欠落を拒否する。"""

    def mutate(descriptor: dict[str, object]) -> None:
        rule = next(rule for rule in _rules(descriptor) if rule["ruleId"] == rule_id)
        assert axis_id in cast(list[str], rule["targetIds"])
        axes = cast(list[dict[str, object]], descriptor["stateTransitionAxes"])
        next(axis for axis in axes if axis["axisId"] == axis_id).pop(field)

    _reject(tmp_path, loaded, DESCRIPTOR, mutate, code)


def test_deferred_constraint_target_drift_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """構造化軸の外部制約対象が射影対象と違えば拒否する。"""

    def mutate(descriptor: dict[str, object]) -> None:
        external = cast(dict[str, object], descriptor["stage2ExternalConstraints"])
        cast(list[str], external["payloadAxisIds"]).pop()

    _reject(tmp_path, loaded, DESCRIPTOR, mutate, "VALUE_RANGE")


def test_projection_keyword_loss_is_undecidable(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """射影が要求する schema キーワードの欠落を判定不能として拒否する。"""

    def mutate(descriptor: dict[str, object]) -> None:
        cast(list[str], _rules(descriptor)[0]["jsonSchemaKeywords"]).pop()

    _reject(tmp_path, loaded, DESCRIPTOR, mutate, "PARITY_UNDECIDABLE")


def test_history_depth_plus_one_declaration_drift_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """D+1 の導出宣言が変われば実値との突合前に拒否する。"""

    def mutate(history: dict[str, object]) -> None:
        plus_one = cast(dict[str, object], history["historyDepthPlusOne"])
        plus_one["valueFrom"] = "unknown"

    _reject(tmp_path, loaded, HISTORY, mutate, "HISTORY_DEPTH")


@pytest.mark.parametrize("rule_index", range(8))
def test_uninterpretable_projection_rule_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff, rule_index: int
) -> None:
    """8規則のどれも未知の射影方式を許さない。"""

    def mutate(descriptor: dict[str, object]) -> None:
        _rules(descriptor)[rule_index]["projectionMode"] = "unknown-mode"

    _reject(tmp_path, loaded, DESCRIPTOR, mutate, "PARITY_UNDECIDABLE")


def test_missing_reference_target_is_rejected(
    tmp_path: Path, loaded: LoadedHandoff
) -> None:
    """状態遷移 schema の参照先集合が変わると判定不能とする。"""

    def mutate(schema: dict[str, object]) -> None:
        constraints = cast(
            dict[str, object], schema["x-pitchlog-reference-constraints"]
        )
        resolver = cast(dict[str, object], constraints["predicateAxisResolution"])
        resolver["descriptorCollections"] = ["missingAxes"]

    _reject(tmp_path, loaded, STATE_SCHEMA, mutate, "PARITY_UNDECIDABLE")
