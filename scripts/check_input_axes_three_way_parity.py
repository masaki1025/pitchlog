"""要件書・ADR-003・入力軸descriptorの機械可読IDを突合する。"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from scripts import check_input_axes_descriptor as descriptor_checker
    from scripts import state_transition_freeze as freeze_checker
except ModuleNotFoundError:  # pragma: no cover - scriptを直接実行する経路
    import check_input_axes_descriptor as descriptor_checker  # type: ignore[no-redef]
    import state_transition_freeze as freeze_checker  # type: ignore[no-redef]

REQUIREMENTS_PATH = PurePosixPath(
    "docs/requirements/requirements-pitchlog-2026-07-22.md"
)
ADR_PATH = PurePosixPath("docs/adr/ADR-003-domain-calc-method.md")
DESCRIPTOR_PATH = descriptor_checker.DESCRIPTOR_PATH
SCHEMA_PATH = descriptor_checker.SCHEMA_PATH

BRANCH_MENTION_PATTERN = re.compile(
    r"`(?P<branch_id>(?:COLD|DRAW|XMARK|OUT3|ADV|INT|SO|RBI|XC)-\d{2})`"
)
ADR_DECISION_HEADING_PATTERN = re.compile(r"^###\s+(?P<decision_id>D-\d+):")
REQUIREMENT_CLAUSE_HEADING_PATTERN = re.compile(
    r"^###\s+(?P<clause_id>[A-Z]-\d+[a-z]?)(?=[:\s])"
)
CODE_COLLECTION_PATTERN = re.compile(r"`(?P<collection>[A-Za-z][A-Za-z0-9]+\[\])`")
ADR_CONSTRAINT_MARKER_PATTERN = re.compile(
    r"`constraint:(?P<constraint_id>XC-\d{2})`"
)
REQUIREMENT_CONSTRAINT_OWNER_PATTERN = re.compile(
    r"`constraint-owner:(?P<constraint_id>XC-\d{2}):"
    r"adr:(?P<decision_id>D-\d+):(?P<layer>[A-Za-z][A-Za-z0-9]+\[\])`"
)
REQUIREMENT_CONSTRAINT_EXCLUSION_PATTERN = re.compile(
    r"`constraint-exclusion:(?P<constraint_id>XC-\d{2}):"
    r"req:(?P<clause_id>[A-Z]-\d+[a-z]?)`"
)
STAGE2_CONSTRAINT_ID_PATTERN = re.compile(
    r"`stage2-constraint:(?P<constraint>[a-z][a-z0-9-]+)`"
)
D12_FREEZE_BASELINE_ID_PATTERN = re.compile(
    r"freeze-baseline-(?:field|series|scope):[A-Za-z][A-Za-z0-9.-]*"
)
CONTRACT_FILENAME_PATTERN = re.compile(
    r"^[a-z]+(?:_[a-z]+)*_v[1-9][0-9]*\.json$"
)



class ThreeWayParityError(Exception):
    """3点突合を決定できない、または不一致の場合を表す。"""


@dataclass(frozen=True)
class ParityCriteria:
    """資産側宣言から読み込んだ3点突合の凍結基準。"""

    requirement_branch_ids: frozenset[str]
    non_definition_branch_mentions: frozenset[str]
    principle_markers: Mapping[str, str]
    adr_d8_constraint_ids: frozenset[str]
    requirement_constraint_owners: Mapping[str, tuple[str, str]]
    requirement_constraint_exclusions: Mapping[str, str]
    branch_coverage_exclusions: Mapping[str, str]
    d11_collection_bindings: Mapping[str, str]
    d11_required_collections: frozenset[str]
    d12_required_code_literals: frozenset[str]


def _frozen_string_set(value: object, label: str) -> frozenset[str]:
    """凍結基準の重複のない文字列配列を集合へ変換する。"""
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ThreeWayParityError(f"凍結基準{label}が空でない文字列配列でない")
    result = frozenset(value)
    if len(result) != len(value):
        raise ThreeWayParityError(f"凍結基準{label}に重複がある")
    return result


def _frozen_string_map(value: object, label: str) -> dict[str, str]:
    """凍結基準の文字列対応表を返す。"""
    if not isinstance(value, dict) or not value or not all(
        isinstance(key, str)
        and key
        and isinstance(item, str)
        and item
        for key, item in value.items()
    ):
        raise ThreeWayParityError(f"凍結基準{label}が文字列対応表でない")
    return dict(value)


def load_parity_criteria(descriptor: Mapping[str, Any]) -> ParityCriteria:
    """descriptor内の資産側宣言から3点突合基準を読み込む。"""
    try:
        declaration = freeze_checker.validate_declaration(
            descriptor.get(freeze_checker.FREEZE_FIELD)
        )
        raw = freeze_checker.checker_criteria(declaration, __file__)
    except freeze_checker.FreezeBaselineError as error:
        raise ThreeWayParityError(f"凍結基準宣言を検証できない: {error}") from error

    owners_value = raw.get("requirementConstraintOwners")
    if not isinstance(owners_value, dict) or not owners_value:
        raise ThreeWayParityError("凍結基準requirementConstraintOwnersがobjectでない")
    owners: dict[str, tuple[str, str]] = {}
    for constraint_id, owner in owners_value.items():
        if (
            not isinstance(constraint_id, str)
            or not isinstance(owner, dict)
            or set(owner) != {"decisionId", "layer"}
            or not all(isinstance(item, str) and item for item in owner.values())
        ):
            raise ThreeWayParityError("凍結基準の制約帰属の型が不正")
        owners[constraint_id] = (owner["decisionId"], owner["layer"])

    return ParityCriteria(
        requirement_branch_ids=_frozen_string_set(
            raw.get("requirementBranchIds"), ".requirementBranchIds"
        ),
        non_definition_branch_mentions=_frozen_string_set(
            raw.get("nonDefinitionBranchMentions"),
            ".nonDefinitionBranchMentions",
        ),
        principle_markers=_frozen_string_map(
            raw.get("principleMarkers"), ".principleMarkers"
        ),
        adr_d8_constraint_ids=_frozen_string_set(
            raw.get("adrD8ConstraintIds"), ".adrD8ConstraintIds"
        ),
        requirement_constraint_owners=owners,
        requirement_constraint_exclusions=_frozen_string_map(
            raw.get("requirementConstraintExclusions"),
            ".requirementConstraintExclusions",
        ),
        branch_coverage_exclusions=_frozen_string_map(
            raw.get("branchCoverageExclusions"),
            ".branchCoverageExclusions",
        ),
        d11_collection_bindings=_frozen_string_map(
            raw.get("d11CollectionBindings"), ".d11CollectionBindings"
        ),
        d11_required_collections=_frozen_string_set(
            raw.get("d11RequiredCollections"), ".d11RequiredCollections"
        ),
        d12_required_code_literals=_frozen_string_set(
            raw.get("d12RequiredCodeLiterals"), ".d12RequiredCodeLiterals"
        ),
    )


@dataclass(frozen=True)
class ParityReport:
    """検査済みの機械可読ID集合を返す。"""

    source_clause_ids: frozenset[str]
    descriptor_clause_ids: frozenset[str]
    descriptor_supporting_clause_ids: frozenset[str]
    requirement_branch_ids: frozenset[str]
    covered_branch_ids: frozenset[str]
    excluded_branch_ids: frozenset[str]
    non_definition_branch_mentions: frozenset[str]
    adr_d8_constraint_ids: frozenset[str]
    requirement_constraint_owners: Mapping[str, tuple[str, str]]
    requirement_constraint_exclusions: Mapping[str, str]
    d11_collection_ids: frozenset[str]
    d11_stage2_constraint_classes: frozenset[str]


def _read_text(path: Path, label: str) -> str:
    """UTF-8テキストを読み込む。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ThreeWayParityError(f"{label}をUTF-8で読めない: {path}: {error}") from error


def extract_requirement_branch_rows(text: str) -> dict[str, str]:
    """要件書の規範表の先頭セルから分岐定義行を決定的に抽出する。"""
    rows: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = descriptor_checker.STABLE_TABLE_CLAUSE_PATTERN.match(line)
        if match is None:
            continue
        branch_id = match.group("clause_id")
        if branch_id in rows:
            raise ThreeWayParityError(
                f"要件書の規範表で分岐IDが重複している: {branch_id} "
                f"(2件目={line_number}行)"
            )
        rows[branch_id] = line
    return rows


def extract_requirement_branch_ids(text: str) -> frozenset[str]:
    """要件書の規範表から閉じた分岐IDを抽出する。"""
    return frozenset(extract_requirement_branch_rows(text))


def extract_requirement_branch_mentions(text: str) -> frozenset[str]:
    """移行差分の監査専用に要件書中の全分岐ID言及を抽出する。"""
    return frozenset(
        match.group("branch_id") for match in BRANCH_MENTION_PATTERN.finditer(text)
    )


def _validate_requirement_branch_definitions(
    text: str, criteria: ParityCriteria
) -> frozenset[str]:
    """規範表の分岐exact-setとXC-13の機械可読な原則IDを検証する。"""
    rows = extract_requirement_branch_rows(text)
    actual_ids = frozenset(rows)
    if actual_ids != criteria.requirement_branch_ids:
        missing = sorted(criteria.requirement_branch_ids - actual_ids)
        unexpected = sorted(actual_ids - criteria.requirement_branch_ids)
        raise ThreeWayParityError(
            "要件書の規範表にある分岐IDがexact-set不一致: "
            f"missing={missing!r}; unexpected={unexpected!r}"
        )

    for branch_id, marker in criteria.principle_markers.items():
        row = rows.get(branch_id)
        if row is None or marker not in extract_code_literals(row):
            raise ThreeWayParityError(
                f"{branch_id}規範行に凍結した原則IDが無い: {marker}"
            )
    return actual_ids


def extract_requirement_clause_section(text: str, clause_id: str) -> str:
    """要件書の第3階層の条文IDから当該節だけを抽出する。"""
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        heading = REQUIREMENT_CLAUSE_HEADING_PATTERN.match(line)
        if heading is None:
            continue
        if start is not None:
            return "\n".join(lines[start:index])
        if heading.group("clause_id") == clause_id:
            start = index
    if start is not None:
        return "\n".join(lines[start:])
    raise ThreeWayParityError(f"要件書の条文IDが実在しない: {clause_id}")


def extract_adr_decision_section(text: str, decision_id: str) -> str:
    """ADRの決定見出しIDから当該節だけを抽出する。"""
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        heading = ADR_DECISION_HEADING_PATTERN.match(line)
        if heading is None:
            continue
        if start is not None:
            return "\n".join(lines[start:index])
        if heading.group("decision_id") == decision_id:
            start = index
    if start is not None:
        return "\n".join(lines[start:])
    raise ThreeWayParityError(f"ADRの決定IDが実在しない: {decision_id}")


def _validate_xc09_definition_and_ownership(
    requirements_text: str,
    adr_text: str,
    criteria: ParityCriteria,
) -> tuple[frozenset[str], dict[str, tuple[str, str]], dict[str, str]]:
    """D-8固有制約とE-1からの外部帰属をexact-setで突合する。"""
    owner_decision_ids = {
        decision_id
        for decision_id, _layer in criteria.requirement_constraint_owners.values()
    }
    if len(owner_decision_ids) != 1:
        raise ThreeWayParityError("外部制約の帰属先decisionを一意に決定できない")
    d8_section = extract_adr_decision_section(adr_text, owner_decision_ids.pop())
    adr_matches = list(ADR_CONSTRAINT_MARKER_PATTERN.finditer(d8_section))
    adr_constraint_ids = frozenset(
        match.group("constraint_id") for match in adr_matches
    )
    if len(adr_matches) != len(adr_constraint_ids):
        raise ThreeWayParityError("D-8の制約定義IDが重複している")
    if adr_constraint_ids != criteria.adr_d8_constraint_ids:
        raise ThreeWayParityError(
            "D-8固有の制約定義IDがexact-set不一致: "
            f"expected={sorted(criteria.adr_d8_constraint_ids)!r}; "
            f"actual={sorted(adr_constraint_ids)!r}"
        )

    exclusion_clause_ids = set(criteria.requirement_constraint_exclusions.values())
    if len(exclusion_clause_ids) != 1:
        raise ThreeWayParityError("外部制約の除外元clauseを一意に決定できない")
    e1_section = extract_requirement_clause_section(
        requirements_text, exclusion_clause_ids.pop()
    )
    owner_matches = list(REQUIREMENT_CONSTRAINT_OWNER_PATTERN.finditer(e1_section))
    owners: dict[str, tuple[str, str]] = {}
    for match in owner_matches:
        constraint_id = match.group("constraint_id")
        if constraint_id in owners:
            raise ThreeWayParityError(
                f"E-1の外部制約帰属IDが重複している: {constraint_id}"
            )
        owners[constraint_id] = (
            match.group("decision_id"),
            match.group("layer"),
        )
    if owners != criteria.requirement_constraint_owners:
        raise ThreeWayParityError(
            "E-1の外部制約帰属がexact-set不一致: "
            f"expected={criteria.requirement_constraint_owners!r}; actual={owners!r}"
        )
    if frozenset(owners) != adr_constraint_ids:
        raise ThreeWayParityError(
            "E-1から帰属させた制約IDとD-8の定義IDが一致しない"
        )

    exclusion_matches = list(
        REQUIREMENT_CONSTRAINT_EXCLUSION_PATTERN.finditer(e1_section)
    )
    exclusions: dict[str, str] = {}
    for match in exclusion_matches:
        constraint_id = match.group("constraint_id")
        if constraint_id in exclusions:
            raise ThreeWayParityError(
                f"E-1の外部制約除外IDが重複している: {constraint_id}"
            )
        exclusions[constraint_id] = match.group("clause_id")
    if exclusions != criteria.requirement_constraint_exclusions:
        raise ThreeWayParityError(
            "E-1の外部制約除外がexact-set不一致: "
            f"expected={criteria.requirement_constraint_exclusions!r}; "
            f"actual={exclusions!r}"
        )
    if frozenset(exclusions) != adr_constraint_ids:
        raise ThreeWayParityError(
            "E-1から除外した制約IDとD-8の定義IDが一致しない"
        )
    return adr_constraint_ids, owners, exclusions


def extract_d11_collection_ids(
    adr_text: str, collection_bindings: Mapping[str, str]
) -> frozenset[str]:
    """D-11がコード表記で名指しするdescriptorコレクションIDを抽出する。"""
    section = extract_adr_decision_section(adr_text, "D-11")
    return frozenset(
        match.group("collection")
        for match in CODE_COLLECTION_PATTERN.finditer(section)
        if match.group("collection") in collection_bindings
    )


def extract_d11_stage2_constraint_classes(adr_text: str) -> frozenset[str]:
    """D-11の機械可読IDから段階2へ委任する制約クラスを抽出する。"""
    section = extract_adr_decision_section(adr_text, "D-11")
    return frozenset(
        match.group("constraint")
        for match in STAGE2_CONSTRAINT_ID_PATTERN.finditer(section)
    )


def extract_code_literals(section: str) -> frozenset[str]:
    """Markdownのコード表記を文字列IDとして抽出する。"""
    return frozenset(re.findall(r"`([^`\n]+)`", section))


def extract_d12_freeze_baseline_ids(section: str) -> frozenset[str]:
    """D-12のコード表記から凍結基準宣言の機械可読IDだけを抽出する。"""
    return frozenset(
        literal
        for literal in extract_code_literals(section)
        if D12_FREEZE_BASELINE_ID_PATTERN.fullmatch(literal) is not None
    )


def collect_descriptor_clause_ids(value: object) -> frozenset[str]:
    """descriptor内の由来条文IDキーだけを再帰的に収集する。"""
    collected: set[str] = set()

    def walk(item: object) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "sourceClauseId" and isinstance(child, str):
                    collected.add(child)
                elif key == "supportingClauseIds" and isinstance(child, list):
                    collected.update(value for value in child if isinstance(value, str))
                else:
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return frozenset(collected)


def collect_descriptor_supporting_clause_ids(value: object) -> frozenset[str]:
    """descriptor内のsupportingClauseIdsだけを再帰的に収集する。"""
    collected: set[str] = set()

    def walk(item: object) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "supportingClauseIds" and isinstance(child, list):
                    collected.update(value for value in child if isinstance(value, str))
                else:
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return frozenset(collected)


def _load_descriptor_assets(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """descriptorとschemaをobjectとして読む。"""
    descriptor_value = descriptor_checker.load_json(root / DESCRIPTOR_PATH, "descriptor")
    schema_value = descriptor_checker.load_json(root / SCHEMA_PATH, "descriptor schema")
    if not isinstance(descriptor_value, dict) or not isinstance(schema_value, dict):
        raise ThreeWayParityError("descriptorとschemaはJSON objectでなければならない")
    return descriptor_value, schema_value


def _validate_source_clause_parity(
    descriptor: Mapping[str, Any], source_clause_ids: frozenset[str]
) -> frozenset[str]:
    """descriptorから参照する全条文IDの実在を突合する。"""
    cited_ids = collect_descriptor_clause_ids(descriptor)
    missing = sorted(cited_ids - source_clause_ids)
    if missing:
        raise ThreeWayParityError(f"由来条文IDが正本に実在しない: {missing!r}")
    return cited_ids


def _validate_branch_coverage(
    branch_ids: frozenset[str],
    descriptor_clause_ids: frozenset[str],
    criteria: ParityCriteria,
) -> tuple[frozenset[str], frozenset[str]]:
    """軸を支える分岐と明示的除外の双方をexact-setで検証する。"""
    excluded_ids = frozenset(criteria.branch_coverage_exclusions)
    stale_exclusions = sorted(excluded_ids - branch_ids)
    if stale_exclusions:
        raise ThreeWayParityError(
            f"要件書に実在しない分岐IDを被覆対象外としている: {stale_exclusions!r}"
        )

    required_ids = branch_ids - excluded_ids
    missing = sorted(
        branch_id
        for branch_id in required_ids
        if f"req:{branch_id}" not in descriptor_clause_ids
    )
    if missing:
        raise ThreeWayParityError(
            f"descriptorの軸から参照されない必須分岐IDがある: {missing!r}"
        )
    return frozenset(required_ids), excluded_ids


def _validate_d11_structure(
    adr_text: str,
    descriptor: Mapping[str, Any],
    criteria: ParityCriteria,
) -> frozenset[str]:
    """D-11が名指しする構造IDとdescriptorの実体を突合する。"""
    collection_ids = extract_d11_collection_ids(
        adr_text, criteria.d11_collection_bindings
    )
    if collection_ids != criteria.d11_required_collections:
        raise ThreeWayParityError(
            "D-11のdescriptorコレクションIDがexact-set不一致: "
            f"expected={sorted(criteria.d11_required_collections)!r}; "
            f"actual={sorted(collection_ids)!r}"
        )
    for collection_id in sorted(collection_ids):
        key = criteria.d11_collection_bindings[collection_id]
        if not isinstance(descriptor.get(key), list):
            raise ThreeWayParityError(
                f"D-11が要求するコレクションがdescriptorに無い: {collection_id}"
            )
    return collection_ids


def _validate_d11_stage2_constraints(
    adr_text: str, descriptor: Mapping[str, Any]
) -> frozenset[str]:
    """D-11とdescriptorの段階2委任制約クラスをexact-setで突合する。"""
    adr_classes = extract_d11_stage2_constraint_classes(adr_text)
    if not adr_classes:
        raise ThreeWayParityError(
            "D-11から段階2委任制約クラスの機械可読IDを抽出できない"
        )
    declaration = descriptor.get("stage2ExternalConstraints")
    if not isinstance(declaration, dict):
        raise ThreeWayParityError("descriptorにstage2ExternalConstraintsが無い")
    descriptor_classes_value = declaration.get("constraintClasses")
    if not isinstance(descriptor_classes_value, list) or not all(
        isinstance(item, str) for item in descriptor_classes_value
    ):
        raise ThreeWayParityError(
            "descriptorのstage2ExternalConstraints.constraintClassesが文字列配列でない"
        )
    descriptor_classes = frozenset(descriptor_classes_value)
    if descriptor_classes != adr_classes:
        raise ThreeWayParityError(
            "D-11とdescriptorの段階2委任制約クラスがexact-set不一致: "
            f"adr={sorted(adr_classes)!r}; descriptor={sorted(descriptor_classes)!r}"
        )
    return adr_classes


def _validate_d12_location(
    adr_text: str,
    descriptor: Mapping[str, Any],
    criteria: ParityCriteria,
) -> None:
    """D-12の機械可読な領域・命名IDとdescriptorのパスを突合する。"""
    section = extract_adr_decision_section(adr_text, "D-12")
    code_literals = extract_code_literals(section)
    declared_freeze_ids = frozenset(
        literal
        for literal in criteria.d12_required_code_literals
        if D12_FREEZE_BASELINE_ID_PATTERN.fullmatch(literal) is not None
    )
    actual_freeze_ids = extract_d12_freeze_baseline_ids(section)
    if not declared_freeze_ids or actual_freeze_ids != declared_freeze_ids:
        raise ThreeWayParityError(
            "D-12とdescriptorのfreezeBaseline宣言IDがexact-set不一致: "
            f"adr={sorted(actual_freeze_ids)!r}; "
            f"descriptor={sorted(declared_freeze_ids)!r}"
        )

    missing_literals = sorted(criteria.d12_required_code_literals - code_literals)
    if missing_literals:
        raise ThreeWayParityError(
            f"D-12の配置・命名IDが不足している: {missing_literals!r}"
        )

    parts = DESCRIPTOR_PATH.parts
    if len(parts) != 3 or parts[:2] != ("contracts", "state-transition"):
        raise ThreeWayParityError(
            f"descriptorがcontracts/<領域>/の1階層にない: {DESCRIPTOR_PATH}"
        )
    if CONTRACT_FILENAME_PATTERN.fullmatch(DESCRIPTOR_PATH.name) is None:
        raise ThreeWayParityError(
            f"descriptorのファイル名が<対象>_v<N>.jsonに適合しない: {DESCRIPTOR_PATH.name}"
        )
    if descriptor.get("version") != DESCRIPTOR_PATH.stem:
        raise ThreeWayParityError(
            "descriptorのversionがファイル名と一致しない: "
            f"{descriptor.get('version')!r} != {DESCRIPTOR_PATH.stem!r}"
        )


def validate_three_way_parity(root: Path) -> ParityReport:
    """要件書・ADR-003・descriptorの機械可読IDを突合する。"""
    requirements_text = _read_text(root / REQUIREMENTS_PATH, "要件書")
    adr_text = _read_text(root / ADR_PATH, "ADR-003")
    descriptor, schema = _load_descriptor_assets(root)
    criteria = load_parity_criteria(descriptor)

    branch_ids = _validate_requirement_branch_definitions(
        requirements_text, criteria
    )
    non_definition_branch_mentions = (
        extract_requirement_branch_mentions(requirements_text) - branch_ids
    )
    if non_definition_branch_mentions != criteria.non_definition_branch_mentions:
        raise ThreeWayParityError(
            "要件書の全文言及集合と規範表定義集合の差がexact-set不一致: "
            f"expected={sorted(criteria.non_definition_branch_mentions)!r}; "
            f"actual={sorted(non_definition_branch_mentions)!r}"
        )
    (
        adr_d8_constraint_ids,
        requirement_constraint_owners,
        requirement_constraint_exclusions,
    ) = (
        _validate_xc09_definition_and_ownership(
            requirements_text, adr_text, criteria
        )
    )
    source_clause_ids = frozenset(
        set(descriptor_checker.load_source_clause_ids(root))
        | {f"req:{branch_id}" for branch_id in branch_ids}
    )
    descriptor_clause_ids = _validate_source_clause_parity(
        descriptor, source_clause_ids
    )
    try:
        descriptor_checker.validate_descriptor_document(
            descriptor, schema, source_clause_ids
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise ThreeWayParityError(f"descriptorの自己検査に失敗した: {error}") from error

    descriptor_supporting_clause_ids = collect_descriptor_supporting_clause_ids(
        descriptor
    )
    covered_ids, excluded_ids = _validate_branch_coverage(
        branch_ids, descriptor_supporting_clause_ids, criteria
    )
    d11_collection_ids = _validate_d11_structure(
        adr_text, descriptor, criteria
    )
    d11_stage2_constraint_classes = _validate_d11_stage2_constraints(
        adr_text, descriptor
    )
    _validate_d12_location(adr_text, descriptor, criteria)

    return ParityReport(
        source_clause_ids=source_clause_ids,
        descriptor_clause_ids=descriptor_clause_ids,
        descriptor_supporting_clause_ids=descriptor_supporting_clause_ids,
        requirement_branch_ids=branch_ids,
        covered_branch_ids=covered_ids,
        excluded_branch_ids=excluded_ids,
        non_definition_branch_mentions=non_definition_branch_mentions,
        adr_d8_constraint_ids=adr_d8_constraint_ids,
        requirement_constraint_owners=requirement_constraint_owners,
        requirement_constraint_exclusions=requirement_constraint_exclusions,
        d11_collection_ids=d11_collection_ids,
        d11_stage2_constraint_classes=d11_stage2_constraint_classes,
    )


def check_repository(root: Path) -> ParityReport:
    """3点突合に加え、PR比較元からの受理履歴が追記専用であることを検証する。"""
    report = validate_three_way_parity(root)
    descriptor, _ = _load_descriptor_assets(root)
    declaration = descriptor.get(freeze_checker.FREEZE_FIELD)
    if not isinstance(declaration, dict):
        raise ThreeWayParityError("descriptorから凍結基準宣言を取得できない")
    try:
        freeze_checker.validate_repository_history(
            root, DESCRIPTOR_PATH, declaration
        )
    except freeze_checker.FreezeBaselineError as error:
        raise ThreeWayParityError(f"凍結基準受理履歴が不正: {error}") from error
    return report


def _build_parser() -> argparse.ArgumentParser:
    """CLI引数を定義する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="リポジトリルート",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """3点突合を実行する。"""
    args = _build_parser().parse_args(argv)
    try:
        check_repository(args.root.resolve())
    except ThreeWayParityError as error:
        print(f"input-axes-three-way-parity: ERROR: {error}", file=sys.stderr)
        return 1
    print("input-axes-three-way-parity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
