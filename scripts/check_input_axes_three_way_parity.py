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
except ModuleNotFoundError:  # pragma: no cover - scriptを直接実行する経路
    import check_input_axes_descriptor as descriptor_checker  # type: ignore[no-redef]

REQUIREMENTS_PATH = PurePosixPath(
    "docs/requirements/requirements-pitchlog-2026-07-22.md"
)
ADR_PATH = PurePosixPath("docs/adr/ADR-003-domain-calc-method.md")
DESCRIPTOR_PATH = descriptor_checker.DESCRIPTOR_PATH
SCHEMA_PATH = descriptor_checker.SCHEMA_PATH

BRANCH_FAMILIES = (
    "COLD",
    "DRAW",
    "XMARK",
    "OUT3",
    "ADV",
    "INT",
    "SO",
    "RBI",
    "XC",
)
BRANCH_ID_PATTERN = re.compile(
    r"`(?P<branch_id>(?:"
    + "|".join(BRANCH_FAMILIES)
    + r")-\d{2})`"
)
ADR_DECISION_HEADING_PATTERN = re.compile(r"^###\s+(?P<decision_id>D-\d+):")
CODE_COLLECTION_PATTERN = re.compile(r"`(?P<collection>[A-Za-z][A-Za-z0-9]+\[\])`")
STAGE2_CONSTRAINT_ID_PATTERN = re.compile(
    r"`stage2-constraint:(?P<constraint>[a-z][a-z0-9-]+)`"
)
CONTRACT_FILENAME_PATTERN = re.compile(
    r"^[a-z]+(?:_[a-z]+)*_v[1-9][0-9]*\.json$"
)

D11_COLLECTION_KEYS = {
    "stateTransitionAxes[]": "stateTransitionAxes",
    "gameEndAxes[]": "gameEndAxes",
    "nonCoverageFields[]": "nonCoverageFields",
    "projectionRules[]": "projectionRules",
}
D11_REQUIRED_COLLECTIONS = frozenset(
    {"gameEndAxes[]", "nonCoverageFields[]", "projectionRules[]"}
)
D12_REQUIRED_CODE_LITERALS = frozenset(
    {
        "contracts/<領域>/",
        "state-transition/",
        "<対象>_v<N>.json",
        "input_axes_descriptor_v<N>.json",
        "gap_register_v<N>.json",
    }
)

BRANCH_COVERAGE_EXCLUSIONS: dict[str, str] = {
    "DRAW-04": (
        "DRAW-01〜03を通過した有効設定の残余分岐であり、判定入力は既存のgameEnd軸が持つ"
    ),
    **{
        f"ADV-{number:02d}": (
            "runnerDefaultAdvanceの期待出力分岐であり、判定入力はstate.runnersと結果IDが持つ"
        )
        for number in range(1, 5)
    },
    **{
        f"SO-{number:02d}": (
            "語彙IDに対応する状態効果の出力分岐であり、本除外はSO-03内のアウト成否coverageを保証しない"
        )
        for number in range(1, 6)
    },
    **{
        f"RBI-{number:02d}": (
            "打点の期待出力分岐であり、RBI-02〜05以外は追加の観測入力軸を要求しない"
        )
        for number in (1, 6, 7, 8, 9)
    },
    **{
        f"XC-{number:02d}": (
            "規範行の列間交差制約であり、単独の入力軸ではない"
        )
        for number in range(1, 13)
    },
    "XC-13": (
        "成績計上フラグの導出原則であり、23件の具体的な導出表と観測入力は"
        "2026-09-26の2回目のPO射程縮小により段階2で確定する"
    ),
}


class ThreeWayParityError(Exception):
    """3点突合を決定できない、または不一致の場合を表す。"""


@dataclass(frozen=True)
class ParityReport:
    """検査済みの機械可読ID集合を返す。"""

    source_clause_ids: frozenset[str]
    descriptor_clause_ids: frozenset[str]
    descriptor_supporting_clause_ids: frozenset[str]
    requirement_branch_ids: frozenset[str]
    covered_branch_ids: frozenset[str]
    excluded_branch_ids: frozenset[str]
    d11_collection_ids: frozenset[str]
    d11_stage2_constraint_classes: frozenset[str]


def _read_text(path: Path, label: str) -> str:
    """UTF-8テキストを読み込む。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ThreeWayParityError(f"{label}をUTF-8で読めない: {path}: {error}") from error


def extract_requirement_branch_ids(text: str) -> frozenset[str]:
    """要件書のコード表記から閉じた分岐IDを決定的に抽出する。"""
    return frozenset(
        match.group("branch_id") for match in BRANCH_ID_PATTERN.finditer(text)
    )


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


def extract_d11_collection_ids(adr_text: str) -> frozenset[str]:
    """D-11がコード表記で名指しするdescriptorコレクションIDを抽出する。"""
    section = extract_adr_decision_section(adr_text, "D-11")
    return frozenset(
        match.group("collection")
        for match in CODE_COLLECTION_PATTERN.finditer(section)
        if match.group("collection") in D11_COLLECTION_KEYS
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
    branch_ids: frozenset[str], descriptor_clause_ids: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """軸を支える分岐と明示的除外の双方をexact-setで検証する。"""
    excluded_ids = frozenset(BRANCH_COVERAGE_EXCLUSIONS)
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
    adr_text: str, descriptor: Mapping[str, Any]
) -> frozenset[str]:
    """D-11が名指しする構造IDとdescriptorの実体を突合する。"""
    collection_ids = extract_d11_collection_ids(adr_text)
    if collection_ids != D11_REQUIRED_COLLECTIONS:
        raise ThreeWayParityError(
            "D-11のdescriptorコレクションIDがexact-set不一致: "
            f"expected={sorted(D11_REQUIRED_COLLECTIONS)!r}; "
            f"actual={sorted(collection_ids)!r}"
        )
    for collection_id in sorted(collection_ids):
        key = D11_COLLECTION_KEYS[collection_id]
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


def _validate_d12_location(adr_text: str, descriptor: Mapping[str, Any]) -> None:
    """D-12の機械可読な領域・命名IDとdescriptorのパスを突合する。"""
    section = extract_adr_decision_section(adr_text, "D-12")
    code_literals = extract_code_literals(section)
    missing_literals = sorted(D12_REQUIRED_CODE_LITERALS - code_literals)
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

    branch_ids = extract_requirement_branch_ids(requirements_text)
    if not branch_ids:
        raise ThreeWayParityError("要件書から分岐IDを抽出できない")
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
        branch_ids, descriptor_supporting_clause_ids
    )
    d11_collection_ids = _validate_d11_structure(adr_text, descriptor)
    d11_stage2_constraint_classes = _validate_d11_stage2_constraints(
        adr_text, descriptor
    )
    _validate_d12_location(adr_text, descriptor)

    return ParityReport(
        source_clause_ids=source_clause_ids,
        descriptor_clause_ids=descriptor_clause_ids,
        descriptor_supporting_clause_ids=descriptor_supporting_clause_ids,
        requirement_branch_ids=branch_ids,
        covered_branch_ids=covered_ids,
        excluded_branch_ids=excluded_ids,
        d11_collection_ids=d11_collection_ids,
        d11_stage2_constraint_classes=d11_stage2_constraint_classes,
    )


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
        validate_three_way_parity(args.root.resolve())
    except ThreeWayParityError as error:
        print(f"input-axes-three-way-parity: ERROR: {error}", file=sys.stderr)
        return 1
    print("input-axes-three-way-parity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
