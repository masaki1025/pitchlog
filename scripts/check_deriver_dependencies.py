"""requiredSet 導出器の実行時ファイル読み取りを宣言と突合する。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar, cast

try:
    import check_input_axes_descriptor as descriptor_checker
except ModuleNotFoundError:  # pragma: no cover - packageとして読み込む経路
    from scripts import check_input_axes_descriptor as descriptor_checker

POLICY_PATH = PurePosixPath(
    "contracts/state-transition/deriver_dependency_policy_v1.json"
)
POLICY_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/deriver_dependency_policy_schema_v1.json"
)

_T = TypeVar("_T")


class DeriverDependencyError(ValueError):
    """導出器の依存宣言または実行時読み取りが不正な場合を表す。"""


@dataclass(frozen=True)
class DeriverRule:
    """1 つの導出器に対する資産側の許可入力を表す。"""

    deriver_id: str
    planned_implementation_step: int
    output: str
    allowed_read_paths: tuple[PurePosixPath, ...]


@dataclass(frozen=True)
class DeriverDependencyPolicy:
    """導出器の依存宣言から検査に必要な値だけを保持する。"""

    policy_id: str
    version: int
    claim_boundary: Mapping[str, Any]
    trace_spec: Mapping[str, Any]
    derivers: Mapping[str, DeriverRule]


@dataclass(frozen=True)
class DeriverTrace:
    """許可された呼出区間で観測したファイル読み取りを保持する。"""

    deriver_id: str
    observed_read_paths: tuple[PurePosixPath, ...]


def _object(value: object, label: str) -> dict[str, Any]:
    """文字列キーの object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DeriverDependencyError(f"{label}がobjectでない")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    """object のキー集合が宣言形式と一致することを確認する。"""
    if set(value) != expected:
        raise DeriverDependencyError(
            f"{label}のキーがexact-set不一致: "
            f"expected={sorted(expected)!r}; actual={sorted(value)!r}"
        )


def _nonempty_string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise DeriverDependencyError(f"{label}が空でない文字列でない")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    """重複のない空でない文字列配列を返す。"""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise DeriverDependencyError(f"{label}が重複のない空でない文字列配列でない")
    return tuple(value)


def _load_json(path: Path) -> dict[str, Any]:
    """重複キーを拒否して JSON object を読み込む。"""

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise DeriverDependencyError(f"JSONキーが重複している: {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeriverDependencyError(f"依存宣言を読み込めない: {path}: {error}") from error
    return _object(value, "依存宣言")


def load_dependency_policy_document(
    root: Path,
    policy_path: PurePosixPath,
    schema_path: PurePosixPath,
    label: str,
) -> dict[str, Any]:
    """共通形式の依存宣言を schema 検証して返す。

    Args:
        root: リポジトリルート。
        policy_path: リポジトリ相対の依存宣言パス。
        schema_path: リポジトリ相対の schema パス。
        label: 診断に用いる資産名。

    Returns:
        schema 検証済みの依存宣言 object。

    Raises:
        DeriverDependencyError: 宣言または schema を検証できない場合。
    """
    raw = _load_json(root / Path(*policy_path.parts))
    try:
        raw_schema = descriptor_checker.load_json(
            root / Path(*schema_path.parts), f"{label}schema"
        )
        schema = _object(raw_schema, f"{label}schema")
        descriptor_checker._validate_instance(raw, schema, schema, label)
    except descriptor_checker.DescriptorCheckError as error:
        raise DeriverDependencyError(str(error)) from error
    return raw


def _repository_path(root: Path, value: str, label: str) -> PurePosixPath:
    """解決後もリポジトリ内にある相対パスを返す。"""
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in value:
        raise DeriverDependencyError(f"{label}が安全なリポジトリ相対パスでない: {value!r}")
    resolved_root = root.resolve()
    resolved = (resolved_root / Path(*path.parts)).resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise DeriverDependencyError(f"{label}がリポジトリ外へ解決される: {value!r}") from error
    return path


def load_policy(
    root: Path, policy_path: PurePosixPath = POLICY_PATH
) -> DeriverDependencyPolicy:
    """資産側の導出器依存宣言を検証して読み込む。

    Args:
        root: リポジトリルート。
        policy_path: リポジトリ相対の依存宣言パス。

    Returns:
        実行時トレースに使用できる依存宣言。

    Raises:
        DeriverDependencyError: 宣言が閉じた形式を満たさない場合。
    """
    raw = load_dependency_policy_document(
        root, policy_path, POLICY_SCHEMA_PATH, "導出器依存宣言"
    )
    _exact_keys(
        raw,
        {
            "schemaVersion",
            "policyId",
            "version",
            "claimBoundary",
            "traceSpec",
            "derivers",
        },
        "依存宣言",
    )
    schema_version = raw["schemaVersion"]
    version = raw["version"]
    if schema_version != 1 or isinstance(schema_version, bool):
        raise DeriverDependencyError("schemaVersionが1でない")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise DeriverDependencyError("versionが正の整数でない")

    claim_boundary = _object(raw["claimBoundary"], "claimBoundary")
    _exact_keys(
        claim_boundary,
        {"subject", "mechanicallyChecked", "notGuaranteed", "expanderCoverage"},
        "claimBoundary",
    )
    _nonempty_string(claim_boundary["subject"], "claimBoundary.subject")
    _nonempty_string(
        claim_boundary["mechanicallyChecked"], "claimBoundary.mechanicallyChecked"
    )
    _string_list(claim_boundary["notGuaranteed"], "claimBoundary.notGuaranteed")
    _nonempty_string(
        claim_boundary["expanderCoverage"], "claimBoundary.expanderCoverage"
    )

    trace_spec = _object(raw["traceSpec"], "traceSpec")
    _exact_keys(
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
        _nonempty_string(value, f"traceSpec.{key}")

    raw_derivers = raw["derivers"]
    if not isinstance(raw_derivers, list) or not raw_derivers:
        raise DeriverDependencyError("deriversが空である")
    derivers: dict[str, DeriverRule] = {}
    for index, raw_deriver in enumerate(raw_derivers):
        deriver = _object(raw_deriver, f"derivers[{index}]")
        _exact_keys(
            deriver,
            {"deriverId", "plannedImplementationStep", "output", "allowedReadPaths"},
            f"derivers[{index}]",
        )
        deriver_id = _nonempty_string(deriver["deriverId"], f"derivers[{index}].deriverId")
        if deriver_id in derivers:
            raise DeriverDependencyError(f"deriverIdが重複している: {deriver_id!r}")
        step = deriver["plannedImplementationStep"]
        if not isinstance(step, int) or isinstance(step, bool) or step < 1:
            raise DeriverDependencyError(
                f"derivers[{index}].plannedImplementationStepが正の整数でない"
            )
        allowed_values = _string_list(
            deriver["allowedReadPaths"], f"derivers[{index}].allowedReadPaths"
        )
        allowed_paths = tuple(
            _repository_path(root, value, f"derivers[{index}].allowedReadPaths")
            for value in allowed_values
        )
        derivers[deriver_id] = DeriverRule(
            deriver_id=deriver_id,
            planned_implementation_step=step,
            output=_nonempty_string(deriver["output"], f"derivers[{index}].output"),
            allowed_read_paths=allowed_paths,
        )

    return DeriverDependencyPolicy(
        policy_id=_nonempty_string(raw["policyId"], "policyId"),
        version=version,
        claim_boundary=claim_boundary,
        trace_spec=trace_spec,
        derivers=derivers,
    )


def _is_read_open(mode: object, flags: object) -> bool:
    """CPython の open 監査イベントが読み取りを含むか判定する。"""
    if isinstance(mode, str):
        return "r" in mode or "+" in mode
    if isinstance(flags, int):
        return flags & os.O_ACCMODE != os.O_WRONLY
    return True


def _observed_repository_path(
    root: Path, raw_path: object, executable_label: str
) -> PurePosixPath:
    """open 監査イベントのパスをリポジトリ相対へ正規化する。"""
    if isinstance(raw_path, int):
        raise DeriverDependencyError("追跡開始前に開かれたファイル記述子の読み取りは判定不能")
    if not isinstance(raw_path, (str, bytes, os.PathLike)):
        raise DeriverDependencyError("open監査イベントのパスを解決できない")
    try:
        path_value = os.fsdecode(raw_path)
    except TypeError as error:
        raise DeriverDependencyError("open監査イベントのパスを解決できない") from error
    path = Path(path_value)
    resolved = path.resolve(strict=False) if path.is_absolute() else (Path.cwd() / path).resolve()
    resolved_root = root.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as error:
        raise DeriverDependencyError(
            f"{executable_label}がリポジトリ外を読み取ろうとした: {resolved}"
        ) from error
    return PurePosixPath(relative.as_posix())


def trace_allowed_file_reads(
    root: Path,
    allowed_read_paths: tuple[PurePosixPath, ...],
    executable_id: str,
    executable_label: str,
    operation: Callable[[], _T],
) -> tuple[_T, tuple[PurePosixPath, ...]]:
    """実行可能処理の呼出区間で観測した読み取りを allowlist と突合する。

    この共通機構が検査するのは、呼出区間に CPython の監査イベントとして
    現れたファイル open だけである。呼出側の宣言が列挙する非保証範囲を
    確認したことにはしない。

    Args:
        root: リポジトリルート。
        allowed_read_paths: 資産側が宣言した読み取り許可集合。
        executable_id: 実行する処理の宣言 ID。
        executable_label: 診断に用いる処理種別。
        operation: 追跡対象の実行可能処理。

    Returns:
        実行結果と、許可された読み取りのリポジトリ相対パス。

    Raises:
        DeriverDependencyError: allowlist 外の読み取り、または子プロセスへ
            追跡を逃がす実行を観測した場合。
    """
    resolved_root = root.resolve()
    allowed = {
        (resolved_root / Path(*path.parts)).resolve(strict=False): path
        for path in allowed_read_paths
    }
    active = True
    observed: list[PurePosixPath] = []
    violations: list[DeriverDependencyError] = []

    def audit(event: str, args: tuple[object, ...]) -> None:
        if not active:
            return
        if event in {"subprocess.Popen", "os.system"}:
            error = DeriverDependencyError(
                f"{executable_label}が未追跡の子プロセスを起動しようとした"
            )
            violations.append(error)
            raise error
        if event != "open" or len(args) < 3 or not _is_read_open(args[1], args[2]):
            return
        try:
            relative = _observed_repository_path(
                resolved_root, args[0], executable_label
            )
        except DeriverDependencyError as error:
            violations.append(error)
            raise
        resolved = (resolved_root / Path(*relative.parts)).resolve(strict=False)
        if resolved not in allowed:
            error = DeriverDependencyError(
                f"{executable_label} {executable_id!r} がallowlist外を読み取ろうとした: "
                f"{relative}"
            )
            violations.append(error)
            raise error
        observed.append(allowed[resolved])

    sys.addaudithook(audit)
    caught: BaseException | None = None
    result: _T | None = None
    try:
        result = operation()
    except BaseException as error:  # noqa: BLE001 - 監査違反を握り潰させないため保持する
        caught = error
    finally:
        active = False
    if violations:
        raise violations[0] from caught
    if caught is not None:
        raise caught
    return cast(_T, result), tuple(dict.fromkeys(observed))


def trace_deriver_file_reads(
    root: Path,
    policy: DeriverDependencyPolicy,
    deriver_id: str,
    operation: Callable[[], _T],
) -> tuple[_T, DeriverTrace]:
    """宣言済み導出器の呼出区間を共通機構で追跡する。

    Args:
        root: リポジトリルート。
        policy: 資産側から読み込んだ導出器依存宣言。
        deriver_id: 実行する導出器の宣言 ID。
        operation: 追跡対象の導出処理。

    Returns:
        導出処理の戻り値と、許可された読み取りの証跡。

    Raises:
        DeriverDependencyError: 導出器が未宣言か、共通依存検査に違反した場合。
    """
    rule = policy.derivers.get(deriver_id)
    if rule is None:
        raise DeriverDependencyError(f"未宣言の導出器である: {deriver_id!r}")
    result, observed = trace_allowed_file_reads(
        root,
        rule.allowed_read_paths,
        deriver_id,
        "導出器",
        operation,
    )
    return result, DeriverTrace(
        deriver_id=deriver_id,
        observed_read_paths=observed,
    )


def validate_repository_policy(root: Path) -> DeriverDependencyPolicy:
    """リポジトリの導出器依存宣言を検証する。

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
    except DeriverDependencyError as error:
        print(f"deriver dependency: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "deriver dependency: PASS "
        f"(policy={policy.policy_id}, derivers={len(policy.derivers)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
