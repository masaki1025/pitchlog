"""検査集合の分離、exit 契約、FR-040 除外宣言を検査する。"""

from __future__ import annotations

import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSET_PATH = ROOT / "backend/domain/check-sets.json"
REQUIREMENTS_PATH = ROOT / "docs/requirements/requirements-pitchlog-2026-07-22.md"
THIS_FILE = Path(__file__).resolve()
EXPECTED_CHECK_SET_IDS = {
    "requirement-targets",
    "manifest-registrations",
    "production-entrypoints",
    "executed-check-layers",
}
EXPECTED_REPORT_KINDS = {
    "missing-declaration",
    "declaration-reality-mismatch",
    "indeterminate",
}
_CIRCLED_NUMBER = re.compile(r"[①-⑳]")


class ContractError(AssertionError):
    """検査集合または FR-040 の契約違反を表す。"""


@pytest.fixture(scope="module")
def check_sets() -> dict[str, Any]:
    """検査集合資産を読み込む。"""
    return json.loads(ASSET_PATH.read_text(encoding="utf-8"))


def _section_text(source_text: str, heading: str) -> str:
    """指定見出しに属する本文を取り出す。"""
    lines = source_text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError as error:
        raise ContractError(f"正本に節見出しがない: {heading}") from error
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#+)\s", lines[index])
        if match is not None and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _split_top_level(value: str, separators: list[str]) -> list[str]:
    """括弧内を除き、指定区切りで日本語の列挙を分解する。"""
    opening = {"(": ")", "（": "）"}
    closing = set(opening.values())
    stack: list[str] = []
    parts: list[str] = []
    start = 0
    index = 0
    ordered = sorted(separators, key=len, reverse=True)
    while index < len(value):
        character = value[index]
        if character in opening:
            stack.append(opening[character])
            index += 1
            continue
        if character in closing:
            if stack and character == stack[-1]:
                stack.pop()
            index += 1
            continue
        if not stack:
            separator = next(
                (item for item in ordered if value.startswith(item, index)), None
            )
            if separator is not None:
                parts.append(value[start:index])
                index += len(separator)
                start = index
                continue
        index += 1
    parts.append(value[start:])
    return [part.strip() for part in parts if part.strip()]


def _without_detail(value: str) -> str:
    """対象名から太字記号と後続する括弧内の説明を除く。"""
    plain = value.replace("**", "").strip()
    positions = [position for mark in ("（", "(") if (position := plain.find(mark)) >= 0]
    if positions:
        plain = plain[: min(positions)]
    return plain.strip(" 。")


def _alpha_targets(section: str, rule: dict[str, Any]) -> set[str]:
    """NFR-018 対象欄の α 列挙から対象名を導出する。"""
    line = next(
        line
        for line in section.splitlines()
        if line.lstrip().startswith(f"- **{rule['marker']}") and ":" in line
    )
    body = line.split(":", maxsplit=1)[1].split("。**NFR-019(a)", maxsplit=1)[0]
    values = _split_top_level(body, rule["separators"])
    return {f"alpha:{_without_detail(value)}" for value in values}


def _top_level_circled_segments(value: str) -> list[tuple[str, str]]:
    """括弧外にある丸数字と後続文を抽出する。"""
    opening = {"(": ")", "（": "）"}
    closing = set(opening.values())
    stack: list[str] = []
    markers: list[tuple[int, str]] = []
    for index, character in enumerate(value):
        if character in opening:
            stack.append(opening[character])
        elif character in closing:
            if stack and character == stack[-1]:
                stack.pop()
        elif not stack and _CIRCLED_NUMBER.fullmatch(character):
            markers.append((index, character))
    result: list[tuple[str, str]] = []
    for marker_index, (start, marker) in enumerate(markers):
        end = markers[marker_index + 1][0] if marker_index + 1 < len(markers) else len(value)
        result.append((marker, value[start + 1 : end]))
    return result


def _beta_targets(section: str, rule: dict[str, Any]) -> set[str]:
    """NFR-018 対象欄の β 丸数字列挙から対象名を導出する。"""
    line = next(
        line
        for line in section.splitlines()
        if line.lstrip().startswith(f"- **{rule['marker']}") and "①" in line
    )
    body = line[line.index("①") :].split("。**いずれも", maxsplit=1)[0]
    return {
        f"beta:{marker}:{_without_detail(value)}"
        for marker, value in _top_level_circled_segments(body)
    }


def _derive_requirement_targets(
    requirements_text: str, asset: dict[str, Any]
) -> dict[str, set[str]]:
    """資産の規則に従って NFR-018 の対象集合を独立導出する。"""
    derivation = asset["targetDerivation"]
    section = _section_text(requirements_text, derivation["section"])
    rules = {rule["id"]: rule for rule in derivation["groups"]}
    return {
        "alpha": _alpha_targets(section, rules["alpha"]),
        "beta": _beta_targets(section, rules["beta"]),
    }


def _validate_schema(instance: Any, schema: Any, path: str = "$") -> None:
    """FR-040 除外宣言 schema が使う閉じた語彙を検証する。"""
    if not isinstance(schema, dict):
        raise ContractError(f"{path}: schema が object でない")
    if "const" in schema and instance != schema["const"]:
        raise ContractError(f"{path}: const に不適合")
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(instance, dict):
        raise ContractError(f"{path}: object でない")
    if expected_type == "string" and not isinstance(instance, str):
        raise ContractError(f"{path}: string でない")
    if isinstance(instance, str) and len(instance) < schema.get("minLength", 0):
        raise ContractError(f"{path}: minLength に不適合")
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(instance)
        if missing:
            raise ContractError(f"{path}: 必須キー不足 {sorted(missing)!r}")
        unknown = set(instance) - set(properties)
        if schema.get("additionalProperties") is False and unknown:
            raise ContractError(f"{path}: 未知キー {sorted(unknown)!r}")
        for key, value in instance.items():
            if key in properties:
                _validate_schema(value, properties[key], f"{path}.{key}")


def _valid_exclusion() -> dict[str, object]:
    """FR-040 非採用時の妥当な除外宣言を返す。"""
    return {
        "requirement": "FR-040",
        "adoption": "not-adopted",
        "authority": "FR-040 優先度 Should",
        "reason": "Should を採用しない決定により状態補正を契約から外す",
        "scope": {
            "contractKind": "target-calculation-vector",
            "manifestField": "vectors[]",
            "excludedEventType": "state-correction",
            "excludedCaseSelector": "fr040-related",
        },
        "decider": "合成 fixture の決定者",
    }


def _assert_fr040_consistency(asset: dict[str, Any], state: dict[str, Any]) -> None:
    """FR-040 の採否、除外宣言、case 集合の遷移を検査する。"""
    if set(state) != {
        "adopted",
        "exclusion",
        "requiredCaseTags",
        "actualCaseTags",
    }:
        raise ContractError("FR-040 状態のキー集合が不正")
    adopted = state["adopted"]
    if not isinstance(adopted, bool):
        raise ContractError("adopted が boolean でない")
    exclusion = state["exclusion"]
    required_cases = set(state["requiredCaseTags"])
    actual_cases = set(state["actualCaseTags"])
    if adopted:
        if exclusion is not None:
            raise ContractError("採用後に除外宣言が残っている")
        if required_cases - actual_cases:
            raise ContractError("採用後に補正関連 case が復帰していない")
        return
    if exclusion is None:
        raise ContractError("FR-040 非採用の除外が無宣言である")
    _validate_schema(exclusion, asset["fr040ExclusionDeclarationSchema"])


def _load_runtime_input(
    asset_path: Path, input_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Subprocess 用の資産と判定入力を読み、形を検査する。"""
    try:
        asset = json.loads(asset_path.read_text(encoding="utf-8"))
        value = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"判定入力を読めない: {error}") from error
    if not isinstance(asset, dict) or not isinstance(value, dict):
        raise ContractError("資産と判定入力は object でなければならない")
    if set(value) != {"resolutionStatus", "sealedSet", "findings"}:
        raise ContractError("判定入力のキー集合が不正")
    if value["resolutionStatus"] not in {"resolved", "indeterminate"}:
        raise ContractError("resolutionStatus が不正")
    sealed_set = value["sealedSet"]
    if not isinstance(sealed_set, dict) or set(sealed_set) != {
        "unresolvedFindingIds"
    }:
        raise ContractError("sealedSet のキー集合が不正")
    unresolved_ids = sealed_set["unresolvedFindingIds"]
    if not isinstance(unresolved_ids, list) or not all(
        isinstance(item, str) for item in unresolved_ids
    ):
        raise ContractError("unresolvedFindingIds が文字列 array でない")
    report_kinds = {
        row["id"] for row in asset["reportVocabulary"]["values"]
    }
    if not isinstance(value["findings"], list):
        raise ContractError("findings が array でない")
    for finding in value["findings"]:
        if not isinstance(finding, dict) or set(finding) != {"findingId", "reportKind"}:
            raise ContractError("finding のキー集合が不正")
        if not isinstance(finding["findingId"], str):
            raise ContractError("findingId が文字列でない")
        if finding["reportKind"] not in report_kinds:
            raise ContractError("reportKind が未宣言である")
    return asset, value


def _evaluate_exemption(value: dict[str, Any]) -> bool:
    """封印 ID の所属だけから全 finding が免除対象かを返す。"""
    sealed_ids = set(value["sealedSet"]["unresolvedFindingIds"])
    finding_ids = {finding["findingId"] for finding in value["findings"]}
    return not bool(finding_ids - sealed_ids)


def _contract_exit(asset: dict[str, Any], value: dict[str, Any]) -> int:
    """資産に宣言された条件に一致する exit コードを返す。"""
    status = value["resolutionStatus"]
    unsealed_state = "empty" if _evaluate_exemption(value) else "nonempty"
    matches: list[int] = []
    for row in asset["exitContract"]:
        condition = row["condition"]
        if condition.get("resolutionStatus") != status:
            continue
        expected_unsealed = condition.get("unsealedFindingIds")
        if expected_unsealed is not None and expected_unsealed != unsealed_state:
            continue
        if not isinstance(row["code"], int) or isinstance(row["code"], bool):
            raise ContractError("exit code が整数でない")
        matches.append(row["code"])
    if len(matches) != 1:
        raise ContractError("exit 条件が一意に決まらない")
    return matches[0]


def _command_line() -> int:
    """テスト用の subprocess 境界で exit 契約を実行する。"""
    if len(sys.argv) != 4 or sys.argv[1] != "--evaluate":
        return 2
    try:
        asset, value = _load_runtime_input(Path(sys.argv[2]), Path(sys.argv[3]))
        return _contract_exit(asset, value)
    except (ContractError, KeyError, TypeError):
        return 2


def _write_json(path: Path, value: object) -> None:
    """合成 fixture を JSON として書き込む。"""
    path.write_text(
        f"{json.dumps(value, ensure_ascii=False, indent=2)}\n", encoding="utf-8"
    )


def _run_exit_contract(
    tmp_path: Path,
    asset: dict[str, Any],
    value: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    """資産の写しと合成入力で exit 判定を別プロセス実行する。"""
    asset_path = tmp_path / "check-sets.json"
    input_path = tmp_path / "input.json"
    _write_json(asset_path, asset)
    _write_json(input_path, value)
    return subprocess.run(
        [sys.executable, str(THIS_FILE), "--evaluate", str(asset_path), str(input_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_four_check_sets_are_separated(check_sets: dict[str, Any]) -> None:
    rows = check_sets["checkSets"]
    identifiers = [row["id"] for row in rows]
    by_id = {row["id"]: row for row in rows}
    assert len(identifiers) == 4
    assert len(identifiers) == len(set(identifiers))
    assert set(identifiers) == EXPECTED_CHECK_SET_IDS
    assert by_id["requirement-targets"]["source"] == "targetDerivation"
    assert by_id["manifest-registrations"]["source"] == (
        "backend/domain/manifest.json"
    )
    assert set(by_id["production-entrypoints"]["collectors"]) == {
        "backend/src/pitchlog/domaincheck/collect_entrypoints_fe.py",
        "backend/src/pitchlog/domaincheck/collect_entrypoints_be.py",
    }
    assert by_id["executed-check-layers"]["layers"] == [
        "vector",
        "property",
        "mutation",
    ]


def test_requirement_targets_are_derived_from_nfr018_target_field(
    check_sets: dict[str, Any],
) -> None:
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    groups = _derive_requirement_targets(requirements, check_sets)
    targets = groups["alpha"] | groups["beta"]

    assert len(groups["alpha"]) == 5
    assert len(groups["beta"]) == 8
    assert len(targets) == len(groups["alpha"]) + len(groups["beta"])
    assert 13 not in _all_integer_values(check_sets)


def _all_integer_values(value: object) -> set[int]:
    """JSON 木の boolean 以外の全整数値を集める。"""
    values: set[int] = set()
    if isinstance(value, dict):
        for child in value.values():
            values.update(_all_integer_values(child))
    elif isinstance(value, list):
        for child in value:
            values.update(_all_integer_values(child))
    elif isinstance(value, int) and not isinstance(value, bool):
        values.add(value)
    return values


def test_rewriting_requirement_target_field_changes_derived_set(
    check_sets: dict[str, Any],
) -> None:
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    section_heading = check_sets["targetDerivation"]["section"]
    section = _section_text(requirements, section_heading)
    changed_section = section.replace(
        "**: 状況判定・", "**: 状況判定・合成対象・", 1
    )
    before = _derive_requirement_targets(section, check_sets)["alpha"]
    after = _derive_requirement_targets(changed_section, check_sets)["alpha"]

    assert after - before == {"alpha:合成対象"}
    assert len(after) == len(before) + 1


def test_reporting_vocabulary_is_absent_from_exemption_predicate(
    check_sets: dict[str, Any],
) -> None:
    vocabulary = check_sets["reportVocabulary"]
    report_tokens = {
        vocabulary["field"],
        *(row["id"] for row in vocabulary["values"]),
        *(row["label"] for row in vocabulary["values"]),
    }
    predicate = json.dumps(
        check_sets["exemptionDecision"]["predicate"], ensure_ascii=False
    )
    assert set(check_sets["exemptionDecision"]["dependsOnlyOn"]) == {
        "findingId",
        "sealedSet.unresolvedFindingIds",
    }
    assert all(token not in predicate for token in report_tokens)

    tree = ast.parse(THIS_FILE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_evaluate_exemption"
    )
    literals = {
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert literals.isdisjoint(report_tokens)


def test_exit_contract_has_exactly_three_disjoint_codes(
    check_sets: dict[str, Any],
) -> None:
    rows = {row["code"]: row["condition"] for row in check_sets["exitContract"]}
    assert set(rows) == {0, 1, 2}
    assert rows[0] == {
        "resolutionStatus": "resolved",
        "unsealedFindingIds": "empty",
    }
    assert rows[1] == {
        "resolutionStatus": "resolved",
        "unsealedFindingIds": "nonempty",
    }
    assert rows[2] == {"resolutionStatus": "indeterminate"}


def test_sealed_only_findings_exit_zero(
    tmp_path: Path, check_sets: dict[str, Any]
) -> None:
    value = {
        "resolutionStatus": "resolved",
        "sealedSet": {
            "unresolvedFindingIds": ["finding-a", "finding-b"]
        },
        "findings": [
            {"findingId": "finding-a", "reportKind": "missing-declaration"},
            {
                "findingId": "finding-b",
                "reportKind": "declaration-reality-mismatch",
            },
        ],
    }
    process = _run_exit_contract(tmp_path, check_sets, value)
    assert process.returncode == 0


def test_unsealed_finding_exits_one(
    tmp_path: Path, check_sets: dict[str, Any]
) -> None:
    value = {
        "resolutionStatus": "resolved",
        "sealedSet": {"unresolvedFindingIds": ["finding-a"]},
        "findings": [
            {"findingId": "finding-a", "reportKind": "missing-declaration"},
            {"findingId": "finding-new", "reportKind": "missing-declaration"},
        ],
    }
    process = _run_exit_contract(tmp_path, check_sets, value)
    assert process.returncode == 1


def test_indeterminate_input_exits_two(
    tmp_path: Path, check_sets: dict[str, Any]
) -> None:
    value = {
        "resolutionStatus": "indeterminate",
        "sealedSet": {"unresolvedFindingIds": ["finding-a"]},
        "findings": [
            {"findingId": "finding-a", "reportKind": "indeterminate"},
        ],
    }
    process = _run_exit_contract(tmp_path, check_sets, value)
    assert process.returncode == 2


def test_unresolvable_sealed_set_exits_two(
    tmp_path: Path, check_sets: dict[str, Any]
) -> None:
    value = {
        "resolutionStatus": "resolved",
        "sealedSet": None,
        "findings": [
            {"findingId": "finding-a", "reportKind": "missing-declaration"}
        ],
    }
    process = _run_exit_contract(tmp_path, check_sets, value)
    assert process.returncode == 2


def test_unreadable_asset_exits_two(
    tmp_path: Path, check_sets: dict[str, Any]
) -> None:
    asset_path = tmp_path / "check-sets.json"
    input_path = tmp_path / "input.json"
    asset_path.write_text("{broken", encoding="utf-8")
    _write_json(
        input_path,
        {
            "resolutionStatus": "resolved",
            "sealedSet": {"unresolvedFindingIds": []},
            "findings": [],
        },
    )
    process = subprocess.run(
        [sys.executable, str(THIS_FILE), "--evaluate", str(asset_path), str(input_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2


def test_fr040_exclusion_schema_has_closed_required_fields(
    check_sets: dict[str, Any],
) -> None:
    schema = check_sets["fr040ExclusionDeclarationSchema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "requirement",
        "adoption",
        "authority",
        "reason",
        "scope",
        "decider",
    }
    assert schema["properties"]["requirement"]["const"] == "FR-040"
    assert schema["properties"]["scope"]["additionalProperties"] is False


def test_valid_fr040_nonadoption_and_adoption_transition_are_accepted(
    check_sets: dict[str, Any],
) -> None:
    required = ["fr040-correction", "fr040-undo"]
    not_adopted: dict[str, Any] = {
        "adopted": False,
        "exclusion": _valid_exclusion(),
        "requiredCaseTags": required,
        "actualCaseTags": [],
    }
    adopted: dict[str, Any] = copy.deepcopy(not_adopted)
    adopted.update(
        {"adopted": True, "exclusion": None, "actualCaseTags": required}
    )
    _assert_fr040_consistency(check_sets, not_adopted)
    _assert_fr040_consistency(check_sets, adopted)


def test_undeclared_fr040_exclusion_is_rejected(
    check_sets: dict[str, Any],
) -> None:
    state = {
        "adopted": False,
        "exclusion": None,
        "requiredCaseTags": ["fr040-correction"],
        "actualCaseTags": [],
    }
    with pytest.raises(ContractError, match="無宣言"):
        _assert_fr040_consistency(check_sets, state)


def test_invalid_fr040_exclusion_is_rejected(
    check_sets: dict[str, Any],
) -> None:
    exclusion = _valid_exclusion()
    exclusion["requirement"] = "FR-041"
    state = {
        "adopted": False,
        "exclusion": exclusion,
        "requiredCaseTags": ["fr040-correction"],
        "actualCaseTags": [],
    }
    with pytest.raises(ContractError, match="const"):
        _assert_fr040_consistency(check_sets, state)


def test_fr040_cases_must_return_after_adoption(
    check_sets: dict[str, Any],
) -> None:
    state = {
        "adopted": True,
        "exclusion": None,
        "requiredCaseTags": ["fr040-correction", "fr040-undo"],
        "actualCaseTags": ["fr040-correction"],
    }
    with pytest.raises(ContractError, match="復帰"):
        _assert_fr040_consistency(check_sets, state)


def test_trigger_seven_materials_cover_coexistence_and_conflicts(
    check_sets: dict[str, Any],
) -> None:
    materials = check_sets["trigger7AssessmentMaterials"]
    assert materials["judge"] == "山田正輝"
    assert set(materials["coexistenceExample"]) == {
        "fr040",
        "contractClassification",
        "incrementalMerge",
        "result",
    }
    conflict_ids = {row["id"] for row in materials["conflictCandidates"]}
    assert conflict_ids == {
        "adopted-with-stale-exclusion",
        "classification-based-exemption",
    }


def test_authority_wording_exists_without_line_references(
    check_sets: dict[str, Any],
) -> None:
    for entry in check_sets["authorityCatalog"]:
        source = (ROOT / entry["source"]).read_text(encoding="utf-8")
        assert entry["verbatim"] in _section_text(source, entry["section"])
    serialized = json.dumps(check_sets, ensure_ascii=False)
    assert re.search(r":\d+", serialized) is None


if __name__ == "__main__":
    raise SystemExit(_command_line())
