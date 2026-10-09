"""descriptor の変異が requiredSet の導出結果に現れることを検査する。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import patch

import check_deriver_dependencies as derivers

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("contracts/state-transition/required_set_mutation_policy_v1.json")

InputDeriver = Callable[[Mapping[str, Any]], tuple[Any, ...]]
GameEndDeriver = Callable[[Mapping[str, Any], str, frozenset[str]], Any]


class RequiredSetMutationError(ValueError):
    """変異宣言または requiredSet の変異耐性が不正な場合を表す。"""


@dataclass(frozen=True)
class Mutant:
    """メモリ上の単一変異体と診断用の位置を保持する。"""

    operator_id: str
    collection: str
    axis_id: str
    original_value: Any | None
    value_index: int | None
    descriptor: dict[str, Any]

    @property
    def label(self) -> str:
        """軸と境界値を含む診断ラベルを返す。"""
        if self.value_index is None:
            return f"{self.operator_id}: {self.collection}/{self.axis_id}"
        return (
            f"{self.operator_id}: {self.collection}/{self.axis_id} "
            f"boundaryValues[{self.value_index}]={self.original_value!r}"
        )


def _exact_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    """閉じた object を検証する。"""
    if not isinstance(value, dict) or set(value) != expected:
        raise RequiredSetMutationError(f"{label}のキーがexact-set不一致")
    return value


def validate_policy(policy: object, descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """変異宣言の閉包と descriptor に対する対象外集合を検証する。"""
    raw = _exact_keys(
        policy,
        {
            "schemaVersion", "policyId", "descriptorPath", "requirementsPath",
            "iterationOrder", "operators", "affectedOutputsByAxisPrefix",
            "supportUpdates", "excludedDescriptorTopLevelFields",
            "excludedDerivedOutputs", "claimBoundary",
        },
        "変異宣言",
    )
    if raw["schemaVersion"] != 1 or isinstance(raw["schemaVersion"], bool):
        raise RequiredSetMutationError("schemaVersionが不正")
    if not isinstance(raw["policyId"], str) or not raw["policyId"]:
        raise RequiredSetMutationError("policyIdが不正")
    if raw["iterationOrder"] != "descriptor-array-order-then-value-index":
        raise RequiredSetMutationError("変異生成順が未対応")
    for key in ("descriptorPath", "requirementsPath"):
        value = raw[key]
        if (
            not isinstance(value, str)
            or not value
            or PurePosixPath(value).is_absolute()
            or ".." in PurePosixPath(value).parts
        ):
            raise RequiredSetMutationError(f"{key}が安全な相対パスでない")
    operators = raw["operators"]
    if not isinstance(operators, list) or not operators:
        raise RequiredSetMutationError("operatorsが空または配列でない")
    ids: set[str] = set()
    for operator in operators:
        if not isinstance(operator, dict):
            raise RequiredSetMutationError("operatorがobjectでない")
        kind = operator.get("kind")
        fields = {"operatorId", "kind", "axisCollections", "expectedMutantCount"}
        if kind == "replace-one-boundary-value":
            fields |= {
                "valueField", "replacementTemplate", "collisionDomain", "collisionResolution"
            }
        elif kind != "delete-one-axis":
            raise RequiredSetMutationError(f"未対応の変異演算子: {kind!r}")
        _exact_keys(operator, fields, "operator")
        operator_id = operator["operatorId"]
        if not isinstance(operator_id, str) or not operator_id or operator_id in ids:
            raise RequiredSetMutationError("operatorIdが空または重複")
        ids.add(operator_id)
        collections = operator["axisCollections"]
        if (
            not isinstance(collections, list)
            or not collections
            or len(set(collections)) != len(collections)
        ):
            raise RequiredSetMutationError(f"{operator_id}の対象軸集合が不正")
        if any(item not in ("stateTransitionAxes", "gameEndAxes") for item in collections):
            raise RequiredSetMutationError(f"{operator_id}の対象軸集合が未対応")
        expected_count = operator["expectedMutantCount"]
        if (
            not isinstance(expected_count, int)
            or isinstance(expected_count, bool)
            or expected_count < 1
        ):
            raise RequiredSetMutationError(f"{operator_id}の変異体総数が不正")
        if kind == "replace-one-boundary-value":
            if operator["valueField"] != "boundaryValues":
                raise RequiredSetMutationError("境界値フィールドが未対応")
            if operator["collisionDomain"] != "axis-values-and-invalid-boundary-values":
                raise RequiredSetMutationError("衝突検査範囲が未対応")
            if (
                operator["collisionResolution"]
                != "append-colon-and-smallest-nonnegative-integer-until-unique"
            ):
                raise RequiredSetMutationError("衝突回避規則が未対応")
            template = operator["replacementTemplate"]
            if (
                not isinstance(template, str)
                or "{axisId}" not in template
                or "{valueIndex}" not in template
            ):
                raise RequiredSetMutationError("境界値置換テンプレートが不正")

    exclusions = raw["excludedDescriptorTopLevelFields"]
    if not isinstance(exclusions, list) or any(
        not isinstance(item, dict)
        or set(item) != {"field", "reason"}
        or not isinstance(item["reason"], str)
        or not item["reason"]
        for item in exclusions
    ):
        raise RequiredSetMutationError("対象外フィールド宣言が不正")
    actual_exclusions = [item["field"] for item in exclusions]
    if (
        len(actual_exclusions) != len(set(actual_exclusions))
        or set(actual_exclusions)
        != set(descriptor) - {"stateTransitionAxes", "gameEndAxes"}
    ):
        raise RequiredSetMutationError("対象外top-levelフィールドがexact-set不一致")
    excluded_outputs = raw["excludedDerivedOutputs"]
    if (
        not isinstance(excluded_outputs, list)
        or len(excluded_outputs) != 1
        or excluded_outputs[0].get("output") != "requiredSet.rowRequirements"
        or not excluded_outputs[0].get("reason")
    ):
        raise RequiredSetMutationError("対象外導出結果がexact-set不一致")
    boundary = _exact_keys(
        raw["claimBoundary"],
        {"subject", "mechanicallyChecked", "notGuaranteed"},
        "claimBoundary",
    )
    if not all(
        isinstance(boundary[key], str) and boundary[key]
        for key in ("subject", "mechanicallyChecked")
    ):
        raise RequiredSetMutationError("claimBoundaryが不正")
    if (
        not isinstance(boundary["notGuaranteed"], list)
        or not boundary["notGuaranteed"]
        or len(boundary["notGuaranteed"]) != len(set(boundary["notGuaranteed"]))
    ):
        raise RequiredSetMutationError("claimBoundary.notGuaranteedが不正")
    targets = raw["affectedOutputsByAxisPrefix"]
    if not isinstance(targets, dict) or set(targets) != {"stateTransitionAxes", "gameEndAxes"}:
        raise RequiredSetMutationError("導出対象の軸集合がexact-set不一致")
    for collection, by_prefix in targets.items():
        prefixes = {axis["axisId"].split(".", 1)[0] for axis in descriptor[collection]}
        if not isinstance(by_prefix, dict) or set(by_prefix) != prefixes:
            raise RequiredSetMutationError(f"{collection}の導出対象prefixがexact-set不一致")
        for outputs in by_prefix.values():
            if (
                not isinstance(outputs, list)
                or not outputs
                or len(outputs) != len(set(outputs))
                or any(
                    output not in ("requiredSet.inputCoordinates", "gameEnd.requiredSet")
                    for output in outputs
                )
            ):
                raise RequiredSetMutationError("導出対象outputが不正")
    return raw


def _replacement(axis: Mapping[str, Any], index: int, operator: Mapping[str, Any]) -> str:
    """既存の有効・不正値と衝突しない置換値を決定する。"""
    base = operator["replacementTemplate"].format(axisId=axis["axisId"], valueIndex=index)
    occupied = {
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        for field in ("values", "boundaryValues", "invalidBoundaryValues")
        for value in axis.get(field, [])
    }
    candidate = base
    ordinal = 0
    while json.dumps(candidate, ensure_ascii=False, sort_keys=True) in occupied:
        candidate = f"{base}:{ordinal}"
        ordinal += 1
    return candidate


def generate_mutants(descriptor: dict[str, Any], operator: Mapping[str, Any]) -> Iterator[Mutant]:
    """資産に列挙された演算子・順序で単一変異体を生成する。"""
    for collection in operator["axisCollections"]:
        for axis_index, axis in enumerate(descriptor[collection]):
            axis_id = axis["axisId"]
            if operator["kind"] == "delete-one-axis":
                mutated = deepcopy(descriptor)
                del mutated[collection][axis_index]
                if collection == "stateTransitionAxes":
                    bindings = mutated["inputCoordinateCoverage"]["axisBindings"]
                    for group in bindings:
                        if axis_id in group["axisIds"]:
                            group["axisIds"].remove(axis_id)
                    bindings[:] = [group for group in bindings if group["axisIds"]]
                yield Mutant(operator["operatorId"], collection, axis_id, None, None, mutated)
                continue
            for value_index, old_value in enumerate(axis.get(operator["valueField"], [])):
                mutated = deepcopy(descriptor)
                replacement = _replacement(axis, value_index, operator)
                mutated_axis = mutated[collection][axis_index]
                mutated_axis[operator["valueField"]][value_index] = replacement
                if collection == "stateTransitionAxes":
                    for group in mutated["inputCoordinateCoverage"]["axisBindings"]:
                        if axis_id not in group["axisIds"]:
                            continue
                        for binding in group["rowBindings"]:
                            values = binding["coverageSelector"].get("values", [])
                            for index, value in enumerate(values):
                                if value == old_value:
                                    values[index] = replacement
                    for condition in mutated_axis.get("conditionalValues", []):
                        if condition["value"] == old_value:
                            condition["value"] = replacement
                yield Mutant(
                    operator["operatorId"],
                    collection,
                    axis_id,
                    old_value,
                    value_index,
                    mutated,
                )


def _output_identities(
    output: str,
    descriptor: Mapping[str, Any],
    requirements_text: str,
    clause_ids: frozenset[str],
    input_deriver: InputDeriver,
    game_end_deriver: GameEndDeriver,
) -> set[Any]:
    """既存導出器の出力を同一性集合に射影する。"""
    if output == "requiredSet.inputCoordinates":
        requirements = input_deriver(descriptor)
    else:
        requirements = game_end_deriver(descriptor, requirements_text, clause_ids).requirements
    identities = [item.identity for item in requirements]
    if len(identities) != len(set(identities)):
        raise RequiredSetMutationError(f"{output}の導出identityが重複")
    return set(identities)


def check_documents(
    policy: object,
    descriptor: dict[str, Any],
    requirements_text: str,
    clause_ids: frozenset[str],
    *,
    input_deriver: InputDeriver = derivers.derive_input_coordinate_requirements_from_descriptor,
    game_end_deriver: GameEndDeriver = derivers.derive_game_end_required_set_from_documents,
) -> dict[str, int]:
    """宣言総数と全変異体の導出差分を検査する。

    Args:
        policy: 資産側の変異宣言。
        descriptor: 原本から読み込んだ descriptor。変更しない。
        requirements_text: 要件書本文。
        clause_ids: 要件書の構造抽出済み条文 ID。
        input_deriver: 負例で置換可能な既存入力座標導出器。
        game_end_deriver: 負例で置換可能な既存終了判定導出器。

    Returns:
        演算子ごとの生成・検査件数。

    Raises:
        RequiredSetMutationError: 総数不一致、導出不能、生存変異体がある場合。
    """
    declaration = validate_policy(policy, descriptor)
    mutants_by_operator = {
        operator["operatorId"]: list(generate_mutants(descriptor, operator))
        for operator in declaration["operators"]
    }
    for operator in declaration["operators"]:
        count = len(mutants_by_operator[operator["operatorId"]])
        if count != operator["expectedMutantCount"]:
            raise RequiredSetMutationError(
                f"{operator['operatorId']}の変異体総数が不一致: "
                f"declared={operator['expectedMutantCount']}; generated={count}"
            )
    baseline = {
        output: _output_identities(
            output, descriptor, requirements_text, clause_ids, input_deriver, game_end_deriver
        )
        for output in ("requiredSet.inputCoordinates", "gameEnd.requiredSet")
    }
    survivors: list[str] = []
    for operator in declaration["operators"]:
        for mutant in mutants_by_operator[operator["operatorId"]]:
            prefix = mutant.axis_id.split(".", 1)[0]
            outputs = declaration["affectedOutputsByAxisPrefix"][mutant.collection][prefix]
            # 凍結された原本の整合検証だけを変異実験中に外す。導出処理は既存関数のまま。
            with (
                patch.object(derivers.descriptor_checker, "_validate_input_coordinate_coverage"),
                patch.object(derivers.descriptor_checker, "_validate_game_end_contract"),
            ):
                for output in outputs:
                    try:
                        actual = _output_identities(
                            output,
                            mutant.descriptor,
                            requirements_text,
                            clause_ids,
                            input_deriver,
                            game_end_deriver,
                        )
                    except Exception as error:
                        raise RequiredSetMutationError(
                            f"変異体を導出できない: {mutant.label}; {output}: {error}"
                        ) from error
                    if actual == baseline[output]:
                        survivors.append(f"{mutant.label}; deriver={output}")
    if survivors:
        raise RequiredSetMutationError("生存した変異体:\n" + "\n".join(survivors))
    return {operator_id: len(mutants) for operator_id, mutants in mutants_by_operator.items()}


def check_repository(root: Path = ROOT, policy_path: Path = POLICY_PATH) -> dict[str, int]:
    """実資産を読み、原本を変更せず全変異体を検査する。"""
    policy = json.loads((root / policy_path).read_text(encoding="utf-8"))
    descriptor_path = root / policy["descriptorPath"]
    requirements_path = root / policy["requirementsPath"]
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    requirements_text = requirements_path.read_text(encoding="utf-8")
    clause_ids = frozenset(
        f"req:{item}"
        for item in derivers.descriptor_checker.load_clause_ids_from_paths(
            root, (PurePosixPath(policy["requirementsPath"]),)
        )
    )
    return check_documents(policy, descriptor, requirements_text, clause_ids)


def main() -> int:
    """CLIから変異耐性検査を実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    args = parser.parse_args()
    try:
        counts = check_repository(policy_path=args.policy)
    except (OSError, ValueError, derivers.DeriverDependencyError) as error:
        print(f"requiredSet変異耐性: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"requiredSet変異耐性: PASS: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
