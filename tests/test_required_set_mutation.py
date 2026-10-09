"""requiredSet の descriptor 変異耐性を検証する。"""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path, PurePosixPath
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


def _inputs() -> tuple[dict[str, Any], dict[str, Any], str, frozenset[str]]:
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
    return policy, descriptor, requirements_text, clause_ids


def test_all_declared_mutants_change_applicable_required_sets() -> None:
    """両 requiredSet の全対象軸で生存変異体がない。"""
    before = (ASSETS / "input_axes_descriptor_v1.json").read_bytes()
    assert checker.check_repository(ROOT) == {
        "axis-deletion": 30,
        "boundary-value-replacement": 95,
    }
    assert (ASSETS / "input_axes_descriptor_v1.json").read_bytes() == before


@pytest.mark.parametrize("output", ["requiredSet.inputCoordinates", "gameEnd.requiredSet"])
def test_injected_deriver_that_ignores_mutations_reports_survivors(output: str) -> None:
    """片方の導出器が入力を見ない場合、軸・値・導出器を含めて赤になる。"""
    policy, descriptor, requirements_text, clause_ids = _inputs()
    input_baseline = (
        checker.derivers.derive_input_coordinate_requirements_from_descriptor(descriptor)
    )
    game_end_baseline = checker.derivers.derive_game_end_required_set_from_documents(
        descriptor, requirements_text, clause_ids
    )
    kwargs: dict[str, Any] = {}
    if output == "requiredSet.inputCoordinates":
        kwargs["input_deriver"] = lambda _descriptor: input_baseline
    else:
        kwargs["game_end_deriver"] = lambda _descriptor, _text, _ids: game_end_baseline
    with pytest.raises(checker.RequiredSetMutationError, match="生存した変異体") as error:
        checker.check_documents(policy, descriptor, requirements_text, clause_ids, **kwargs)
    message = str(error.value)
    assert "axis-deletion" in message
    assert "boundary-value-replacement" in message
    assert "boundaryValues[" in message
    assert f"deriver={output}" in message


def test_declared_mutant_count_mismatch_is_red() -> None:
    """宣言件数が生成件数と違う場合は導出前に赤になる。"""
    policy, descriptor, requirements_text, clause_ids = _inputs()
    changed = deepcopy(policy)
    changed["operators"][0]["expectedMutantCount"] += 1
    with pytest.raises(checker.RequiredSetMutationError, match="declared=31; generated=30"):
        checker.check_documents(changed, descriptor, requirements_text, clause_ids)


def test_excluded_top_level_fields_are_exact_set() -> None:
    """対象外の取りこぼしや過剰宣言を拒否する。"""
    policy, descriptor, _, _ = _inputs()
    changed = deepcopy(policy)
    changed["excludedDescriptorTopLevelFields"].pop()
    with pytest.raises(checker.RequiredSetMutationError, match="exact-set不一致"):
        checker.validate_policy(changed, descriptor)


def test_replacement_avoids_existing_axis_value() -> None:
    """テンプレートが既存値と一致しても決定的な接尾辞で衝突を避ける。"""
    policy, descriptor, _, _ = _inputs()
    operator = policy["operators"][1]
    axis = next(axis for axis in descriptor["gameEndAxes"] if axis["axisId"] == "gameEnd.tiebreak")
    base = operator["replacementTemplate"].format(axisId=axis["axisId"], valueIndex=0)
    axis["boundaryValues"].append(base)
    assert checker._replacement(axis, 0, operator) == f"{base}:0"
    assert checker._replacement(axis, 0, operator) == f"{base}:0"
