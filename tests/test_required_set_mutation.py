"""requiredSet の descriptor 変異耐性を検証する。"""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ASSETS = ROOT / "contracts/state-transition"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象を独立したモジュール名で読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", SCRIPTS / "state_transition_freeze.py")
_load_module("check_input_axes_descriptor", SCRIPTS / "check_input_axes_descriptor.py")
_load_module("check_deriver_dependencies", SCRIPTS / "check_deriver_dependencies.py")
checker = _load_module("check_required_set_mutation", SCRIPTS / "check_required_set_mutation.py")


def _inputs() -> tuple[dict[str, Any], dict[str, Any], str, frozenset[str], Any]:
    """実資産をメモリ上に読み込む。"""
    policy = json.loads(
        (ASSETS / "required_set_mutation_policy_v1.json").read_text(encoding="utf-8")
    )
    descriptor = json.loads(
        (ASSETS / "input_axes_descriptor_v1.json").read_text(encoding="utf-8")
    )
    requirements_text = (ROOT / policy["requirementsPath"]).read_text(encoding="utf-8")
    clause_ids = frozenset(
        f"req:{item}"
        for item in checker.derivers.descriptor_checker.load_clause_ids_from_paths(
            ROOT, (PurePosixPath(policy["requirementsPath"]),)
        )
    )
    documents = checker.derivers.descriptor_checker.load_game_end_observation_documents(
        ROOT, checker.derivers.descriptor_checker.load_descriptor_criteria(descriptor)
    )
    return policy, descriptor, requirements_text, clause_ids, documents


def test_all_declared_mutants_change_applicable_required_sets() -> None:
    """両 requiredSet の全対象軸で生存変異体がない。"""
    before = (ASSETS / "input_axes_descriptor_v1.json").read_bytes()
    policy, _, _, _, _ = _inputs()
    assert checker.check_repository(ROOT) == {
        operator["operatorId"]: operator["expectedMutantCount"]
        for operator in policy["operators"]
    }
    assert (ASSETS / "input_axes_descriptor_v1.json").read_bytes() == before


@pytest.mark.parametrize("output", ["requiredSet.inputCoordinates", "gameEnd.requiredSet"])
def test_injected_deriver_that_ignores_mutations_reports_survivors(output: str) -> None:
    """片方の導出器が入力を見ない場合、軸・値・導出器を含めて赤になる。"""
    policy, descriptor, requirements_text, clause_ids, documents = _inputs()
    input_baseline = (
        checker.derivers.derive_input_coordinate_requirements_from_descriptor(descriptor)
    )
    game_end_baseline = checker.derivers.derive_game_end_required_set_from_documents(
        descriptor, requirements_text, clause_ids, documents
    )
    kwargs: dict[str, Any] = {}
    if output == "requiredSet.inputCoordinates":
        kwargs["input_deriver"] = lambda _descriptor: input_baseline
    else:
        kwargs["game_end_deriver"] = lambda _descriptor, _text, _ids, _documents: game_end_baseline
    with pytest.raises(checker.RequiredSetMutationError, match="生存した変異体") as error:
        checker.check_documents(
            policy, descriptor, requirements_text, clause_ids,
            observation_documents=documents, **kwargs,
        )
    message = str(error.value)
    assert "axis-deletion" in message
    assert "boundary-value-replacement" in message
    assert "boundaryValues[" in message
    assert f"deriver={output}" in message


def test_declared_mutant_count_mismatch_is_red() -> None:
    """宣言件数が生成件数と違う場合は導出前に赤になる。"""
    policy, descriptor, requirements_text, clause_ids, documents = _inputs()
    changed = deepcopy(policy)
    changed["operators"][0]["expectedMutantCount"] += 1
    declared = policy["operators"][0]["expectedMutantCount"]
    with pytest.raises(
        checker.RequiredSetMutationError,
        match=f"declared={declared + 1}; generated={declared}",
    ):
        checker.check_documents(
            changed, descriptor, requirements_text, clause_ids,
            observation_documents=documents,
        )


def test_excluded_top_level_fields_are_exact_set() -> None:
    """対象外の取りこぼしや過剰宣言を拒否する。"""
    policy, descriptor, _, _, _ = _inputs()
    changed = deepcopy(policy)
    changed["excludedDescriptorTopLevelFields"].pop()
    with pytest.raises(checker.RequiredSetMutationError, match="exact-set不一致"):
        checker.validate_policy(changed, descriptor)


def test_replacement_avoids_existing_axis_value() -> None:
    """テンプレートが既存値と一致しても決定的な接尾辞で衝突を避ける。"""
    policy, descriptor, _, _, _ = _inputs()
    operator = policy["operators"][1]
    axis = next(axis for axis in descriptor["gameEndAxes"] if axis["axisId"] == "gameEnd.tiebreak")
    base = operator["replacementTemplate"].format(axisId=axis["axisId"], valueIndex=0)
    axis["boundaryValues"].append(base)
    assert checker._replacement(axis, 0, operator) == f"{base}:0"
    assert checker._replacement(axis, 0, operator) == f"{base}:0"


def _observation_axes(descriptor: dict[str, Any], documents: Any) -> frozenset[str]:
    """唯一資格APIで検証したT2対象の補集合を取得する。"""
    source = checker.derivers.descriptor_checker
    criteria = source.load_descriptor_criteria(descriptor)
    included = source.game_end_coordinate_axis_ids(descriptor, criteria, documents)
    return source._play_coordinate_axis_ids(descriptor) - included


def test_observation_mutants_must_keep_game_end_output_unchanged() -> None:
    """観測専用軸を誤ってT2へ混入する導出器は不変検査で拒否する。"""
    policy, descriptor, text, clauses, documents = _inputs()
    observations = _observation_axes(descriptor, documents)
    real = checker.derivers.derive_game_end_required_set_from_documents

    def leaking_deriver(value: Any, body: str, ids: Any, supplied: Any) -> Any:
        """観測軸欠落だけでT2要求を失う不正導出器を注入する。"""
        result = real(value, body, ids, supplied)
        present = {axis["axisId"] for axis in value["stateTransitionAxes"]}
        if not observations <= present:
            return SimpleNamespace(requirements=result.requirements[:-1])
        return result

    with pytest.raises(checker.RequiredSetMutationError, match="T2不変違反"):
        checker.check_documents(
            policy, descriptor, text, clauses, observation_documents=documents,
            game_end_deriver=leaking_deriver,
        )


@pytest.mark.parametrize("mutation", ["missing-observation", "move-legacy", "unknown-observation"])
def test_unqualified_original_scope_is_rejected_before_mutation(mutation: str) -> None:
    """欠落・旧軸移動・未知の観測軸を元入力の独立資格で拒否する。"""
    policy, descriptor, text, clauses, documents = _inputs()
    observations = _observation_axes(descriptor, documents)
    scope = descriptor["freezeBaseline"]["criteria"]["inputAxesDescriptor"][
        "checkerExpectedValues"
    ]["gameEndCoordinateScope"]
    if mutation == "missing-observation":
        target = next(iter(observations))
        descriptor["stateTransitionAxes"][:] = [
            axis for axis in descriptor["stateTransitionAxes"] if axis["axisId"] != target
        ]
    elif mutation == "move-legacy":
        scope["observationOnlyAxisIds"].append(scope["includedAxisIds"].pop())
    else:
        unknown = "event.perPitch.unknownObservation"
        original = next(iter(observations))
        axis = deepcopy(next(
            item for item in descriptor["stateTransitionAxes"] if item["axisId"] == original
        ))
        axis["axisId"] = unknown
        descriptor["stateTransitionAxes"].append(axis)
        scope["observationOnlyAxisIds"].append(unknown)
        group = next(
            item for item in descriptor["inputCoordinateCoverage"]["axisBindings"]
            if original in item["axisIds"]
        )
        group["axisIds"].append(unknown)
    with pytest.raises(checker.derivers.descriptor_checker.DescriptorCheckError):
        checker.check_documents(
            policy, descriptor, text, clauses, observation_documents=documents,
        )


def test_readonly_qualification_bytes_remain_mandatory() -> None:
    """通常入力の独立原byte欠落をmutatorの試験文脈でも拒否する。"""
    policy, descriptor, text, clauses, _ = _inputs()
    with pytest.raises(
        checker.derivers.descriptor_checker.DescriptorCheckError, match="原byteが欠落"
    ):
        checker.check_documents(policy, descriptor, text, clauses)


@pytest.mark.parametrize("field", ["rules", "input_schema", "baseline_snapshot"])
def test_each_readonly_qualification_byte_tamper_is_rejected(field: str) -> None:
    """binding/schema/旧snapshotの原byte改竄を推測補完せず拒否する。"""
    policy, descriptor, text, clauses, documents = _inputs()
    changed = replace(documents, **{field: getattr(documents, field) + b" "})
    with pytest.raises(
        checker.derivers.descriptor_checker.DescriptorCheckError, match="原byte SHA"
    ):
        checker.check_documents(
            policy, descriptor, text, clauses, observation_documents=changed,
        )
