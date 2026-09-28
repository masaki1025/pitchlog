"""人間確認の署名記録を、宣言済みの機械保証範囲だけで検証する。"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import check_input_axes_descriptor as descriptor_checker
except ModuleNotFoundError:  # pragma: no cover - packageとして読み込む経路
    from scripts import check_input_axes_descriptor as descriptor_checker

SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/human_review_signature_schema_v1.json"
)


class HumanReviewSignatureRecordError(ValueError):
    """署名記録を宣言済みの機械保証範囲で検証できない場合を表す。"""


def _object(value: object, label: str) -> dict[str, Any]:
    """文字列キーのobjectを返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise HumanReviewSignatureRecordError(f"{label}がobjectでない")
    return value


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise HumanReviewSignatureRecordError(f"{label}が空でない文字列でない")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    """重複のない空でない文字列配列を返す。"""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise HumanReviewSignatureRecordError(
            f"{label}が重複のない空でない文字列配列でない"
        )
    return tuple(value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    """objectのキー集合が宣言形式と一致することを確認する。"""
    if set(value) != expected:
        raise HumanReviewSignatureRecordError(
            f"{label}のキーがexact-set不一致: "
            f"expected={sorted(expected)!r}; actual={sorted(value)!r}"
        )


def _load_schema(root: Path) -> dict[str, Any]:
    """署名記録schemaを重複キー拒否付きで読み込む。"""
    try:
        value = descriptor_checker.load_json(root / SCHEMA_PATH, "署名記録schema")
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    return _object(value, "署名記録schema")


def _policy(schema: Mapping[str, Any]) -> dict[str, Any]:
    """schemaの署名記録方針を閉じた宣言として返す。"""
    policy = _object(
        schema.get("x-pitchlog-human-review-signature-policy"),
        "x-pitchlog-human-review-signature-policy",
    )
    _exact_keys(
        policy,
        {
            "recordLocation",
            "subjectDigest",
            "recordedMethods",
            "attestationItems",
            "assuranceBoundary",
            "provenanceRelation",
            "devHarness63Relation",
        },
        "x-pitchlog-human-review-signature-policy",
    )
    if _string(policy["recordLocation"], "recordLocation") != "separate-document":
        raise HumanReviewSignatureRecordError("署名記録が独立文書として宣言されていない")

    digest = _object(policy["subjectDigest"], "subjectDigest")
    _exact_keys(
        digest,
        {
            "documentKind",
            "pathRoot",
            "canonicalization",
            "algorithm",
            "safeIntegerLimit",
        },
        "subjectDigest",
    )
    for key in ("documentKind", "pathRoot", "canonicalization", "algorithm"):
        _string(digest[key], f"subjectDigest.{key}")
    supported_digest_declaration = {
        "documentKind": "json",
        "canonicalization": "RFC8785",
        "algorithm": "sha256",
    }
    for key, supported in supported_digest_declaration.items():
        if digest[key] != supported:
            raise HumanReviewSignatureRecordError(
                f"未対応のsubjectDigest.{key}である: {digest[key]!r}"
            )
    safe_integer_limit = digest["safeIntegerLimit"]
    if (
        not isinstance(safe_integer_limit, int)
        or isinstance(safe_integer_limit, bool)
        or safe_integer_limit < 1
    ):
        raise HumanReviewSignatureRecordError(
            "subjectDigest.safeIntegerLimitが正の整数でない"
        )

    methods = _object(policy["recordedMethods"], "recordedMethods")
    attestations = _object(policy["attestationItems"], "attestationItems")
    if not methods or not attestations:
        raise HumanReviewSignatureRecordError("署名記録の閉じた宣言が空である")
    for method_id, raw_method in methods.items():
        method = _object(raw_method, f"recordedMethods.{method_id}")
        _exact_keys(method, {"humanMeaning"}, f"recordedMethods.{method_id}")
        _string(method["humanMeaning"], f"recordedMethods.{method_id}.humanMeaning")
    for attestation_id, raw_attestation in attestations.items():
        attestation = _object(
            raw_attestation, f"attestationItems.{attestation_id}"
        )
        _exact_keys(
            attestation,
            {"acceptedRecordedResponses", "humanMeaning"},
            f"attestationItems.{attestation_id}",
        )
        responses = attestation["acceptedRecordedResponses"]
        if not isinstance(responses, list) or not responses:
            raise HumanReviewSignatureRecordError(
                f"attestationItems.{attestation_id}.acceptedRecordedResponsesが空である"
            )
        _string(
            attestation["humanMeaning"],
            f"attestationItems.{attestation_id}.humanMeaning",
        )

    assurance = _object(policy["assuranceBoundary"], "assuranceBoundary")
    _exact_keys(
        assurance,
        {"mechanicallyGuaranteed", "humanControls", "wordingRule"},
        "assuranceBoundary",
    )
    _string_list(
        assurance["mechanicallyGuaranteed"],
        "assuranceBoundary.mechanicallyGuaranteed",
    )
    _string_list(assurance["humanControls"], "assuranceBoundary.humanControls")
    _string(assurance["wordingRule"], "assuranceBoundary.wordingRule")
    _string(policy["provenanceRelation"], "provenanceRelation")
    _string(policy["devHarness63Relation"], "devHarness63Relation")
    return policy


def _repository_subject_path(
    root: Path, raw_path: str, declared_root: str
) -> Path:
    """宣言された領域内の対象パスを返す。"""
    relative = PurePosixPath(raw_path)
    root_relative = PurePosixPath(declared_root)
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or "\\" in raw_path
        or relative.parts[: len(root_relative.parts)] != root_relative.parts
    ):
        raise HumanReviewSignatureRecordError(
            f"署名対象pathが宣言領域外である: {raw_path!r}"
        )
    resolved_root = root.resolve()
    resolved = (resolved_root / Path(*relative.parts)).resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise HumanReviewSignatureRecordError(
            f"署名対象pathがリポジトリ外へ解決される: {raw_path!r}"
        ) from error
    return resolved


def _response_is_accepted(response: object, accepted: list[object]) -> bool:
    """JSON型を含めて記録済み宣誓応答が許容値に一致するか返す。"""
    actual = descriptor_checker.canonicalize_json(response)
    return any(
        actual == descriptor_checker.canonicalize_json(candidate)
        for candidate in accepted
    )


def compute_subject_digest(subject: object, safe_integer_limit: int) -> str:
    """対象JSON文書全体のRFC 8785 + SHA-256 digestを返す。

    Args:
        subject: 重複キー拒否を通過した対象JSON文書。
        safe_integer_limit: 許容する整数の絶対値上限。

    Returns:
        ``sha256:`` 接頭辞付きの小文字16進digest。
    """
    canonical = descriptor_checker.canonicalize_json(subject, safe_integer_limit)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def validate_signature_record(
    root: Path,
    record: Mapping[str, Any],
    *,
    schema_value: Mapping[str, Any] | None = None,
) -> None:
    """署名記録の形式・対象digest・宣誓記載だけを検証する。

    Args:
        root: リポジトリルート。
        record: 検証する署名記録。
        schema_value: テスト用の署名記録schema差し替え。

    Raises:
        HumanReviewSignatureRecordError: 宣言形式、対象digest、記録上の
            識別子差、または宣誓記載を確認できない場合。

    Note:
        レビューの実施、確認者が実際に別人であること、条文からの直接
        レビュー、記載内容の真実性、および判断の正しさは保証しない。
    """
    schema = _load_schema(root) if schema_value is None else dict(schema_value)
    policy = _policy(schema)
    try:
        descriptor_checker._validate_instance(
            dict(record), schema, schema, "署名記録"
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error

    author_id = _string(record.get("artifactAuthorId"), "artifactAuthorId")
    reviewer_id = _string(record.get("recordedReviewerId"), "recordedReviewerId")
    if author_id == reviewer_id:
        raise HumanReviewSignatureRecordError(
            "作成者と確認者の記録上の識別子が同一である"
        )

    recorded_on = _string(record.get("recordedOn"), "recordedOn")
    try:
        date.fromisoformat(recorded_on)
    except ValueError as error:
        raise HumanReviewSignatureRecordError(
            f"recordedOnが実在するISO日付でない: {recorded_on!r}"
        ) from error

    methods = _object(policy["recordedMethods"], "recordedMethods")
    recorded_method = _string(record.get("recordedMethod"), "recordedMethod")
    if recorded_method not in methods:
        raise HumanReviewSignatureRecordError(
            f"未宣言の記録済み確認方法である: {recorded_method!r}"
        )

    subject = _object(record.get("subject"), "subject")
    digest_rule = _object(policy["subjectDigest"], "subjectDigest")
    subject_path = _repository_subject_path(
        root,
        _string(subject.get("path"), "subject.path"),
        _string(digest_rule.get("pathRoot"), "subjectDigest.pathRoot"),
    )
    try:
        subject_value = descriptor_checker.load_json(subject_path, "署名対象")
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    safe_integer_limit = digest_rule["safeIntegerLimit"]
    if not isinstance(safe_integer_limit, int) or isinstance(
        safe_integer_limit, bool
    ):
        raise HumanReviewSignatureRecordError(
            "subjectDigest.safeIntegerLimitが整数でない"
        )
    try:
        actual_digest = compute_subject_digest(subject_value, safe_integer_limit)
    except descriptor_checker.DescriptorCheckError as error:
        raise HumanReviewSignatureRecordError(str(error)) from error
    recorded_digest = _string(subject.get("digest"), "subject.digest")
    if recorded_digest != actual_digest:
        raise HumanReviewSignatureRecordError(
            "署名対象digestが現物と不一致: "
            f"recorded={recorded_digest}; actual={actual_digest}"
        )

    declared_attestations = _object(
        policy["attestationItems"], "attestationItems"
    )
    recorded: dict[str, object] = {}
    for index, raw_attestation in enumerate(record["attestations"]):
        attestation = _object(raw_attestation, f"attestations[{index}]")
        attestation_id = _string(
            attestation.get("attestationId"),
            f"attestations[{index}].attestationId",
        )
        if attestation_id in recorded:
            raise HumanReviewSignatureRecordError(
                f"宣誓記載が重複している: {attestation_id!r}"
            )
        recorded[attestation_id] = attestation["recordedResponse"]
    if set(recorded) != set(declared_attestations):
        raise HumanReviewSignatureRecordError(
            "宣誓記載がexact-set不一致: "
            f"missing={sorted(set(declared_attestations) - set(recorded))!r}; "
            f"unexpected={sorted(set(recorded) - set(declared_attestations))!r}"
        )
    for attestation_id, response in recorded.items():
        declaration = _object(
            declared_attestations[attestation_id],
            f"attestationItems.{attestation_id}",
        )
        accepted = declaration["acceptedRecordedResponses"]
        if not isinstance(accepted, list) or not _response_is_accepted(
            response, accepted
        ):
            raise HumanReviewSignatureRecordError(
                f"宣誓の記録済み応答が充足値でない: {attestation_id!r}"
            )


def main(argv: Sequence[str] | None = None) -> int:
    """指定した署名記録の形式・対象digest・宣誓記載を検証する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, help="検証する署名記録JSON")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        raw_record = descriptor_checker.load_json(args.record, "署名記録")
        record = _object(raw_record, "署名記録")
        validate_signature_record(args.root, record)
    except (
        descriptor_checker.DescriptorCheckError,
        HumanReviewSignatureRecordError,
    ) as error:
        print(f"human review signature record: FAIL: {error}", file=sys.stderr)
        return 1
    print("human review signature record: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
