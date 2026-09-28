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
ROW_REQUIREMENT_RULES_PATH = PurePosixPath(
    "contracts/state-transition/required_set_row_rules_v1.json"
)
ROW_REQUIREMENT_RULES_SCHEMA_PATH = PurePosixPath(
    "contracts/state-transition/required_set_row_rules_schema_v1.json"
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


@dataclass(frozen=True)
class RowRequirement:
    """語彙 ID と前提条件 partition から得た 1 行の要求を表す。"""

    event_kind: str
    result_id: str
    partition_rule_id: str
    partition_id: str
    source_clause_ids: tuple[str, ...]

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """出力列に依存しない行要求の同一性を返す。"""
        return (
            self.event_kind,
            self.result_id,
            self.partition_rule_id,
            self.partition_id,
        )


@dataclass(frozen=True)
class InputCoordinateRequirement:
    """descriptor の軸 1 件・coverage 値 1 件に対する要求を表す。"""

    axis_id: str
    classification: str
    coverage_value: object
    coverage_value_identity: str
    row_layers: tuple[str, ...]
    natural_key_role: str
    natural_key_field: str | None
    natural_key_value_projection: str
    when_clause_id: str | None
    when_state: str | None

    @property
    def identity(self) -> tuple[str, str]:
        """軸間の組合せを含まない軸ごとの要求 identity を返す。"""
        return (self.axis_id, self.coverage_value_identity)


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


def _possibly_empty_string_list(value: object, label: str) -> tuple[str, ...]:
    """重複のない文字列配列を返す。"""
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise DeriverDependencyError(f"{label}が重複のない文字列配列でない")
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


def load_row_requirement_rules_document(
    root: Path,
    rules_path: PurePosixPath = ROW_REQUIREMENT_RULES_PATH,
    schema_path: PurePosixPath = ROW_REQUIREMENT_RULES_SCHEMA_PATH,
) -> dict[str, Any]:
    """行要求規則を schema 検証して返す。

    Args:
        root: リポジトリルート。
        rules_path: 行要求規則のリポジトリ相対パス。
        schema_path: 規則 schema のリポジトリ相対パス。

    Returns:
        schema 検証済みの行要求規則。

    Raises:
        DeriverDependencyError: 規則または schema が不正な場合。
    """
    return load_dependency_policy_document(
        root,
        rules_path,
        schema_path,
        "requiredSet行要求規則",
    )


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


def _validated_clause_ids(
    value: object,
    source_clause_ids: frozenset[str],
    label: str,
) -> tuple[str, ...]:
    """空でなく実在する要件書条文 ID を返す。"""
    clause_ids = _possibly_empty_string_list(value, label)
    if not clause_ids:
        raise DeriverDependencyError(f"{label}が空であり、典拠の無い分割規則である")
    missing = sorted(set(clause_ids) - source_clause_ids)
    if missing:
        raise DeriverDependencyError(f"{label}が実在しない条文IDを含む: {missing!r}")
    return clause_ids


def _vocabulary_axes(seed: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """語彙シードから軸ごとの ID 集合を宣言順で返す。"""
    raw_axes = seed.get("axes")
    if not isinstance(raw_axes, list) or not raw_axes:
        raise DeriverDependencyError("語彙シードaxesが空である")
    axes: dict[str, tuple[str, ...]] = {}
    all_ids: set[str] = set()
    for axis_index, raw_axis in enumerate(raw_axes):
        axis = _object(raw_axis, f"語彙シードaxes[{axis_index}]")
        axis_id = _nonempty_string(
            axis.get("axisId"), f"語彙シードaxes[{axis_index}].axisId"
        )
        if axis_id in axes:
            raise DeriverDependencyError(f"語彙軸IDが重複している: {axis_id!r}")
        raw_entries = axis.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise DeriverDependencyError(f"語彙軸{axis_id!r}のentriesが空である")
        entry_ids: list[str] = []
        for entry_index, raw_entry in enumerate(raw_entries):
            entry = _object(
                raw_entry, f"語彙軸{axis_id!r}.entries[{entry_index}]"
            )
            entry_id = _nonempty_string(
                entry.get("id"), f"語彙軸{axis_id!r}.entries[{entry_index}].id"
            )
            if entry_id in all_ids:
                raise DeriverDependencyError(f"語彙IDが大域重複している: {entry_id!r}")
            all_ids.add(entry_id)
            entry_ids.append(entry_id)
        axes[axis_id] = tuple(entry_ids)
    return axes


def _validate_vocabulary_binding(
    manifest: Mapping[str, Any],
    seed: Mapping[str, Any],
    vocabulary: Mapping[str, Any],
) -> None:
    """規則・manifest・シードの ID、パス、版 binding を突合する。"""
    _exact_keys(
        vocabulary,
        {"manifestPath", "vocabularyId", "seedPath"},
        "行要求規則.vocabulary",
    )
    vocabulary_id = _nonempty_string(
        vocabulary["vocabularyId"], "行要求規則.vocabulary.vocabularyId"
    )
    seed_path = _nonempty_string(
        vocabulary["seedPath"], "行要求規則.vocabulary.seedPath"
    )
    declarations = manifest.get("seeds")
    if not isinstance(declarations, list):
        raise DeriverDependencyError("語彙manifest.seedsが配列でない")
    matches = [
        _object(item, f"語彙manifest.seeds[{index}]")
        for index, item in enumerate(declarations)
        if isinstance(item, dict) and item.get("vocabularyId") == vocabulary_id
    ]
    if len(matches) != 1:
        raise DeriverDependencyError(
            f"語彙manifestのvocabularyIdがちょうど1件でない: {vocabulary_id!r}"
        )
    declaration = matches[0]
    if declaration.get("path") != seed_path:
        raise DeriverDependencyError("行要求規則とmanifestの語彙seed pathが一致しない")
    if seed.get("vocabularyId") != vocabulary_id:
        raise DeriverDependencyError("行要求規則と語彙シードのvocabularyIdが一致しない")
    if declaration.get("version") != seed.get("version"):
        raise DeriverDependencyError("manifestと語彙シードのversionが一致しない")
    if declaration.get("schemaVersion") != seed.get("schemaVersion"):
        raise DeriverDependencyError("manifestと語彙シードのschemaVersionが一致しない")


def derive_row_requirements_from_documents(
    rules: Mapping[str, Any],
    manifest: Mapping[str, Any],
    seed: Mapping[str, Any],
    source_clause_ids: frozenset[str],
) -> tuple[RowRequirement, ...]:
    """機械可読な軸分類と分割規則から行要求を導出する。

    Args:
        rules: 行要求規則。
        manifest: 共有語彙 manifest。
        seed: manifest が指す語彙シード。
        source_clause_ids: 要件書から機械抽出した名前空間付き条文 ID。

    Returns:
        語彙 ID と抽象 partition identity の直積で得た行要求。

    Raises:
        DeriverDependencyError: 軸が未分類、語彙 ID が未帰属・重複帰属、
            または分割規則に実在する典拠がない場合。
    """
    _exact_keys(
        rules,
        {
            "schemaVersion",
            "version",
            "sourceClausePath",
            "vocabulary",
            "axisAssignments",
            "partitionRules",
        },
        "行要求規則",
    )
    vocabulary = _object(rules["vocabulary"], "行要求規則.vocabulary")
    _validate_vocabulary_binding(manifest, seed, vocabulary)
    axes = _vocabulary_axes(seed)

    raw_assignments = rules["axisAssignments"]
    if not isinstance(raw_assignments, list) or not raw_assignments:
        raise DeriverDependencyError("axisAssignmentsが空である")
    assignments: dict[str, tuple[str | None, tuple[str, ...]]] = {}
    result_id_event_kinds: dict[str, str] = {}
    for index, raw_assignment in enumerate(raw_assignments):
        assignment = _object(raw_assignment, f"axisAssignments[{index}]")
        axis_id = _nonempty_string(
            assignment.get("axisId"), f"axisAssignments[{index}].axisId"
        )
        if axis_id in assignments:
            raise DeriverDependencyError(f"語彙軸分類が重複している: {axis_id!r}")
        role = _nonempty_string(
            assignment.get("role"), f"axisAssignments[{index}].role"
        )
        _nonempty_string(
            assignment.get("reason"), f"axisAssignments[{index}].reason"
        )
        clause_ids = _validated_clause_ids(
            assignment.get("sourceClauseIds"),
            source_clause_ids,
            f"axisAssignments[{index}].sourceClauseIds",
        )
        if role == "result-id-source":
            _exact_keys(
                assignment,
                {"axisId", "role", "eventKind", "reason", "sourceClauseIds"},
                f"axisAssignments[{index}]",
            )
            event_kind = _nonempty_string(
                assignment["eventKind"], f"axisAssignments[{index}].eventKind"
            )
            for result_id in axes.get(axis_id, ()):
                result_id_event_kinds[result_id] = event_kind
            assignments[axis_id] = (event_kind, clause_ids)
        elif role == "not-result-id-source":
            _exact_keys(
                assignment,
                {"axisId", "role", "reason", "sourceClauseIds"},
                f"axisAssignments[{index}]",
            )
            assignments[axis_id] = (None, clause_ids)
        else:
            raise DeriverDependencyError(
                f"axisAssignments[{index}].roleが未定義である: {role!r}"
            )

    missing_axes = sorted(set(axes) - set(assignments))
    unexpected_axes = sorted(set(assignments) - set(axes))
    if missing_axes or unexpected_axes:
        raise DeriverDependencyError(
            "語彙軸分類がexact-set不一致: "
            f"missing={missing_axes!r}; unexpected={unexpected_axes!r}"
        )

    raw_rules = rules["partitionRules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise DeriverDependencyError("partitionRulesが空である")
    assigned_result_ids: set[str] = set()
    rule_ids: set[str] = set()
    requirements: list[RowRequirement] = []
    for rule_index, raw_rule in enumerate(raw_rules):
        rule = _object(raw_rule, f"partitionRules[{rule_index}]")
        _exact_keys(
            rule,
            {
                "partitionRuleId",
                "vocabularyIds",
                "partitions",
                "sourceClauseIds",
            },
            f"partitionRules[{rule_index}]",
        )
        rule_id = _nonempty_string(
            rule["partitionRuleId"],
            f"partitionRules[{rule_index}].partitionRuleId",
        )
        if rule_id in rule_ids:
            raise DeriverDependencyError(f"partitionRuleIdが重複している: {rule_id!r}")
        rule_ids.add(rule_id)
        vocabulary_ids = _string_list(
            rule["vocabularyIds"], f"partitionRules[{rule_index}].vocabularyIds"
        )
        partitions = _string_list(
            rule["partitions"], f"partitionRules[{rule_index}].partitions"
        )
        clause_ids = _validated_clause_ids(
            rule["sourceClauseIds"],
            source_clause_ids,
            f"partitionRules[{rule_index}].sourceClauseIds",
        )
        for result_id in vocabulary_ids:
            event_kind = result_id_event_kinds.get(result_id)
            if event_kind is None:
                raise DeriverDependencyError(
                    f"分割規則がresultId源でない語彙IDを参照する: {result_id!r}"
                )
            if result_id in assigned_result_ids:
                raise DeriverDependencyError(
                    f"resultIdが複数の分割規則へ属する: {result_id!r}"
                )
            assigned_result_ids.add(result_id)
            axis_id = result_id.split(".", 1)[0]
            assignment_clauses = assignments[axis_id][1]
            requirement_clauses = tuple(
                dict.fromkeys((*assignment_clauses, *clause_ids))
            )
            for partition_id in partitions:
                requirements.append(
                    RowRequirement(
                        event_kind=event_kind,
                        result_id=result_id,
                        partition_rule_id=rule_id,
                        partition_id=partition_id,
                        source_clause_ids=requirement_clauses,
                    )
                )

    required_result_ids = set(result_id_event_kinds)
    missing_result_ids = sorted(required_result_ids - assigned_result_ids)
    unexpected_result_ids = sorted(assigned_result_ids - required_result_ids)
    if missing_result_ids or unexpected_result_ids:
        raise DeriverDependencyError(
            "resultIdの分割規則帰属がexact-set不一致: "
            f"missing={missing_result_ids!r}; unexpected={unexpected_result_ids!r}"
        )
    identities = [requirement.identity for requirement in requirements]
    if len(identities) != len(set(identities)):
        raise DeriverDependencyError("導出した行要求のidentityが重複している")
    return tuple(requirements)


def validate_row_requirement_coverage(
    required: Sequence[RowRequirement],
    actual: Sequence[RowRequirement],
) -> None:
    """規範行要求の実在集合を双方向 exact-set で検査する。"""
    required_ids = {item.identity for item in required}
    actual_ids = {item.identity for item in actual}
    if len(actual_ids) != len(actual):
        raise DeriverDependencyError("規範行要求に重複がある")
    missing = sorted(required_ids - actual_ids)
    unexpected = sorted(actual_ids - required_ids)
    if missing or unexpected:
        raise DeriverDependencyError(
            "規範行要求がexact-set不一致: "
            f"missing={missing!r}; unexpected={unexpected!r}"
        )


def derive_input_coordinate_requirements_from_descriptor(
    descriptor: Mapping[str, Any],
) -> tuple[InputCoordinateRequirement, ...]:
    """descriptor の宣言だけから軸ごとの入力座標要求を導出する。

    軸間の組合せは段階2の成果物であり、この導出結果には含めない。

    Args:
        descriptor: 入力軸 descriptor。

    Returns:
        軸 ID と coverage 値の組を identity とする要求集合。

    Raises:
        DeriverDependencyError: coverage 宣言が軸集合・値集合と一致しない場合。
    """
    try:
        criteria = descriptor_checker.load_descriptor_criteria(descriptor)
        descriptor_checker._validate_input_coordinate_coverage(
            descriptor, criteria
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise DeriverDependencyError(str(error)) from error

    declaration = _object(
        descriptor.get("inputCoordinateCoverage"), "inputCoordinateCoverage"
    )
    value_fields = _object(
        declaration.get("coverageValueFieldsByClassification"),
        "coverageValueFieldsByClassification",
    )
    conditional_policy = _object(
        declaration.get("conditionalValuePolicy"), "conditionalValuePolicy"
    )
    conditional_source_field = _nonempty_string(
        conditional_policy.get("sourceField"), "conditionalValuePolicy.sourceField"
    )
    conditional_clause_field = _nonempty_string(
        conditional_policy.get("clauseIdField"),
        "conditionalValuePolicy.clauseIdField",
    )
    conditional_state_field = _nonempty_string(
        conditional_policy.get("stateField"), "conditionalValuePolicy.stateField"
    )

    raw_axes = descriptor.get("stateTransitionAxes")
    if not isinstance(raw_axes, list) or not raw_axes:
        raise DeriverDependencyError("stateTransitionAxesが空である")
    axes: dict[str, Mapping[str, Any]] = {}
    for index, raw_axis in enumerate(raw_axes):
        axis = _object(raw_axis, f"stateTransitionAxes[{index}]")
        axis_id = _nonempty_string(axis.get("axisId"), f"stateTransitionAxes[{index}].axisId")
        if axis_id in axes:
            raise DeriverDependencyError(f"stateTransitionAxesのaxisIdが重複する: {axis_id!r}")
        axes[axis_id] = axis

    binding_for_value: dict[tuple[str, str], Mapping[str, Any]] = {}
    raw_binding_groups = declaration.get("axisBindings")
    if not isinstance(raw_binding_groups, list) or not raw_binding_groups:
        raise DeriverDependencyError("inputCoordinateCoverage.axisBindingsが空である")
    for group_index, raw_group in enumerate(raw_binding_groups):
        group = _object(raw_group, f"axisBindings[{group_index}]")
        axis_ids = _string_list(group.get("axisIds"), f"axisBindings[{group_index}].axisIds")
        raw_row_bindings = group.get("rowBindings")
        if not isinstance(raw_row_bindings, list) or not raw_row_bindings:
            raise DeriverDependencyError(
                f"axisBindings[{group_index}].rowBindingsが空である"
            )
        for axis_id in axis_ids:
            axis = axes[axis_id]
            classification = _nonempty_string(
                axis.get("classification"), f"{axis_id}.classification"
            )
            value_field = _nonempty_string(
                value_fields.get(classification),
                f"coverageValueFieldsByClassification.{classification}",
            )
            raw_values = axis.get(value_field)
            if not isinstance(raw_values, list) or not raw_values:
                raise DeriverDependencyError(f"{axis_id}.{value_field}が空である")
            for row_index, raw_row_binding in enumerate(raw_row_bindings):
                row_binding = _object(
                    raw_row_binding,
                    f"axisBindings[{group_index}].rowBindings[{row_index}]",
                )
                selector = _object(
                    row_binding.get("coverageSelector"),
                    f"{axis_id}.coverageSelector",
                )
                selected_values = selector.get("values", raw_values)
                if not isinstance(selected_values, list) or not selected_values:
                    raise DeriverDependencyError(
                        f"{axis_id}.coverageSelectorが値を選択しない"
                    )
                for value in selected_values:
                    value_identity = descriptor_checker._canonical_json_text(
                        value, criteria.safe_integer_limit
                    )
                    key = (axis_id, value_identity)
                    if key in binding_for_value:
                        raise DeriverDependencyError(
                            f"入力座標値が複数の行割当へ属する: {key!r}"
                        )
                    binding_for_value[key] = row_binding

    requirements: list[InputCoordinateRequirement] = []
    for axis_id, axis in axes.items():
        classification = _nonempty_string(
            axis.get("classification"), f"{axis_id}.classification"
        )
        value_field = _nonempty_string(
            value_fields.get(classification),
            f"coverageValueFieldsByClassification.{classification}",
        )
        raw_values = axis.get(value_field)
        if not isinstance(raw_values, list) or not raw_values:
            raise DeriverDependencyError(f"{axis_id}.{value_field}が空である")
        conditions: dict[str, tuple[str, str]] = {}
        raw_conditions = axis.get(conditional_source_field, [])
        if not isinstance(raw_conditions, list):
            raise DeriverDependencyError(
                f"{axis_id}.{conditional_source_field}が配列でない"
            )
        for condition_index, raw_condition in enumerate(raw_conditions):
            condition = _object(
                raw_condition,
                f"{axis_id}.{conditional_source_field}[{condition_index}]",
            )
            value_identity = descriptor_checker._canonical_json_text(
                condition.get("value"), criteria.safe_integer_limit
            )
            if value_identity in conditions:
                raise DeriverDependencyError(
                    f"{axis_id}の条件付きcoverage値が重複する: {value_identity}"
                )
            conditions[value_identity] = (
                _nonempty_string(
                    condition.get(conditional_clause_field),
                    f"{axis_id}.{conditional_clause_field}",
                ),
                _nonempty_string(
                    condition.get(conditional_state_field),
                    f"{axis_id}.{conditional_state_field}",
                ),
            )

        for value in raw_values:
            value_identity = descriptor_checker._canonical_json_text(
                value, criteria.safe_integer_limit
            )
            binding = binding_for_value.get((axis_id, value_identity))
            if binding is None:
                raise DeriverDependencyError(
                    f"入力座標値に行割当がない: {(axis_id, value_identity)!r}"
                )
            condition = conditions.get(value_identity)
            natural_key_field = binding.get("naturalKeyField")
            if natural_key_field is not None and not isinstance(natural_key_field, str):
                raise DeriverDependencyError(
                    f"{axis_id}.naturalKeyFieldが文字列でない"
                )
            requirements.append(
                InputCoordinateRequirement(
                    axis_id=axis_id,
                    classification=classification,
                    coverage_value=value,
                    coverage_value_identity=value_identity,
                    row_layers=_string_list(
                        binding.get("rowLayers"), f"{axis_id}.rowLayers"
                    ),
                    natural_key_role=_nonempty_string(
                        binding.get("naturalKeyRole"), f"{axis_id}.naturalKeyRole"
                    ),
                    natural_key_field=natural_key_field,
                    natural_key_value_projection=_nonempty_string(
                        binding.get("naturalKeyValueProjection"),
                        f"{axis_id}.naturalKeyValueProjection",
                    ),
                    when_clause_id=condition[0] if condition is not None else None,
                    when_state=condition[1] if condition is not None else None,
                )
            )

    identities = [requirement.identity for requirement in requirements]
    if len(identities) != len(set(identities)):
        raise DeriverDependencyError("導出した入力座標要求のidentityが重複している")
    return tuple(requirements)


def active_input_coordinate_requirements(
    requirements: Sequence[InputCoordinateRequirement],
    clause_adoption_states: Mapping[str, str],
) -> tuple[InputCoordinateRequirement, ...]:
    """条文の採用状態を適用して有効な軸ごとの要求だけを返す。"""
    active: list[InputCoordinateRequirement] = []
    for requirement in requirements:
        clause_id = requirement.when_clause_id
        expected_state = requirement.when_state
        if clause_id is None and expected_state is None:
            active.append(requirement)
            continue
        if clause_id is None or expected_state is None:
            raise DeriverDependencyError("条件付き入力座標要求の条件が不完全である")
        actual_state = clause_adoption_states.get(clause_id)
        if actual_state is None:
            raise DeriverDependencyError(
                f"条件付き入力座標要求の採用状態を判定できない: {clause_id}"
            )
        if actual_state == expected_state:
            active.append(requirement)
    return tuple(active)


def validate_input_coordinate_coverage(
    required: Sequence[InputCoordinateRequirement],
    observed: Sequence[InputCoordinateRequirement],
) -> None:
    """軸ごとの入力座標 coverage を双方向 exact-set で検査する。"""
    required_ids = {item.identity for item in required}
    observed_ids = {item.identity for item in observed}
    missing = sorted(required_ids - observed_ids)
    unexpected = sorted(observed_ids - required_ids)
    if missing or unexpected:
        raise DeriverDependencyError(
            "入力座標要求がexact-set不一致: "
            f"missing={missing!r}; unexpected={unexpected!r}"
        )


def _derive_repository_row_requirements(root: Path) -> tuple[RowRequirement, ...]:
    """宣言された4入力だけを読み、リポジトリの行要求を導出する。"""
    try:
        rules = _object(
            descriptor_checker.load_json(
                root / ROW_REQUIREMENT_RULES_PATH, "requiredSet行要求規則"
            ),
            "requiredSet行要求規則",
        )
        vocabulary = _object(rules.get("vocabulary"), "行要求規則.vocabulary")
        manifest_path = _repository_path(
            root,
            _nonempty_string(vocabulary.get("manifestPath"), "vocabulary.manifestPath"),
            "vocabulary.manifestPath",
        )
        seed_path = _repository_path(
            root,
            _nonempty_string(vocabulary.get("seedPath"), "vocabulary.seedPath"),
            "vocabulary.seedPath",
        )
        source_path = _repository_path(
            root,
            _nonempty_string(rules.get("sourceClausePath"), "sourceClausePath"),
            "sourceClausePath",
        )
        manifest = _object(
            descriptor_checker.load_json(root / manifest_path, "語彙manifest"),
            "語彙manifest",
        )
        seed = _object(
            descriptor_checker.load_json(root / seed_path, "語彙シード"),
            "語彙シード",
        )
        clause_ids = frozenset(
            f"req:{clause_id}"
            for clause_id in descriptor_checker.load_clause_ids_from_paths(
                root, (source_path,)
            )
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise DeriverDependencyError(str(error)) from error
    return derive_row_requirements_from_documents(
        rules,
        manifest,
        seed,
        clause_ids,
    )


def derive_repository_row_requirements(
    root: Path,
    policy: DeriverDependencyPolicy | None = None,
) -> tuple[tuple[RowRequirement, ...], DeriverTrace]:
    """依存トレース下でリポジトリの行要求を導出する。

    Args:
        root: リポジトリルート。
        policy: 検証済み依存宣言。省略時は実資産から読む。

    Returns:
        行要求と実際に観測した読み取り証跡。

    Raises:
        DeriverDependencyError: 規則・入力・依存トレースが不正な場合。
    """
    active_policy = policy or load_policy(root)
    load_row_requirement_rules_document(root)
    requirements, trace = trace_deriver_file_reads(
        root,
        active_policy,
        "required-set-row-requirements",
        lambda: _derive_repository_row_requirements(root),
    )
    rule = active_policy.derivers[trace.deriver_id]
    missing_reads = sorted(set(rule.allowed_read_paths) - set(trace.observed_read_paths))
    if missing_reads:
        raise DeriverDependencyError(
            f"導出器が宣言入力を読んでいない: {missing_reads!r}"
        )
    return requirements, trace


def _derive_repository_input_coordinate_requirements(
    root: Path,
) -> tuple[InputCoordinateRequirement, ...]:
    """入力軸 descriptor だけを読み、軸ごとの入力座標要求を導出する。"""
    try:
        descriptor = _object(
            descriptor_checker.load_json(
                root / descriptor_checker.DESCRIPTOR_PATH, "入力軸descriptor"
            ),
            "入力軸descriptor",
        )
    except descriptor_checker.DescriptorCheckError as error:
        raise DeriverDependencyError(str(error)) from error
    return derive_input_coordinate_requirements_from_descriptor(descriptor)


def derive_repository_input_coordinate_requirements(
    root: Path,
    policy: DeriverDependencyPolicy | None = None,
) -> tuple[tuple[InputCoordinateRequirement, ...], DeriverTrace]:
    """依存トレース下で descriptor 由来の入力座標要求を導出する。

    Args:
        root: リポジトリルート。
        policy: 検証済み依存宣言。省略時は実資産から読む。

    Returns:
        軸ごとの入力座標要求と実際に観測した読み取り証跡。

    Raises:
        DeriverDependencyError: descriptor または依存トレースが不正な場合。
    """
    active_policy = policy or load_policy(root)
    requirements, trace = trace_deriver_file_reads(
        root,
        active_policy,
        "required-set-input-coordinates",
        lambda: _derive_repository_input_coordinate_requirements(root),
    )
    rule = active_policy.derivers[trace.deriver_id]
    missing_reads = sorted(set(rule.allowed_read_paths) - set(trace.observed_read_paths))
    if missing_reads:
        raise DeriverDependencyError(
            f"導出器が宣言入力を読んでいない: {missing_reads!r}"
        )
    return requirements, trace


def validate_repository_policy(root: Path) -> DeriverDependencyPolicy:
    """リポジトリの導出器依存宣言を検証する。

    Args:
        root: リポジトリルート。

    Returns:
        検証済みの依存宣言。
    """
    policy = load_policy(root)
    load_row_requirement_rules_document(root)
    return policy


def main(argv: Sequence[str] | None = None) -> int:
    """依存宣言と requiredSet 2段の導出閉包を検証する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        policy = validate_repository_policy(args.root)
        requirements, trace = derive_repository_row_requirements(args.root, policy)
        coordinate_requirements, coordinate_trace = (
            derive_repository_input_coordinate_requirements(args.root, policy)
        )
    except DeriverDependencyError as error:
        print(f"deriver dependency: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "deriver dependency: PASS "
        f"(policy={policy.policy_id}, derivers={len(policy.derivers)}, "
        f"rowRequirements={len(requirements)}, "
        f"inputCoordinateRequirements={len(coordinate_requirements)}, "
        f"reads={len(trace.observed_read_paths) + len(coordinate_trace.observed_read_paths)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
