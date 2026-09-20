"""BOOT-REPORT の未解消要素一覧を出力し、移行状態の緑を検証する。"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.boot.phase2 import Phase2Decision
from pitchlog.domaincheck.cli import (
    CheckerExecutionError,
    CheckerViolation,
    exact_set_difference,
    read_json,
    validate_asset,
)

BOOT_SEAL_ASSET = Path("backend/domain/boot-seal.json")
BOOT_REPORT_SCHEMA = Path("backend/domain/boot-report.schema.json")


@dataclass(frozen=True, slots=True)
class SealedElement:
    """レポートへ引き継ぐ封印要素の識別情報。

    Attributes:
        identifier: 改名で変わらない封印要素 ID。
        canonical_key: 代数的型が与えた正規キー。
        constructor: 封印要素の構成子。
        target_id: 対象計算に属する場合の安定 ID。
    """

    identifier: str
    canonical_key: str
    constructor: str
    target_id: str | None


def _object(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckerExecutionError(f"{label}が JSON object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise CheckerExecutionError(f"{label}が JSON array でない")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CheckerExecutionError(f"{label}が空でない文字列でない")
    return value


def _sealed_elements(sealed_asset: object) -> tuple[SealedElement, ...]:
    """封印資産から順序付きの識別情報を読む。"""
    asset = _object(sealed_asset, "boot-seal")
    raw_elements = _array(asset.get("elements"), "boot-seal.elements")
    elements: list[SealedElement] = []
    for index, raw_element in enumerate(raw_elements):
        element = _object(raw_element, f"boot-seal.elements[{index}]")
        identifier = _string(element.get("id"), f"elements[{index}].id")
        canonical_key = _string(
            element.get("canonicalKey"),
            f"elements[{index}].canonicalKey",
        )
        constructor = _string(
            element.get("constructor"),
            f"elements[{index}].constructor",
        )
        arguments = _object(
            element.get("arguments"),
            f"elements[{index}].arguments",
        )
        target = arguments.get("target")
        target_id = target if isinstance(target, str) and target else None
        elements.append(
            SealedElement(identifier, canonical_key, constructor, target_id)
        )
    identifiers = [element.identifier for element in elements]
    canonical_keys = [element.canonical_key for element in elements]
    if not elements:
        raise CheckerExecutionError("封印集合が空である")
    if len(identifiers) != len(set(identifiers)):
        raise CheckerViolation("BOOT-SEAL の要素 ID が重複している")
    if len(canonical_keys) != len(set(canonical_keys)):
        raise CheckerViolation("BOOT-SEAL の正規キーが重複している")
    return tuple(elements)


def _resolved_ids(values: Collection[str]) -> frozenset[str]:
    """解消済み要素 ID を検査して集合へ正規化する。"""
    if not all(isinstance(value, str) and value for value in values):
        raise CheckerExecutionError(
            "解消済み要素 ID は空でない文字列でなければならない"
        )
    return frozenset(values)


def _transition_meaning() -> dict[str, object]:
    """BOOT-NO-CLAIM と BOOT-CI-MEANING の固定文言を返す。"""
    return {
        "noClaimAuthority": "NFR-018 (e) BOOT-NO-CLAIM",
        "nfr018b2Satisfied": False,
        "nfr019aPassed": False,
        "ciMeaningAuthority": "設計書 10.1 BOOT-CI-MEANING",
        "ciGreenMeaning": "transition-requirements-only",
        "statement": (
            "移行状態では NFR-018 (b)② の充足および NFR-019(a) の合格を"
            "主張しない。CI 全ジョブ green は移行状態の要求を満たしていること"
            "のみを意味する。"
        ),
    }


def build_boot_report(
    sealed_asset: object,
    resolved_element_ids: Collection[str],
) -> dict[str, object]:
    """封印集合と解消済み集合の差から未解消一覧を一度だけ導出する。

    Args:
        sealed_asset: `backend/domain/boot-seal.json` の内容。
        resolved_element_ids: 生の検査で解消成立を確認済みの要素 ID。

    Returns:
        一覧から件数を算出した BOOT-REPORT。

    Raises:
        CheckerExecutionError: 入力の形を解釈できない場合。
        CheckerViolation: 封印集合にない ID を解消済みとした場合。
    """
    elements = _sealed_elements(sealed_asset)
    resolved = _resolved_ids(resolved_element_ids)
    sealed_ids = frozenset(element.identifier for element in elements)
    difference = exact_set_difference(sealed_ids, resolved)
    if difference.unexpected:
        raise CheckerViolation(
            f"封印集合にない要素を解消済みにできない={sorted(difference.unexpected)!r}"
        )
    unresolved = [
        {
            "elementId": element.identifier,
            "canonicalKey": element.canonical_key,
        }
        for element in elements
        if element.identifier not in resolved
    ]
    return {
        "schemaVersion": 1,
        "reportType": "boot-unresolved-elements",
        "sealedSet": BOOT_SEAL_ASSET.as_posix(),
        "unresolvedCount": len(unresolved),
        "unresolvedElements": unresolved,
        "transitionMeaning": _transition_meaning(),
    }


def resolved_element_ids_from_phase2(
    sealed_asset: object,
    decision: Phase2Decision,
) -> frozenset[str]:
    """段階 2 で 4 点が揃った対象の宣言要素だけを解消候補へ写す。

    宣言だけの変更では `resolution_target_ids` が空なので、解消要素も生じない。
    この関数は生の検査結果を再実行せず、ステップ 18 の判定結果だけを変換する。

    Args:
        sealed_asset: 封印集合の資産。
        decision: ステップ 18 の対象単位の判定結果。

    Returns:
        対象に属する D-11 由来の封印要素 ID。
    """
    targets = decision.resolution_target_ids
    return frozenset(
        element.identifier
        for element in _sealed_elements(sealed_asset)
        if element.constructor == "declaration_absence" and element.target_id in targets
    )


def _schema_output_path(schema: object) -> Path:
    """Schema が固定した出力先を安全な相対パスとして返す。"""
    mapping = _object(schema, "boot-report schema")
    raw_path = _string(mapping.get("x-outputPath"), "schema.x-outputPath")
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise CheckerExecutionError("schema.x-outputPathは安全な相対パスでない")
    return path


def _write_report(path: Path, report: object) -> None:
    """人間にも逐行確認できる整形済み JSON を書く。"""
    try:
        serialized = json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{serialized}\n", encoding="utf-8")
    except (OSError, TypeError, ValueError) as error:
        message = f"BOOT-REPORT を書けない: {path}: {error}"
        raise CheckerExecutionError(message) from error


def assert_report_matches(
    sealed_asset: object,
    resolved_element_ids: Collection[str],
    report: object,
    schema: object,
) -> None:
    """Schema と封印集合差の双方にレポートが一致することを要求する。"""
    validate_asset(report, schema)
    expected = build_boot_report(sealed_asset, resolved_element_ids)
    if report != expected:
        raise CheckerViolation("BOOT-REPORT が封印集合と解消済み集合の差に一致しない")


def emit_boot_report(
    root: Path,
    resolved_element_ids: Collection[str],
) -> Path:
    """固定ファイル名へ未解消要素レポートを実際に出力する。

    Args:
        root: リポジトリルート。
        resolved_element_ids: 生の検査で解消成立を確認済みの要素 ID。

    Returns:
        出力したレポートの絶対パス。
    """
    resolved_root = root.resolve()
    schema = read_json(resolved_root / BOOT_REPORT_SCHEMA)
    sealed_asset = read_json(resolved_root / BOOT_SEAL_ASSET)
    report = build_boot_report(sealed_asset, resolved_element_ids)
    validate_asset(report, schema)
    destination = resolved_root / _schema_output_path(schema)
    _write_report(destination, report)
    return destination


def accept_transition_green(
    root: Path,
    resolved_element_ids: Collection[str],
) -> dict[str, object]:
    """出力済みレポートを含む移行状態の緑だけを受理する。

    Args:
        root: リポジトリルート。
        resolved_element_ids: 生の検査で解消成立を確認済みの要素 ID。

    Returns:
        検査済みの機械可読レポート。

    Raises:
        CheckerViolation: 出力が無い、または集合差と一致しない場合。
    """
    resolved_root = root.resolve()
    schema = read_json(resolved_root / BOOT_REPORT_SCHEMA)
    report_path = resolved_root / _schema_output_path(schema)
    if not report_path.is_file():
        raise CheckerViolation(
            "NFR-018 (e) BOOT-REPORT: 出力のない緑は本規定の充足とみなさない"
        )
    report = read_json(report_path)
    sealed_asset = read_json(resolved_root / BOOT_SEAL_ASSET)
    assert_report_matches(sealed_asset, resolved_element_ids, report, schema)
    return _object(report, "boot-report")
