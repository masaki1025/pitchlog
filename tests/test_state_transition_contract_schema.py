"""状況判定契約schemaの構造を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/state_transition_contract_schema_v1.json"
)
DESCRIPTOR_PATH = (
    REPOSITORY_ROOT / "contracts/state-transition/input_axes_descriptor_v1.json"
)


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
schema_checker = _load_module(
    "state_transition_contract_descriptor_checker", DESCRIPTOR_CHECKER_PATH
)


def _load_object(path: Path) -> dict[str, Any]:
    """JSON objectを読み込む。

    Args:
        path: 読み込むJSONファイル。

    Returns:
        読み込んだJSON object。
    """
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _schema() -> dict[str, Any]:
    """状況判定契約schemaを返す。"""
    return _load_object(SCHEMA_PATH)


def _descriptor() -> dict[str, Any]:
    """入力軸descriptorを返す。"""
    return _load_object(DESCRIPTOR_PATH)


def _minimal_contract() -> dict[str, Any]:
    """構造検査だけを通る最小の状況判定契約を返す。"""
    descriptor = _descriptor()
    return {
        "schemaVersion": 1,
        "version": "state_transition_contract_v1",
        "calculation": "state-transition",
        "inputAxesDescriptor": {
            "descriptorId": descriptor["descriptorId"],
            "version": descriptor["version"],
            "digest": descriptor["digest"],
        },
        "matrixRows": [{}],
        "operationRows": [{}],
        "undoRows": [{}],
        "mustOperationCoverage": {},
        "requiredSet": {},
        "cases": [{}],
    }


def _validate(contract: dict[str, Any]) -> None:
    """既存の汎用validatorで状況判定契約を検証する。"""
    schema = _schema()
    schema_checker._validate_instance(contract, schema, schema, "$")


def test_repository_schema_accepts_the_three_normative_row_layers() -> None:
    """3規範行層と派生層を持つ最小構造を受理する。"""
    schema = _schema()

    assert schema["version"] == SCHEMA_PATH.stem
    assert "decisionRows" not in schema["properties"]
    _validate(_minimal_contract())


def test_schema_binding_matches_the_input_axes_descriptor_identity() -> None:
    """schemaのdescriptor拘束が正本descriptorのidentityと一致する。"""
    schema = _schema()
    descriptor = _descriptor()
    properties = schema["$defs"]["inputAxesDescriptorBinding"]["properties"]

    assert properties["descriptorId"]["const"] == descriptor["descriptorId"]
    assert properties["version"]["const"] == descriptor["version"]
    assert properties["digest"]["const"] == descriptor["digest"]


@pytest.mark.parametrize("missing_layer", ["matrixRows", "operationRows", "undoRows"])
def test_missing_normative_row_layer_is_red(missing_layer: str) -> None:
    """3規範行層のいずれかが欠けた契約を拒否する。"""
    contract = copy.deepcopy(_minimal_contract())
    del contract[missing_layer]

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match=rf"必須キー不足: .*{missing_layer}",
    ):
        _validate(contract)


def test_row_internals_remain_open_for_later_constraint_steps() -> None:
    """行内部の参照・値域・交差制約を本ステップで先取りしない。"""
    contract = _minimal_contract()
    for layer in ("matrixRows", "operationRows", "undoRows"):
        contract[layer] = [{"futureConstraintField": {"notClosedYet": True}}]

    _validate(contract)


def test_decision_rows_belong_to_the_separate_game_end_contract() -> None:
    """終了判定のdecisionRowsを状況判定契約へ混在させない。"""
    contract = _minimal_contract()
    contract["decisionRows"] = []

    with pytest.raises(
        schema_checker.DescriptorCheckError,
        match="未知キー: .*decisionRows",
    ):
        _validate(contract)
