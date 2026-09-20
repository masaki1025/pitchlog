"""三言語の変異演算子が合成対象を変異し、実際にkillされることを検査する。"""

from __future__ import annotations

import importlib
import json
import math
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
COST_PATH = ROOT / "docs/features/domain-calc-dsl/mutation-cost.json"

sys.path.insert(0, str(BACKEND_SRC))
ENGINE = importlib.import_module("pitchlog.domainmut.engine")
OPERATORS = importlib.import_module("pitchlog.domainmut.operators_lang")

SOURCES = {
    OPERATORS.Language.PYTHON: "def calculate(a, b):\n    return a + b\n",
    OPERATORS.Language.TYPESCRIPT: (
        "function calculate(a, b) { return a + b; }\n"
    ),
    OPERATORS.Language.SQL: "SELECT SUM(value) AS result FROM samples",
}
UNSUPPORTED = {
    OPERATORS.Language.PYTHON: "def calculate(a):\n    return a ** 2\n",
    OPERATORS.Language.TYPESCRIPT: (
        "function calculate(a) { return a ** 2; }\n"
    ),
    OPERATORS.Language.SQL: "SELECT value FROM samples QUALIFY value > 0",
}


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object をUTF-8で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _target(language: Any) -> Any:
    """一言語の固定された合成対象を返す。"""
    title = language.value.title()
    return ENGINE.SyntheticMutationTarget(
        calculation=f"synthetic{title}Calculation",
        target_id=f"synthetic{title}Target",
        source=OPERATORS.LanguageSource(language, SOURCES[language]),
    )


def _unsupported_target(language: Any) -> Any:
    """未対応構文を一つ含む合成対象を返す。"""
    title = language.value.title()
    return ENGINE.SyntheticMutationTarget(
        calculation=f"syntheticUnsupported{title}",
        target_id=f"unsupported{title}Target",
        source=OPERATORS.LanguageSource(language, UNSUPPORTED[language]),
    )


def _python_result(code: str) -> object:
    """Python合成計算を実行して結果を返す。"""
    namespace: dict[str, object] = {}
    exec(compile(code, "<python-mutant>", "exec"), namespace)
    function = namespace["calculate"]
    assert callable(function)
    return cast(Callable[[int, int], object], function)(2, 3)


def _typescript_result(code: str) -> object:
    """NodeでTypeScript互換の合成JavaScriptを実行して結果を返す。"""
    script = f"{code}\nconsole.log(JSON.stringify(calculate(2, 3)));"
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return {"executionError": result.stderr}
    return json.loads(result.stdout)


def _sql_result(code: str) -> object:
    """SQLiteの合成表にSQLを実行して全行を返す。"""
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE samples(value INTEGER NOT NULL)")
        connection.executemany(
            "INSERT INTO samples(value) VALUES (?)",
            [(2,), (3,), (5,)],
        )
        return connection.execute(code).fetchall()


def _execute(language: Any, code: str) -> object:
    """言語別の実ランタイムで合成計算を実行する。"""
    if language is OPERATORS.Language.PYTHON:
        return _python_result(code)
    if language is OPERATORS.Language.TYPESCRIPT:
        return _typescript_result(code)
    return _sql_result(code)


@dataclass(frozen=True, slots=True)
class _SemanticExecutor:
    """元実装との意味差をプロパティ層のkill要因として記録する。"""

    originals: dict[str, Any]

    def execute(self, mutant: Any) -> Any:
        """元実装とmutantを実行し、出力差があればkillする。"""
        original = self.originals[mutant.target_id]
        changed = mutant.mutated
        assert isinstance(changed, OPERATORS.LanguageSource)
        expected = _execute(original.language, original.code)
        actual = _execute(changed.language, changed.code)
        if actual == expected:
            return ENGINE.MutationExecution(False, ())
        return ENGINE.MutationExecution(
            True,
            (
                ENGINE.KillEvidence(
                    mutant_id=mutant.mutant_id,
                    calculation=mutant.calculation,
                    layer=ENGINE.KillLayer.PROPERTY_INVARIANT,
                    check_id=f"{mutant.target_id}.semantic-output",
                ),
            ),
        )


def _executor(*targets: Any) -> _SemanticExecutor:
    """対象IDから元の言語ソースを引ける実行器を返す。"""
    return _SemanticExecutor({target.target_id: target.source for target in targets})


@pytest.mark.parametrize("language", tuple(OPERATORS.Language))
def test_each_language_generates_mutants_individually(language: Any) -> None:
    """Python・TypeScript・SQLの各演算子が個別にmutantを生成する。"""
    target = _target(language)
    operator = OPERATORS.LANGUAGE_OPERATORS[language]

    batch = ENGINE.generate_mutants((target,), (operator,))

    assert batch.mutants
    assert all(mutant.calculation == target.calculation for mutant in batch.mutants)
    assert all(mutant.mutated != target.source for mutant in batch.mutants)


def test_language_mother_set_is_exactly_three() -> None:
    """言語と演算子の母集合が過不足なく3件であることを固定する。"""
    languages = set(OPERATORS.Language)

    assert len(languages) == 3
    assert set(OPERATORS.LANGUAGE_OPERATORS) == languages


@pytest.mark.parametrize("language", tuple(OPERATORS.Language))
def test_unsupported_syntax_is_listed_and_fails(language: Any) -> None:
    """三言語それぞれの未対応構文を列挙してfailする。"""
    target = _unsupported_target(language)
    operator = OPERATORS.LANGUAGE_OPERATORS[language]

    generation = operator.generate(target)

    assert generation.unsupported
    with pytest.raises(ENGINE.MutationEngineError, match="未対応箇所"):
        ENGINE.run_mutations(
            targets=(target,),
            operators=(operator,),
            executor=_executor(target),
        )


@pytest.mark.parametrize("language", tuple(OPERATORS.Language))
def test_each_language_mutants_are_actually_killed(language: Any) -> None:
    """三言語のmutantを各ランタイムで実行し意味差によってkillする。"""
    target = _target(language)
    operator = OPERATORS.LANGUAGE_OPERATORS[language]

    report = ENGINE.run_mutations(
        targets=(target,),
        operators=(operator,),
        executor=_executor(target),
    )

    result = report.calculations[0]
    assert report.complete
    assert result.generated
    assert result.killed == result.generated
    assert result.property_killed == result.generated


def test_mutation_cost_record_has_measured_shape_not_fixed_values() -> None:
    """変異コストが実測sampleと再現条件を持ち、値自体は固定しない。"""
    asset = _read_json(COST_PATH)
    assert set(asset) == {"schemaVersion", "measurements"}
    measurement = next(item for item in asset["measurements"] if item["step"] == 40)
    assert set(measurement) == {
        "step",
        "measuredAt",
        "measurementCommand",
        "environment",
        "syntheticTargets",
        "languages",
        "estimatedTotalSeconds",
    }
    assert measurement["measurementCommand"]
    assert measurement["environment"]["python"]
    assert measurement["environment"]["platform"]
    assert measurement["syntheticTargets"]["languageCount"] == len(
        OPERATORS.Language
    )
    estimated_total = 0.0
    for row in measurement["languages"]:
        assert set(row) == {
            "language",
            "mutantCount",
            "suiteSamplesSeconds",
            "suiteSecondsPerMutant",
            "estimatedSeconds",
        }
        assert row["language"] in {language.value for language in OPERATORS.Language}
        assert row["mutantCount"] > 0
        assert row["suiteSamplesSeconds"]
        assert all(sample > 0 for sample in row["suiteSamplesSeconds"])
        assert row["suiteSecondsPerMutant"] > 0
        assert math.isclose(
            row["estimatedSeconds"],
            row["mutantCount"] * row["suiteSecondsPerMutant"],
            rel_tol=1e-9,
        )
        estimated_total += row["estimatedSeconds"]
    assert {row["language"] for row in measurement["languages"]} == {
        language.value for language in OPERATORS.Language
    }
    assert math.isclose(
        measurement["estimatedTotalSeconds"],
        estimated_total,
        rel_tol=1e-9,
    )
