"""生成器と不変条件カタログの動的・静的な独立性を検査する。"""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
CATALOG_PATH = ROOT / "backend/domain/property-catalog.json"
AUTHORITIES_PATH = ROOT / "backend/domain/step-authorities.json"

sys.path.insert(0, str(BACKEND_SRC))
INDEPENDENCE = importlib.import_module(
    "pitchlog.domaincheck.runners.catalog_independence"
)
PROPERTIES = importlib.import_module(
    "pitchlog.domaincheck.runners.properties"
)
CORE = importlib.import_module("pitchlog.domaingen.core")


def _read_json(path: Path) -> dict[str, Any]:
    """JSON object を UTF-8 で読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    """合成 DSL 用の不変条件カタログを返す。"""
    return _read_json(CATALOG_PATH)


def _evaluators() -> dict[str, Any]:
    """カタログとは別に実装された二つの合成 evaluator を返す。"""
    return {
        "synthetic.count-nonnegative": lambda value: isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0,
        "synthetic.empty-aggregate-null-display": lambda value: value
        == {"structured": None, "display": "−"},
    }


def _policy(catalog: dict[str, Any]) -> tuple[str, str, frozenset[str]]:
    """カタログから source・catalog path・allowlist を返す。"""
    return INDEPENDENCE.catalog_policy(catalog)


def _synthetic_generation() -> int:
    """既存生成コアをステップ 30 の合成 DSL で実際に起動する。"""
    fixture_root = "backend/tests/domain/fixtures/synthetic_dsl"
    return CORE.main(
        [
            "--root",
            str(ROOT),
            "--model",
            f"{fixture_root}/model.json",
            "--manifest",
            f"{fixture_root}/manifest.json",
        ]
    )


def test_catalog_predicates_match_step_thirty_six_types_and_authorities(
    catalog: dict[str, Any],
) -> None:
    """典拠付きカタログをステップ 36 の述語型へそのまま接続できる。"""
    predicates = INDEPENDENCE.predicates_from_catalog(catalog, _evaluators())
    registry = _read_json(AUTHORITIES_PATH)
    authorities = PROPERTIES.authorities_from_registry(registry)

    PROPERTIES.validate_predicate_authorities(ROOT, predicates, authorities)
    assert {predicate.property_id for predicate in predicates} == {
        row["propertyId"] for row in catalog["predicates"]
    }
    assert {predicate.authority_id for predicate in predicates} == {
        row["authorityId"] for row in catalog["predicates"]
    }


def test_read_outside_generator_input_allowlist_fails(
    catalog: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """生成中に allowlist 外のファイルを読むと動的証跡が拒否される。"""
    source, catalog_path, allowlist = _policy(catalog)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")

    def generation_with_extra_read() -> int:
        """正規入力に加えて未許可ファイルを読む生成処理を模す。"""
        result = _synthetic_generation()
        outside.read_text(encoding="utf-8")
        return result

    traced = INDEPENDENCE.trace_generator_file_access(
        ROOT,
        generation_with_extra_read,
    )
    graph = INDEPENDENCE.derive_generator_dependency_graph(ROOT / source)
    capsys.readouterr()

    assert traced.result == 0
    assert traced.evidence.external_reads
    with pytest.raises(
        INDEPENDENCE.CatalogIndependenceError,
        match="allowlist 外の読み取り",
    ):
        INDEPENDENCE.validate_catalog_independence(
            evidence=traced.evidence,
            dependency_graph=graph,
            allowed_inputs=allowlist,
            catalog_path=catalog_path,
        )


def test_catalog_in_generator_dependency_graph_fails(
    catalog: dict[str, Any],
    tmp_path: Path,
) -> None:
    """生成器 AST にカタログ資産参照を混ぜると静的検査が拒否する。"""
    source, catalog_path, allowlist = _policy(catalog)
    copied = tmp_path / "domaingen"
    shutil.copytree(ROOT / source, copied)
    core_copy = copied / "core.py"
    core_copy.write_text(
        core_copy.read_text(encoding="utf-8")
        + '\n_PROPERTY_CATALOG = "property-catalog.json"\n',
        encoding="utf-8",
    )
    graph = INDEPENDENCE.derive_generator_dependency_graph(copied)
    evidence = INDEPENDENCE.FileAccessEvidence(
        repository_reads=frozenset(),
        external_reads=frozenset(),
    )

    assert catalog_path in graph.targets
    with pytest.raises(
        INDEPENDENCE.CatalogIndependenceError,
        match="依存グラフ",
    ):
        INDEPENDENCE.validate_catalog_independence(
            evidence=evidence,
            dependency_graph=graph,
            allowed_inputs=allowlist,
            catalog_path=catalog_path,
        )


def test_generator_completes_with_only_allowlisted_reads(
    catalog: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """既存生成コアが許可入力だけを読み、独立性検査を実際に完走する。"""
    source, catalog_path, allowlist = _policy(catalog)
    traced = INDEPENDENCE.trace_generator_file_access(ROOT, _synthetic_generation)
    graph = INDEPENDENCE.derive_generator_dependency_graph(ROOT / source)
    captured = capsys.readouterr()

    report = INDEPENDENCE.validate_catalog_independence(
        evidence=traced.evidence,
        dependency_graph=graph,
        allowed_inputs=allowlist,
        catalog_path=catalog_path,
    )

    assert traced.result == 0
    assert json.loads(captured.out)["calculations"]
    assert report.complete
    assert report.accesses.repository_reads <= report.allowed_inputs
    assert report.catalog_path not in report.accesses.repository_reads
    assert report.catalog_path not in report.dependency_graph.targets
