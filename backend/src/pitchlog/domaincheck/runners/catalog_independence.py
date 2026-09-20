"""不変条件カタログを生成器の入力と依存グラフから分離する。

`ADR-003 D-11 3 層表 プロパティ層` に従い、生成中の実ファイル読み取りを
独立に採取して allowlist と突合する。さらに `domaingen` の Python AST から
import と JSON 資産参照を導出し、カタログへの静的な依存も拒否する。
"""

from __future__ import annotations

import ast
import builtins
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast
from unittest.mock import patch

from pitchlog.domaincheck.runners.properties import (
    InvariantEvaluator,
    InvariantPredicate,
)

_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_EVALUATOR_ID = re.compile(r"^[a-z][a-z0-9.-]*$")
_LINE_REFERENCE = re.compile(r":\d+")
_CATALOG_KEYS = {
    "schemaVersion",
    "catalogId",
    "scope",
    "predicates",
    "independence",
}
_PREDICATE_KEYS = {"propertyId", "evaluatorId", "authorityId"}
_INDEPENDENCE_KEYS = {
    "generatorSource",
    "catalogPath",
    "generatorInputAllowlist",
}
_T = TypeVar("_T")


class CatalogIndependenceError(Exception):
    """カタログの形式または生成器からの独立性違反を表す。"""


@dataclass(frozen=True, slots=True)
class FileAccessEvidence:
    """生成処理中に観測した読み取りパス。

    Attributes:
        repository_reads: リポジトリルートからの相対読み取りパス。
        external_reads: リポジトリ外の絶対読み取りパス。
    """

    repository_reads: frozenset[str]
    external_reads: frozenset[str]


@dataclass(frozen=True, slots=True)
class TracedGeneration:
    """生成処理の返り値と独立採取したファイルアクセス証跡。"""

    result: object
    evidence: FileAccessEvidence


@dataclass(frozen=True, order=True, slots=True)
class DependencyEdge:
    """生成器ソースから module または資産への静的依存。"""

    source: str
    target: str
    kind: str


@dataclass(frozen=True, slots=True)
class GeneratorDependencyGraph:
    """生成器の Python AST から導出した依存グラフ。"""

    sources: frozenset[str]
    edges: frozenset[DependencyEdge]

    @property
    def targets(self) -> frozenset[str]:
        """全依存先を返す。"""
        return frozenset(edge.target for edge in self.edges)


@dataclass(frozen=True, slots=True)
class IndependenceReport:
    """動的読み取りと静的依存の双方が独立である証跡。"""

    accesses: FileAccessEvidence
    dependency_graph: GeneratorDependencyGraph
    allowed_inputs: frozenset[str]
    catalog_path: str

    @property
    def complete(self) -> bool:
        """読み取りと依存先に違反が無い場合だけ真を返す。"""
        return (
            not self.accesses.external_reads
            and self.accesses.repository_reads <= self.allowed_inputs
            and self.catalog_path not in self.accesses.repository_reads
            and self.catalog_path not in self.dependency_graph.targets
        )


def _mapping(value: object, label: str) -> dict[str, object]:
    """文字列キーだけを持つ object を返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise CatalogIndependenceError(f"{label} が object でない")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    """Array を返す。"""
    if not isinstance(value, list):
        raise CatalogIndependenceError(f"{label} が array でない")
    return value


def _string(value: object, label: str) -> str:
    """空でない文字列を返す。"""
    if not isinstance(value, str) or not value:
        raise CatalogIndependenceError(f"{label} が空でない文字列でない")
    return value


def _relative_path(value: object, label: str) -> str:
    """親参照を含まない POSIX 相対パスを返す。"""
    text = _string(value, label)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != text:
        raise CatalogIndependenceError(f"{label} が安全な相対パスでない")
    return text


def validate_catalog(catalog: Mapping[str, object]) -> None:
    """合成不変条件カタログの厳密キー集合と独立性宣言を検査する。"""
    if set(catalog) != _CATALOG_KEYS:
        raise CatalogIndependenceError("property catalog のキー集合が不正")
    if catalog.get("schemaVersion") != _SCHEMA_VERSION:
        raise CatalogIndependenceError("property catalog の schemaVersion が不正")
    _string(catalog.get("catalogId"), "catalogId")
    if catalog.get("scope") != "synthetic-dsl":
        raise CatalogIndependenceError("製品対象の property catalog は扱えない")

    rows = _array(catalog.get("predicates"), "predicates")
    if not rows:
        raise CatalogIndependenceError("predicates が空")
    property_ids: list[str] = []
    evaluator_ids: list[str] = []
    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, f"predicates[{index}]")
        if set(row) != _PREDICATE_KEYS:
            raise CatalogIndependenceError("predicate のキー集合が不正")
        property_id = _string(row.get("propertyId"), "predicate.propertyId")
        evaluator_id = _string(row.get("evaluatorId"), "predicate.evaluatorId")
        authority_id = _string(row.get("authorityId"), "predicate.authorityId")
        if _IDENTIFIER.fullmatch(property_id) is None:
            raise CatalogIndependenceError(f"property ID が不正: {property_id}")
        if _EVALUATOR_ID.fullmatch(evaluator_id) is None:
            raise CatalogIndependenceError(f"evaluator ID が不正: {evaluator_id}")
        if _LINE_REFERENCE.search(authority_id):
            raise CatalogIndependenceError(
                f"条項 ID に行番号参照がある: {authority_id}"
            )
        property_ids.append(property_id)
        evaluator_ids.append(evaluator_id)
    if len(property_ids) != len(set(property_ids)):
        raise CatalogIndependenceError("property ID が重複")
    if len(evaluator_ids) != len(set(evaluator_ids)):
        raise CatalogIndependenceError("evaluator ID が重複")

    independence = _mapping(catalog.get("independence"), "independence")
    if set(independence) != _INDEPENDENCE_KEYS:
        raise CatalogIndependenceError("independence のキー集合が不正")
    _relative_path(independence.get("generatorSource"), "generatorSource")
    catalog_path = _relative_path(
        independence.get("catalogPath"),
        "catalogPath",
    )
    raw_allowlist = _array(
        independence.get("generatorInputAllowlist"),
        "generatorInputAllowlist",
    )
    allowlist = [
        _relative_path(item, "generatorInputAllowlist[]")
        for item in raw_allowlist
    ]
    if not allowlist or len(allowlist) != len(set(allowlist)):
        raise CatalogIndependenceError("generator input allowlist が空または重複")
    if catalog_path in allowlist:
        raise CatalogIndependenceError("property catalog を生成器入力にできない")


def predicates_from_catalog(
    catalog: Mapping[str, object],
    evaluators: Mapping[str, InvariantEvaluator],
) -> tuple[InvariantPredicate, ...]:
    """カタログの典拠付き述語をステップ 36 の型へ接続する。

    Args:
        catalog: `property-catalog.json` の内容。
        evaluators: カタログとは別に実装された evaluator の索引。

    Returns:
        ステップ 36 の runner が直接適用できる述語。

    Raises:
        CatalogIndependenceError: カタログまたは evaluator 集合が不適合な場合。
    """
    validate_catalog(catalog)
    predicates: list[InvariantPredicate] = []
    used_evaluators: set[str] = set()
    for raw_row in _array(catalog.get("predicates"), "predicates"):
        row = _mapping(raw_row, "predicates[]")
        evaluator_id = _string(row.get("evaluatorId"), "predicate.evaluatorId")
        try:
            evaluator = evaluators[evaluator_id]
        except KeyError as error:
            raise CatalogIndependenceError(
                f"evaluator が未登録: {evaluator_id}"
            ) from error
        predicates.append(
            InvariantPredicate(
                property_id=_string(row.get("propertyId"), "propertyId"),
                authority_id=_string(row.get("authorityId"), "authorityId"),
                evaluate=evaluator,
            )
        )
        used_evaluators.add(evaluator_id)
    unexpected = set(evaluators) - used_evaluators
    if unexpected:
        raise CatalogIndependenceError(
            f"カタログに無い evaluator が登録された: {sorted(unexpected)!r}"
        )
    return tuple(predicates)


def catalog_policy(
    catalog: Mapping[str, object],
) -> tuple[str, str, frozenset[str]]:
    """検証済みカタログから生成器 source・catalog・allowlist を返す。"""
    validate_catalog(catalog)
    independence = _mapping(catalog.get("independence"), "independence")
    source = _relative_path(independence.get("generatorSource"), "generatorSource")
    catalog_path = _relative_path(independence.get("catalogPath"), "catalogPath")
    allowlist = frozenset(
        _relative_path(item, "generatorInputAllowlist[]")
        for item in _array(
            independence.get("generatorInputAllowlist"),
            "generatorInputAllowlist",
        )
    )
    return source, catalog_path, allowlist


def _is_read_mode(mode: object) -> bool:
    """Open mode が読み取りを含む場合だけ真を返す。"""
    if not isinstance(mode, str):
        return True
    return "r" in mode or "+" in mode


def trace_generator_file_access(
    root: Path,
    operation: Callable[[], _T],
) -> TracedGeneration:
    """生成処理を実行し、実際に開いた読み取りファイルを独立採取する。

    Args:
        root: リポジトリルート。
        operation: 既存生成器を呼び出す引数なし関数。

    Returns:
        生成結果とリポジトリ内外に分けた読み取り証跡。
    """
    resolved_root = root.resolve()
    repository_reads: set[str] = set()
    external_reads: set[str] = set()
    original_path_open = Path.open
    original_open = builtins.open

    def record(raw_path: object, mode: object) -> None:
        """読み取りパスを正規化して内外いずれかへ記録する。"""
        if not _is_read_mode(mode) or isinstance(raw_path, int):
            return
        if not isinstance(raw_path, (str, bytes, os.PathLike)):
            external_reads.add(repr(raw_path))
            return
        filesystem_path = cast(
            str | bytes | os.PathLike[str] | os.PathLike[bytes],
            raw_path,
        )
        path = Path(os.fsdecode(filesystem_path)).resolve()
        try:
            relative = path.relative_to(resolved_root)
        except ValueError:
            external_reads.add(path.as_posix())
        else:
            repository_reads.add(relative.as_posix())

    def traced_path_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        """`Path.open` の読み取りを記録して元実装へ委譲する。"""
        mode = kwargs.get("mode", args[0] if args else "r")
        record(path, mode)
        return original_path_open(path, *args, **kwargs)

    def traced_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        """組み込み `open` の読み取りを記録して元実装へ委譲する。"""
        mode = kwargs.get("mode", args[0] if args else "r")
        record(file, mode)
        return original_open(file, *args, **kwargs)

    with (
        patch.object(Path, "open", traced_path_open),
        patch("builtins.open", traced_open),
    ):
        result = operation()
    return TracedGeneration(
        result=result,
        evidence=FileAccessEvidence(
            repository_reads=frozenset(repository_reads),
            external_reads=frozenset(external_reads),
        ),
    )


def _module_name(generator_root: Path, source: Path) -> str:
    """生成器 root 内の Python パスを module 名へ変換する。"""
    relative = source.relative_to(generator_root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    suffix = ".".join(parts)
    return "pitchlog.domaingen" + (f".{suffix}" if suffix else "")


def _resource_target(value: str) -> str | None:
    """文字列リテラルが指す JSON 資産を正規パスへ変換する。"""
    if not value.endswith(".json"):
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return value
    if len(path.parts) == 1:
        return f"backend/domain/{value}"
    return path.as_posix()


def derive_generator_dependency_graph(
    generator_root: Path,
) -> GeneratorDependencyGraph:
    """生成器 Python AST から import と JSON 資産依存を導出する。"""
    resolved_root = generator_root.resolve()
    sources = tuple(sorted(resolved_root.rglob("*.py")))
    if not sources:
        raise CatalogIndependenceError("生成器 source が空")
    source_names = {_module_name(resolved_root, source) for source in sources}
    edges: set[DependencyEdge] = set()
    observed_sources: set[str] = set()
    for source in sources:
        source_name = _module_name(resolved_root, source)
        observed_sources.add(source_name)
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError) as error:
            raise CatalogIndependenceError(
                f"生成器 source を解析できない: {source}"
            ) from error
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in source_names:
                        edges.add(DependencyEdge(source_name, alias.name, "import"))
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module in source_names:
                    edges.add(DependencyEdge(source_name, node.module, "import"))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                target = _resource_target(node.value)
                if target is not None:
                    edges.add(DependencyEdge(source_name, target, "resource"))
    return GeneratorDependencyGraph(
        sources=frozenset(observed_sources),
        edges=frozenset(edges),
    )


def validate_catalog_independence(
    *,
    evidence: FileAccessEvidence,
    dependency_graph: GeneratorDependencyGraph,
    allowed_inputs: Iterable[str],
    catalog_path: str,
) -> IndependenceReport:
    """動的読み取りと静的依存をカタログ分離規則へ突合する。"""
    allowed = frozenset(allowed_inputs)
    if not allowed:
        raise CatalogIndependenceError("generator input allowlist が空")
    if catalog_path in allowed:
        raise CatalogIndependenceError("property catalog が allowlist にある")
    unexpected = evidence.repository_reads - allowed
    if unexpected or evidence.external_reads:
        raise CatalogIndependenceError(
            "allowlist 外の読み取り: "
            f"repository={sorted(unexpected)!r}, "
            f"external={sorted(evidence.external_reads)!r}"
        )
    if catalog_path in evidence.repository_reads:
        raise CatalogIndependenceError("生成器が property catalog を読んだ")
    if catalog_path in dependency_graph.targets:
        raise CatalogIndependenceError(
            "生成器の依存グラフに property catalog がある"
        )
    report = IndependenceReport(
        accesses=evidence,
        dependency_graph=dependency_graph,
        allowed_inputs=allowed,
        catalog_path=catalog_path,
    )
    if not report.complete:
        raise CatalogIndependenceError("カタログ独立性を証明できない")
    return report


__all__ = [
    "CatalogIndependenceError",
    "DependencyEdge",
    "FileAccessEvidence",
    "GeneratorDependencyGraph",
    "IndependenceReport",
    "TracedGeneration",
    "catalog_policy",
    "derive_generator_dependency_graph",
    "predicates_from_catalog",
    "trace_generator_file_access",
    "validate_catalog",
    "validate_catalog_independence",
]
