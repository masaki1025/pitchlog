"""状況判定契約の由来記録を宣言済みの機械保証範囲で検証する。"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import check_input_axes_descriptor as descriptor_checker
    import check_vocabulary_manifest as vocabulary_checker
except ModuleNotFoundError:  # pragma: no cover - packageとして読み込む経路
    from scripts import check_input_axes_descriptor as descriptor_checker
    from scripts import check_vocabulary_manifest as vocabulary_checker

SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/state_transition_contract_schema_v1.json"
)


class ProvenanceCheckError(ValueError):
    """由来記録を宣言済みの範囲で検証できない場合を表す。"""


def _object(value: object, label: str) -> dict[str, Any]:
    """文字列キーのobjectを返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ProvenanceCheckError(f"{label}がobjectでない")
    return value


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise ProvenanceCheckError(f"{label}が空でない文字列でない")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    """重複のない空でない文字列配列を返す。"""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise ProvenanceCheckError(f"{label}が閉じた文字列配列でない")
    return tuple(value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    """objectのキー集合が宣言された文法と一致することを検証する。"""
    if set(value) != expected:
        raise ProvenanceCheckError(
            f"{label}のキーがexact-set不一致: "
            f"expected={sorted(expected)!r}; actual={sorted(value)!r}"
        )


def _load_schema(root: Path) -> dict[str, Any]:
    """状況判定契約schemaを重複キー拒否付きで読み込む。"""
    try:
        value = descriptor_checker.load_json(root / SCHEMA_PATH, "状況判定契約schema")
    except descriptor_checker.DescriptorCheckError as error:
        raise ProvenanceCheckError(str(error)) from error
    return _object(value, "状況判定契約schema")


def _policy(schema: Mapping[str, Any]) -> dict[str, Any]:
    """schemaの由来記録方針を閉じた宣言として返す。"""
    policy = _object(
        schema.get("x-pitchlog-provenance-policy"),
        "x-pitchlog-provenance-policy",
    )
    _exact_keys(
        policy,
        {
            "recordLocation",
            "recordField",
            "sourceKinds",
            "subjectKinds",
            "attestationItems",
            "assuranceBoundary",
        },
        "x-pitchlog-provenance-policy",
    )
    record_location = _string(
        policy["recordLocation"], "provenance.recordLocation"
    )
    record_field = _string(policy["recordField"], "provenance.recordField")
    if record_location != "contract-top-level":
        raise ProvenanceCheckError(
            f"未対応のprovenance配置: {record_location!r}"
        )
    required = schema.get("required")
    properties = schema.get("properties")
    if (
        not isinstance(required, list)
        or record_field not in required
        or not isinstance(properties, dict)
        or properties.get(record_field) != {"$ref": "#/$defs/provenance"}
    ):
        raise ProvenanceCheckError(
            "provenance宣言を契約トップレベルへ解決できない"
        )

    source_kinds = _object(policy["sourceKinds"], "provenance.sourceKinds")
    subject_kinds = _object(policy["subjectKinds"], "provenance.subjectKinds")
    attestation_items = _object(
        policy["attestationItems"], "provenance.attestationItems"
    )
    if not source_kinds or not subject_kinds or not attestation_items:
        raise ProvenanceCheckError("provenanceの閉じた宣言が空である")

    priorities: list[int] = []
    for source_kind, raw_rule in source_kinds.items():
        rule = _object(raw_rule, f"sourceKinds.{source_kind}")
        priority = rule.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            raise ProvenanceCheckError(f"sourceKinds.{source_kind}.priorityが不正")
        priorities.append(priority)
        _string(rule.get("verificationMode"), f"sourceKinds.{source_kind}.verificationMode")
        _string(rule.get("machineCapability"), f"sourceKinds.{source_kind}.machineCapability")
    if sorted(priorities) != list(range(1, len(priorities) + 1)):
        raise ProvenanceCheckError("典拠の優先順位が1始まりの連続値でない")

    for subject_kind, raw_rule in subject_kinds.items():
        rule = _object(raw_rule, f"subjectKinds.{subject_kind}")
        _exact_keys(rule, {"sufficientSourceKinds"}, f"subjectKinds.{subject_kind}")
        sufficient = _string_list(
            rule["sufficientSourceKinds"],
            f"subjectKinds.{subject_kind}.sufficientSourceKinds",
        )
        if not set(sufficient) <= set(source_kinds):
            raise ProvenanceCheckError(
                f"subjectKinds.{subject_kind}が未知の典拠種別を参照している"
            )

    for attestation_id, raw_rule in attestation_items.items():
        rule = _object(raw_rule, f"attestationItems.{attestation_id}")
        _exact_keys(
            rule,
            {"acceptedResponses", "humanMeaning"},
            f"attestationItems.{attestation_id}",
        )
        responses = rule["acceptedResponses"]
        if not isinstance(responses, list) or not responses:
            raise ProvenanceCheckError(
                f"attestationItems.{attestation_id}.acceptedResponsesが空である"
            )
        _string(rule["humanMeaning"], f"attestationItems.{attestation_id}.humanMeaning")

    assurance = _object(policy["assuranceBoundary"], "provenance.assuranceBoundary")
    _exact_keys(
        assurance,
        {"mechanicallyGuaranteed", "humanControls", "step43Excluded"},
        "provenance.assuranceBoundary",
    )
    _string_list(
        assurance["mechanicallyGuaranteed"],
        "provenance.assuranceBoundary.mechanicallyGuaranteed",
    )
    _string_list(
        assurance["humanControls"],
        "provenance.assuranceBoundary.humanControls",
    )
    _string(assurance["step43Excluded"], "provenance.assuranceBoundary.step43Excluded")
    return policy


def _validate_requirement_source(
    root: Path, source_id: str, rule: Mapping[str, Any]
) -> None:
    """要件書から機械抽出した条文IDの実在を検証する。"""
    source_path = PurePosixPath(_string(rule.get("sourcePath"), "sourcePath"))
    namespace = _string(rule.get("sourceIdNamespace"), "sourceIdNamespace")
    try:
        clause_ids = descriptor_checker.load_clause_ids_from_paths(
            root, (source_path,)
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise ProvenanceCheckError(str(error)) from error
    expected_ids = {f"{namespace}:{clause_id}" for clause_id in clause_ids}
    if source_id not in expected_ids:
        raise ProvenanceCheckError(f"要件書の典拠IDが実在しない: {source_id!r}")


def _validate_format_only_source(source_id: str, rule: Mapping[str, Any]) -> None:
    """原典を持たない典拠IDについて宣言済みの書式だけを検証する。"""
    pattern = _string(rule.get("sourceIdPattern"), "sourceIdPattern")
    if re.fullmatch(pattern, source_id) is None:
        raise ProvenanceCheckError(f"典拠IDの書式が不正: {source_id!r}")
    not_verified = _string_list(
        rule.get("notMechanicallyVerified"), "notMechanicallyVerified"
    )
    if not not_verified:
        raise ProvenanceCheckError("機械で確かめない範囲が宣言されていない")


def _validate_vocabulary_source(
    root: Path, source_id: str, rule: Mapping[str, Any]
) -> None:
    """共有語彙manifestを通して語彙IDの実在を検証する。"""
    manifest_path = PurePosixPath(
        _string(rule.get("manifestPath"), "manifestPath")
    )
    if manifest_path != vocabulary_checker.MANIFEST_PATH:
        raise ProvenanceCheckError(
            "provenance宣言の共有語彙manifestがD-12の解決先と一致しない"
        )
    try:
        resolved = vocabulary_checker.validate_manifest(root)
    except vocabulary_checker.VocabularyManifestError as error:
        raise ProvenanceCheckError(str(error)) from error
    matches = sum(source_id in seed_ids for seed_ids in resolved.values())
    if matches != 1:
        raise ProvenanceCheckError(
            f"語彙IDを共有manifestへ一意に解決できない: {source_id!r}"
        )


def _validate_legacy_line_source(
    root: Path, source_id: str, rule: Mapping[str, Any]
) -> None:
    """版固定の旧調査資料についてパスと行の実在を検証する。"""
    pattern = _string(rule.get("sourceIdPattern"), "sourceIdPattern")
    match = re.fullmatch(pattern, source_id)
    if match is None:
        raise ProvenanceCheckError(f"旧調査資料の典拠ID書式が不正: {source_id!r}")
    relative = PurePosixPath(match.group("path"))
    declared_root = PurePosixPath(_string(rule.get("pathRoot"), "pathRoot"))
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.parts[: len(declared_root.parts)] != declared_root.parts
    ):
        raise ProvenanceCheckError(f"旧調査資料のpathが宣言範囲外: {relative}")
    path = root.joinpath(*relative.parts)
    try:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeError) as error:
        raise ProvenanceCheckError(
            f"旧調査資料をUTF-8で読めない: {path}: {error}"
        ) from error
    line_number = int(match.group("line"))
    if line_number > line_count:
        raise ProvenanceCheckError(
            f"旧調査資料の行が実在しない: {relative}:{line_number}"
        )


def _validate_source_reference(
    root: Path,
    source_kind: str,
    source_id: str,
    rule: Mapping[str, Any],
) -> None:
    """典拠種別が宣言する機械能力の範囲だけで参照を検証する。"""
    mode = _string(rule.get("verificationMode"), "verificationMode")
    if mode == "repository-clause-id-existence":
        _validate_requirement_source(root, source_id, rule)
        return
    if mode == "identifier-format-only":
        _validate_format_only_source(source_id, rule)
        return
    if mode == "vocabulary-id-existence-via-manifest":
        _validate_vocabulary_source(root, source_id, rule)
        return
    if mode == "repository-line-reference-existence":
        _validate_legacy_line_source(root, source_id, rule)
        return
    raise ProvenanceCheckError(
        f"未対応の典拠参照検査方式: sourceKind={source_kind!r}; mode={mode!r}"
    )


def _response_is_accepted(response: object, accepted: list[object]) -> bool:
    """JSON型を含めて宣誓応答が許容値に一致するか返す。"""
    actual = descriptor_checker.canonicalize_json(response)
    return any(
        actual == descriptor_checker.canonicalize_json(candidate)
        for candidate in accepted
    )


def validate_provenance(
    root: Path,
    provenance: Mapping[str, Any],
    *,
    schema_value: Mapping[str, Any] | None = None,
) -> None:
    """由来記録をschemaと宣言済みの機械保証範囲で検証する。

    Args:
        root: リポジトリルート。
        provenance: 検証する契約単位の由来記録。
        schema_value: テスト用の状況判定契約schema差し替え。

    Raises:
        ProvenanceCheckError: schema、典拠参照、記録上の独立性、または宣誓の
            充足を宣言済みの範囲で確認できない場合。

    Note:
        実際の独立確認、宣誓の真実性、典拠による主張の支持、および公認
        野球規則の条番号の実在・内容は人間統制であり、本関数は保証しない。
    """
    schema = _load_schema(root) if schema_value is None else dict(schema_value)
    policy = _policy(schema)
    definitions = _object(schema.get("$defs"), "schema.$defs")
    provenance_schema = _object(definitions.get("provenance"), "$defs.provenance")
    try:
        descriptor_checker._validate_instance(
            dict(provenance), provenance_schema, schema, "$.provenance"
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise ProvenanceCheckError(str(error)) from error

    author_id = _string(provenance.get("authorId"), "provenance.authorId")
    verifier_id = _string(
        provenance.get("independentVerifierId"),
        "provenance.independentVerifierId",
    )
    if author_id == verifier_id:
        raise ProvenanceCheckError("作成者と独立確認者が記録上同一である")

    source_kinds = _object(policy["sourceKinds"], "provenance.sourceKinds")
    actual_source_kinds: set[str] = set()
    for index, raw_source in enumerate(provenance["sources"]):
        source = _object(raw_source, f"provenance.sources[{index}]")
        source_kind = _string(
            source.get("sourceKind"), f"provenance.sources[{index}].sourceKind"
        )
        source_id = _string(
            source.get("sourceId"), f"provenance.sources[{index}].sourceId"
        )
        rule = source_kinds.get(source_kind)
        if not isinstance(rule, dict):
            raise ProvenanceCheckError(f"未知の典拠種別: {source_kind!r}")
        _validate_source_reference(root, source_kind, source_id, rule)
        actual_source_kinds.add(source_kind)

    subject_kind = _string(provenance.get("subjectKind"), "provenance.subjectKind")
    subject_kinds = _object(policy["subjectKinds"], "provenance.subjectKinds")
    subject_rule = subject_kinds.get(subject_kind)
    if not isinstance(subject_rule, dict):
        raise ProvenanceCheckError(f"未知の対象種別: {subject_kind!r}")
    sufficient = set(
        _string_list(
            subject_rule.get("sufficientSourceKinds"),
            f"subjectKinds.{subject_kind}.sufficientSourceKinds",
        )
    )
    if not actual_source_kinds & sufficient:
        raise ProvenanceCheckError(
            f"対象種別を支える優先典拠が無い: subjectKind={subject_kind!r}"
        )

    declared_attestations = _object(
        policy["attestationItems"], "provenance.attestationItems"
    )
    recorded: dict[str, object] = {}
    for index, raw_attestation in enumerate(provenance["attestations"]):
        attestation = _object(
            raw_attestation, f"provenance.attestations[{index}]"
        )
        attestation_id = _string(
            attestation.get("attestationId"),
            f"provenance.attestations[{index}].attestationId",
        )
        if attestation_id in recorded:
            raise ProvenanceCheckError(f"宣誓項目が重複している: {attestation_id!r}")
        recorded[attestation_id] = attestation["response"]
    if set(recorded) != set(declared_attestations):
        raise ProvenanceCheckError(
            "宣誓項目がexact-set不一致: "
            f"missing={sorted(set(declared_attestations) - set(recorded))!r}; "
            f"unexpected={sorted(set(recorded) - set(declared_attestations))!r}"
        )
    for attestation_id, response in recorded.items():
        declaration = _object(
            declared_attestations[attestation_id],
            f"attestationItems.{attestation_id}",
        )
        accepted = declaration["acceptedResponses"]
        if not isinstance(accepted, list) or not _response_is_accepted(
            response, accepted
        ):
            raise ProvenanceCheckError(
                f"宣誓応答が充足値でない: {attestation_id!r}"
            )

    independent_review = _object(
        provenance.get("independentReview"),
        "provenance.independentReview",
    )
    chronology = independent_review.get("chronology")
    if not isinstance(chronology, list) or not chronology:
        raise ProvenanceCheckError("独立確認の経緯が空または配列でない")
    sequences: list[int] = []
    actors: set[str] = set()
    for index, raw_event in enumerate(chronology):
        event = _object(raw_event, f"independentReview.chronology[{index}]")
        sequence = event.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise ProvenanceCheckError("独立確認の経緯に整数の順序が無い")
        sequences.append(sequence)
        actors.add(_string(event.get("actorId"), "chronology.actorId"))
    if sequences != list(range(1, len(chronology) + 1)):
        raise ProvenanceCheckError("独立確認の経緯が1始まりの連続順序でない")
    if verifier_id not in actors:
        raise ProvenanceCheckError("独立確認者が確認経緯のactorIdに現れない")

    exposure = _string(
        independent_review.get("authorWorkExposure"),
        "independentReview.authorWorkExposure",
    )
    expected_exposure_by_response = {
        "not-seen-before-source-review": "not-seen-before-source-review",
        "seen-and-recorded": "seen-before-source-review",
    }
    exposure_response = recorded["author-work-exposure"]
    expected_exposure = expected_exposure_by_response.get(exposure_response)
    if expected_exposure is None or exposure != expected_exposure:
        raise ProvenanceCheckError(
            "作業結果の閲覧順序とauthor-work-exposure宣誓が一致しない"
        )


def main(argv: list[str] | None = None) -> int:
    """指定した状況判定契約の由来記録を検証する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="検証する状況判定契約JSON")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        contract = _object(
            descriptor_checker.load_json(args.contract, "状況判定契約"),
            "状況判定契約",
        )
        provenance = _object(contract.get("provenance"), "provenance")
        validate_provenance(root, provenance)
    except (descriptor_checker.DescriptorCheckError, ProvenanceCheckError) as error:
        print(f"provenance検査失敗: {error}", file=sys.stderr)
        return 1
    print("provenance検査: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
