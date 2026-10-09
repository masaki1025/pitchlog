"""cases 展開器の実行時ファイル読み取りを宣言と突合する。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

try:
    import check_deriver_dependencies as dependency_core
except ModuleNotFoundError:  # pragma: no cover - packageとして読み込む経路
    from scripts import check_deriver_dependencies as dependency_core

POLICY_PATH = PurePosixPath(
    "contracts/state-transition/expander_dependency_policy_v1.json"
)
POLICY_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/expander_dependency_policy_schema_v1.json"
)

_T = TypeVar("_T")


class ExpanderDependencyError(ValueError):
    """展開器の依存宣言または実行時読み取りが不正な場合を表す。"""


@dataclass(frozen=True)
class ExpanderRule:
    """1 つの展開器に対する資産側の許可入力を表す。"""

    expander_id: str
    planned_implementation_step: int
    output: str
    allowed_read_paths: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class ExpanderDependencyPolicy:
    """展開器の依存宣言から検査に必要な値だけを保持する。"""

    policy_id: str
    version: int
    claim_boundary: Mapping[str, Any]
    trace_spec: Mapping[str, Any]
    expanders: Mapping[str, ExpanderRule]


@dataclass(frozen=True)
class ExpanderTrace:
    """許可された呼出区間で観測したファイル読み取りを保持する。"""

    expander_id: str
    observed_read_paths: tuple[PurePosixPath, ...]


def _translate_error(error: dependency_core.DeriverDependencyError) -> None:
    """共通機構の診断を展開器検査の例外へ変換する。"""
    raise ExpanderDependencyError(str(error)) from error


def load_policy(
    root: Path, policy_path: PurePosixPath = POLICY_PATH
) -> ExpanderDependencyPolicy:
    """資産側の展開器依存宣言を検証して読み込む。

    Args:
        root: リポジトリルート。
        policy_path: リポジトリ相対の依存宣言パス。

    Returns:
        実行時トレースに使用できる依存宣言。

    Raises:
        ExpanderDependencyError: 宣言が閉じた形式を満たさない場合。
    """
    try:
        raw = dependency_core.load_dependency_policy_document(
            root, policy_path, POLICY_SCHEMA_PATH, "展開器依存宣言"
        )
        dependency_core._exact_keys(
            raw,
            {
                "schemaVersion",
                "policyId",
                "version",
                "claimBoundary",
                "traceSpec",
                "expanders",
            },
            "展開器依存宣言",
        )
        schema_version = raw["schemaVersion"]
        version = raw["version"]
        if schema_version != 1 or isinstance(schema_version, bool):
            raise dependency_core.DeriverDependencyError("schemaVersionが1でない")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise dependency_core.DeriverDependencyError("versionが正の整数でない")

        claim_boundary = dependency_core._object(
            raw["claimBoundary"], "claimBoundary"
        )
        dependency_core._exact_keys(
            claim_boundary,
            {
                "subject",
                "mechanicallyChecked",
                "notGuaranteed",
                "deriverCoverage",
                "fixtureIndependenceClaim",
                "clauseBranchRegisterIndependence",
            },
            "claimBoundary",
        )
        dependency_core._nonempty_string(
            claim_boundary["subject"], "claimBoundary.subject"
        )
        dependency_core._nonempty_string(
            claim_boundary["mechanicallyChecked"],
            "claimBoundary.mechanicallyChecked",
        )
        dependency_core._string_list(
            claim_boundary["notGuaranteed"], "claimBoundary.notGuaranteed"
        )
        for key in (
            "deriverCoverage",
            "fixtureIndependenceClaim",
            "clauseBranchRegisterIndependence",
        ):
            dependency_core._nonempty_string(
                claim_boundary[key], f"claimBoundary.{key}"
            )

        trace_spec = dependency_core._object(raw["traceSpec"], "traceSpec")
        dependency_core._exact_keys(
            trace_spec,
            {
                "mechanism",
                "pathIdentity",
                "outsideRepositoryAction",
                "unresolvablePathAction",
                "subprocessAction",
            },
            "traceSpec",
        )
        for key, value in trace_spec.items():
            dependency_core._nonempty_string(value, f"traceSpec.{key}")

        raw_expanders = raw["expanders"]
        if not isinstance(raw_expanders, list) or not raw_expanders:
            raise dependency_core.DeriverDependencyError("expandersが空である")
        expanders: dict[str, ExpanderRule] = {}
        for index, raw_expander in enumerate(raw_expanders):
            expander = dependency_core._object(
                raw_expander, f"expanders[{index}]"
            )
            dependency_core._exact_keys(
                expander,
                {
                    "expanderId",
                    "plannedImplementationStep",
                    "output",
                    "allowedReadPaths",
                },
                f"expanders[{index}]",
            )
            expander_id = dependency_core._nonempty_string(
                expander["expanderId"], f"expanders[{index}].expanderId"
            )
            if expander_id in expanders:
                raise dependency_core.DeriverDependencyError(
                    f"expanderIdが重複している: {expander_id!r}"
                )
            step = expander["plannedImplementationStep"]
            if not isinstance(step, int) or isinstance(step, bool) or step < 1:
                raise dependency_core.DeriverDependencyError(
                    f"expanders[{index}].plannedImplementationStepが正の整数でない"
                )
            allowed_values = dependency_core._string_list(
                expander["allowedReadPaths"],
                f"expanders[{index}].allowedReadPaths",
            )
            allowed_paths = tuple(
                dependency_core._repository_path(
                    root, value, f"expanders[{index}].allowedReadPaths"
                )
                for value in allowed_values
            )
            expanders[expander_id] = ExpanderRule(
                expander_id=expander_id,
                planned_implementation_step=step,
                output=dependency_core._nonempty_string(
                    expander["output"], f"expanders[{index}].output"
                ),
                allowed_read_paths=allowed_paths,
            )
    except dependency_core.DeriverDependencyError as error:
        _translate_error(error)

    return ExpanderDependencyPolicy(
        policy_id=dependency_core._nonempty_string(raw["policyId"], "policyId"),
        version=version,
        claim_boundary=claim_boundary,
        trace_spec=trace_spec,
        expanders=expanders,
    )


def trace_expander_file_reads(
    root: Path,
    policy: ExpanderDependencyPolicy,
    expander_id: str,
    operation: Callable[[], _T],
) -> tuple[_T, ExpanderTrace]:
    """宣言済み展開器の呼出区間を共通機構で追跡する。

    Args:
        root: リポジトリルート。
        policy: 資産側から読み込んだ展開器依存宣言。
        expander_id: 実行する展開器の宣言 ID。
        operation: 追跡対象の展開処理。

    Returns:
        展開処理の戻り値と、許可された読み取りの証跡。

    Raises:
        ExpanderDependencyError: 展開器が未宣言か、共通依存検査に違反した場合。
    """
    rule = policy.expanders.get(expander_id)
    if rule is None:
        raise ExpanderDependencyError(f"未宣言の展開器である: {expander_id!r}")
    try:
        result, observed = dependency_core.trace_allowed_file_reads(
            root,
            rule.allowed_read_paths,
            expander_id,
            "展開器",
            operation,
        )
    except dependency_core.DeriverDependencyError as error:
        _translate_error(error)
    return result, ExpanderTrace(
        expander_id=expander_id,
        observed_read_paths=observed,
    )


def validate_repository_policy(root: Path) -> ExpanderDependencyPolicy:
    """リポジトリの展開器依存宣言を検証する。

    Args:
        root: リポジトリルート。

    Returns:
        検証済みの依存宣言。
    """
    return load_policy(root)


def main(argv: Sequence[str] | None = None) -> int:
    """依存宣言の閉包と安全なパス解決を検証する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        policy = validate_repository_policy(args.root)
    except ExpanderDependencyError as error:
        print(f"expander dependency: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "expander dependency: PASS "
        f"(policy={policy.policy_id}, expanders={len(policy.expanders)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
