"""失敗注入点資産を DDL 適用手順および閉じた位置規則と照合する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

try:
    from check_authz_catalog import git_blob_digest
except ModuleNotFoundError:  # pragma: no cover - モジュールとして読む場合だけ通る。
    from scripts.check_authz_catalog import git_blob_digest


ASSET_PATH = PurePosixPath("contracts/authz/failure-injection-points.json")
DDL_ELEMENTS_PATH = PurePosixPath("contracts/authz/ddl-elements.json")
ASSET_KIND = "authz_failure_injection_points"
BLOB_DIGEST_RE = re.compile(r"^[0-9a-f]{40}$")
ROLLBACK_BOUNDARY = "after_current_transaction_rollback"
COMPARISON_TARGETS = frozenset(
    {
        "all_target_catalogs",
        "role_memberships",
        "default_acls",
        "fixture_data",
    }
)


class FailureInjectionPointCheckError(Exception):
    """検査を開始できない入力不正を表す。"""


@dataclass(frozen=True)
class PositionRule:
    """資産要素内の checkpoint 位置と失敗時の境界を表す。"""

    after_command: str
    command_ordinal_within_element: int
    failure_boundary: str


@dataclass(frozen=True)
class ExpectedPosition:
    """閉じた失敗注入点 ID に対応する実行位置を表す。"""

    operation_kind: str
    element_type: str
    position_rule: PositionRule


@dataclass(frozen=True)
class InjectionPoint:
    """失敗注入点資産の 1 行を表す。"""

    injection_point_id: str
    step_id: str
    checkpoint_id: str
    operation_kind: str
    element_type: str
    position_rule: PositionRule
    comparison_targets: tuple[str, ...]


@dataclass(frozen=True)
class SourceAsset:
    """失敗注入点の基礎となる DDL 要素資産を表す。"""

    path: PurePosixPath
    git_blob_digest: str


@dataclass(frozen=True)
class ValidationResult:
    """静的照合の違反と資産由来の件数を表す。"""

    findings: tuple[str, ...]
    injection_point_count: int


EXPECTED_POSITIONS = {
    "FAILURE-INJECTION:AFTER-ROLE-CREATION": ExpectedPosition(
        operation_kind="create_no_login_bypass_owner",
        element_type="role",
        position_rule=PositionRule(
            after_command="create_role",
            command_ordinal_within_element=1,
            failure_boundary=ROLLBACK_BOUNDARY,
        ),
    ),
    "FAILURE-INJECTION:AFTER-POLICY-CHANGE": ExpectedPosition(
        operation_kind="create_and_assign_owned_objects",
        element_type="policy",
        position_rule=PositionRule(
            after_command="create_policy",
            command_ordinal_within_element=2,
            failure_boundary=ROLLBACK_BOUNDARY,
        ),
    ),
    "FAILURE-INJECTION:AFTER-FUNCTION-BODY-REPLACEMENT": ExpectedPosition(
        operation_kind="create_and_assign_owned_objects",
        element_type="function",
        position_rule=PositionRule(
            after_command="create_or_replace_function",
            command_ordinal_within_element=1,
            failure_boundary=ROLLBACK_BOUNDARY,
        ),
    ),
    "FAILURE-INJECTION:AFTER-OWNER-CHANGE": ExpectedPosition(
        operation_kind="create_and_assign_owned_objects",
        element_type="function",
        position_rule=PositionRule(
            after_command="alter_owner",
            command_ordinal_within_element=2,
            failure_boundary=ROLLBACK_BOUNDARY,
        ),
    ),
    "FAILURE-INJECTION:DURING-ACL-NORMALIZATION": ExpectedPosition(
        operation_kind="revoke_public_and_grant_named_execute",
        element_type="acl_expectation",
        position_rule=PositionRule(
            after_command="revoke_all_privileges",
            command_ordinal_within_element=1,
            failure_boundary=ROLLBACK_BOUNDARY,
        ),
    ),
}


def _read_bytes(path: Path, label: str) -> bytes:
    """ファイルを生バイト列で読む。"""
    try:
        return path.read_bytes()
    except OSError as error:
        raise FailureInjectionPointCheckError(
            f"{label}を読めない: {path}: {error}"
        ) from error


def _read_text(path: Path, label: str) -> str:
    """UTF-8 ファイルを読む。"""
    data = _read_bytes(path, label)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FailureInjectionPointCheckError(
            f"{label}がUTF-8でない: {path}: {error}"
        ) from error


def _read_json(path: Path, label: str) -> object:
    """JSON ファイルを読む。"""
    try:
        return json.loads(_read_text(path, label))
    except json.JSONDecodeError as error:
        raise FailureInjectionPointCheckError(
            f"{label}がJSONでない: {path}: {error}"
        ) from error


def _expect_object(value: object, label: str) -> dict[str, object]:
    """値が JSON object であることを検査する。"""
    if not isinstance(value, dict):
        raise FailureInjectionPointCheckError(
            f"{label}はobjectでなければならない"
        )
    if not all(isinstance(key, str) for key in value):
        raise FailureInjectionPointCheckError(
            f"{label}のkeyは文字列でなければならない"
        )
    return value


def _expect_list(value: object, label: str) -> list[object]:
    """値が JSON array であることを検査する。"""
    if not isinstance(value, list):
        raise FailureInjectionPointCheckError(
            f"{label}はarrayでなければならない"
        )
    return value


def _expect_string(value: object, label: str) -> str:
    """値が空でない文字列であることを検査する。"""
    if not isinstance(value, str) or not value:
        raise FailureInjectionPointCheckError(
            f"{label}は空でない文字列でなければならない"
        )
    return value


def _expect_positive_int(value: object, label: str) -> int:
    """値が 1 始まりの整数であることを検査する。"""
    if type(value) is not int or value < 1:
        raise FailureInjectionPointCheckError(f"{label}は正の整数でなければならない")
    return value


def _expect_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    """JSON object の key 集合を完全照合する。"""
    if set(value) != expected:
        raise FailureInjectionPointCheckError(f"{label}のkey集合が不正")


def _parse_position_rule(raw: object, label: str) -> PositionRule:
    """要素内コマンド位置と失敗境界を読む。"""
    rule = _expect_object(raw, label)
    _expect_keys(
        rule,
        {
            "after_command",
            "command_ordinal_within_element",
            "failure_boundary",
        },
        label,
    )
    return PositionRule(
        after_command=_expect_string(rule["after_command"], f"{label}.after_command"),
        command_ordinal_within_element=_expect_positive_int(
            rule["command_ordinal_within_element"],
            f"{label}.command_ordinal_within_element",
        ),
        failure_boundary=_expect_string(
            rule["failure_boundary"], f"{label}.failure_boundary"
        ),
    )


def _parse_comparison_targets(raw: object, label: str) -> tuple[str, ...]:
    """比較対象の列を読む。"""
    return tuple(
        _expect_string(value, f"{label}[{index}]")
        for index, value in enumerate(_expect_list(raw, label))
    )


def _parse_injection_points(raw: object) -> tuple[InjectionPoint, ...]:
    """失敗注入点の行を読む。"""
    points: list[InjectionPoint] = []
    for index, item in enumerate(_expect_list(raw, "injection_points")):
        label = f"injection_points[{index}]"
        point = _expect_object(item, label)
        _expect_keys(
            point,
            {
                "injection_point_id",
                "step_id",
                "checkpoint_id",
                "operation_kind",
                "element_type",
                "position_rule",
                "comparison_targets",
            },
            label,
        )
        points.append(
            InjectionPoint(
                injection_point_id=_expect_string(
                    point["injection_point_id"], f"{label}.injection_point_id"
                ),
                step_id=_expect_string(point["step_id"], f"{label}.step_id"),
                checkpoint_id=_expect_string(
                    point["checkpoint_id"], f"{label}.checkpoint_id"
                ),
                operation_kind=_expect_string(
                    point["operation_kind"], f"{label}.operation_kind"
                ),
                element_type=_expect_string(
                    point["element_type"], f"{label}.element_type"
                ),
                position_rule=_parse_position_rule(
                    point["position_rule"], f"{label}.position_rule"
                ),
                comparison_targets=_parse_comparison_targets(
                    point["comparison_targets"], f"{label}.comparison_targets"
                ),
            )
        )
    return tuple(points)


def _parse_source_asset(raw: object) -> SourceAsset:
    """DDL 要素資産への参照を読む。"""
    source = _expect_object(raw, "source_asset")
    _expect_keys(source, {"path", "git_blob_digest"}, "source_asset")
    path_text = _expect_string(source["path"], "source_asset.path")
    path = PurePosixPath(path_text)
    if path.as_posix() != path_text or path != DDL_ELEMENTS_PATH:
        raise FailureInjectionPointCheckError(
            "source_asset.pathが所定の正規相対パスでない"
        )
    digest = _expect_string(source["git_blob_digest"], "source_asset.git_blob_digest")
    if BLOB_DIGEST_RE.fullmatch(digest) is None:
        raise FailureInjectionPointCheckError(
            "source_asset.git_blob_digestがGit blob digest形式でない"
        )
    return SourceAsset(path=path, git_blob_digest=digest)


def _parse_asset(raw: object) -> tuple[SourceAsset, tuple[InjectionPoint, ...]]:
    """失敗注入点資産の構造を検査して値を読む。"""
    asset = _expect_object(raw, "失敗注入点資産")
    _expect_keys(
        asset,
        {"schema_version", "asset_kind", "source_asset", "injection_points"},
        "失敗注入点資産",
    )
    if type(asset["schema_version"]) is not int or asset["schema_version"] != 1:
        raise FailureInjectionPointCheckError("schema_versionが未対応")
    if asset["asset_kind"] != ASSET_KIND:
        raise FailureInjectionPointCheckError("asset_kindが不正")
    return (
        _parse_source_asset(asset["source_asset"]),
        _parse_injection_points(asset["injection_points"]),
    )


def _parse_ordered_steps(raw: object) -> dict[str, str]:
    """DDL 要素資産から step ID と operation kind の対応を読む。"""
    asset = _expect_object(raw, "ddl-elements")
    claim = _expect_object(asset.get("provisioning_claim"), "provisioning_claim")
    steps: dict[str, str] = {}
    for index, item in enumerate(
        _expect_list(claim.get("ordered_steps"), "provisioning_claim.ordered_steps")
    ):
        label = f"provisioning_claim.ordered_steps[{index}]"
        step = _expect_object(item, label)
        step_id = _expect_string(step.get("step_id"), f"{label}.step_id")
        operation_kind = _expect_string(
            step.get("operation_kind"), f"{label}.operation_kind"
        )
        if step_id in steps:
            raise FailureInjectionPointCheckError(
                "provisioning_claim.ordered_stepsのstep_idが重複"
            )
        steps[step_id] = operation_kind
    if not steps:
        raise FailureInjectionPointCheckError(
            "provisioning_claim.ordered_stepsが空"
        )
    return steps


def _format_values(values: Collection[str]) -> str:
    """文字列集合を診断用に安定整列する。"""
    return ", ".join(sorted(values)) or "なし"


def _checkpoint_step_id(checkpoint_id: str) -> str | None:
    """checkpoint ID が正形式なら埋め込まれた step ID を返す。"""
    step_id, separator, ordinal_text = checkpoint_id.rpartition("#")
    if (
        not separator
        or not step_id
        or not ordinal_text.isascii()
        or not ordinal_text.isdecimal()
        or int(ordinal_text) < 1
    ):
        return None
    return step_id


def validate_repository(root: Path) -> ValidationResult:
    """リポジトリ内の失敗注入点資産を静的照合する。

    Args:
        root: リポジトリルート。

    Returns:
        違反一覧と資産から導出した件数。
    """
    root = root.resolve()
    source_asset, points = _parse_asset(
        _read_json(root / ASSET_PATH, "失敗注入点資産")
    )
    source_data = _read_bytes(root / source_asset.path, "ddl-elements")
    ordered_steps = _parse_ordered_steps(json.loads(source_data))
    findings: list[str] = []

    current_digest = git_blob_digest(source_data)
    if current_digest != source_asset.git_blob_digest:
        findings.append(
            f"{source_asset.path}: git_blob_digestが現ファイルと不一致; "
            "digest の取り直しが必要"
        )

    id_counts = Counter(point.injection_point_id for point in points)
    actual_ids = set(id_counts)
    expected_ids = set(EXPECTED_POSITIONS)
    if len(points) != len(EXPECTED_POSITIONS):
        findings.append(
            "injection_points件数が閉じたID集合と不一致: "
            f"期待={len(EXPECTED_POSITIONS)} 実際={len(points)}"
        )
    missing_ids = expected_ids - actual_ids
    extra_ids = actual_ids - expected_ids
    if missing_ids or extra_ids:
        findings.append(
            "injection_point_idが閉じた集合と不一致: "
            f"不足={_format_values(missing_ids)} 余分={_format_values(extra_ids)}"
        )
    duplicate_ids = {value for value, count in id_counts.items() if count > 1}
    if duplicate_ids:
        findings.append(
            f"injection_point_idが重複: {_format_values(duplicate_ids)}"
        )

    checkpoint_counts = Counter(point.checkpoint_id for point in points)
    duplicate_checkpoints = {
        value for value, count in checkpoint_counts.items() if count > 1
    }
    if duplicate_checkpoints:
        findings.append(
            "checkpoint_idが相互に異ならない: "
            f"{_format_values(duplicate_checkpoints)}"
        )

    for point in points:
        expected_position = EXPECTED_POSITIONS.get(point.injection_point_id)
        actual_position = (
            point.operation_kind,
            point.element_type,
            point.position_rule,
        )
        if expected_position is not None:
            expected_tuple = (
                expected_position.operation_kind,
                expected_position.element_type,
                expected_position.position_rule,
            )
            if actual_position != expected_tuple:
                findings.append(
                    f"{point.injection_point_id}: "
                    "(operation_kind, element_type, position_rule)が所定位置と不一致"
                )

        expected_operation = ordered_steps.get(point.step_id)
        if expected_operation is None:
            findings.append(
                f"{point.injection_point_id}: step_idがordered_stepsに存在しない"
            )
        elif point.operation_kind != expected_operation:
            findings.append(
                f"{point.injection_point_id}: "
                "operation_kindがordered_stepsのstep_idと不整合"
            )

        checkpoint_step_id = _checkpoint_step_id(point.checkpoint_id)
        if checkpoint_step_id is None:
            findings.append(
                f"{point.injection_point_id}: checkpoint_idの形式が不正"
            )
        elif checkpoint_step_id != point.step_id:
            findings.append(
                f"{point.injection_point_id}: checkpoint_idとstep_idが不整合"
            )

        if (
            point.operation_kind == "create_and_assign_owned_objects"
            and point.element_type == "function"
            and point.position_rule.failure_boundary != ROLLBACK_BOUNDARY
        ):
            findings.append(
                f"{point.injection_point_id}: D-7違反; 関数作成とPUBLIC REVOKEの間を"
                "確定境界にせず現transactionをrollbackする必要がある"
            )

        targets = point.comparison_targets
        if not targets:
            findings.append(
                f"{point.injection_point_id}: comparison_targetsが空"
            )
        duplicate_targets = {
            value for value, count in Counter(targets).items() if count > 1
        }
        if duplicate_targets:
            findings.append(
                f"{point.injection_point_id}: comparison_targetsが重複: "
                f"{_format_values(duplicate_targets)}"
            )
        unknown_targets = set(targets) - COMPARISON_TARGETS
        if unknown_targets:
            findings.append(
                f"{point.injection_point_id}: comparison_targetsが閉じた語彙の外: "
                f"{_format_values(unknown_targets)}"
            )
        missing_targets = COMPARISON_TARGETS - set(targets)
        if missing_targets:
            findings.append(
                f"{point.injection_point_id}: R-5の比較面が不足: "
                f"{_format_values(missing_targets)}"
            )

    return ValidationResult(
        findings=tuple(findings),
        injection_point_count=len(points),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: 引数列。省略時はプロセスの引数を使う。

    Returns:
        解釈済みの引数。
    """
    parser = argparse.ArgumentParser(description="失敗注入点資産を静的照合する")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="リポジトリルート")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """静的照合を実行して終了コードを返す。

    Args:
        argv: 引数列。省略時はプロセスの引数を使う。

    Returns:
        合格は 0、規約違反は 1、入力不正は 2。
    """
    try:
        args = parse_args(argv)
        result = validate_repository(args.root)
    except (FailureInjectionPointCheckError, json.JSONDecodeError) as error:
        print(f"authz-failure-injection-points: 入力不正: {error}", file=sys.stderr)
        return 2
    if result.findings:
        for finding in result.findings:
            print(
                f"authz-failure-injection-points: 違反: {finding}",
                file=sys.stderr,
            )
        return 1
    print(
        "authz-failure-injection-points: OK "
        f"injection_points={result.injection_point_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
