"""中間表現から三言語だけを生成する backend を検査する。"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
BACKENDS_DIR = BACKEND_SRC / "pitchlog/domaingen/backends"

sys.path.insert(0, str(BACKEND_SRC))
CORE = importlib.import_module("pitchlog.domaingen.core")
BACKENDS = importlib.import_module("pitchlog.domaingen.backends")

EXPECTED_LANGUAGES = {"python", "typescript", "sql"}
EXPECTED_TARGET_CLASSES = {"alpha", "beta-1-5", "beta-7", "beta-6-8"}
AGGREGATE_SQL_PATTERN = re.compile(
    r"\b(?:SUM|COUNT|AVG)\s*\(|\bGROUP\s+BY\b",
    re.IGNORECASE,
)
ARTIFACT_FIELDS = {
    "generatorVersion",
    "sourceId",
    "calculationId",
    "directTargetId",
    "targetClass",
    "stage",
    "generatedId",
    "language",
    "sourceHash",
    "delivery",
    "content",
}


@pytest.fixture(scope="module")
def schemas() -> Any:
    """ステップ 26 の中間表現検証に使う既存 schema を返す。"""
    return CORE.SourceSchemas(
        model=_read_json(ROOT / "backend/domain/model.schema.json"),
        manifest=_read_json(ROOT / "backend/domain/manifest.schema.json"),
        vocabulary=_read_json(ROOT / "backend/domain/vocabulary.schema.json"),
    )


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _integer(value: int) -> dict[str, object]:
    """構造化整数を返す。"""
    return {"kind": "integer", "value": value}


def _field(field_id: str) -> dict[str, object]:
    """合成宣言の整数フィールドを返す。"""
    return {
        "fieldId": field_id,
        "type": {"kind": "integer"},
        "nullable": False,
        "range": {
            "minimum": _integer(0),
            "maximum": _integer(999),
        },
        "unit": "point",
        "scale": 0,
    }


def _declaration(calculation_id: str) -> dict[str, object]:
    """一つの状態遷移を持つ合成計算宣言を返す。"""
    output = _field("visibleMetric")
    output["visibility"] = "user-visible"
    return {
        "calculationId": calculation_id,
        "inputs": [_field("delta")],
        "states": [
            {
                "stateId": "scoreState",
                "fields": [_field("total")],
            }
        ],
        "events": [
            {
                "eventId": "advance",
                "fields": [_field("amount")],
            }
        ],
        "rules": [
            {
                "kind": "transition",
                "ruleId": "applyAdvance",
                "eventRef": "advance",
                "guardRefs": [],
                "nextState": [
                    {
                        "fieldRef": "total",
                        "value": {
                            "kind": "arithmetic",
                            "operator": "add",
                            "operands": [
                                {
                                    "kind": "state-ref",
                                    "fieldRef": "total",
                                },
                                {
                                    "kind": "event-ref",
                                    "fieldRef": "amount",
                                },
                            ],
                        },
                    }
                ],
            }
        ],
        "outputs": [output],
        "displayRuleRefs": [],
    }


def _hash(character: str) -> str:
    """識別しやすい有効な段別 hash を返す。"""
    return f"sha256:{character * 64}"


def _stage(name: str, generated_id: str, character: str) -> dict[str, str]:
    """ステップ 26 と同じキー集合の IR 段を返す。"""
    return {
        "stage": name,
        "generatedId": generated_id,
        "sourceHash": _hash(character),
    }


def _calculation(
    target_class: str,
    kind: str,
    stages: list[dict[str, str]],
) -> dict[str, object]:
    """指定区分と段を持つ中間表現の計算要素を返す。"""
    calculation_id = f"synthetic-{target_class}"
    return {
        "calculationId": calculation_id,
        "sourceId": "ADR-003 D-11 構成の完全性",
        "declaration": _declaration(calculation_id),
        "targets": [
            {
                "directTargetId": f"{calculation_id}-direct",
                "targetClass": target_class,
                "kind": kind,
                "stages": stages,
                "invocation": {
                    "adapter": f"synthetic/adapters/{calculation_id}.py",
                    "operation": "execute",
                },
            }
        ],
    }


def _intermediate() -> dict[str, Any]:
    """全 target class を覆う正しい中間表現を返す。"""
    return {
        "schemaVersion": 1,
        "generatorVersion": CORE.GENERATOR_VERSION,
        "displayRules": [],
        "calculations": [
            _calculation(
                "alpha",
                "single",
                [_stage("python", "alpha-core", "a")],
            ),
            _calculation(
                "beta-1-5",
                "composite",
                [
                    _stage("sql", "beta-aggregate-sql", "b"),
                    _stage("typed-receiver", "beta-aggregate-receiver", "c"),
                    _stage("formatter", "beta-aggregate-formatter", "d"),
                ],
            ),
            _calculation(
                "beta-7",
                "composite",
                [
                    _stage("sql", "beta-classification-sql", "e"),
                    _stage("typed-receiver", "beta-classification-receiver", "f"),
                ],
            ),
            _calculation(
                "beta-6-8",
                "single",
                [_stage("python", "beta-python", "1")],
            ),
        ],
    }


def _artifacts(schemas: Any) -> tuple[Any, ...]:
    """検証済み中間表現から言語別生成物を返す。"""
    intermediate = _intermediate()
    CORE.validate_intermediate_representation(intermediate, schemas)
    return BACKENDS.generate_language_artifacts(intermediate)


def _assert_language_population(artifacts: Collection[Any]) -> None:
    """三言語の母集合と実測集合が一致することを検査する。"""
    expected = {language.value for language in BACKENDS.LANGUAGES}
    observed = {artifact.language.value for artifact in artifacts}
    assert len(expected) == 3
    assert expected == EXPECTED_LANGUAGES
    assert observed == expected


def _tree_snapshot(root: Path) -> tuple[tuple[str, str], ...]:
    """ディレクトリ配下のパスと内容 hash を返す。"""
    if not root.exists():
        return ()
    values: list[tuple[str, str]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        values.append((path.relative_to(root).as_posix(), digest))
    return tuple(values)


def test_language_population_is_exactly_three(schemas: Any) -> None:
    artifacts = _artifacts(schemas)

    _assert_language_population(artifacts)
    assert len(BACKENDS.LANGUAGES) == 3


def test_two_languages_do_not_satisfy_population(schemas: Any) -> None:
    artifacts = tuple(
        artifact
        for artifact in _artifacts(schemas)
        if artifact.language.value != "typescript"
    )

    with pytest.raises(AssertionError):
        _assert_language_population(artifacts)


def test_target_matrix_classes_are_contractual(schemas: Any) -> None:
    artifacts = _artifacts(schemas)
    observed = {artifact.target_class for artifact in artifacts}

    assert len(BACKENDS.TARGET_CLASSES) == 4
    assert BACKENDS.TARGET_CLASSES == EXPECTED_TARGET_CLASSES
    assert observed == EXPECTED_TARGET_CLASSES


def test_core_stage_hash_is_reused_without_recalculation(schemas: Any) -> None:
    intermediate = _intermediate()
    artifacts = _artifacts(schemas)
    input_hashes = {
        (
            target["directTargetId"],
            stage["stage"],
        ): stage["sourceHash"]
        for calculation in intermediate["calculations"]
        for target in calculation["targets"]
        for stage in target["stages"]
    }

    for artifact in artifacts:
        assert artifact.source_hash == input_hashes[
            (artifact.direct_target_id, artifact.stage)
        ]

    for source_path in BACKENDS_DIR.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "hashlib" not in imported_modules


def test_same_alpha_stage_hash_matches_across_languages(schemas: Any) -> None:
    alpha = [
        artifact
        for artifact in _artifacts(schemas)
        if artifact.target_class == "alpha"
    ]

    assert {artifact.language.value for artifact in alpha} == {
        "python",
        "typescript",
    }
    assert len({artifact.stage for artifact in alpha}) == 1
    assert len({artifact.source_hash for artifact in alpha}) == 1


def test_beta_seven_sql_is_row_classification_not_aggregate(schemas: Any) -> None:
    sql_artifact = next(
        artifact
        for artifact in _artifacts(schemas)
        if artifact.target_class == "beta-7" and artifact.language.value == "sql"
    )

    assert "CASE WHEN" in sql_artifact.content
    assert AGGREGATE_SQL_PATTERN.search(sql_artifact.content) is None
    assert "reducer" not in sql_artifact.content.lower()


def test_beta_seven_python_receiver_applies_enum_display_map(schemas: Any) -> None:
    receiver = next(
        artifact
        for artifact in _artifacts(schemas)
        if artifact.target_class == "beta-7" and artifact.language.value == "python"
    )
    namespace: dict[str, object] = {"__name__": "__pitchlog_generated_wrapper__"}
    exec(compile(receiver.content, "<generated-receiver>", "exec"), namespace)
    function = cast(
        Callable[[dict[str, str], dict[str, str]], object],
        namespace["_pitchlog_generated"],
    )

    assert callable(function)
    assert function({"value": "home"}, {"home": "ホーム"}) == "ホーム"


def test_formatter_stage_is_not_generated_by_language_backends(schemas: Any) -> None:
    artifacts = _artifacts(schemas)

    assert "formatter" not in {artifact.stage for artifact in artifacts}
    assert all("reference implementation" not in artifact.content for artifact in artifacts)


def test_generated_artifacts_are_wrapper_only(schemas: Any) -> None:
    artifacts = _artifacts(schemas)
    mappings = [artifact.as_mapping() for artifact in artifacts]
    typescript = next(
        artifact for artifact in artifacts if artifact.language.value == "typescript"
    )

    assert all(set(mapping) == ARTIFACT_FIELDS for mapping in mappings)
    assert all(
        artifact.delivery == "wrapper-only-fragment" for artifact in artifacts
    )
    assert "__PITCHLOG_GENERATED_WRAPPER__" in typescript.content
    assert re.search(r"\bexport\b", typescript.content) is None


def test_python_artifact_rejects_direct_import(
    tmp_path: Path,
    schemas: Any,
) -> None:
    artifact = next(
        item
        for item in _artifacts(schemas)
        if item.target_class == "alpha" and item.language.value == "python"
    )
    generated_path = tmp_path / "generated_direct.py"
    generated_path.write_text(artifact.content, encoding="utf-8")
    script = "\n".join(
        [
            "import importlib.util",
            f"spec = importlib.util.spec_from_file_location('direct', {str(generated_path)!r})",
            "module = importlib.util.module_from_spec(spec)",
            "spec.loader.exec_module(module)",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "ラッパー経由" in result.stderr


def test_wrapper_can_load_python_artifact(schemas: Any) -> None:
    artifact = next(
        item
        for item in _artifacts(schemas)
        if item.target_class == "alpha" and item.language.value == "python"
    )
    namespace: dict[str, object] = {"__name__": "__pitchlog_generated_wrapper__"}

    exec(compile(artifact.content, "<generated-python>", "exec"), namespace)
    function = cast(
        Callable[[dict[str, int]], object],
        namespace["_pitchlog_generated"],
    )

    assert callable(function)
    assert function({"delta": 1}) == {
        "calculationId": "synthetic-alpha",
        "context": {"delta": 1},
    }


def test_valid_intermediate_outputs_all_three_languages(schemas: Any) -> None:
    artifacts = _artifacts(schemas)

    assert len(artifacts) == 7
    _assert_language_population(artifacts)
    assert all(artifact.content.strip() for artifact in artifacts)
    assert all(artifact.generator_version == CORE.GENERATOR_VERSION for artifact in artifacts)
    assert all(artifact.source_id == "ADR-003 D-11 構成の完全性" for artifact in artifacts)
    for artifact in artifacts:
        if artifact.language.value == "python":
            compile(artifact.content, f"<{artifact.generated_id}>", "exec")


def test_generation_writes_neither_product_paths_nor_contracts(schemas: Any) -> None:
    watched = (ROOT / "backend/src/pitchlog", ROOT / "frontend", ROOT / "contracts")
    before = tuple(_tree_snapshot(path) for path in watched)

    artifacts = _artifacts(schemas)

    after = tuple(_tree_snapshot(path) for path in watched)
    assert artifacts
    assert after == before
