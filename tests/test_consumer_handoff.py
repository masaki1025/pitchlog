"""付録Eの段階2向けbindingの構造と参照先を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/appendix_e_consumer_handoff_v1.json"
)
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/appendix_e_consumer_handoff_schema_v1.json"
)


def _load_module(name: str, path: Path) -> Any:
    """既存のschema検証器をsys.pathの変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module(
    "state_transition_freeze", REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
)
schema_checker = _load_module(
    "check_input_axes_descriptor",
    REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py",
)


class HandoffReferenceError(ValueError):
    """引き渡し宣言の参照が実資産へ解決できないことを表す。"""


def _load_object(path: Path) -> dict[str, Any]:
    """JSON objectを読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _schema() -> dict[str, Any]:
    """引き渡し契約のschemaを返す。"""
    return _load_object(SCHEMA_PATH)


def _handoff() -> dict[str, Any]:
    """引き渡し契約を返す。"""
    return _load_object(HANDOFF_PATH)


def _resolve_pointer(document: object, pointer: str) -> object:
    """JSON Pointerをdocumentから解決し、不達なら失敗する。"""
    if not pointer.startswith("/"):
        raise HandoffReferenceError(f"JSON Pointerでない: {pointer!r}")
    current = document
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdecimal():
            index = int(token)
            if index >= len(current):
                raise HandoffReferenceError(f"JSON Pointerが範囲外: {pointer!r}")
            current = current[index]
        else:
            raise HandoffReferenceError(f"JSON Pointerが不達: {pointer!r}")
    return current


def _contract_schema_path(contract_path: Path) -> Path:
    """既存の契約/schemaの対になるファイル名を返す。"""
    name = contract_path.name
    schema_name = name.replace("_contract_v", "_contract_schema_v", 1)
    if schema_name == name:
        raise HandoffReferenceError(f"契約schema名を導出できない: {name}")
    return contract_path.with_name(schema_name)


def _binding_pointers(binding: dict[str, Any]) -> list[str]:
    """必須のcase側JSON Pointerを宣言から取り出す。"""
    mapping = binding["caseFieldMapping"]
    return [
        mapping["id"]["contractPointer"],
        mapping["input"]["raw"]["contractPointer"],
        mapping["input"]["normalized"]["contractPointer"],
        mapping["expected"]["contractPointer"],
    ]


def _validate_execution_paths(binding: dict[str, Any], schema: dict[str, Any]) -> None:
    """軽量schema検証器が未対応のallOf/containsも宣言どおり照合する。"""
    path_schema = schema["$defs"]["executionPaths"]
    paths = binding["executionPaths"]
    allowed_runners = set(schema["$defs"]["executionPath"]["properties"]["runner"]["enum"])
    conditions = path_schema["allOf"]
    declared_runners = [
        condition["contains"]["properties"]["runner"]["const"]
        for condition in conditions
    ]
    if len(declared_runners) != len(allowed_runners) or set(declared_runners) != allowed_runners:
        raise HandoffReferenceError("executionPathsのexact-set宣言が不完全")
    for condition in conditions:
        matches = 0
        for path in paths:
            try:
                schema_checker._validate_instance(
                    path, condition["contains"], schema, "$.executionPaths[]"
                )
            except schema_checker.DescriptorCheckError:
                continue
            matches += 1
        if not condition["minContains"] <= matches <= condition["maxContains"]:
            raise HandoffReferenceError("executionPathsのrunner exact-setが不一致")


def _validate_handoff(handoff: dict[str, Any]) -> dict[str, int]:
    """schemaと全caseの参照を照合する。"""
    schema = _schema()
    schema_checker._validate_instance(handoff, schema, schema, "$")
    declared_ids = handoff["calculationIds"]
    binding_ids = [item["calculationId"] for item in handoff["consumerBindings"]]
    if len(binding_ids) != len(set(binding_ids)) or set(binding_ids) != set(
        declared_ids
    ):
        raise HandoffReferenceError("calculationIdsとconsumerBindingsが不一致")

    counts = {}
    for binding in handoff["consumerBindings"]:
        _validate_execution_paths(binding, schema)
        contract_path = REPOSITORY_ROOT / binding["contractPath"]
        contract = _load_object(contract_path)
        if (
            binding["calculationId"] != contract["calculation"]
            or binding["vectorId"] != contract["calculation"]
            or binding["version"] != contract["version"]
            or binding["schemaVersion"] != contract["schemaVersion"]
        ):
            raise HandoffReferenceError("計算IDまたは契約版が実資産と不一致")
        contract_schema = _load_object(_contract_schema_path(contract_path))
        case_schema = _resolve_pointer(
            contract_schema, binding["caseSchemaRef"].removeprefix("#")
        )
        if not isinstance(case_schema, dict):
            raise HandoffReferenceError("caseSchemaRefがschema objectを指さない")

        cases = contract["cases"]
        pointers = _binding_pointers(binding)
        for index, case in enumerate(cases):
            schema_checker._validate_instance(
                case, case_schema, contract_schema, f"cases[{index}]"
            )
            for pointer in pointers:
                _resolve_pointer(case, pointer)

        tags_mapping = binding["caseFieldMapping"]["tags"]
        if tags_mapping["availability"] == "absent" and any(
            "tags" in case for case in cases
        ):
            raise HandoffReferenceError("tagsの不在宣言が実caseと不一致")
        counts[binding["calculationId"]] = len(cases)
    return counts


def test_repository_handoff_schema_and_all_case_pointers_resolve() -> None:
    """2契約の全caseとcase schemaへの参照が解決できる。"""
    assert _validate_handoff(_handoff()) == {
        "state-transition": 96,
        "game-end": 170,
    }


def test_game_end_binding_uses_actual_normalization_points() -> None:
    """終了判定の3点を素直に写し、期待値の名称差を宣言する。"""
    binding = next(
        item for item in _handoff()["consumerBindings"]
        if item["calculationId"] == "game-end"
    )
    assert binding["caseSchemaRef"] == "#/$defs/normalizedCase"
    mapping = binding["caseFieldMapping"]
    assert mapping["input"]["raw"]["contractPointer"] == "/raw"
    assert mapping["input"]["normalized"]["contractPointer"] == "/normalized"
    assert mapping["expected"]["contractPointer"] == "/decision"
    assert "/expected" in _schema()["$defs"]["caseFieldMapping"]["$comment"]
    assert "/decision" in _schema()["$defs"]["caseFieldMapping"]["$comment"]
    boundary = _handoff()["claimBoundary"]
    assert "状況判定caseの/expected" in boundary["guaranteed"]
    assert "終了判定caseの/decision" in boundary["guaranteed"]
    assert "/inputCoordinateは正規形" in boundary["guaranteed"]
    assert "/normalizedと一致する" in boundary["guaranteed"]
    assert all("/inputCoordinate" not in item for item in boundary["notGuaranteed"])


@pytest.mark.parametrize("field", _schema()["$defs"]["consumerBinding"]["required"])
def test_missing_required_binding_field_fails_schema(field: str) -> None:
    """各必須フィールドの欠落はschema検証で拒否される。"""
    handoff = copy.deepcopy(_handoff())
    del handoff["consumerBindings"][0][field]
    with pytest.raises(schema_checker.DescriptorCheckError, match="必須キー不足"):
        _validate_handoff(handoff)


def test_unresolved_case_pointer_fails_closed() -> None:
    """構文上は有効でも実caseへ不達のJSON Pointerを拒否する。"""
    handoff = copy.deepcopy(_handoff())
    handoff["consumerBindings"][0]["caseFieldMapping"]["input"]["raw"][
        "contractPointer"
    ] = "/missing"
    with pytest.raises(HandoffReferenceError, match="JSON Pointerが不達"):
        _validate_handoff(handoff)


def test_non_pointer_mapping_fails_schema() -> None:
    """フィールド名だけを置いた写像はJSON Pointerとして受理しない。"""
    handoff = copy.deepcopy(_handoff())
    handoff["consumerBindings"][0]["caseFieldMapping"]["id"][
        "contractPointer"
    ] = "caseId"
    with pytest.raises(schema_checker.DescriptorCheckError, match="pattern不一致"):
        _validate_handoff(handoff)


def test_single_execution_path_fails_schema() -> None:
    """片方のrunner経路を欠くbindingを拒否する。"""
    handoff = copy.deepcopy(_handoff())
    handoff["consumerBindings"][0]["executionPaths"].pop()
    with pytest.raises(schema_checker.DescriptorCheckError, match="配列要素数が下限未満"):
        _validate_handoff(handoff)


def test_duplicate_runner_fails_exact_set() -> None:
    """2経路あっても同一runnerの重複は拒否する。"""
    handoff = copy.deepcopy(_handoff())
    handoff["consumerBindings"][0]["executionPaths"][1]["runner"] = "pytest"
    with pytest.raises(HandoffReferenceError, match="runner exact-set"):
        _validate_handoff(handoff)


def test_runner_revision_cannot_claim_resolved() -> None:
    """段階1でrunnerのcommit OIDを確定済みと宣言できない。"""
    handoff = copy.deepcopy(_handoff())
    handoff["consumerBindings"][0]["executionPaths"][0]["runnerRevision"] = "a" * 40
    with pytest.raises(schema_checker.DescriptorCheckError, match="const不一致"):
        _validate_handoff(handoff)
