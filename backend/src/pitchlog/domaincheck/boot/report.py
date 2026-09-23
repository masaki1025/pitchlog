"""BOOT-REPORT の未解消要素一覧を出力し、移行状態の緑を検証する。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.boot import phase2, stall
from pitchlog.domaincheck.boot.phase2 import Phase2Decision
from pitchlog.domaincheck.cli import (
    CheckerExecutionError,
    CheckerViolation,
    canonical_hash,
    exact_set_difference,
    read_json,
    validate_asset,
)
from pitchlog.domaincheck.seal import _run_git

BOOT_SEAL_ASSET = Path("backend/domain/boot-seal.json")
BOOT_REPORT_SCHEMA = Path("backend/domain/boot-report.schema.json")
MANIFEST_ASSET = Path("backend/domain/manifest.json")
_SYNTHETIC_COMMIT_OID = "0" * 40


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


@dataclass(slots=True)
class InputAssetCollector:
    """実行中に読んだ JSON 資産を path と内容 digest へ収集する。"""

    root: Path
    _records: dict[str, str] = field(default_factory=dict)

    def read_json(self, path: Path) -> object:
        """JSON を読み、実際に読んだ相対 path と canonical digest を記録する。"""
        resolved_root = self.root.resolve()
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(resolved_root).as_posix()
        except ValueError as error:
            raise CheckerExecutionError(f"入力資産がリポジトリ外: {path}") from error
        value = read_json(resolved)
        self._records[relative] = canonical_hash(value)
        return value

    def records(self) -> tuple[dict[str, str], ...]:
        """読取順に依存しない入力資産レコードを返す。"""
        if not self._records:
            raise CheckerExecutionError("BOOT-REPORT の入力資産を 1 件も読んでいない")
        return tuple(
            {"path": path, "digest": digest}
            for path, digest in sorted(self._records.items())
        )


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


def _head_commit_oid(root: Path) -> str:
    """現在木を指す完全な commit OID を Git から実測する。"""
    result = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    oid = result.stdout.strip()
    if (
        result.returncode != 0
        or len(oid) != 40
        or any(character not in "0123456789abcdef" for character in oid)
    ):
        raise CheckerExecutionError("BOOT-REPORT の HEAD commit OID を実測できない")
    return oid


def _head_or_synthetic_oid(root: Path) -> str:
    """合成入力 API だけは Git 履歴のない単体 fixture を許す。"""
    result = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if result.returncode != 0:
        return _SYNTHETIC_COMMIT_OID
    oid = result.stdout.strip()
    if len(oid) != 40 or any(character not in "0123456789abcdef" for character in oid):
        raise CheckerExecutionError("合成 BOOT-REPORT の commit OID が不正")
    return oid


def _resolution_evidence(
    resolved_element_ids: Collection[str],
    *,
    source: str,
    manifest_present: bool,
    phase2_status: str,
    resolution_target_ids: Collection[str] = (),
) -> dict[str, object]:
    """解消済み集合を得た判定経路を digest 入力として固定する。"""
    return {
        "source": source,
        "manifestPath": MANIFEST_ASSET.as_posix(),
        "manifestPresent": manifest_present,
        "phase2Status": phase2_status,
        "resolutionTargetIds": sorted(resolution_target_ids),
        "resolvedElementIds": sorted(resolved_element_ids),
    }


def measure_resolved_element_ids(
    root: Path,
    sealed_asset: object,
    commit_oid: str,
    *,
    input_collector: InputAssetCollector,
) -> tuple[frozenset[str], dict[str, object]]:
    """実在資産をステップ18の判定経路へ渡して解消済み集合を実測する。

    現時点では製品マニフェストが未作成なので、実在確認から空の意味
    スナップショットを作り、段階2判定器が 0 件と測る。マニフェストが
    存在する段階で収集器が未接続なら、空へ倒さず判定不能にする。

    Args:
        root: リポジトリルート。
        sealed_asset: 検査済みの封印集合。
        commit_oid: 実測対象の HEAD commit OID。
        input_collector: 判定経路が読む全 JSON 資産の収集器。

    Returns:
        解消済み要素 ID と、その導出を再計算できる入力記録。

    Raises:
        CheckerExecutionError: 実在するマニフェストを意味証跡へ変換できない場合。
    """
    manifest_path = root / MANIFEST_ASSET
    if manifest_path.exists():
        raise CheckerExecutionError(
            "製品マニフェストは実在するが BOOT 解消判定の意味証跡を収集できない"
        )
    state = stall.activate(
        stall.defined_state(len(_sealed_elements(sealed_asset))),
        commit_oid,
    )
    empty = phase2.SemanticSnapshot.empty()
    decision = phase2.evaluate_phase2(
        root,
        state,
        empty,
        empty,
        read_asset=input_collector.read_json,
    )
    resolved = resolved_element_ids_from_phase2(sealed_asset, decision)
    evidence = _resolution_evidence(
        resolved,
        source="phase2.evaluate_phase2",
        manifest_present=False,
        phase2_status=decision.status.value,
        resolution_target_ids=decision.resolution_target_ids,
    )
    return resolved, evidence


def _provenance(
    sealed_asset: object,
    commit_oid: str,
    resolution_evidence: object,
    input_files: Sequence[dict[str, str]],
) -> dict[str, object]:
    """HEAD と全入力を canonical digest へ束縛する provenance を返す。"""
    files = list(input_files)
    return {
        "commitOid": commit_oid,
        "inputDigest": canonical_hash(
            {
                "inputFiles": files,
                "resolutionEvidence": resolution_evidence,
            }
        ),
        "inputFiles": files,
        "sealedSetDigest": canonical_hash(sealed_asset),
        "resolutionEvidenceDigest": canonical_hash(resolution_evidence),
    }


def build_boot_report(
    sealed_asset: object,
    resolved_element_ids: Collection[str],
    *,
    commit_oid: str = _SYNTHETIC_COMMIT_OID,
    resolution_evidence: object | None = None,
    input_files: Sequence[dict[str, str]] | None = None,
) -> dict[str, object]:
    """封印集合と解消済み集合の差から未解消一覧を一度だけ導出する。

    Args:
        sealed_asset: `backend/domain/boot-seal.json` の内容。
        resolved_element_ids: 生の検査で解消成立を確認済みの要素 ID。
        commit_oid: レポートを生成した完全な commit OID。
        resolution_evidence: 解消済み集合を導いた機械可読な入力記録。
        input_files: 実行中に読んだ全 JSON 資産の path と digest。

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
    evidence = (
        _resolution_evidence(
            resolved,
            source="explicit-test-input",
            manifest_present=False,
            phase2_status="synthetic",
        )
        if resolution_evidence is None
        else resolution_evidence
    )
    files = (
        (
            {
                "path": BOOT_SEAL_ASSET.as_posix(),
                "digest": canonical_hash(sealed_asset),
            },
        )
        if input_files is None
        else tuple(input_files)
    )
    return {
        "schemaVersion": 2,
        "reportType": "boot-unresolved-elements",
        "sealedSet": BOOT_SEAL_ASSET.as_posix(),
        "provenance": _provenance(
            sealed_asset,
            commit_oid,
            evidence,
            files,
        ),
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
    *,
    commit_oid: str = _SYNTHETIC_COMMIT_OID,
    resolution_evidence: object | None = None,
    input_files: Sequence[dict[str, str]] | None = None,
) -> None:
    """Schema と封印集合差の双方にレポートが一致することを要求する。"""
    validate_asset(report, schema)
    expected = build_boot_report(
        sealed_asset,
        resolved_element_ids,
        commit_oid=commit_oid,
        resolution_evidence=resolution_evidence,
        input_files=input_files,
    )
    if report != expected:
        raise CheckerViolation("BOOT-REPORT が封印集合と解消済み集合の差に一致しない")


def emit_boot_report(
    root: Path,
    resolved_element_ids: Collection[str] | None = None,
) -> Path:
    """固定ファイル名へ未解消要素レポートを実際に出力する。

    Args:
        root: リポジトリルート。
        resolved_element_ids: 生の検査で解消成立を確認済みの要素 ID。

    Returns:
        出力したレポートの絶対パス。
    """
    resolved_root = root.resolve()
    collector = InputAssetCollector(resolved_root)
    schema = collector.read_json(resolved_root / BOOT_REPORT_SCHEMA)
    sealed_asset = collector.read_json(resolved_root / BOOT_SEAL_ASSET)
    if resolved_element_ids is None:
        commit_oid = _head_commit_oid(resolved_root)
        resolved, evidence = measure_resolved_element_ids(
            resolved_root,
            sealed_asset,
            commit_oid,
            input_collector=collector,
        )
    else:
        commit_oid = _head_or_synthetic_oid(resolved_root)
        resolved = _resolved_ids(resolved_element_ids)
        evidence = _resolution_evidence(
            resolved,
            source="explicit-test-input",
            manifest_present=(resolved_root / MANIFEST_ASSET).exists(),
            phase2_status="synthetic",
        )
    report = build_boot_report(
        sealed_asset,
        resolved,
        commit_oid=commit_oid,
        resolution_evidence=evidence,
        input_files=collector.records(),
    )
    validate_asset(report, schema)
    destination = resolved_root / _schema_output_path(schema)
    _write_report(destination, report)
    return destination


def accept_transition_green(
    root: Path,
    resolved_element_ids: Collection[str] | None = None,
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
    collector = InputAssetCollector(resolved_root)
    schema = collector.read_json(resolved_root / BOOT_REPORT_SCHEMA)
    report_path = resolved_root / _schema_output_path(schema)
    if not report_path.is_file():
        raise CheckerViolation(
            "NFR-018 (e) BOOT-REPORT: 出力のない緑は本規定の充足とみなさない"
        )
    sealed_asset = collector.read_json(resolved_root / BOOT_SEAL_ASSET)
    if resolved_element_ids is None:
        commit_oid = _head_commit_oid(resolved_root)
        resolved, evidence = measure_resolved_element_ids(
            resolved_root,
            sealed_asset,
            commit_oid,
            input_collector=collector,
        )
    else:
        commit_oid = _head_or_synthetic_oid(resolved_root)
        resolved = _resolved_ids(resolved_element_ids)
        evidence = _resolution_evidence(
            resolved,
            source="explicit-test-input",
            manifest_present=(resolved_root / MANIFEST_ASSET).exists(),
            phase2_status="synthetic",
        )
    report = read_json(report_path)
    assert_report_matches(
        sealed_asset,
        resolved,
        report,
        schema,
        commit_oid=commit_oid,
        resolution_evidence=evidence,
        input_files=collector.records(),
    )
    return _object(report, "boot-report")


def main(argv: Sequence[str] | None = None) -> int:
    """未解消レポートを出力し、走査件数を標準出力へ書く。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        0 = 出力成功。2 = 判定不能(fail-closed)。
    """
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--root", default=".", help="リポジトリルート")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="既存出力が現在 HEAD と実測入力に一致することだけを検査する",
    )
    try:
        arguments = parser.parse_args(argv)
        root = Path(arguments.root)
        if arguments.verify:
            report = accept_transition_green(root)
            schema = read_json(root.resolve() / BOOT_REPORT_SCHEMA)
            path = root.resolve() / _schema_output_path(schema)
        else:
            path = emit_boot_report(root)
            report = read_json(path)
        mapping = _object(report, "boot-report")
        count = mapping.get("unresolvedCount")
        # 走査件数を出力へ出す。`exit 0` だけでは、1 件も見ずに終わった実行と
        # 区別できない(ステップ 45 の空振り事故と同じ形)。
        print(f"BOOT-REPORT emitted: {count} unresolved -> {path}")
    except (CheckerExecutionError, CheckerViolation) as error:
        print(f"判定不能: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
