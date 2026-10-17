"""状態遷移契約(状況判定・終了判定)の由来記録を宣言済みの機械保証範囲で検証する。"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal

try:
    import check_input_axes_descriptor as descriptor_checker
    import check_vocabulary_manifest as vocabulary_checker
except ModuleNotFoundError:  # pragma: no cover - packageとして読み込む経路
    from scripts import check_input_axes_descriptor as descriptor_checker
    from scripts import check_vocabulary_manifest as vocabulary_checker

SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/state_transition_contract_schema_v1.json"
)
CONTRACT_SIZE_LIMIT_PATH = PurePosixPath(
    "contracts/state-transition/contract_size_limit_v1.json"
)
# 由来記録を検査する契約の閉じた登録表(種別 → 契約パス・schemaパス・表示名)。
# 契約の集合はcontract_size_limit_v1.jsonのcontractPathsと一致させる。
CONTRACTS: dict[str, tuple[PurePosixPath, PurePosixPath, str]] = {
    "state-transition": (
        PurePosixPath("contracts/state-transition/state_transition_contract_v1.json"),
        SCHEMA_PATH,
        "状況判定契約",
    ),
    "game-end": (
        PurePosixPath("contracts/state-transition/game_end_contract_v1.json"),
        PurePosixPath("contracts/state-transition/game_end_contract_schema_v1.json"),
        "終了判定契約",
    ),
}
NOT_PERFORMED = "not-performed"
# 独立確認が未実施であることを表す宣誓の閉じた形。
NOT_PERFORMED_ATTESTATIONS: dict[str, object] = {
    "direct-source-clause-review": False,
    "author-work-exposure": NOT_PERFORMED,
    "source-support-judgment": False,
}
ProvenanceStatus = Literal["not-performed", "verified"]


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


def _registration(
    contract_kind: str,
) -> tuple[PurePosixPath, PurePosixPath, str]:
    """登録表から契約種別の登録を返す。"""
    registration = CONTRACTS.get(contract_kind)
    if registration is None:
        raise ProvenanceCheckError(f"登録表に無い契約種別: {contract_kind!r}")
    return registration


def _load_schema(root: Path, contract_kind: str = "state-transition") -> dict[str, Any]:
    """契約種別のschemaを重複キー拒否付きで読み込む。"""
    _, schema_path, label = _registration(contract_kind)
    try:
        value = descriptor_checker.load_json(root / schema_path, f"{label}schema")
    except descriptor_checker.DescriptorCheckError as error:
        raise ProvenanceCheckError(str(error)) from error
    return _object(value, f"{label}schema")


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


def _validated_policy(
    root: Path,
    provenance: Mapping[str, Any],
    schema_value: Mapping[str, Any] | None,
    contract_kind: str,
) -> dict[str, Any]:
    """schemaを読み、由来記録をschemaへ適合させて由来記録方針を返す。"""
    _registration(contract_kind)
    schema = (
        _load_schema(root, contract_kind)
        if schema_value is None
        else dict(schema_value)
    )
    policy = _policy(schema)
    definitions = _object(schema.get("$defs"), "schema.$defs")
    provenance_schema = _object(definitions.get("provenance"), "$defs.provenance")
    try:
        descriptor_checker._validate_instance(
            dict(provenance), provenance_schema, schema, "$.provenance"
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise ProvenanceCheckError(str(error)) from error
    return policy


def _validate_sources_and_subject(
    root: Path, provenance: Mapping[str, Any], policy: Mapping[str, Any]
) -> None:
    """典拠参照の実在と、対象種別を支える優先典拠の存在を検証する。"""
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


def validate_provenance(
    root: Path,
    provenance: Mapping[str, Any],
    *,
    schema_value: Mapping[str, Any] | None = None,
    contract_kind: str = "state-transition",
) -> None:
    """由来記録をschemaと宣言済みの機械保証範囲で検証する。

    独立確認を実施済みとして主張する記録を検証する。未実施の記録は
    宣誓が充足値でないため本関数では失敗する(3状態の判定は
    ``classify_provenance``)。

    Args:
        root: リポジトリルート。
        provenance: 検証する契約単位の由来記録。
        schema_value: テスト用の契約schema差し替え。
        contract_kind: 登録表の契約種別。既定は状況判定契約。

    Raises:
        ProvenanceCheckError: schema、典拠参照、記録上の独立性、または宣誓の
            充足を宣言済みの範囲で確認できない場合。

    Note:
        実際の独立確認、宣誓の真実性、典拠による主張の支持、および公認
        野球規則の条番号の実在・内容は人間統制であり、本関数は保証しない。
    """
    policy = _validated_policy(root, provenance, schema_value, contract_kind)

    author_id = _string(provenance.get("authorId"), "provenance.authorId")
    verifier_id = _string(
        provenance.get("independentVerifierId"),
        "provenance.independentVerifierId",
    )
    if author_id == verifier_id:
        raise ProvenanceCheckError("作成者と独立確認者が記録上同一である")

    _validate_sources_and_subject(root, provenance, policy)

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


def _same_json(actual: object, expected: object) -> bool:
    """JSON型を含めて2値が一致するかを返す。"""
    return descriptor_checker.canonicalize_json(
        actual
    ) == descriptor_checker.canonicalize_json(expected)


def _reserved_locations(provenance: Mapping[str, Any]) -> list[str]:
    """予約値not-performedが現れる判定キーの位置を返す。

    判定キーは閉じた4か所(authorId・independentVerifierId・
    attestations[].response・independentReview.chronology[].actorId)。
    """
    locations: list[str] = []
    for key in ("authorId", "independentVerifierId"):
        if _same_json(provenance.get(key), NOT_PERFORMED):
            locations.append(key)
    for index, attestation in enumerate(provenance.get("attestations", [])):
        if isinstance(attestation, dict) and _same_json(
            attestation.get("response"), NOT_PERFORMED
        ):
            locations.append(f"attestations[{index}].response")
    review = provenance.get("independentReview")
    if isinstance(review, dict):
        for index, event in enumerate(review.get("chronology", [])):
            if isinstance(event, dict) and _same_json(
                event.get("actorId"), NOT_PERFORMED
            ):
                locations.append(f"independentReview.chronology[{index}].actorId")
    return locations


def _require_not_performed_form(
    provenance: Mapping[str, Any], policy: Mapping[str, Any]
) -> None:
    """予約値を含む記録が未実施の閉じた形と完全一致することを検証する。"""
    declared = _object(policy["attestationItems"], "provenance.attestationItems")
    if set(declared) != set(NOT_PERFORMED_ATTESTATIONS):
        raise ProvenanceCheckError(
            "未実施の閉じた形が宣誓項目の宣言とexact-set不一致"
        )
    mismatch = "予約値not-performedを含むが未実施の閉じた形と一致しない"
    if not _same_json(provenance.get("independentVerifierId"), NOT_PERFORMED):
        raise ProvenanceCheckError(f"{mismatch}: independentVerifierId")
    if "independentReview" in provenance:
        raise ProvenanceCheckError(f"{mismatch}: independentReviewがある")
    recorded: dict[str, object] = {}
    for index, raw_attestation in enumerate(provenance["attestations"]):
        attestation = _object(raw_attestation, f"provenance.attestations[{index}]")
        attestation_id = _string(
            attestation.get("attestationId"),
            f"provenance.attestations[{index}].attestationId",
        )
        if attestation_id in recorded:
            raise ProvenanceCheckError(f"宣誓項目が重複している: {attestation_id!r}")
        recorded[attestation_id] = attestation.get("response")
    if set(recorded) != set(NOT_PERFORMED_ATTESTATIONS) or not all(
        _same_json(recorded[attestation_id], expected)
        for attestation_id, expected in NOT_PERFORMED_ATTESTATIONS.items()
    ):
        raise ProvenanceCheckError(f"{mismatch}: attestations")


def classify_provenance(
    root: Path,
    provenance: Mapping[str, Any],
    *,
    schema_value: Mapping[str, Any] | None = None,
    contract_kind: str = "state-transition",
) -> ProvenanceStatus:
    """由来記録を未実施・実施済みのいずれかに分類し、不正なら失敗する。

    未実施の記録も、schema・典拠参照・対象種別・優先典拠は全件検証する。
    免除するのは記録上の独立性・宣誓の充足・独立確認の経緯だけで、
    予約値not-performedを含む記録は未実施の閉じた形と完全一致する場合に
    限って未実施とする。

    Args:
        root: リポジトリルート。
        provenance: 分類する契約単位の由来記録。
        schema_value: テスト用の契約schema差し替え。
        contract_kind: 登録表の契約種別。既定は状況判定契約。

    Returns:
        未実施の閉じた形なら ``"not-performed"``、実施済みの主張として全項目を
        満たせば ``"verified"``。

    Raises:
        ProvenanceCheckError: schema・典拠・対象種別が不正、予約値の位置が
            未実施の閉じた形と一致しない、または実施済みの主張が
            ``validate_provenance`` を満たさない場合。
    """
    policy = _validated_policy(root, provenance, schema_value, contract_kind)
    reserved = _reserved_locations(provenance)
    if "authorId" in reserved:
        raise ProvenanceCheckError("作成者IDに予約値not-performedが使われている")
    if not reserved:
        validate_provenance(
            root,
            provenance,
            schema_value=schema_value,
            contract_kind=contract_kind,
        )
        return "verified"
    _require_not_performed_form(provenance, policy)
    _validate_sources_and_subject(root, provenance, policy)
    return "not-performed"


def check_registry_closure(
    root: Path,
    registry: Mapping[str, tuple[PurePosixPath, PurePosixPath, str]] = CONTRACTS,
) -> None:
    """登録表の契約集合が契約一覧の宣言と一致することを検証する。

    Args:
        root: リポジトリルート。
        registry: 検証する登録表。既定は本モジュールの登録表。

    Raises:
        ProvenanceCheckError: 契約一覧に載る契約が登録表に無い、または
            登録表に契約一覧に無い契約がある場合。
    """
    try:
        declaration = _object(
            descriptor_checker.load_json(
                root / CONTRACT_SIZE_LIMIT_PATH, "契約サイズ上限"
            ),
            "契約サイズ上限",
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise ProvenanceCheckError(str(error)) from error
    declared = set(_string_list(declaration.get("contractPaths"), "contractPaths"))
    registered = {str(contract_path) for contract_path, _, _ in registry.values()}
    if registered != declared:
        raise ProvenanceCheckError(
            "provenance登録表と契約一覧がexact-set不一致: "
            f"unregistered={sorted(declared - registered)!r}; "
            f"undeclared={sorted(registered - declared)!r}"
        )


def check_repository(root: Path) -> dict[str, ProvenanceStatus]:
    """登録表のすべての契約について由来記録の状態を返す。

    Args:
        root: リポジトリルート。

    Returns:
        契約種別ごとの状態(未実施・実施済み)。

    Raises:
        ProvenanceCheckError: 登録表の閉包が崩れている、由来記録が無い
            (未記載)、または由来記録が不正な場合。
    """
    check_registry_closure(root)
    statuses: dict[str, ProvenanceStatus] = {}
    for contract_kind, (contract_path, _, label) in CONTRACTS.items():
        try:
            contract = _object(
                descriptor_checker.load_json(root / contract_path, label), label
            )
        except descriptor_checker.DescriptorCheckError as error:
            raise ProvenanceCheckError(str(error)) from error
        if "provenance" not in contract:
            raise ProvenanceCheckError(f"{label}にprovenanceが無い: {contract_path}")
        statuses[contract_kind] = classify_provenance(
            root,
            _object(contract["provenance"], f"{label}.provenance"),
            contract_kind=contract_kind,
        )
    return statuses


def contract_kind_for_path(root: Path, contract: Path) -> str:
    """契約ファイルのパスを登録表に照らして契約種別を返す。

    Args:
        root: リポジトリルート。
        contract: 契約ファイルのパス。

    Returns:
        登録表の契約種別。

    Raises:
        ProvenanceCheckError: 登録表に無いパスの場合。
    """
    resolved = contract.resolve()
    for contract_kind, (contract_path, _, _) in CONTRACTS.items():
        if resolved == (root / contract_path).resolve():
            return contract_kind
    raise ProvenanceCheckError(f"登録表に無い契約: {contract}")


def main(argv: list[str] | None = None) -> int:
    """指定した契約、またはリポジトリの全契約の由来記録を検証する。

    契約を指定した場合は実施済みの主張として検証する(未実施は失敗)。
    ``--repository`` は登録表の全契約を3状態で判定し、未実施を列挙する。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "contract", type=Path, nargs="?", help="検証する登録済み契約JSON"
    )
    parser.add_argument(
        "--repository",
        action="store_true",
        help="登録表の全契約を未記載・未実施・実施済みの3状態で判定する",
    )
    args = parser.parse_args(argv)
    if args.repository == (args.contract is not None):
        parser.error("契約JSONか--repositoryのどちらか一方を指定する")
    root = Path(__file__).resolve().parents[1]
    try:
        if args.repository:
            statuses = check_repository(root)
            for contract_kind, status in statuses.items():
                print(f"provenance状態: {contract_kind}={status}")
        else:
            contract_kind = contract_kind_for_path(root, args.contract)
            label = _registration(contract_kind)[2]
            contract = _object(
                descriptor_checker.load_json(args.contract, label), label
            )
            provenance = _object(contract.get("provenance"), "provenance")
            validate_provenance(root, provenance, contract_kind=contract_kind)
    except (descriptor_checker.DescriptorCheckError, ProvenanceCheckError) as error:
        print(f"provenance検査失敗: {error}", file=sys.stderr)
        return 1
    print("provenance検査: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
