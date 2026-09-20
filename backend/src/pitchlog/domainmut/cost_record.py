"""合成生成物に対する変異コストの拘束実測を記録する。

ステップ 30 の合成 DSL を既存生成器へ通し、言語別三系統と表示系の
mutant 母数を実生成物から求める。スイート再実行時間との積をステップ 42 の
内部上限と比較し、生ログを含む再現可能なレコードを返す。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

from pitchlog.domaincheck.seal import _run_git
from pitchlog.domaingen import core, formatter, pregen_checks
from pitchlog.domaingen.backends import (
    GeneratedArtifact,
    generate_language_artifacts,
)
from pitchlog.domainmut import operators_display, operators_lang
from pitchlog.domainmut.engine import SyntheticMutationTarget
from pitchlog.domainmut.scope import DIFF_BUDGET_SECONDS, FULL_BUDGET_SECONDS

_FIXTURE_ROOT = Path("backend/tests/domain/fixtures/synthetic_dsl")
_MODEL_PATH = _FIXTURE_ROOT / "model.json"
_MANIFEST_PATH = _FIXTURE_ROOT / "manifest.json"
_RUNNER_TESTS = (
    ("vectors", "tests/domain/runners/test_vectors.py"),
    ("coverage-proof", "tests/domain/runners/test_coverage_proof.py"),
    ("invariants", "tests/domain/runners/test_invariants.py"),
    ("equivalence", "tests/domain/runners/test_equivalence.py"),
    (
        "catalog-independence",
        "tests/domain/runners/test_catalog_independence.py",
    ),
)
_MUTATION_TESTS = (
    "tests/domain/mut/test_engine.py",
    "tests/domain/mut/test_lang_operators.py",
    "tests/domain/mut/test_display_operators.py",
)
_MEASUREMENT_KEYS = frozenset(
    {
        "step",
        "schemaVersion",
        "measuredAt",
        "recordSchema",
        "evidence",
        "scopes",
        "syntheticSource",
        "environment",
        "extrapolation",
    }
)
_EVIDENCE_KEYS = frozenset(
    {
        "rawLogs",
        "commands",
        "commitSha",
        "runners",
        "mutantClassifications",
    }
)
_RAW_LOG_KEYS = frozenset(
    {"scope", "stdout", "stderr", "exitCode", "durationSeconds"}
)
_COMMAND_KEYS = frozenset({"scope", "argv", "cwd"})
_RUNNER_KEYS = frozenset({"id", "testPath"})
_CLASSIFICATION_KEYS = frozenset(
    {
        "id",
        "artifactCount",
        "operatorIds",
        "mutantCount",
        "mutantIds",
    }
)
_SCOPE_KEYS = frozenset(
    {
        "id",
        "budgetSeconds",
        "mutantCount",
        "suiteRerunSeconds",
        "estimatedTotalSeconds",
        "headroomSeconds",
        "headroomPercent",
        "withinBudget",
    }
)
_SYNTHETIC_KEYS = frozenset(
    {
        "modelPath",
        "manifestPath",
        "calculationIds",
        "targetClasses",
        "languageArtifactCount",
        "displayArtifactCount",
        "canonicalInputDigest",
    }
)
_ENVIRONMENT_KEYS = frozenset(
    {"python", "platform", "processor", "cpuCount", "node", "sqlite"}
)
_EXTRAPOLATION_KEYS = frozenset(
    {
        "basis",
        "syntheticCalculationCount",
        "productProjectionAvailable",
        "limitation",
    }
)
_RECORD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(_EVIDENCE_KEYS),
    "properties": {
        "rawLogs": {"type": "array", "minItems": 2},
        "commands": {"type": "array", "minItems": 2},
        "commitSha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "runners": {"type": "array", "minItems": 1},
        "mutantClassifications": {"type": "array", "minItems": 4},
    },
}


class CostRecordError(Exception):
    """実測またはレコードが契約に適合しないことを表す。"""


class MutationClassification(StrEnum):
    """拘束実測で数える四つの変異系統。"""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    SQL = "sql"
    DISPLAY = "display"


@dataclass(frozen=True, slots=True)
class SuiteObservation:
    """一つの実行範囲で観測したスイート再実行結果。"""

    scope: str
    command: tuple[str, ...]
    duration_seconds: float
    exit_code: int
    stdout: str
    stderr: str


def _read_object(path: Path) -> dict[str, object]:
    """UTF-8 の JSON object を読む。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CostRecordError(f"JSON を読めない: {path}") from error
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise CostRecordError(f"JSON object でない: {path}")
    return cast(dict[str, object], value)


def _canonical_digest(*values: object) -> str:
    """複数の JSON 値を canonical JSON として hash 化する。"""
    payload = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _schemas(root: Path) -> core.SourceSchemas:
    """既存の三つの schema を生成コアの入力型へ束ねる。"""
    return core.SourceSchemas(
        model=_read_object(root / "backend/domain/model.schema.json"),
        manifest=_read_object(root / "backend/domain/manifest.schema.json"),
        vocabulary=_read_object(root / "backend/domain/vocabulary.schema.json"),
    )


def _intermediate(root: Path) -> tuple[dict[str, object], object, object]:
    """ステップ 30 と同じ生成経路で合成 DSL と入力文書を返す。"""
    model = _read_object(root / _MODEL_PATH)
    manifest = _read_object(root / _MANIFEST_PATH)
    value = pregen_checks.generate_checked(
        model,
        manifest,
        _schemas(root),
        root,
    )
    core.validate_intermediate_representation(value, _schemas(root))
    return value, model, manifest


def _sql_statement(expression: str) -> str:
    """生成 SQL 式を既存の SQL 演算子が解析する SELECT 文へ載せる。"""
    return f"SELECT {expression}"


def _language_inventory(
    artifacts: Sequence[GeneratedArtifact],
) -> tuple[dict[str, object], ...]:
    """Step 30 の言語生成物から三言語の mutant を列挙する。"""
    artifact_counts: Counter[str] = Counter()
    mutant_ids: dict[str, list[str]] = {
        language.value: [] for language in operators_lang.Language
    }
    operator_ids: dict[str, set[str]] = {
        language.value: set() for language in operators_lang.Language
    }
    for artifact in artifacts:
        language = operators_lang.Language(artifact.language.value)
        code = artifact.content
        if language is operators_lang.Language.SQL:
            code = _sql_statement(code)
        target = SyntheticMutationTarget(
            calculation=artifact.calculation_id,
            target_id=artifact.generated_id,
            source=operators_lang.LanguageSource(language, code),
        )
        operator = operators_lang.LANGUAGE_OPERATORS[language]
        generated = operator.generate(target)
        if generated.unsupported:
            raise CostRecordError(
                f"Step 30 生成物に未対応構文がある: {generated.unsupported!r}"
            )
        artifact_counts[language.value] += 1
        operator_ids[language.value].add(operator.operator_id)
        mutant_ids[language.value].extend(
            mutant.mutant_id for mutant in generated.mutants
        )
    return tuple(
        {
            "id": classification.value,
            "artifactCount": artifact_counts[classification.value],
            "operatorIds": sorted(operator_ids[classification.value]),
            "mutantCount": len(mutant_ids[classification.value]),
            "mutantIds": sorted(mutant_ids[classification.value]),
        }
        for classification in (
            MutationClassification.PYTHON,
            MutationClassification.TYPESCRIPT,
            MutationClassification.SQL,
        )
    )


def _first_numeric_rule(intermediate: Mapping[str, object]) -> str:
    """実在する最初の数値表示規則 ID を返す。"""
    rules = intermediate.get("displayRules")
    if not isinstance(rules, list):
        raise CostRecordError("displayRules が array でない")
    for rule in rules:
        if (
            isinstance(rule, dict)
            and rule.get("kind") == "numeric-primitive"
            and isinstance(rule.get("id"), str)
        ):
            return cast(str, rule["id"])
    raise CostRecordError("数値表示規則がなく表示変異を実測できない")


def _display_inventory(
    intermediate: Mapping[str, object],
    artifact_count: int,
) -> dict[str, object]:
    """Step 30 の表示 IR へ五系統を適用して表示 mutant を列挙する。"""
    calculations = intermediate.get("calculations")
    if not isinstance(calculations, list) or not calculations:
        raise CostRecordError("合成計算が空")
    first = calculations[0]
    if not isinstance(first, dict) or not isinstance(
        first.get("calculationId"), str
    ):
        raise CostRecordError("合成計算 ID を読めない")
    source = operators_display.DisplayMutationSource(
        intermediate=intermediate,
        invocation=operators_display.FormatterInvocation(
            rule_id=_first_numeric_rule(intermediate),
            numeric_value={"kind": "integer", "value": 7},
            language_value=7,
        ),
    )
    target = SyntheticMutationTarget(
        calculation=cast(str, first["calculationId"]),
        target_id="step30-display-artifacts",
        source=source,
    )
    mutant_ids: list[str] = []
    operator_ids: list[str] = []
    for operator in operators_display.DISPLAY_OPERATORS.values():
        generated = operator.generate(target)
        if generated.unsupported:
            raise CostRecordError(
                f"Step 30 表示生成物に未対応箇所がある: {generated.unsupported!r}"
            )
        operator_ids.append(operator.operator_id)
        mutant_ids.extend(mutant.mutant_id for mutant in generated.mutants)
    return {
        "id": MutationClassification.DISPLAY.value,
        "artifactCount": artifact_count,
        "operatorIds": sorted(operator_ids),
        "mutantCount": len(mutant_ids),
        "mutantIds": sorted(mutant_ids),
    }


def collect_mutant_inventory(root: Path) -> tuple[dict[str, object], ...]:
    """Step 30 の実生成物から四系統の mutant 分類を導出する。"""
    intermediate, _, _ = _intermediate(root)
    language_artifacts = generate_language_artifacts(intermediate)
    display_artifacts = formatter.generate_display_artifacts(intermediate)
    inventory = (
        *_language_inventory(language_artifacts),
        _display_inventory(intermediate, len(display_artifacts)),
    )
    ids = {cast(str, item["id"]) for item in inventory}
    expected = {item.value for item in MutationClassification}
    if ids != expected:
        raise CostRecordError(f"変異分類の集合差: {sorted(ids ^ expected)!r}")
    if any(cast(int, item["mutantCount"]) <= 0 for item in inventory):
        raise CostRecordError("mutant が 0 件の変異分類がある")
    mutant_ids = [
        mutant_id
        for item in inventory
        for mutant_id in cast(list[str], item["mutantIds"])
    ]
    if len(mutant_ids) != len(set(mutant_ids)):
        raise CostRecordError("mutant ID が分類間で重複している")
    return inventory


def _python_command(root: Path) -> str:
    """実際に起動でき、記録可能な Python コマンドを返す。"""
    for relative in (Path(".venv/bin/python"), Path("backend/.venv/bin/python")):
        if (root / relative).is_file():
            return relative.as_posix()
    return sys.executable


def suite_command(root: Path) -> tuple[str, ...]:
    """全 runner と四変異系統を実行するスイートコマンドを返す。"""
    return (
        _python_command(root),
        "-m",
        "pytest",
        "-q",
        "tests/domain/gen/test_target_matrix.py",
        *(path for _, path in _RUNNER_TESTS),
        *_MUTATION_TESTS,
    )


def run_suite(
    root: Path,
    scope: str,
    command: Sequence[str] | None = None,
) -> SuiteObservation:
    """一つの範囲についてスイートを実行し、生ログと時間を返す。"""
    actual = tuple(command) if command is not None else suite_command(root)
    started_at = time.monotonic()
    try:
        result = subprocess.run(
            actual,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise CostRecordError(f"測定スイートを起動できない: {error}") from error
    duration = time.monotonic() - started_at
    observation = SuiteObservation(
        scope=scope,
        command=actual,
        duration_seconds=duration,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if result.returncode != 0:
        raise CostRecordError(
            f"測定スイートが失敗した: scope={scope}, exit={result.returncode}"
        )
    return observation


def budget_result(
    scope: str,
    mutant_count: int,
    suite_seconds: float,
    budget_seconds: int,
) -> dict[str, object]:
    """Mutant 数とスイート時間の積を内部上限と比較する。"""
    if mutant_count <= 0 or suite_seconds < 0 or budget_seconds <= 0:
        raise ValueError("予算比較の入力が正でない")
    estimated = mutant_count * suite_seconds
    headroom = budget_seconds - estimated
    return {
        "id": scope,
        "budgetSeconds": budget_seconds,
        "mutantCount": mutant_count,
        "suiteRerunSeconds": suite_seconds,
        "estimatedTotalSeconds": estimated,
        "headroomSeconds": headroom,
        "headroomPercent": headroom / budget_seconds * 100,
        "withinBudget": estimated <= budget_seconds,
    }


def _commit_sha(root: Path) -> str:
    """既存の版管理境界から現在の完全 commit OID を得る。"""
    result = _run_git(root, "rev-parse", "HEAD")
    sha = result.stdout.strip()
    if result.returncode != 0 or len(sha) != 40 or any(
        character not in "0123456789abcdef" for character in sha
    ):
        raise CostRecordError("完全 commit OID を取得できない")
    return sha


def _node_version(root: Path) -> str:
    """TypeScript 実行に用いる Node の版を返す。"""
    try:
        result = subprocess.run(
            ["node", "--version"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise CostRecordError("Node の版を取得できない") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise CostRecordError("Node の版を取得できない")
    return result.stdout.strip()


def _environment(root: Path) -> dict[str, object]:
    """拘束実測の再現に必要な実行環境を返す。"""
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "cpuCount": os.cpu_count(),
        "node": _node_version(root),
        "sqlite": sqlite3.sqlite_version,
    }


def _source_record(root: Path) -> dict[str, object]:
    """合成入力と実生成物の規模を機械可読に返す。"""
    intermediate, model, manifest = _intermediate(root)
    language_artifacts = generate_language_artifacts(intermediate)
    display_artifacts = formatter.generate_display_artifacts(intermediate)
    calculations = cast(list[dict[str, object]], intermediate["calculations"])
    target_classes = {
        cast(str, target["targetClass"])
        for calculation in calculations
        for target in cast(list[dict[str, object]], calculation["targets"])
    }
    return {
        "modelPath": _MODEL_PATH.as_posix(),
        "manifestPath": _MANIFEST_PATH.as_posix(),
        "calculationIds": sorted(
            cast(str, calculation["calculationId"])
            for calculation in calculations
        ),
        "targetClasses": sorted(target_classes),
        "languageArtifactCount": len(language_artifacts),
        "displayArtifactCount": len(display_artifacts),
        "canonicalInputDigest": _canonical_digest(model, manifest),
    }


def create_measurement(
    root: Path,
    *,
    command: Sequence[str] | None = None,
    measured_at: str | None = None,
) -> dict[str, object]:
    """実生成物と二回のスイート実行からステップ 49 記録を作る。"""
    inventory = collect_mutant_inventory(root)
    mutant_count = sum(cast(int, item["mutantCount"]) for item in inventory)
    observations = (
        run_suite(root, "differential", command),
        run_suite(root, "full", command),
    )
    scopes = (
        budget_result(
            "differential",
            mutant_count,
            observations[0].duration_seconds,
            DIFF_BUDGET_SECONDS,
        ),
        budget_result(
            "full",
            mutant_count,
            observations[1].duration_seconds,
            FULL_BUDGET_SECONDS,
        ),
    )
    source = _source_record(root)
    evidence = {
        "rawLogs": [
            {
                "scope": observation.scope,
                "stdout": observation.stdout,
                "stderr": observation.stderr,
                "exitCode": observation.exit_code,
                "durationSeconds": observation.duration_seconds,
            }
            for observation in observations
        ],
        "commands": [
            {
                "scope": observation.scope,
                "argv": list(observation.command),
                "cwd": ".",
            }
            for observation in observations
        ],
        "commitSha": _commit_sha(root),
        "runners": [
            {"id": runner_id, "testPath": path}
            for runner_id, path in _RUNNER_TESTS
        ],
        "mutantClassifications": list(inventory),
    }
    record: dict[str, object] = {
        "step": 49,
        "schemaVersion": 1,
        "measuredAt": measured_at
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "recordSchema": _RECORD_SCHEMA,
        "evidence": evidence,
        "scopes": list(scopes),
        "syntheticSource": source,
        "environment": _environment(root),
        "extrapolation": {
            "basis": "mutant-count-times-suite-rerun-seconds",
            "syntheticCalculationCount": len(
                cast(list[object], source["calculationIds"])
            ),
            "productProjectionAvailable": False,
            "limitation": (
                "合成 DSL は一対象計算なので差分・全面の mutant 母数が同じ。"
                "製品対象の mutant 母数が未確定のため製品規模の数値外挿は行わない。"
            ),
        },
    }
    validate_measurement(record)
    return record


def _object(value: object, label: str) -> Mapping[str, object]:
    """文字列キーの object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise CostRecordError(f"{label} が object でない")
    return cast(Mapping[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """JSON array を返す。"""
    if not isinstance(value, list):
        raise CostRecordError(f"{label} が array でない")
    return cast(list[object], value)


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    """Object の未知キーと欠落キーを両方向で拒否する。"""
    actual = set(value)
    if actual != expected:
        raise CostRecordError(
            f"{label} のキー集合差: missing={sorted(expected - actual)!r}, "
            f"unknown={sorted(actual - expected)!r}"
        )


def _positive_number(value: object, label: str, *, allow_zero: bool = False) -> float:
    """有限の非負または正の数を返す。"""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (value < 0 if allow_zero else value <= 0)
    ):
        raise CostRecordError(f"{label} が有効な数でない")
    return float(value)


def _validate_evidence(evidence: Mapping[str, object]) -> None:
    """生ログ・コマンド・SHA・runner・分類の厳密な形を検査する。"""
    _exact_keys(evidence, _EVIDENCE_KEYS, "evidence")
    logs = _array(evidence["rawLogs"], "rawLogs")
    commands = _array(evidence["commands"], "commands")
    runners = _array(evidence["runners"], "runners")
    classifications = _array(
        evidence["mutantClassifications"], "mutantClassifications"
    )
    if len(logs) != 2 or len(commands) != 2 or not runners:
        raise CostRecordError("実測の生ログ・コマンド・runner が不足している")
    log_scopes: set[str] = set()
    for index, item in enumerate(logs):
        log = _object(item, f"rawLogs[{index}]")
        _exact_keys(log, _RAW_LOG_KEYS, f"rawLogs[{index}]")
        scope = log["scope"]
        if not isinstance(scope, str):
            raise CostRecordError("生ログの scope が文字列でない")
        log_scopes.add(scope)
        if (
            log["exitCode"] != 0
            or not isinstance(log["stdout"], str)
            or not log["stdout"]
            or not isinstance(log["stderr"], str)
        ):
            raise CostRecordError("生ログが成功した実行結果でない")
        _positive_number(
            log["durationSeconds"],
            "durationSeconds",
            allow_zero=True,
        )
    command_scopes: set[str] = set()
    for index, item in enumerate(commands):
        command = _object(item, f"commands[{index}]")
        _exact_keys(command, _COMMAND_KEYS, f"commands[{index}]")
        scope = command["scope"]
        if not isinstance(scope, str):
            raise CostRecordError("コマンドの scope が文字列でない")
        command_scopes.add(scope)
        argv = _array(command["argv"], "argv")
        if not argv or not all(isinstance(argument, str) for argument in argv):
            raise CostRecordError("実行コマンドが空または文字列以外を含む")
    if log_scopes != {"differential", "full"} or command_scopes != log_scopes:
        raise CostRecordError("生ログとコマンドの差分・全面 scope が一致しない")
    sha = evidence["commitSha"]
    if not isinstance(sha, str) or len(sha) != 40 or any(
        character not in "0123456789abcdef" for character in sha
    ):
        raise CostRecordError("commitSha が完全 OID でない")
    runner_ids: list[str] = []
    runner_paths: list[str] = []
    for index, item in enumerate(runners):
        runner = _object(item, f"runners[{index}]")
        _exact_keys(runner, _RUNNER_KEYS, f"runners[{index}]")
        runner_id = runner["id"]
        runner_path = runner["testPath"]
        if not isinstance(runner_id, str) or not isinstance(runner_path, str):
            raise CostRecordError("runner ID または test path が文字列でない")
        runner_ids.append(runner_id)
        runner_paths.append(runner_path)
    if len(runner_ids) != len(set(runner_ids)) or len(runner_paths) != len(
        set(runner_paths)
    ):
        raise CostRecordError("runner ID または test path が重複している")
    for item in commands:
        command = _object(item, "command")
        argv = set(cast(list[str], command["argv"]))
        if not set(runner_paths) <= argv:
            raise CostRecordError("実行コマンドが全 runner を含まない")
    observed_ids: set[str] = set()
    all_mutant_ids: list[str] = []
    for index, item in enumerate(classifications):
        classification = _object(item, f"mutantClassifications[{index}]")
        _exact_keys(
            classification,
            _CLASSIFICATION_KEYS,
            f"mutantClassifications[{index}]",
        )
        classification_id = classification["id"]
        if not isinstance(classification_id, str):
            raise CostRecordError("変異分類 ID が文字列でない")
        observed_ids.add(classification_id)
        _positive_number(classification["artifactCount"], "artifactCount")
        operator_ids = _array(classification["operatorIds"], "operatorIds")
        if not operator_ids or not all(
            isinstance(operator_id, str) for operator_id in operator_ids
        ):
            raise CostRecordError("変異分類の演算子 ID が空または文字列でない")
        count = _positive_number(
            classification["mutantCount"],
            "mutantCount",
        )
        mutant_ids = _array(classification["mutantIds"], "mutantIds")
        if not all(isinstance(mutant_id, str) for mutant_id in mutant_ids):
            raise CostRecordError("mutant ID が文字列でない")
        if count != len(mutant_ids) or len(mutant_ids) != len(set(mutant_ids)):
            raise CostRecordError("mutantCount と一意な mutantIds が一致しない")
        all_mutant_ids.extend(cast(list[str], mutant_ids))
    expected_ids = {item.value for item in MutationClassification}
    if observed_ids != expected_ids:
        raise CostRecordError(
            f"四変異分類の集合差: {sorted(observed_ids ^ expected_ids)!r}"
        )
    if len(all_mutant_ids) != len(set(all_mutant_ids)):
        raise CostRecordError("mutant ID が変異分類間で重複している")


def _validate_scope(value: object, expected_budget: int) -> None:
    """一つの範囲の積・余裕・上限判定を再計算して検査する。"""
    scope = _object(value, "scope")
    _exact_keys(scope, _SCOPE_KEYS, "scope")
    if scope["budgetSeconds"] != expected_budget:
        raise CostRecordError("範囲の内部上限が契約値でない")
    mutant_count = _positive_number(scope["mutantCount"], "mutantCount")
    suite_seconds = _positive_number(
        scope["suiteRerunSeconds"],
        "suiteRerunSeconds",
        allow_zero=True,
    )
    estimated = mutant_count * suite_seconds
    recorded = _positive_number(
        scope["estimatedTotalSeconds"],
        "estimatedTotalSeconds",
        allow_zero=True,
    )
    if abs(recorded - estimated) > 1e-9:
        raise CostRecordError("mutant 数と再実行時間の積が一致しない")
    within = estimated <= expected_budget
    if scope["withinBudget"] is not within:
        raise CostRecordError("上限との比較結果が実測値と一致しない")
    expected_headroom = expected_budget - estimated
    if abs(float(cast(float, scope["headroomSeconds"])) - expected_headroom) > 1e-9:
        raise CostRecordError("残り秒数が実測値と一致しない")
    expected_percent = expected_headroom / expected_budget * 100
    if abs(float(cast(float, scope["headroomPercent"])) - expected_percent) > 1e-9:
        raise CostRecordError("余裕率が実測値と一致しない")


def validate_measurement(value: object) -> None:
    """ステップ 49 の測定レコードを厳密キーと関係で検査する。"""
    measurement = _object(value, "measurement")
    _exact_keys(measurement, _MEASUREMENT_KEYS, "measurement")
    if measurement["step"] != 49 or measurement["schemaVersion"] != 1:
        raise CostRecordError("ステップまたは schema version が不正")
    measured_at = measurement["measuredAt"]
    if not isinstance(measured_at, str):
        raise CostRecordError("measuredAt が文字列でない")
    try:
        datetime.fromisoformat(measured_at)
    except ValueError as error:
        raise CostRecordError("measuredAt が ISO 8601 でない") from error
    if measurement["recordSchema"] != _RECORD_SCHEMA:
        raise CostRecordError("五証拠項目の schema が不正")
    evidence = _object(measurement["evidence"], "evidence")
    _validate_evidence(evidence)
    scopes = _array(measurement["scopes"], "scopes")
    if len(scopes) != 2:
        raise CostRecordError("差分・全面の測定が揃っていない")
    by_id = {_object(item, "scope")["id"]: item for item in scopes}
    if set(by_id) != {"differential", "full"}:
        raise CostRecordError("差分・全面の範囲集合が不正")
    _validate_scope(by_id["differential"], DIFF_BUDGET_SECONDS)
    _validate_scope(by_id["full"], FULL_BUDGET_SECONDS)
    classifications = _array(
        evidence["mutantClassifications"], "mutantClassifications"
    )
    expected_mutants = sum(
        cast(int, _object(item, "classification")["mutantCount"])
        for item in classifications
    )
    logs = {
        cast(str, _object(item, "rawLog")["scope"]): _object(item, "rawLog")
        for item in _array(evidence["rawLogs"], "rawLogs")
    }
    for scope_id, scope_value in by_id.items():
        scope = _object(scope_value, "scope")
        if scope["mutantCount"] != expected_mutants:
            raise CostRecordError("範囲の mutant 数が四分類の合計と一致しない")
        if scope["suiteRerunSeconds"] != logs[cast(str, scope_id)][
            "durationSeconds"
        ]:
            raise CostRecordError("範囲の再実行時間が生ログと一致しない")
    _exact_keys(
        _object(measurement["syntheticSource"], "syntheticSource"),
        _SYNTHETIC_KEYS,
        "syntheticSource",
    )
    _exact_keys(
        _object(measurement["environment"], "environment"),
        _ENVIRONMENT_KEYS,
        "environment",
    )
    extrapolation = _object(measurement["extrapolation"], "extrapolation")
    _exact_keys(extrapolation, _EXTRAPOLATION_KEYS, "extrapolation")
    if extrapolation["productProjectionAvailable"] is not False:
        raise CostRecordError("未実測の製品規模を数値外挿している")


def append_measurement(
    document: Mapping[str, object], measurement: Mapping[str, object]
) -> dict[str, object]:
    """既存のステップ 40・41 記録を保持してステップ 49 を追記する。"""
    if set(document) != {"schemaVersion", "measurements"}:
        raise CostRecordError("mutation-cost 資産のトップレベルが不正")
    measurements = _array(document["measurements"], "measurements")
    if any(not isinstance(item, dict) for item in measurements):
        raise CostRecordError("既存の測定行が object でない")
    validate_measurement(measurement)
    retained = [
        item
        for item in measurements
        if not (isinstance(item, dict) and item.get("step") == 49)
    ]
    return {
        "schemaVersion": document["schemaVersion"],
        "measurements": [*retained, dict(measurement)],
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """拘束実測 CLI の引数を解釈する。"""
    parser = argparse.ArgumentParser(description="変異コストを拘束実測する")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """実測レコードを canonical JSON として標準出力へ出す。"""
    arguments = _parse_args(argv)
    try:
        measurement = create_measurement(arguments.root.resolve())
    except (CostRecordError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(measurement, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
