"""テナント境界迂回検査のセンサス差分を検証する。"""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_tenant_boundary_bypass.py"


def _load_checker_module(path: Path, module_name: str) -> ModuleType:
    """検査器を指定した別モジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_checker() -> ModuleType:
    """検査器をリポジトリの import 設定に依存せず読む。"""
    return _load_checker_module(
        SCRIPT,
        "check_tenant_boundary_bypass_under_test",
    )


def _load_checker_from_revision(revision: str, destination: Path) -> ModuleType:
    """VCS 上の検査器と同 revision の依存を別モジュールとして読む。"""
    relative_script = SCRIPT.relative_to(REPOSITORY_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_script}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    scripts_directory = destination.parent / f"{destination.stem}_scripts"
    scripts_directory.mkdir()
    extracted_checker = scripts_directory / SCRIPT.name
    extracted_checker.write_bytes(result.stdout)
    dependency = "scripts/frozen_history.py"
    dependency_result = subprocess.run(
        ["git", "show", f"{revision}:{dependency}"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )
    if dependency_result.returncode == 0:
        (scripts_directory / "frozen_history.py").write_bytes(
            dependency_result.stdout
        )
    digest = hashlib.sha256(result.stdout).hexdigest()
    previous_dependency = sys.modules.pop("frozen_history", None)
    previous_path = list(sys.path)
    try:
        sys.path.insert(0, str(scripts_directory))
        return _load_checker_module(
            extracted_checker,
            f"check_tenant_boundary_bypass_{digest}",
        )
    finally:
        sys.path[:] = previous_path
        sys.modules.pop("frozen_history", None)
        if previous_dependency is not None:
            sys.modules["frozen_history"] = previous_dependency


checker = _load_checker()

CENSUS_BASELINE_PATH = (
    REPOSITORY_ROOT / "contracts" / "tenant_boundary" / "census-baseline.json"
)
CensusIdentity = tuple[str, int, int, str, str, str, str]

_CONDITION_2_AST_CASES = {
    "Name": "idempotency_key\n",
    "Attribute": "holder.idempotency_key\n",
    "arg": "def safe(idempotency_key: str):\n    pass\n",
    "keyword": "safe(idempotency_key=1)\n",
    "MatchAs": "match value:\n    case idempotency_key:\n        pass\n",
    "MatchClass": (
        "match value:\n"
        "    case Safe(idempotency_key=bound):\n"
        "        pass\n"
    ),
    "MatchMapping": "match value:\n    case {**idempotency_key}:\n        pass\n",
    "MatchStar": "match value:\n    case [*idempotency_key]:\n        pass\n",
}


@dataclass(frozen=True)
class _ObservedGitBlob:
    """監視開始後の単一 git show 応答と、その監視世代を保持する。"""

    monitor: object
    revision: str
    content: bytes


@dataclass
class _DeclarationImplementationAudit:
    """宣言フィールドと実装による読取り・利用の対応を記録する。"""

    declarations: list[dict[str, Any]] = field(default_factory=list)
    read_fields: set[str] = field(default_factory=set)
    implementation_sources: set[str] = field(default_factory=set)
    undeclared_inputs: set[str] = field(default_factory=set)


_ACTIVE_DECLARATION_AUDIT: ContextVar[
    _DeclarationImplementationAudit | None
] = ContextVar("active_census_declaration_audit", default=None)


class _TrackedDeclaration(dict[str, Any]):
    """leaf 値の読取りを宣言パスとして記録する dict。"""

    def __init__(
        self,
        value: dict[str, Any],
        *,
        path: str,
        audit: _DeclarationImplementationAudit,
    ) -> None:
        self._path = path
        self._audit = audit
        super().__init__(
            {
                key: _wrap_tracked_declaration_value(
                    child,
                    path=f"{path}.{key}" if path else key,
                    audit=audit,
                )
                for key, child in value.items()
            }
        )

    def _record(self, key: str, value: object) -> None:
        path = f"{self._path}.{key}" if self._path else key
        if isinstance(value, dict):
            return
        self._audit.read_fields.add(path)
        self._audit.implementation_sources.add(path)

    def __getitem__(self, key: str) -> Any:
        """leaf の直接参照を追跡する。"""
        value = super().__getitem__(key)
        self._record(key, value)
        return value

    def get(self, key: object, default: Any = None) -> Any:
        """leaf の get 参照を追跡する。"""
        if not isinstance(key, str) or key not in self:
            return default
        return self[key]


def _wrap_tracked_declaration_value(
    value: object,
    *,
    path: str,
    audit: _DeclarationImplementationAudit,
) -> object:
    """JSON 値を同じ値の読取り追跡付き構造へ変換する。"""
    if isinstance(value, dict):
        return _TrackedDeclaration(value, path=path, audit=audit)
    if isinstance(value, list):
        item_path = f"{path}[]"
        return [
            _wrap_tracked_declaration_value(
                item,
                path=item_path,
                audit=audit,
            )
            for item in value
        ]
    return value


@contextmanager
def _audit_declaration_implementation() -> Iterator[_DeclarationImplementationAudit]:
    """単一 census 実行の宣言読取りを隔離して追跡する。"""
    audit = _DeclarationImplementationAudit()
    token = _ACTIVE_DECLARATION_AUDIT.set(audit)
    try:
        yield audit
    finally:
        _ACTIVE_DECLARATION_AUDIT.reset(token)


def _record_undeclared_implementation_input(description: str) -> None:
    """比較元構築へ宣言外の値が入った変異を監査へ記録する。"""
    audit = _ACTIVE_DECLARATION_AUDIT.get()
    if audit is not None:
        audit.undeclared_inputs.add(description)


def _object(value: object, location: str) -> dict[str, Any]:
    """宣言値を JSON object として取得する。"""
    assert isinstance(value, dict), f"{location}: object が必要"
    return value


def _string(value: object, location: str) -> str:
    """宣言値を空でない文字列として取得する。"""
    assert isinstance(value, str) and value, f"{location}: 空でない文字列が必要"
    return value


def _string_array(value: object, location: str) -> tuple[str, ...]:
    """宣言値を空でない文字列配列として取得する。"""
    assert isinstance(value, list) and value, f"{location}: 空でない配列が必要"
    assert all(isinstance(item, str) and item for item in value), (
        f"{location}: 空でない文字列だけが必要"
    )
    return tuple(value)


def _array(value: object, location: str) -> list[object]:
    """宣言値を空でない配列として取得する。"""
    assert isinstance(value, list) and value, f"{location}: 空でない配列が必要"
    return value


def _integer(value: object, location: str) -> int:
    """宣言値を bool ではない整数として取得する。"""
    assert isinstance(value, int) and not isinstance(value, bool), (
        f"{location}: 整数が必要"
    )
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], location: str) -> None:
    """宣言 object が期待キーの exact-set であることを検証する。"""
    assert set(value) == expected, (
        f"{location}: キーが不一致: "
        f"missing={sorted(expected - set(value))}, "
        f"extra={sorted(set(value) - expected)}"
    )


def _load_census_baseline_declaration() -> dict[str, Any]:
    """census の固定比較元宣言を読む。"""
    value = json.loads(CENSUS_BASELINE_PATH.read_text(encoding="utf-8"))
    declaration = _object(value, CENSUS_BASELINE_PATH.as_posix())
    audit = _ACTIVE_DECLARATION_AUDIT.get()
    if audit is None:
        return declaration
    audit.declarations.append(copy.deepcopy(declaration))
    return _TrackedDeclaration(declaration, path="", audit=audit)


def _declared_implementation_fields(declaration: dict[str, Any]) -> frozenset[str]:
    """census 宣言の実装向けフィールドを wildcard パスへ全数展開する。"""
    excluded_top_level = {
        "contract_revision",
        "baseline_control",
        "implementation_field_inventory",
    }
    fields: set[str] = set()

    def collect(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                collect(child, f"{path}.{key}" if path else key)
            return
        fields.add(path)
        if isinstance(value, list) and any(
            isinstance(item, dict) for item in value
        ):
            for item in value:
                if isinstance(item, dict):
                    collect(item, f"{path}[]")

    for key, value in declaration.items():
        if key not in excluded_top_level:
            collect(value, key)
    return frozenset(fields)


def _assert_declaration_implementation_wiring(
    audit: _DeclarationImplementationAudit,
) -> None:
    """宣言全数・read 集合・実装入力元を両方向に完全照合する。"""
    assert audit.declarations, "census 宣言の読取り記録が無い"
    first = audit.declarations[0]
    assert all(declaration == first for declaration in audit.declarations), (
        "単一実行中に census 宣言の内容が変化した"
    )
    raw_inventory = first.get("implementation_field_inventory")
    inventory = frozenset(
        _string_array(raw_inventory, "census.implementation_field_inventory")
    )
    assert len(inventory) == len(cast(list[object], raw_inventory)), (
        "implementation_field_inventory を重複できない"
    )
    declared_fields = _declared_implementation_fields(first)
    assert declared_fields == inventory, (
        "宣言フィールド全数表が不一致: "
        f"missing={sorted(declared_fields - inventory)}, "
        f"extra={sorted(inventory - declared_fields)}"
    )
    assert audit.read_fields == inventory, (
        "宣言と実装の read 集合が不一致: "
        f"unread={sorted(inventory - audit.read_fields)}, "
        f"undeclared={sorted(audit.read_fields - inventory)}"
    )
    assert audit.implementation_sources <= inventory, (
        "比較元構築が宣言外フィールドを使用: "
        f"{sorted(audit.implementation_sources - inventory)}"
    )
    assert not audit.undeclared_inputs, (
        f"比較元構築が宣言外の値を使用: {sorted(audit.undeclared_inputs)}"
    )


def _assert_declared_anchor_materialization_provenance(
    *,
    declaration: dict[str, Any],
    destination: Path,
    listed_revision: str,
    relative_paths: tuple[str, ...],
    monitor: object,
    observed_blobs: dict[str, _ObservedGitBlob],
    written_blobs: dict[str, _ObservedGitBlob],
) -> None:
    """列挙・取得・書込みが同じ宣言アンカーの内容であることを検証する。"""
    anchor = _object(declaration.get("anchor"), "census.anchor")
    anchor_commit = _string(anchor.get("commit"), "census.anchor.commit")
    assert listed_revision == anchor_commit, (
        f"列挙 revision が宣言アンカーと不一致: {listed_revision}"
    )
    assert set(observed_blobs) == set(relative_paths), (
        "git show の観測集合が materialize 対象と不一致"
    )
    assert set(written_blobs) == set(relative_paths), (
        "書込み証跡が materialize 対象と不一致"
    )
    for relative_path in relative_paths:
        observed = observed_blobs[relative_path]
        written = written_blobs[relative_path]
        assert observed.monitor is monitor, (
            f"git show の観測世代が監視開始前: {relative_path}"
        )
        assert written is observed, (
            f"書込みが監視した git show 応答を消費していない: {relative_path}"
        )
        assert observed.revision == anchor_commit, (
            "取得 revision が宣言アンカーと不一致: "
            f"{relative_path}: {observed.revision}"
        )
        materialized_content = (destination / relative_path).read_bytes()
        assert materialized_content == observed.content, (
            f"materialize 内容が監視した git show と不一致: {relative_path}"
        )


def _materialize_declared_anchor(
    destination: Path,
) -> tuple[dict[str, Any], dict[str, bytes], str]:
    """宣言アンカーの対象ファイルを展開し、ツリー digest を突合する。"""
    declaration = _load_census_baseline_declaration()
    anchor = _object(declaration.get("anchor"), "census.anchor")
    anchor_commit = _string(anchor.get("commit"), "census.anchor.commit")
    assert anchor.get("resolution") == "direct_full_commit_sha"
    assert len(anchor_commit) == 40

    tree = _object(declaration.get("materialized_tree"), "census.materialized_tree")
    assert tree.get("digest_algorithm") == "sha256"
    expected_digest = _string(tree.get("digest"), "census.materialized_tree.digest")
    assert len(expected_digest) == 64
    expected_file_count = tree.get("file_count")
    assert isinstance(expected_file_count, int) and expected_file_count > 0
    paths = _string_array(tree.get("paths"), "census.materialized_tree.paths")
    assert tree.get("path_enumeration") == "git_ls_tree_recursive_names"
    assert tree.get("path_order") == "lexicographic_ascending"
    assert tree.get("entry_encoding") == (
        "relative_path + NUL + lowercase_content_sha256 + LF"
    )

    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", anchor_commit, "--", *paths],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    relative_paths = tuple(sorted(result.stdout.splitlines()))
    assert len(relative_paths) == expected_file_count
    assert len(relative_paths) == len(set(relative_paths))

    destination.mkdir(parents=True)
    contents: dict[str, bytes] = {}
    monitor = object()
    observed_blobs: dict[str, _ObservedGitBlob] = {}
    written_blobs: dict[str, _ObservedGitBlob] = {}
    digest_rows: list[bytes] = []
    for relative_path in relative_paths:
        path = Path(relative_path)
        assert not path.is_absolute() and ".." not in path.parts
        content = subprocess.run(
            ["git", "show", f"{anchor_commit}:{relative_path}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        target = destination / path
        observed = _ObservedGitBlob(monitor, anchor_commit, content)
        observed_blobs[relative_path] = observed
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(observed.content)
        written_blobs[relative_path] = observed
        contents[relative_path] = content
        content_digest = hashlib.sha256(content).hexdigest()
        digest_rows.append(
            relative_path.encode("utf-8")
            + b"\0"
            + content_digest.encode("ascii")
            + b"\n"
        )

    _assert_declared_anchor_materialization_provenance(
        declaration=declaration,
        destination=destination,
        listed_revision=anchor_commit,
        relative_paths=relative_paths,
        monitor=monitor,
        observed_blobs=observed_blobs,
        written_blobs=written_blobs,
    )

    actual_digest = hashlib.sha256(b"".join(digest_rows)).hexdigest()
    assert actual_digest == expected_digest
    return declaration, contents, actual_digest


def _cross_check_accepted_external_snapshots(
    declaration: dict[str, Any],
    materialized_contents: dict[str, bytes],
) -> dict[str, str]:
    """受理記録とアンカー由来 checker・helper の digest を相互検査する。"""
    cross_check = _object(
        declaration.get("acceptance_cross_check"),
        "census.acceptance_cross_check",
    )
    assert cross_check.get("requirement") == (
        "accepted_external_snapshot_sha256_equals_materialized_git_content_sha256"
    )
    acceptance_id = _string(
        cross_check.get("acceptance_id"),
        "census.acceptance_cross_check.acceptance_id",
    )
    history_asset = _string(
        cross_check.get("history_asset"),
        "census.acceptance_cross_check.history_asset",
    )
    checker_path = _string(
        cross_check.get("checker_path"),
        "census.acceptance_cross_check.checker_path",
    )
    helper_path = _string(
        cross_check.get("helper_path"),
        "census.acceptance_cross_check.helper_path",
    )
    history_asset_path = REPOSITORY_ROOT / history_asset
    history_asset_value = _object(
        json.loads(history_asset_path.read_text(encoding="utf-8")),
        history_asset,
    )
    control = _object(history_asset_value.get("baseline_control"), "history.control")
    history = control.get("history")
    assert isinstance(history, list)
    matching_records = [
        _object(record, "history.record")
        for record in history
        if isinstance(record, dict) and record.get("acceptance_id") == acceptance_id
    ]
    assert len(matching_records) == 1
    change = _object(matching_records[0].get("change"), "history.record.change")
    before = _object(change.get("before"), "history.record.change.before")
    raw_snapshots = before.get("external_snapshots")
    assert isinstance(raw_snapshots, list)
    snapshots = {
        _string(snapshot.get("path"), "history.external_snapshot.path"): _string(
            snapshot.get("sha256"),
            "history.external_snapshot.sha256",
        )
        for raw_snapshot in raw_snapshots
        if isinstance(raw_snapshot, dict)
        for snapshot in [_object(raw_snapshot, "history.external_snapshot")]
    }
    assert len(snapshots) == len(raw_snapshots)

    verified: dict[str, str] = {}
    for relative_path in (checker_path, helper_path):
        assert relative_path in materialized_contents
        actual_digest = hashlib.sha256(
            materialized_contents[relative_path]
        ).hexdigest()
        assert snapshots.get(relative_path) == actual_digest
        verified[relative_path] = actual_digest
    return verified


def _load_isolated_anchor_checker(
    reference_root: Path,
    declaration: dict[str, Any],
) -> tuple[ModuleType, Path]:
    """materialize 済みの旧 checker と helper を import 状態から隔離して読む。"""
    cross_check = _object(
        declaration.get("acceptance_cross_check"),
        "census.acceptance_cross_check",
    )
    checker_path = reference_root / _string(
        cross_check.get("checker_path"),
        "census.acceptance_cross_check.checker_path",
    )
    helper_path = (
        reference_root
        / _string(
            cross_check.get("helper_path"),
            "census.acceptance_cross_check.helper_path",
        )
    ).resolve()
    scripts_directory = checker_path.resolve().parent
    previous_path = list(sys.path)
    previous_modules = dict(sys.modules)
    try:
        sys.path.insert(0, str(scripts_directory))
        sys.modules.pop("frozen_history", None)
        module_name = "check_tenant_boundary_bypass_declared_anchor"
        spec = importlib.util.spec_from_file_location(module_name, checker_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        loaded_helper = sys.modules.get("frozen_history")
        assert loaded_helper is not None
        loaded_helper_file = Path(
            _string(getattr(loaded_helper, "__file__", None), "frozen_history.__file__")
        ).resolve()
        assert loaded_helper_file == helper_path
        assert loaded_helper_file.is_relative_to(reference_root.resolve())
        assert Path(_string(module.__file__, "checker.__file__")).resolve().is_relative_to(
            reference_root.resolve()
        )
        return module, loaded_helper_file
    finally:
        sys.path[:] = previous_path
        sys.modules.clear()
        sys.modules.update(previous_modules)


def _assert_loaded_checker_from_materialized_anchor(
    checker_module: ModuleType,
    *,
    reference_root: Path,
    declaration: dict[str, Any],
) -> None:
    """比較 checker が宣言アンカーの materialize 先そのものであると検証する。"""
    cross_check = _object(
        declaration.get("acceptance_cross_check"),
        "census.acceptance_cross_check",
    )
    checker_path = _string(
        cross_check.get("checker_path"),
        "census.acceptance_cross_check.checker_path",
    )
    expected = (reference_root / checker_path).resolve()
    actual = Path(
        _string(getattr(checker_module, "__file__", None), "checker.__file__")
    ).resolve()
    assert actual == expected, (
        f"比較 checker が宣言アンカーの materialize 先でない: {actual}"
    )


def _declared_anchor_checker(
    reference_root: Path,
) -> tuple[ModuleType, Path, Path, str, dict[str, str]]:
    """宣言の検査を完了した比較元 checker と検証証跡を返す。"""
    declaration, contents, tree_digest = _materialize_declared_anchor(
        reference_root
    )
    verified_snapshots = _cross_check_accepted_external_snapshots(
        declaration,
        contents,
    )
    baseline_checker, helper_file = _load_isolated_anchor_checker(
        reference_root,
        declaration,
    )
    _assert_loaded_checker_from_materialized_anchor(
        baseline_checker,
        reference_root=reference_root,
        declaration=declaration,
    )
    return (
        baseline_checker,
        reference_root,
        helper_file,
        tree_digest,
        verified_snapshots,
    )


def _checker_census(
    checker_module: ModuleType,
    *,
    repository_root: Path,
    source_root: Path,
) -> frozenset[CensusIdentity]:
    """検査器の全文走査結果を比較用の exact-set にする。"""
    contract = checker_module.load_contract(repository_root)
    violations = checker_module.scan_directory(source_root, contract=contract)
    return frozenset(
        (
            violation.path,
            violation.line,
            violation.end_line,
            violation.scope,
            violation.code,
            violation.symbol,
            violation.message,
        )
        for violation in violations
    )


def _compare_checker_census(
    reference_checker: ModuleType,
    candidate_checker: ModuleType,
    *,
    repository_root: Path,
    source_root: Path,
    reference_repository_root: Path | None = None,
) -> tuple[frozenset[CensusIdentity], frozenset[CensusIdentity]]:
    """宣言アンカー版から作業ツリー版への違反集合の増減を返す。

    この比較が証明するのは、両版が ``source_root`` にある現在の
    ``backend/src`` へ出す違反集合が同じこと、またはその差が期待どおりであること。
    現在のツリーに存在しない構文やコードへの挙動は証明せず、将来のコードは覆わない。
    """
    reference = _checker_census(
        reference_checker,
        repository_root=reference_repository_root or repository_root,
        source_root=source_root,
    )
    candidate = _checker_census(
        candidate_checker,
        repository_root=repository_root,
        source_root=source_root,
    )
    return candidate - reference, reference - candidate


def _condition_rule(contract: Any, condition: int) -> Any:
    """契約から指定番号の条件を一意に取得する。"""
    matching = [rule for rule in contract.rules if rule.condition == condition]
    assert len(matching) == 1
    return matching[0]


def _normalize_identifier(value: str, normalization: str) -> str:
    """宣言された方式で Python 識別子または完全修飾名を正規化する。"""
    assert normalization == "python_identifier_or_qualified_name_to_snake_case"
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def _matches_condition_rule(text: str, rule: Any, normalization: str) -> bool:
    """独立に正規化した識別子を契約の条件パターンへ照合する。"""
    candidates = {_normalize_identifier(text, normalization)}
    candidates.update(
        _normalize_identifier(part, normalization) for part in text.split(".")
    )
    return any(
        pattern.search(candidate)
        for candidate in candidates
        for pattern in rule.patterns
    )


def _module_name(path: str) -> str:
    """source root 相対パスから Python モジュール名を導出する。"""
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _absolute_import_from_module(
    *,
    current_module: str,
    current_is_package: bool,
    imported_module: str | None,
    level: int,
) -> str | None:
    """相対 import の宣言から絶対モジュール名を導出する。"""
    if level == 0:
        return imported_module
    parts = current_module.split(".")
    if not current_is_package:
        parts.pop()
    parents_to_drop = level - 1
    if not parts or parents_to_drop >= len(parts):
        return None
    if parents_to_drop:
        parts = parts[:-parents_to_drop]
    if imported_module:
        parts.extend(imported_module.split("."))
    return ".".join(parts)


class _IndependentSymbolResolver(ast.NodeVisitor):
    """AST の import・代入・注釈だけから名前の静的な由来を集める。"""

    def __init__(
        self,
        *,
        module: str,
        module_is_package: bool,
        symbol_aliases: dict[str, str] | Any,
    ) -> None:
        self.module = module
        self.module_is_package = module_is_package
        self.symbol_aliases = symbol_aliases
        self.aliases = {
            name: f"builtins.{name}"
            for name, value in vars(builtins).items()
            if callable(value)
        }
        self.direct_import_names: set[str] = set()
        self.known_class_symbols = {
            f"builtins.{name}"
            for name, value in vars(builtins).items()
            if isinstance(value, type)
        }
        self.class_stack: list[str] = []

    def _canonical(self, symbol: str) -> str:
        """契約の公開別名を標準シンボルへ寄せる。"""
        return cast(str, self.symbol_aliases.get(symbol, symbol))

    def resolve(self, node: ast.AST) -> str | None:
        """AST 式を既知の完全修飾名へ解決する。"""
        if isinstance(node, ast.Subscript):
            return self.resolve(node.value)
        if isinstance(node, ast.Name):
            return self._canonical(self.aliases.get(node.id, node.id))
        if isinstance(node, ast.Attribute):
            parent = self.resolve(node.value)
            if parent is None:
                return None
            return self._canonical(f"{parent}.{node.attr}")
        return None

    def _resolve_value(self, node: ast.AST) -> str | None:
        """代入値から後続の Name が表す静的な型またはシンボルを得る。"""
        resolved = self.resolve(node)
        if resolved is not None:
            return resolved
        if isinstance(node, ast.Dict):
            return "builtins.dict"
        if isinstance(node, ast.List):
            return "builtins.list"
        if isinstance(node, ast.Set):
            return "builtins.set"
        if isinstance(node, ast.Tuple):
            return "builtins.tuple"
        if isinstance(node, ast.Constant):
            return f"builtins.{type(node.value).__name__}"
        return None

    def _record(self, local_name: str, symbol: str) -> None:
        """確認できたローカル名の由来を記録する。"""
        self.aliases[local_name] = self._canonical(symbol)

    def _record_arguments(self, arguments: ast.arguments) -> None:
        """関数引数の注釈を静的な名前解決へ反映する。"""
        all_arguments = (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            arguments.vararg,
            arguments.kwarg,
        )
        for argument in all_arguments:
            if argument is None or argument.annotation is None:
                continue
            resolved = self.resolve(argument.annotation)
            if resolved is not None:
                self._record(argument.arg, resolved)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """import が束縛する名前と絶対名を記録する。"""
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            imported = alias.name if alias.asname else alias.name.split(".")[0]
            self.direct_import_names.add(local_name)
            self._record(local_name, imported)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """from import が束縛する名前と絶対名を記録する。"""
        module = _absolute_import_from_module(
            current_module=self.module,
            current_is_package=self.module_is_package,
            imported_module=node.module,
            level=node.level,
        )
        if module is None:
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            self.direct_import_names.add(local_name)
            self._record(local_name, f"{module}.{alias.name}")

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """単純代入値の静的な由来を名前へ伝播する。"""
        self.visit(node.value)
        resolved = self._resolve_value(node.value)
        if resolved is None:
            return
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._record(target.id, resolved)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """注釈付き名前へ注釈の静的な由来を伝播する。"""
        resolved_annotation = self.resolve(node.annotation)
        if isinstance(node.target, ast.Name) and resolved_annotation is not None:
            self._record(node.target.id, resolved_annotation)
        if node.value is not None:
            self.visit(node.value)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """クラス定義名とクラス内の注釈・代入を収集する。"""
        symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
        self._record(node.name, symbol)
        self.known_class_symbols.add(symbol)
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """関数定義名・引数注釈・関数内の代入を収集する。"""
        symbol = ".".join([self.module, *self.class_stack, node.name]).strip(".")
        self._record(node.name, symbol)
        self._record_arguments(node.args)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """同期関数の名前解決情報を収集する。"""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数の名前解決情報を収集する。"""
        self._visit_function(node)


class _IndependentCondition2Candidates(ast.NodeVisitor):
    """候補 checker を使わず AST と両契約から条件2の増分を導出する。"""

    def __init__(
        self,
        *,
        path: str,
        tree: ast.Module,
        current_resolver: _IndependentSymbolResolver,
        anchor_resolver: _IndependentSymbolResolver,
        current_contract: Any,
        anchor_contract: Any,
        enumeration: dict[str, Any],
        identity_fields: tuple[str, ...],
    ) -> None:
        self.path = path
        self.module = _module_name(path)
        self.current_resolver = current_resolver
        self.anchor_resolver = anchor_resolver
        self.identity_fields = identity_fields
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.identities: set[CensusIdentity] = set()
        self.violation_keys: set[tuple[int, int, str, str]] = set()
        node_types = _string_array(
            enumeration.get("ast_node_type"),
            "candidate_enumeration.ast_node_type",
        )
        assert len(node_types) == len(set(node_types)), (
            "candidate_enumeration.ast_node_type: 重複を許可しない"
        )
        self.node_types = frozenset(node_types)

        condition = _integer(
            enumeration.get("condition"),
            "candidate_enumeration.condition",
        )
        self.current_rule = _condition_rule(current_contract, condition)
        self.anchor_rule = _condition_rule(anchor_contract, condition)
        self.condition = condition
        self.message = _string(
            enumeration.get("message"),
            "candidate_enumeration.message",
        )
        self.current_projection = _string(
            enumeration.get("current_contract_projection"),
            "candidate_enumeration.current_contract_projection",
        )
        self.anchor_projection = _string(
            enumeration.get("anchor_contract_projection"),
            "candidate_enumeration.anchor_contract_projection",
        )
        self.identity_symbol_projection = _string(
            enumeration.get("identity_symbol_projection"),
            "candidate_enumeration.identity_symbol_projection",
        )
        self.normalization = _string(
            enumeration.get("identifier_normalization"),
            "candidate_enumeration.identifier_normalization",
        )
        self.adjudicated_symbols = {
            adjudication.symbol
            for adjudication in getattr(current_contract, "condition2_adjudications", ())
        }
        self.visit(tree)

    @staticmethod
    def _projection(
        projection: str,
        *,
        identifier: str,
        resolved_symbol: str,
    ) -> str:
        """宣言された候補 projection をサイト値へ適用する。"""
        values = {
            "syntax_identifier": identifier,
            "resolved_symbol": resolved_symbol,
        }
        assert projection in values, f"未対応の候補 projection: {projection}"
        return values[projection]

    def _scope(self) -> str:
        """候補サイトの CensusIdentity scope を組み立てる。"""
        if self.function_stack:
            return self.function_stack[-1]
        return ".".join([self.module, *self.class_stack, "<module>"])

    def _record_candidate(
        self,
        node: ast.AST,
        *,
        identifier: str,
        current_resolved_symbol: str,
        anchor_resolved_symbol: str,
    ) -> None:
        """単一 AST サイトを両版の条件2候補抽出へ照合する。"""
        if type(node).__name__ not in self.node_types:
            return
        current_candidate = self._projection(
            self.current_projection,
            identifier=identifier,
            resolved_symbol=current_resolved_symbol,
        )
        anchor_candidate = self._projection(
            self.anchor_projection,
            identifier=identifier,
            resolved_symbol=anchor_resolved_symbol,
        )
        if not _matches_condition_rule(
            current_candidate,
            self.current_rule,
            self.normalization,
        ) or _matches_condition_rule(
            anchor_candidate,
            self.anchor_rule,
            self.normalization,
        ):
            return
        adjudication_candidates = {
            identifier,
            current_resolved_symbol,
            f"{self.module}.{identifier}",
        }
        if adjudication_candidates & self.adjudicated_symbols:
            return
        symbol = self._projection(
            self.identity_symbol_projection,
            identifier=identifier,
            resolved_symbol=current_resolved_symbol,
        )
        line = cast(int, getattr(node, "lineno"))
        end_line = cast(int | None, getattr(node, "end_lineno", None)) or line
        code = cast(str, self.current_rule.error)
        key = (line, self.condition, code, symbol)
        if key in self.violation_keys:
            return
        self.violation_keys.add(key)
        values: dict[str, str | int] = {
            "path": self.path,
            "line": line,
            "end_line": end_line,
            "scope": self._scope(),
            "code": code,
            "symbol": symbol,
            "message": self.message,
        }
        self.identities.add(
            cast(
                CensusIdentity,
                tuple(values[field] for field in self.identity_fields),
            )
        )

    def _record_syntax_candidate(self, node: ast.AST, identifier: str) -> None:
        """現行版で新設された構文サイトを条件2候補として記録する。"""
        self._record_candidate(
            node,
            identifier=identifier,
            current_resolved_symbol=identifier,
            anchor_resolved_symbol="",
        )

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """Name サイトを現行・アンカー両契約の候補規則へ照合する。"""
        self._record_candidate(
            node,
            identifier=node.id,
            current_resolved_symbol=self.current_resolver.resolve(node) or node.id,
            anchor_resolved_symbol=self.anchor_resolver.resolve(node) or node.id,
        )

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        """Attribute サイトを現行・アンカー両契約へ照合する。"""
        self._record_candidate(
            node,
            identifier=node.attr,
            current_resolved_symbol=(
                self.current_resolver.resolve(node) or node.attr
            ),
            anchor_resolved_symbol=(
                self.anchor_resolver.resolve(node) or node.attr
            ),
        )
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        """引数名を現行版の構文候補として照合する。"""
        self._record_syntax_candidate(node, node.arg)
        if node.annotation is not None:
            self.visit(node.annotation)

    def visit_keyword(self, node: ast.keyword) -> None:
        """呼び出し・class keyword 名を現行版の構文候補として照合する。"""
        if node.arg is not None:
            self._record_syntax_candidate(node, node.arg)
        self.visit(node.value)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:  # noqa: N802
        """match capture 名を現行版の構文候補として照合する。"""
        if node.name is not None:
            self._record_syntax_candidate(node, node.name)
        if node.pattern is not None:
            self.visit(node.pattern)

    def visit_MatchClass(self, node: ast.MatchClass) -> None:  # noqa: N802
        """class pattern の keyword 名を現行版の構文候補として照合する。"""
        for name in node.kwd_attrs:
            self._record_syntax_candidate(node, name)
        self.generic_visit(node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:  # noqa: N802
        """mapping rest capture 名を現行版の構文候補として照合する。"""
        if node.rest is not None:
            self._record_syntax_candidate(node, node.rest)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:  # noqa: N802
        """star capture 名を現行版の構文候補として照合する。"""
        if node.name is not None:
            self._record_syntax_candidate(node, node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """scanner と同じ順序でクラス定義式と本体の scope を扱う。"""
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        for type_parameter in node.type_params:
            self.visit(type_parameter)
        self.class_stack.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.class_stack.pop()

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """scanner と同じ順序で関数定義式と本体の scope を扱う。"""
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            node.args.vararg,
            node.args.kwarg,
        )
        for argument in arguments:
            if argument is not None:
                self.visit(argument)
        if node.returns is not None:
            self.visit(node.returns)
        for type_parameter in node.type_params:
            self.visit(type_parameter)
        prefix = ".".join([self.module, *self.class_stack]).strip(".")
        symbol = f"{prefix}.{node.name}" if prefix else node.name
        self.function_stack.append(symbol)
        for statement in node.body:
            self.visit(statement)
        self.function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """同期関数の候補サイトを列挙する。"""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """非同期関数の候補サイトを列挙する。"""
        self._visit_function(node)


def _identity_fields(declaration: dict[str, Any]) -> tuple[str, ...]:
    """宣言された CensusIdentity のフィールド順を取得する。"""
    identity = _object(declaration.get("census_identity"), "census.census_identity")
    _exact_keys(identity, {"kind", "ordered_fields"}, "census.census_identity")
    assert identity.get("kind") == "ordered_tuple"
    fields = _string_array(
        identity.get("ordered_fields"),
        "census.census_identity.ordered_fields",
    )
    assert len(fields) == len(set(fields))
    return fields


def _independently_derived_added(
    *,
    declaration: dict[str, Any],
    predicate: dict[str, Any],
    source_root: Path,
    current_contract: Any,
    anchor_contract: Any,
) -> frozenset[CensusIdentity]:
    """現行 backend/src の AST と両契約だけから条件2の増分を導出する。"""
    assert predicate.get("candidate_source") == "current_backend_src_ast"
    assert predicate.get("filters") == [
        "matches_current_condition_2_contract",
        "does_not_match_anchor_condition_2_contract",
    ]
    assert predicate.get("forbidden_derivation_source") == (
        "candidate_checker_census"
    )
    enumeration = _object(
        predicate.get("candidate_enumeration"),
        "pass_fail_mapping.predicate.candidate_enumeration",
    )
    _exact_keys(
        enumeration,
        {
            "source_glob",
            "ast_node_type",
            "current_contract_projection",
            "anchor_contract_projection",
            "identity_symbol_projection",
            "identifier_normalization",
            "condition",
            "message",
        },
        "pass_fail_mapping.predicate.candidate_enumeration",
    )
    ast_node_types = _string_array(
        enumeration.get("ast_node_type"),
        "candidate_enumeration.ast_node_type",
    )
    assert len(ast_node_types) == len(set(ast_node_types)), (
        "candidate_enumeration.ast_node_type: 重複を許可しない"
    )
    source_glob = _string(
        enumeration.get("source_glob"),
        "candidate_enumeration.source_glob",
    )
    identities: set[CensusIdentity] = set()
    for path in sorted(source_root.rglob(source_glob)):
        relative_path = path.relative_to(source_root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        current_resolver = _IndependentSymbolResolver(
            module=_module_name(relative_path),
            module_is_package=path.stem == "__init__",
            symbol_aliases=current_contract.symbol_aliases,
        )
        current_resolver.visit(tree)
        anchor_resolver = _IndependentSymbolResolver(
            module=_module_name(relative_path),
            module_is_package=path.stem == "__init__",
            symbol_aliases=anchor_contract.symbol_aliases,
        )
        anchor_resolver.visit(tree)
        candidates = _IndependentCondition2Candidates(
            path=relative_path,
            tree=tree,
            current_resolver=current_resolver,
            anchor_resolver=anchor_resolver,
            current_contract=current_contract,
            anchor_contract=anchor_contract,
            enumeration=enumeration,
            identity_fields=_identity_fields(declaration),
        )
        identities.update(candidates.identities)
    return frozenset(identities)


def _assert_removed_tb007_matches_declared_relaxations(
    removed: frozenset[CensusIdentity],
    *,
    expected_code: str,
) -> None:
    """減分を宣言済みの緩和と発行入口の exact な許可に帰属させる。"""
    source_root = REPOSITORY_ROOT / "backend" / "src"
    sources = {
        path.relative_to(source_root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.py"))
    }
    reexport_map = checker._build_reexport_map(sources)
    contract = checker.load_contract(REPOSITORY_ROOT)
    scanners: dict[str, tuple[ast.Module, Any]] = {}

    for identity in removed:
        path, line, end_line, scope, code, symbol, _ = identity
        assert code == expected_code
        if path not in scanners:
            tree = ast.parse(sources[path], filename=path)
            scanner = checker._SourceScanner(
                path=path,
                module=checker._module_name(path),
                tree=tree,
                changed_lines=None,
                contract=contract,
                reject_all_db_calls=False,
                reexport_map=reexport_map,
            )
            scanner.visit(tree)
            scanner._validate_call_coverage(tree)
            scanners[path] = (tree, scanner)
        tree, scanner = scanners[path]

        matching_calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if node.lineno != line or node.end_lineno != end_line:
                continue
            resolved = scanner.aliases.resolve(
                node.func
            ) or scanner._raw_expression(node.func)
            if symbol == "<unresolved-callable>" or symbol == resolved:
                matching_calls.append(node)

        assert matching_calls, identity
        explanations = []
        for node in matching_calls:
            resolved = scanner.aliases.resolve(
                node.func
            ) or scanner._raw_expression(node.func)
            if (
                isinstance(node.func, ast.Name)
                and id(node.func) in scanner.lexically_bound_name_ids
            ):
                explanations.append(node)
                continue
            constructor_name = contract.tenant_context.constructor_symbol.rsplit(
                ".", 1
            )[-1]
            callable_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if callable_name == constructor_name:
                if (
                    symbol == contract.tenant_context.constructor_symbol
                    and scope == contract.tenant_context.issuance_entrypoint_symbol
                    and scanner.module
                    in contract.tenant_context.allowed_product_modules
                    and (
                        resolved == contract.tenant_context.constructor_symbol
                        or scanner.flow.callable_symbol(node)
                        == contract.tenant_context.constructor_symbol
                    )
                ):
                    explanations.append(node)
                continue
            reexport = scanner._reexport_resolution(node.func, resolved)
            if reexport is not None and (
                reexport.unresolved
                or contract.tenant_context.constructor_symbol in reexport.origins
            ):
                continue
            known_callable = scanner.flow.callable_symbol(node)
            if (
                known_callable is not None
                and known_callable
                != contract.tenant_context.constructor_symbol
            ):
                explanations.append(node)
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and known_callable is None
            ):
                explanations.append(node)
                continue
            alias_resolved = scanner.aliases.resolve(node.func)
            known_alias_callable = (
                scanner.aliases.resolve_known(node.func)
                if isinstance(node.func, ast.Name) and alias_resolved is not None
                else None
            )
            if (
                known_alias_callable is not None
                and scanner.aliases.canonical(known_alias_callable)
                != contract.tenant_context.constructor_symbol
                and known_callable is None
            ):
                explanations.append(node)

        assert explanations, identity


def test_issuance_constructor_relaxation_rejects_another_scope(
    census_predicate_context: dict[str, Any],
) -> None:
    """許可モジュール内でも発行入口以外の構築は緩和に含めない。"""
    data_sets = cast(
        dict[str, frozenset[CensusIdentity]], census_predicate_context["data_sets"]
    )
    entrypoint = checker.load_contract(
        REPOSITORY_ROOT
    ).tenant_context.issuance_entrypoint_symbol
    original = next(
        identity
        for identity in data_sets["removed"]
        if identity[0].endswith("tenant_context_issuance.py")
        and identity[3] == entrypoint
        and identity[4] == "TB007"
    )
    changed = _replace_identity_field(original, index=3, value=f"{entrypoint}.other")
    with pytest.raises(AssertionError):
        _assert_removed_tb007_matches_declared_relaxations(
            frozenset({changed}), expected_code="TB007"
        )


def _load_json_pointer(
    locator: str, *, repository_root: Path | None = None
) -> object:
    """リポジトリ相対 JSON path と RFC 6901 pointer の宣言値を読む。"""
    relative_path, separator, pointer = locator.partition("#")
    assert separator and pointer.startswith("/"), f"JSON pointer が不正: {locator}"
    root = repository_root or REPOSITORY_ROOT
    value: object = json.loads((root / relative_path).read_text(encoding="utf-8"))
    for raw_part in pointer.removeprefix("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = _object(value, locator)
        assert part in current, f"JSON pointer の参照先が無い: {locator}"
        value = current[part]
    return value


def _predicate_data_sets(
    *,
    added: frozenset[CensusIdentity],
    removed: frozenset[CensusIdentity],
    current_census: frozenset[CensusIdentity],
) -> dict[str, frozenset[CensusIdentity]]:
    """宣言中の集合名を実測 census 集合へ対応付ける。"""
    return {
        "added": added,
        "removed": removed,
        "current_census": current_census,
    }


def _declared_predicates(declaration: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """合否写像の述語宣言を順序どおり取得する。"""
    mapping = _object(
        declaration.get("pass_fail_mapping"),
        "census.pass_fail_mapping",
    )
    _exact_keys(mapping, {"predicates"}, "census.pass_fail_mapping")
    predicates = tuple(
        _object(raw, f"census.pass_fail_mapping.predicates[{index}]")
        for index, raw in enumerate(
            _array(mapping.get("predicates"), "census.pass_fail_mapping.predicates")
        )
    )
    predicate_ids = [
        _string(predicate.get("id"), "pass_fail_mapping.predicate.id")
        for predicate in predicates
    ]
    assert len(predicate_ids) == len(set(predicate_ids))
    return predicates


def _assert_difference_codes_within_allowed_set(
    predicate: dict[str, Any],
    *,
    data_sets: dict[str, frozenset[CensusIdentity]],
    identity_indexes: dict[str, int],
    **_: Any,
) -> None:
    """宣言された集合の code が宣言 allowed-set 内にあることを検証する。"""
    _exact_keys(predicate, {"id", "sets", "allowed_codes"}, predicate["id"])
    set_names = _string_array(predicate.get("sets"), f"{predicate['id']}.sets")
    allowed_codes = frozenset(
        _string_array(
            predicate.get("allowed_codes"),
            f"{predicate['id']}.allowed_codes",
        )
    )
    code_index = identity_indexes["code"]
    for set_name in set_names:
        assert set_name in data_sets, f"未知の census 集合: {set_name}"
        actual_codes = {
            identity[code_index] for identity in data_sets[set_name]
        }
        assert actual_codes <= allowed_codes, (
            f"{set_name}: undeclared={sorted(actual_codes - allowed_codes)}"
        )


def _counterfactual_allowed_symbol_rows(
    *,
    current_entries: list[dict[str, Any]],
    anchor_entries: list[dict[str, Any]],
    substituted_from: str,
) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]
]:
    """新規行と共通行の署名差を、記号単位の反実仮想に分ける。"""
    assert substituted_from == "anchor_symbol_set_plus_scoped_signature_rows"
    anchor_symbols = [
        _string(row.get("symbol"), "anchor.symbol") for row in anchor_entries
    ]
    current_symbols = [
        _string(row.get("symbol"), "current.symbol") for row in current_entries
    ]
    assert len(set(anchor_symbols)) == len(anchor_symbols)
    assert len(set(current_symbols)) == len(current_symbols)
    anchor_set = set(anchor_symbols)
    assert anchor_set <= set(current_symbols), (
        "anchor の許可記号を現行から削除できない"
    )
    retained = [row for row in current_entries if row["symbol"] in anchor_set]
    added = [row for row in current_entries if row["symbol"] not in anchor_set]
    current_by_symbol = {row["symbol"]: row for row in retained}
    changed_signatures: dict[str, dict[str, Any]] = {}
    for anchor_row in anchor_entries:
        symbol = anchor_row["symbol"]
        current_row = current_by_symbol[symbol]
        missing = object()
        different_fields = sorted(
            field
            for field in anchor_row.keys() | current_row.keys()
            if anchor_row.get(field, missing) != current_row.get(field, missing)
        )
        if different_fields:
            assert different_fields == ["signature"], (
                "共通する allowed_symbols の行差は署名だけ帰属できる"
                f"({symbol}: {', '.join(different_fields)})"
            )
            _string(anchor_row.get("signature"), f"anchor.{symbol}.signature")
            _string(current_row.get("signature"), f"current.{symbol}.signature")
            changed_signatures[symbol] = anchor_row
    return retained, added, changed_signatures


def _allowed_symbol_product_path(symbol: str, source_root: Path) -> str:
    """許可記号の所属する製品モジュールを曖昧さなく求める。"""
    parts = symbol.split(".")
    for length in range(len(parts) - 1, 0, -1):
        module = Path(*parts[:length])
        candidates = (
            module.with_suffix(".py"),
            module / "__init__.py",
        )
        existing = [
            candidate for candidate in candidates if (source_root / candidate).is_file()
        ]
        assert len(existing) <= 1, (
            f"許可記号の製品モジュールが曖昧: {symbol}: "
            f"{[path.as_posix() for path in existing]}"
        )
        if existing:
            return existing[0].as_posix()
    raise AssertionError(f"許可記号の製品モジュールが無い: {symbol}")


def _scoped_signature_suppression(
    identities: frozenset[CensusIdentity], *, product_path: str, symbol: str
) -> frozenset[CensusIdentity]:
    """署名差による製品定義の TB005 だけを帰属対象にする。"""
    return frozenset(
        identity
        for identity in identities
        if identity[0] == product_path
        and identity[4] == "TB005"
        and identity[5] == symbol
    )


def _measured_allowlist_suppression(
    *,
    substituted_field: str,
    substituted_from: str,
    reference_repository_root: Path,
    source_root: Path,
    current_census: frozenset[CensusIdentity],
) -> tuple[
    frozenset[CensusIdentity], frozenset[str], frozenset[CensusIdentity]
]:
    """現行 checker で新規行と共通行の署名差を個別に測る。

    ``Violation.path`` は ``scan_directory`` の ``backend/src`` 相対パス。
    fixture も同じ根からの相対パスへ写像するため、通常は
    ``../../tests/fixtures/...`` となり本番モジュールとは衝突しない。
    """
    current_rows = _array(_load_json_pointer(substituted_field), substituted_field)
    anchor_rows = _array(
        _load_json_pointer(
            substituted_field, repository_root=reference_repository_root
        ),
        f"anchor.{substituted_field}",
    )
    anchor_entries = [_object(row, "anchor.allowed_symbols[]") for row in anchor_rows]
    current_entries = [_object(row, "current.allowed_symbols[]") for row in current_rows]
    retained_rows, added_rows, changed_signatures = _counterfactual_allowed_symbol_rows(
        current_entries=current_entries,
        anchor_entries=anchor_entries,
        substituted_from=substituted_from,
    )
    fixture_root = Path("tests/fixtures/tenant_boundary/positive")
    grown_fixtures: set[str] = set()
    removed_paths: set[str] = set()
    for row in added_rows:
        fixture = _string(row.get("fixture"), f"{row['symbol']}.fixture")
        fixture_path = Path(fixture)
        assert not fixture_path.is_absolute(), f"fixture は相対パスが必要: {fixture}"
        try:
            fixture_path.relative_to(fixture_root)
        except ValueError as error:
            raise AssertionError(f"正例 fixture の外を指す: {fixture}") from error
        assert fixture_path.suffix == ".py" and ".." not in fixture_path.parts
        assert (REPOSITORY_ROOT / fixture_path).is_file(), (
            f"正例 fixture が存在しない: {fixture}"
        )
        mapped_path = Path(
            os.path.relpath(REPOSITORY_ROOT / fixture_path, source_root)
        ).as_posix()
        grown_fixtures.add(fixture)
        removed_paths.add(mapped_path)

    with tempfile.TemporaryDirectory(prefix="census-allowlist-counterfactual-") as raw:
        counterfactual_root = Path(raw)
        for relative in (
            Path("contracts/tenant_boundary"),
            Path("tests/fixtures/tenant_boundary"),
        ):
            shutil.copytree(REPOSITORY_ROOT / relative, counterfactual_root / relative)
        counterfactual_source = counterfactual_root / "backend/src"
        shutil.copytree(source_root, counterfactual_source)
        asset_path, _, _ = substituted_field.partition("#")
        asset = json.loads((counterfactual_root / asset_path).read_text(encoding="utf-8"))
        def scan_with_rows(rows: list[dict[str, Any]]) -> frozenset[CensusIdentity]:
            """同じソースに対し、指定した許可行で checker を走らせる。"""
            asset["allowed_symbols"] = rows
            (counterfactual_root / asset_path).write_text(
                json.dumps(asset, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return _checker_census(
                checker,
                repository_root=counterfactual_root,
                source_root=counterfactual_source,
            )

        signature_suppression: set[CensusIdentity] = set()
        for symbol, anchor_row in changed_signatures.items():
            single_row_reverted = [
                anchor_row if row["symbol"] == symbol else row
                for row in current_entries
            ]
            product_path = _allowed_symbol_product_path(symbol, source_root)
            signature_suppression.update(
                _scoped_signature_suppression(
                    scan_with_rows(single_row_reverted) - current_census,
                    product_path=product_path,
                    symbol=symbol,
                )
            )
        for fixture in grown_fixtures:
            target = counterfactual_root / fixture
            assert target.is_file(), f"反実仮想の正例 fixture が無い: {fixture}"
            target.unlink()
        counterfactual_census = scan_with_rows(retained_rows)
    suppression = (counterfactual_census - current_census) | signature_suppression
    assert not {str(identity[0]) for identity in suppression} & removed_paths, (
        "除いた fixture が抑止集合を製造した"
    )
    return (
        suppression,
        frozenset(removed_paths),
        current_census - counterfactual_census,
    )


def _measured_condition4_suppression(
    *,
    substituted_fields: tuple[str, ...],
    substituted_from: str,
    code: str,
    reference_repository_root: Path,
    source_root: Path,
    current_census: frozenset[CensusIdentity],
    current_contract: Any,
) -> frozenset[CensusIdentity]:
    """契約で増えた許可呼び出しの TB004 抑止だけを反実仮想で測る。"""
    assert substituted_fields == (
        "contracts/tenant_boundary/cache-invalidation-contract.json#/api/public_symbols",
        "contracts/tenant_boundary/cache-invalidation-contract.json#/api/condition4_allowed_call_symbols",
    )
    assert substituted_from == "anchor_symbol_set"
    assert code == "TB004"
    current_public = frozenset(
        _string_array(_load_json_pointer(substituted_fields[0]), substituted_fields[0])
    )
    anchor_public = frozenset(
        _string_array(
            _load_json_pointer(
                substituted_fields[0], repository_root=reference_repository_root
            ),
            f"anchor.{substituted_fields[0]}",
        )
    )
    current_calls = frozenset(
        _string_array(_load_json_pointer(substituted_fields[1]), substituted_fields[1])
    )
    anchor_calls = frozenset(
        _string_array(
            _load_json_pointer(
                substituted_fields[1], repository_root=reference_repository_root
            ),
            f"anchor.{substituted_fields[1]}",
        )
    )
    assert anchor_public <= current_public
    assert anchor_calls <= current_calls
    added_calls = current_calls - anchor_calls
    boundary = current_contract.cache_invalidation
    assert boundary.public_symbols == current_public
    assert boundary.allowed_call_symbols == current_calls
    counterfactual_contract = replace(
        current_contract,
        cache_invalidation=replace(
            boundary,
            public_symbols=anchor_public,
            allowed_call_symbols=anchor_calls,
        ),
    )
    counterfactual_census = frozenset(
        (
            violation.path,
            violation.line,
            violation.end_line,
            violation.scope,
            violation.code,
            violation.symbol,
            violation.message,
        )
        for violation in checker.scan_directory(
            source_root, contract=counterfactual_contract
        )
    )
    assert not current_census - counterfactual_census
    suppression = counterfactual_census - current_census
    assert all(
        identity[4] == code and identity[5] in added_calls
        for identity in suppression
    ), "宣言した許可呼び出し以外の違反が抑止された"
    return suppression


def _assert_removed_equals_measured_allowlist_suppression(
    predicate: dict[str, Any],
    *,
    data_sets: dict[str, frozenset[CensusIdentity]],
    identity_indexes: dict[str, int],
    source_root: Path,
    reference_repository_root: Path | None,
    current_contract: Any,
    **_: Any,
) -> None:
    """removed の対象外 code が実測した許可記号の抑止集合に含まれることを検証する。"""
    _exact_keys(
        predicate,
        {"id", "set", "applies_to_codes_outside", "derivation", "quantifier"},
        predicate["id"],
    )
    set_name = _string(predicate.get("set"), f"{predicate['id']}.set")
    assert set_name == "removed"
    assert set_name in data_sets
    excluded_codes = frozenset(
        _string_array(
            predicate.get("applies_to_codes_outside"),
            f"{predicate['id']}.applies_to_codes_outside",
        )
    )
    derivation = _object(predicate.get("derivation"), f"{predicate['id']}.derivation")
    _exact_keys(
        derivation,
        {
            "kind",
            "checker",
            "substituted_field",
            "substituted_from",
            "co_substituted",
            "relation",
            "condition4_substituted_fields",
            "condition4_substituted_from",
            "condition4_code",
        },
        f"{predicate['id']}.derivation",
    )
    assert _string(derivation.get("kind"), "derivation.kind") == (
        "counterfactual_allowlist_substitution"
    )
    assert _string(derivation.get("checker"), "derivation.checker") == "current"
    substituted_field = _string(
        derivation.get("substituted_field"), "derivation.substituted_field"
    )
    assert substituted_field == f"{checker.DEFAULT_ALLOWLIST.as_posix()}#/allowed_symbols"
    assert _string(derivation.get("substituted_from"), "derivation.substituted_from") == (
        "anchor_symbol_set_plus_scoped_signature_rows"
    )
    assert _string(derivation.get("co_substituted"), "derivation.co_substituted") == (
        "positive_fixtures_of_allowed_symbols_absent_from_anchor"
    )
    assert _string(derivation.get("relation"), "derivation.relation") == (
        "subset_of_measured_suppression"
    )
    assert _string(predicate.get("quantifier"), f"{predicate['id']}.quantifier") == "every"
    assert isinstance(reference_repository_root, Path)
    suppression = _measured_allowlist_suppression(
        substituted_field=substituted_field,
        substituted_from=derivation["substituted_from"],
        reference_repository_root=reference_repository_root,
        source_root=source_root,
        current_census=data_sets["current_census"],
    )[0] | _measured_condition4_suppression(
        substituted_fields=_string_array(
            derivation.get("condition4_substituted_fields"),
            "derivation.condition4_substituted_fields",
        ),
        substituted_from=_string(
            derivation.get("condition4_substituted_from"),
            "derivation.condition4_substituted_from",
        ),
        code=_string(derivation.get("condition4_code"), "derivation.condition4_code"),
        reference_repository_root=reference_repository_root,
        source_root=source_root,
        current_census=data_sets["current_census"],
        current_contract=current_contract,
    )
    code_index = identity_indexes["code"]
    for identity in data_sets[set_name]:
        code = identity[code_index]
        if code in excluded_codes:
            continue
        assert identity in suppression, identity


def _assert_removed_matches_declared_relaxations(
    predicate: dict[str, Any],
    *,
    data_sets: dict[str, frozenset[CensusIdentity]],
    identity_indexes: dict[str, int],
    **_: Any,
) -> None:
    """宣言対象の減分がすべて宣言済み緩和で説明できることを検証する。"""
    _exact_keys(
        predicate,
        {"id", "set", "code", "quantifier", "requirement"},
        predicate["id"],
    )
    assert predicate.get("quantifier") == "every"
    assert predicate.get("requirement") == "matches_declared_relaxation"
    set_name = _string(predicate.get("set"), f"{predicate['id']}.set")
    assert set_name in data_sets, f"未知の census 集合: {set_name}"
    code = _string(predicate.get("code"), f"{predicate['id']}.code")
    selected = frozenset(
        identity
        for identity in data_sets[set_name]
        if identity[identity_indexes["code"]] == code
    )
    _assert_removed_tb007_matches_declared_relaxations(
        selected,
        expected_code=code,
    )


def _matches_equal_or_delimited_prefix(
    left: str,
    right: str,
    *,
    delimiter: str,
) -> bool:
    """完全一致か、宣言された区切り境界での双方向接頭辞だけを許す。"""
    return (
        left == right
        or left.startswith(f"{right}{delimiter}")
        or right.startswith(f"{left}{delimiter}")
    )


def _assert_unadjudicated_removed_remains(
    predicate: dict[str, Any],
    *,
    data_sets: dict[str, frozenset[CensusIdentity]],
    identity_indexes: dict[str, int],
    **_: Any,
) -> None:
    """裁定外の指定減分が現行 census の指定 code として残ることを検証する。"""
    _exact_keys(
        predicate,
        {
            "id",
            "set",
            "code",
            "adjudications",
            "adjudication_symbol_field",
            "identity_symbol_field",
            "adjudication_match",
            "current_set",
            "match_fields",
            "symbol_match",
            "required_current_code",
        },
        predicate["id"],
    )
    set_name = _string(predicate.get("set"), f"{predicate['id']}.set")
    assert set_name in data_sets, f"未知の census 集合: {set_name}"
    code = _string(predicate.get("code"), f"{predicate['id']}.code")
    required_current_code = _string(
        predicate.get("required_current_code"),
        f"{predicate['id']}.required_current_code",
    )
    match_fields = _string_array(
        predicate.get("match_fields"),
        f"{predicate['id']}.match_fields",
    )
    assert set(match_fields) <= set(identity_indexes)
    symbol_match = _object(
        predicate.get("symbol_match"),
        f"{predicate['id']}.symbol_match",
    )
    _exact_keys(
        symbol_match,
        {"field", "relation"},
        f"{predicate['id']}.symbol_match",
    )
    symbol_match_field = _string(
        symbol_match.get("field"),
        f"{predicate['id']}.symbol_match.field",
    )
    assert symbol_match_field in identity_indexes
    symbol_match_relation = _object(
        symbol_match.get("relation"),
        f"{predicate['id']}.symbol_match.relation",
    )
    _exact_keys(
        symbol_match_relation,
        {"kind", "delimiter"},
        f"{predicate['id']}.symbol_match.relation",
    )
    symbol_match_kind = _string(
        symbol_match_relation.get("kind"),
        f"{predicate['id']}.symbol_match.relation.kind",
    )
    assert symbol_match_kind == "equal_or_bidirectional_delimited_prefix"
    symbol_match_delimiter = _string(
        symbol_match_relation.get("delimiter"),
        f"{predicate['id']}.symbol_match.relation.delimiter",
    )
    adjudication_symbol_field = _string(
        predicate.get("adjudication_symbol_field"),
        f"{predicate['id']}.adjudication_symbol_field",
    )
    identity_symbol_field = _string(
        predicate.get("identity_symbol_field"),
        f"{predicate['id']}.identity_symbol_field",
    )
    assert identity_symbol_field in identity_indexes
    assert predicate.get("adjudication_match") == "full_symbol_or_terminal_name"
    current_set = _string(
        predicate.get("current_set"),
        f"{predicate['id']}.current_set",
    )
    assert current_set in data_sets, f"未知の census 集合: {current_set}"
    adjudication_values = _array(
        _load_json_pointer(
            _string(
                predicate.get("adjudications"),
                f"{predicate['id']}.adjudications",
            )
        ),
        f"{predicate['id']}.adjudications",
    )
    adjudicated_symbols = {
        _string(
            _object(value, f"{predicate['id']}.adjudication").get(
                adjudication_symbol_field
            ),
            f"{predicate['id']}.adjudication.{adjudication_symbol_field}",
        )
        for value in adjudication_values
    }
    adjudicated_names = {
        symbol.rsplit(".", 1)[-1] for symbol in adjudicated_symbols
    }
    symbol_index = identity_indexes[identity_symbol_field]
    code_index = identity_indexes["code"]
    current_census = data_sets[current_set]
    for identity in data_sets[set_name]:
        if identity[code_index] != code or identity[symbol_index] in (
            adjudicated_symbols | adjudicated_names
        ):
            continue
        assert any(
            all(
                current[identity_indexes[field]]
                == (
                    required_current_code
                    if field == "code"
                    else identity[identity_indexes[field]]
                )
                for field in match_fields
            )
            and _matches_equal_or_delimited_prefix(
                str(current[identity_indexes[symbol_match_field]]),
                str(identity[identity_indexes[symbol_match_field]]),
                delimiter=symbol_match_delimiter,
            )
            for current in current_census
        ), identity


def _assert_added_equals_independently_derived_candidates(
    predicate: dict[str, Any],
    *,
    declaration: dict[str, Any],
    data_sets: dict[str, frozenset[CensusIdentity]],
    source_root: Path,
    current_contract: Any,
    anchor_contract: Any,
    **_: Any,
) -> None:
    """added を候補 checker 非依存の AST 導出 exact-set と比較する。"""
    _exact_keys(
        predicate,
        {
            "id",
            "set",
            "relation",
            "candidate_source",
            "filters",
            "forbidden_derivation_source",
            "candidate_enumeration",
        },
        predicate["id"],
    )
    assert predicate.get("relation") == "exact_set_equality"
    set_name = _string(predicate.get("set"), f"{predicate['id']}.set")
    assert set_name in data_sets, f"未知の census 集合: {set_name}"
    expected = _independently_derived_added(
        declaration=declaration,
        predicate=predicate,
        source_root=source_root,
        current_contract=current_contract,
        anchor_contract=anchor_contract,
    )
    actual = data_sets[set_name]
    assert actual == expected, (
        f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
    )


def _assert_difference_sets_are_nonempty(
    predicate: dict[str, Any],
    *,
    data_sets: dict[str, frozenset[CensusIdentity]],
    **_: Any,
) -> None:
    """宣言された各差分集合が空でないことを検証する。"""
    _exact_keys(predicate, {"id", "nonempty_sets"}, predicate["id"])
    set_names = _string_array(
        predicate.get("nonempty_sets"),
        f"{predicate['id']}.nonempty_sets",
    )
    for set_name in set_names:
        assert set_name in data_sets, f"未知の census 集合: {set_name}"
        assert data_sets[set_name], f"空の census 集合: {set_name}"


_PREDICATE_HANDLERS = {
    "difference_codes_within_allowed_set": (
        _assert_difference_codes_within_allowed_set
    ),
    "removed_outside_allowed_codes_equals_measured_allowlist_suppression": (
        _assert_removed_equals_measured_allowlist_suppression
    ),
    "removed_tb007_matches_declared_relaxations": (
        _assert_removed_matches_declared_relaxations
    ),
    "unadjudicated_removed_tb002_remains_in_current_census": (
        _assert_unadjudicated_removed_remains
    ),
    "added_equals_independently_derived_condition_2_candidates": (
        _assert_added_equals_independently_derived_candidates
    ),
    "difference_sets_are_nonempty": _assert_difference_sets_are_nonempty,
}


def _assert_declared_predicate(
    predicate: dict[str, Any],
    *,
    declaration: dict[str, Any],
    data_sets: dict[str, frozenset[CensusIdentity]],
    source_root: Path,
    current_contract: Any,
    anchor_contract: Any,
    reference_repository_root: Any = None,
) -> None:
    """単一の宣言述語を対応する汎用検証処理へ渡す。"""
    predicate_id = _string(predicate.get("id"), "pass_fail_mapping.predicate.id")
    assert predicate_id in _PREDICATE_HANDLERS, f"未知の述語: {predicate_id}"
    identity_fields = _identity_fields(declaration)
    identity_indexes = {
        field: index for index, field in enumerate(identity_fields)
    }
    try:
        _PREDICATE_HANDLERS[predicate_id](
            predicate,
            declaration=declaration,
            data_sets=data_sets,
            identity_indexes=identity_indexes,
            source_root=source_root,
            current_contract=current_contract,
            anchor_contract=anchor_contract,
            reference_repository_root=reference_repository_root,
        )
    except AssertionError as error:
        raise AssertionError(f"{predicate_id}: {error}") from error


def _assert_declared_pass_fail_mapping(
    *,
    declaration: dict[str, Any],
    added: frozenset[CensusIdentity],
    removed: frozenset[CensusIdentity],
    current_census: frozenset[CensusIdentity],
    source_root: Path,
    current_contract: Any,
    anchor_contract: Any,
    reference_repository_root: Path | None = None,
) -> None:
    """宣言に列挙された全述語を census 差分へ順番に適用する。"""
    data_sets = _predicate_data_sets(
        added=added,
        removed=removed,
        current_census=current_census,
    )
    for predicate in _declared_predicates(declaration):
        _assert_declared_predicate(
            predicate,
            declaration=declaration,
            data_sets=data_sets,
            source_root=source_root,
            current_contract=current_contract,
            anchor_contract=anchor_contract,
            reference_repository_root=reference_repository_root,
        )


def _run_declared_census_check_core(
    reference_root: Path, *, source_root: Path | None = None
) -> None:
    """宣言アンカーとの census 差分へ、宣言された全述語を適用する。"""
    (
        baseline_checker,
        reference_repository_root,
        _,
        _,
        _,
    ) = _declared_anchor_checker(
        reference_root,
    )

    source_root = source_root or REPOSITORY_ROOT / "backend" / "src"
    added, removed = _compare_checker_census(
        baseline_checker,
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=source_root,
        reference_repository_root=reference_repository_root,
    )

    declaration = _load_census_baseline_declaration()
    current_census = _checker_census(
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=source_root,
    )
    _assert_declared_pass_fail_mapping(
        declaration=declaration,
        added=added,
        removed=removed,
        current_census=current_census,
        source_root=source_root,
        current_contract=checker.load_contract(REPOSITORY_ROOT),
        anchor_contract=baseline_checker.load_contract(reference_repository_root),
        reference_repository_root=reference_repository_root,
    )


def _run_declared_census_check(
    reference_root: Path, *, source_root: Path | None = None
) -> None:
    """宣言と実装の対応を監査しながら census 検査を実行する。"""
    with _audit_declaration_implementation() as audit:
        _run_declared_census_check_core(reference_root, source_root=source_root)
        _assert_declaration_implementation_wiring(audit)


def test_checker_census_matches_declared_anchor(tmp_path: Path) -> None:
    """現行検査器と宣言アンカーを比べ、現行全文の差分を TB002・TB007 に拘束する。

    現行の検査器が、宣言されたアンカー時点の検査器と比べて、現行
    ``backend/src`` 全文に対する違反センサスの差分を対象コード内に収める。
    """
    _run_declared_census_check(tmp_path / "declared_anchor_repository")


def main() -> int:
    """pytest の収集を経由せず census 検査を直接実行する。"""
    with tempfile.TemporaryDirectory(prefix="census-baseline-") as directory:
        _run_declared_census_check(Path(directory) / "declared_anchor_repository")
    print("census-baseline: OK")
    return 0


@pytest.fixture(scope="module")
def census_predicate_context(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Any]:
    """述語変異テストが共有する実測 census と両版契約を構築する。"""
    reference_root = tmp_path_factory.mktemp("declared_anchor_predicates")
    baseline_checker, reference_repository_root, *_ = _declared_anchor_checker(
        reference_root / "repository"
    )
    source_root = REPOSITORY_ROOT / "backend" / "src"
    added, removed = _compare_checker_census(
        baseline_checker,
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=source_root,
        reference_repository_root=reference_repository_root,
    )
    current_census = _checker_census(
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=source_root,
    )
    declaration = _load_census_baseline_declaration()
    return {
        "baseline_checker": baseline_checker,
        "reference_repository_root": reference_repository_root,
        "source_root": source_root,
        "declaration": declaration,
        "data_sets": _predicate_data_sets(
            added=added,
            removed=removed,
            current_census=current_census,
        ),
        "current_contract": checker.load_contract(REPOSITORY_ROOT),
        "anchor_contract": baseline_checker.load_contract(
            reference_repository_root
        ),
    }


def _condition2_candidate_predicate(
    declaration: dict[str, Any],
) -> dict[str, Any]:
    """独立条件2候補を宣言する述語を一意に取得する。"""
    matching = [
        predicate
        for predicate in _declared_predicates(declaration)
        if predicate.get("candidate_source") == "current_backend_src_ast"
    ]
    assert len(matching) == 1
    return matching[0]


def _condition2_identities_for_source(
    checker_module: ModuleType,
    *,
    source: str,
    contract: Any,
) -> frozenset[CensusIdentity]:
    """最小ソースに対する checker の TB002 identity 集合を返す。"""
    return frozenset(
        (
            violation.path,
            violation.line,
            violation.end_line,
            violation.scope,
            violation.code,
            violation.symbol,
            violation.message,
        )
        for violation in checker_module.scan_source(
            source,
            path="condition_2_ast_case.py",
            contract=contract,
        )
        if violation.code == "TB002"
    )


def _independent_condition2_identities_for_source(
    *,
    source: str,
    declaration: dict[str, Any],
    current_contract: Any,
    anchor_contract: Any,
) -> frozenset[CensusIdentity]:
    """最小ソースから独立右辺の条件2 identity 集合を導出する。"""
    path = "condition_2_ast_case.py"
    tree = ast.parse(source, filename=path)
    predicate = _condition2_candidate_predicate(declaration)
    enumeration = _object(
        predicate.get("candidate_enumeration"),
        "pass_fail_mapping.predicate.candidate_enumeration",
    )
    current_resolver = _IndependentSymbolResolver(
        module=_module_name(path),
        module_is_package=False,
        symbol_aliases=current_contract.symbol_aliases,
    )
    current_resolver.visit(tree)
    anchor_resolver = _IndependentSymbolResolver(
        module=_module_name(path),
        module_is_package=False,
        symbol_aliases=anchor_contract.symbol_aliases,
    )
    anchor_resolver.visit(tree)
    candidates = _IndependentCondition2Candidates(
        path=path,
        tree=tree,
        current_resolver=current_resolver,
        anchor_resolver=anchor_resolver,
        current_contract=current_contract,
        anchor_contract=anchor_contract,
        enumeration=enumeration,
        identity_fields=_identity_fields(declaration),
    )
    return frozenset(candidates.identities)


def test_declared_condition2_ast_node_types_match_minimal_cases() -> None:
    """宣言した AST 型集合を8種の最小ケース集合と完全一致させる。"""
    declaration = _load_census_baseline_declaration()
    predicate = _condition2_candidate_predicate(declaration)
    enumeration = _object(
        predicate.get("candidate_enumeration"),
        "pass_fail_mapping.predicate.candidate_enumeration",
    )

    assert frozenset(
        _string_array(
            enumeration.get("ast_node_type"),
            "candidate_enumeration.ast_node_type",
        )
    ) == frozenset(_CONDITION_2_AST_CASES)


def test_declared_unadjudicated_tb002_match_uses_symbol_prefix_relation() -> None:
    """述語3を同一サイトと宣言済みの識別子境界付き接頭辞関係へ閉じる。"""
    declaration = _load_census_baseline_declaration()
    matching = [
        predicate
        for predicate in _declared_predicates(declaration)
        if predicate.get("id")
        == "unadjudicated_removed_tb002_remains_in_current_census"
    ]

    assert len(matching) == 1
    assert matching[0].get("match_fields") == [
        "path",
        "line",
        "code",
    ]
    assert matching[0].get("symbol_match") == {
        "field": "symbol",
        "relation": {
            "kind": "equal_or_bidirectional_delimited_prefix",
            "delimiter": ".",
        },
    }


def _suppression_predicate(declaration: dict[str, Any]) -> dict[str, Any]:
    """反実仮想の実測抑止集合を使う述語を一意に取得する。"""
    matching = [
        predicate
        for predicate in _declared_predicates(declaration)
        if predicate.get("id")
        == "removed_outside_allowed_codes_equals_measured_allowlist_suppression"
    ]
    assert len(matching) == 1
    return matching[0]


def _suppression_arguments(
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, frozenset[CensusIdentity]]]:
    """実測 census と materialized anchor を述語に渡す。"""
    declaration = cast(dict[str, Any], context["declaration"])
    arguments = {
        "declaration": declaration,
        "source_root": context["source_root"],
        "current_contract": context["current_contract"],
        "anchor_contract": context["anchor_contract"],
        "reference_repository_root": context["reference_repository_root"],
    }
    data_sets = cast(dict[str, frozenset[CensusIdentity]], context["data_sets"])
    return _suppression_predicate(declaration), arguments, data_sets


def _run_with_extra_removed(
    identity: CensusIdentity,
    *,
    monkeypatch: pytest.MonkeyPatch,
    reference_root: Path,
) -> None:
    """removed に 1 件加え、本番の宣言検査入口まで通す。"""
    original_compare = _compare_checker_census

    def with_extra_removed(
        *args: Any, **kwargs: Any
    ) -> tuple[frozenset[CensusIdentity], frozenset[CensusIdentity]]:
        added, removed = original_compare(*args, **kwargs)
        return added, removed | {identity}

    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__], "_compare_checker_census", with_extra_removed
        )
        with pytest.raises(
            AssertionError, match="removed_outside_allowed_codes_equals_measured"
        ):
            _run_declared_census_check(reference_root)


def _copy_current_contract_tree(destination: Path) -> None:
    """一時の現在ツリーへ、契約読取りに必要な資産と fixture を複写する。"""
    for relative in (
        Path("contracts/tenant_boundary"),
        Path("tests/fixtures/tenant_boundary"),
        Path("backend/src"),
    ):
        shutil.copytree(REPOSITORY_ROOT / relative, destination / relative)


def _set_temporary_allowed_symbols(
    destination: Path,
    *,
    rows: list[dict[str, Any]],
    removed_fixtures: set[str],
) -> None:
    """一時ツリーの許可集合だけを差し替え、対応する正例だけを除く。"""
    asset_path = destination / checker.DEFAULT_ALLOWLIST
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    asset["allowed_symbols"] = rows
    asset_path.write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for fixture in removed_fixtures:
        (destination / fixture).unlink()


def test_measured_suppression_predicate_accepts_actual_a2_census(
    census_predicate_context: dict[str, Any],
) -> None:
    """A2 の実差分と宣言形を確認する。"""
    predicate, arguments, data_sets = _suppression_arguments(
        census_predicate_context
    )
    assert predicate["applies_to_codes_outside"] == ["TB002", "TB007"]
    assert predicate["derivation"] == {
        "kind": "counterfactual_allowlist_substitution",
        "checker": "current",
        "substituted_field": "contracts/tenant_boundary/base-allowlist.json#/allowed_symbols",
        "substituted_from": "anchor_symbol_set_plus_scoped_signature_rows",
        "co_substituted": "positive_fixtures_of_allowed_symbols_absent_from_anchor",
        "relation": "subset_of_measured_suppression",
        "condition4_substituted_fields": [
            "contracts/tenant_boundary/cache-invalidation-contract.json#/api/public_symbols",
            "contracts/tenant_boundary/cache-invalidation-contract.json#/api/condition4_allowed_call_symbols",
        ],
        "condition4_substituted_from": "anchor_symbol_set",
        "condition4_code": "TB004",
    }
    _assert_declared_predicate(predicate, data_sets=data_sets, **arguments)


def test_condition4_suppression_is_measured_only_for_declared_call_symbol(
    census_predicate_context: dict[str, Any],
) -> None:
    """契約の新しい許可呼び出しが抑止する TB004 の 4 箇所を測る。"""
    predicate, arguments, data_sets = _suppression_arguments(census_predicate_context)
    derivation = predicate["derivation"]
    suppression = _measured_condition4_suppression(
        substituted_fields=tuple(derivation["condition4_substituted_fields"]),
        substituted_from=derivation["condition4_substituted_from"],
        code=derivation["condition4_code"],
        reference_repository_root=arguments["reference_repository_root"],
        source_root=arguments["source_root"],
        current_census=data_sets["current_census"],
        current_contract=arguments["current_contract"],
    )
    symbol = "pitchlog.repositories.cache_invalidation.SharedAggregateTargetSelector"
    assert suppression <= data_sets["removed"]
    anchor_calls = frozenset(
        _string_array(
            _load_json_pointer(
                derivation["condition4_substituted_fields"][1],
                repository_root=arguments["reference_repository_root"],
            ),
            "anchor.condition4_allowed_call_symbols",
        )
    )
    current_calls = arguments["current_contract"].cache_invalidation.allowed_call_symbols
    if symbol not in current_calls - anchor_calls:
        assert all(identity[5] != symbol for identity in suppression)
        return
    assert {(identity[0], identity[3], identity[4], identity[5]) for identity in suppression} == {
        (
            "pitchlog/api/routers/players.py",
            "pitchlog.api.routers.players.<module>",
            "TB004",
            symbol,
        ),
        (
            "pitchlog/api/routers/players.py",
            "pitchlog.api.routers.players._apply_player_status_in_transaction",
            "TB004",
            symbol,
        ),
        (
            "pitchlog/repositories/invalidation_intents.py",
            "pitchlog.repositories.invalidation_intents.<module>",
            "TB004",
            symbol,
        ),
        (
            "pitchlog/repositories/invalidation_intents.py",
            "pitchlog.repositories.invalidation_intents.record_invalidation_intent",
            "TB004",
            symbol,
        ),
    }


@pytest.mark.parametrize("public_only", (False, True), ids=("no_addition", "public_only"))
def test_condition4_suppression_accepts_empty_measured_difference(
    public_only: bool,
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """許可呼び出しの追加が無ければ抑止 0 件を受理する。"""
    predicate, arguments, _ = _suppression_arguments(census_predicate_context)
    derivation = predicate["derivation"]
    public_field, calls_field = derivation["condition4_substituted_fields"]
    reference_root = arguments["reference_repository_root"]
    anchor_public = frozenset(
        _string_array(
            _load_json_pointer(public_field, repository_root=reference_root),
            "anchor.public_symbols",
        )
    )
    anchor_calls = frozenset(
        _string_array(
            _load_json_pointer(calls_field, repository_root=reference_root),
            "anchor.condition4_allowed_call_symbols",
        )
    )
    current_public = anchor_public
    if public_only:
        current_public |= {
            "pitchlog.repositories.cache_invalidation.SharedAggregateTargetSelector"
        }
    boundary = replace(
        arguments["current_contract"].cache_invalidation,
        public_symbols=current_public,
        allowed_call_symbols=anchor_calls,
    )
    contract = replace(arguments["current_contract"], cache_invalidation=boundary)
    original_loader = _load_json_pointer

    def substituted_rows(
        locator: str, *, repository_root: Path | None = None
    ) -> object:
        if repository_root is None and locator == public_field:
            return sorted(current_public)
        if repository_root is None and locator == calls_field:
            return sorted(anchor_calls)
        return original_loader(locator, repository_root=repository_root)

    source_root = tmp_path / "backend/src/pitchlog"
    source_root.mkdir(parents=True)
    (source_root / "safe.py").write_text("def safe():\n    pass\n", encoding="utf-8")
    with monkeypatch.context() as mutation:
        mutation.setattr(sys.modules[__name__], "_load_json_pointer", substituted_rows)
        suppression = _measured_condition4_suppression(
            substituted_fields=(public_field, calls_field),
            substituted_from=derivation["condition4_substituted_from"],
            code=derivation["condition4_code"],
            reference_repository_root=reference_root,
            source_root=source_root.parent,
            current_census=frozenset(),
            current_contract=contract,
        )
    assert suppression == frozenset()


def test_condition4_suppression_rejects_unrelated_removed_tb004(
    census_predicate_context: dict[str, Any],
) -> None:
    """別シンボルの TB004 減分は許可呼び出しの緩和に帰属しない。"""
    predicate, arguments, data_sets = _suppression_arguments(census_predicate_context)
    unrelated: CensusIdentity = (
        "pitchlog/api/routers/players.py",
        1,
        1,
        "pitchlog.api.routers.players.<module>",
        "TB004",
        "pitchlog.repositories.cache_invalidation.UnrelatedSelector",
        "条件 4 の禁止シンボルを検出",
    )
    with pytest.raises(
        AssertionError, match="removed_outside_allowed_codes_equals_measured"
    ):
        _assert_declared_predicate(
            predicate,
            data_sets={**data_sets, "removed": data_sets["removed"] | {unrelated}},
            **arguments,
        )


@pytest.mark.parametrize("field", ("missing", "signature", "allowed_api_ids"))
def test_measured_suppression_shared_allowed_entry_follows_declared_substitution(
    field: str,
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """共通行の署名だけを個別に帰属し、記号削除や API 差は拒否する。

    署名変更を正当に含むため、従来の「行変更は常に拒否」を改める。
    実変更のある行を避けて合成変異を作り、その行自体の処理を検証する。
    署名ケースの全走査による帰属までは検査しない。実差分は A2 検証で扱い、
    帰属の 3 条件は合成 identity の変異テストで固定する。
    """
    predicate, arguments, data_sets = _suppression_arguments(census_predicate_context)
    locator = predicate["derivation"]["substituted_field"]
    anchor_rows = cast(
        list[dict[str, Any]],
        _load_json_pointer(locator, repository_root=arguments["reference_repository_root"]),
    )
    current_rows = cast(list[dict[str, Any]], _load_json_pointer(locator))
    current_by_symbol = {row["symbol"]: row for row in current_rows}
    shared = next(
        row
        for row in anchor_rows
        if len(row["allowed_api_ids"]) > 1
        and current_by_symbol[row["symbol"]] == row
    )
    rows = copy.deepcopy(current_rows)
    changed = next(row for row in rows if row["symbol"] == shared["symbol"])
    if field == "missing":
        rows.remove(changed)
    elif field == "signature":
        changed[field] += "_changed"
    else:
        changed[field] = changed[field][:-1]

    if field in ("missing", "allowed_api_ids"):
        expected = (
            "anchor の許可記号を現行から削除できない"
            if field == "missing"
            else re.escape(f"{shared['symbol']}: allowed_api_ids")
        )
        with pytest.raises(AssertionError, match=expected):
            _counterfactual_allowed_symbol_rows(
                current_entries=rows,
                anchor_entries=anchor_rows,
                substituted_from=predicate["derivation"]["substituted_from"],
            )
        original_loader = _load_json_pointer

        def changed_current_rows(
            path: str, *, repository_root: Path | None = None
        ) -> object:
            if path == locator and repository_root is None:
                return rows
            return original_loader(path, repository_root=repository_root)

        with monkeypatch.context() as mutation:
            mutation.setattr(
                sys.modules[__name__], "_load_json_pointer", changed_current_rows
            )
            with pytest.raises(AssertionError, match=expected):
                _measured_allowlist_suppression(
                    substituted_field=locator,
                    substituted_from=predicate["derivation"]["substituted_from"],
                    reference_repository_root=arguments["reference_repository_root"],
                    source_root=arguments["source_root"],
                    current_census=data_sets["current_census"],
                )
        return

    assert changed != shared
    retained, added, changed_signatures = _counterfactual_allowed_symbol_rows(
        current_entries=rows,
        anchor_entries=anchor_rows,
        substituted_from=predicate["derivation"]["substituted_from"],
    )
    assert next(row for row in retained if row["symbol"] == shared["symbol"]) == changed
    assert changed_signatures[shared["symbol"]] == shared
    assert {row["symbol"] for row in added} == (
        {row["symbol"] for row in current_rows}
        - {row["symbol"] for row in anchor_rows}
    )


@pytest.mark.parametrize(
    ("changed_index", "changed_value"),
    (
        (0, "pitchlog/repositories/other.py"),
        (4, "TB007"),
        (5, "pitchlog.repositories.context.Other.__init__"),
    ),
)
def test_scoped_signature_suppression_rejects_each_mismatched_identity(
    changed_index: int, changed_value: str
) -> None:
    """製品パス・TB005・許可記号の各条件を外す変異を拒否する。"""
    product_path = "pitchlog/repositories/context.py"
    symbol = "pitchlog.repositories.context.TenantContext.__init__"
    matching: CensusIdentity = (
        product_path,
        46,
        58,
        "pitchlog.repositories.context.TenantContext.<module>",
        "TB005",
        symbol,
        "signature mismatch",
    )
    mismatched = _replace_identity_field(
        matching, index=changed_index, value=changed_value
    )
    assert mismatched != matching
    assert _scoped_signature_suppression(
        frozenset({matching, mismatched}),
        product_path=product_path,
        symbol=symbol,
    ) == frozenset({matching})


@pytest.mark.parametrize(
    ("paths", "expected"),
    (
        (("pitchlog/foo.py",), "pitchlog/foo.py"),
        (("pitchlog/foo/__init__.py",), "pitchlog/foo/__init__.py"),
        (("pitchlog/foo.py", "pitchlog/foo/__init__.py"), None),
    ),
)
def test_allowed_symbol_product_path_requires_unique_module(
    paths: tuple[str, ...], expected: str | None, tmp_path: Path
) -> None:
    """単一の .py・__init__.py は解決し、同名モジュールの重複は拒否する。"""
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    symbol = "pitchlog.foo.issue"
    if expected is None:
        with pytest.raises(AssertionError, match="製品モジュールが曖昧"):
            _allowed_symbol_product_path(symbol, tmp_path)
    else:
        assert _allowed_symbol_product_path(symbol, tmp_path) == expected


def test_measured_suppression_rejects_unrelated_api_inside_allowed_function(
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """一時ソースへ非許可 API を足し、現行 inventory だけから除いて実消失を作る。

    anchor と現行の比較、反実仮想の再計測は同じ一時ソースを走査する。
    比較結果には手を加えず、現行 checker の API 入力だけを変える。
    """
    predicate, arguments, _ = _suppression_arguments(census_predicate_context)
    source_root = tmp_path / "source" / "backend" / "src"
    shutil.copytree(REPOSITORY_ROOT / "backend" / "src", source_root)
    target = source_root / "pitchlog" / "authz" / "product_provisioning.py"
    source = target.read_text(encoding="utf-8")
    marker = '    """閉じた操作を正規資産から生成し、1 トランザクションで実行する。"""\n'
    assert source.count(marker) == 1
    target.write_text(
        source.replace(marker, marker + '    connection.pgconn.exec_(b"SELECT 1")\n'),
        encoding="utf-8",
    )
    original_load_contract = checker.load_contract

    def without_unrelated_api(repository_root: Path) -> Any:
        contract = original_load_contract(repository_root)
        return replace(
            contract,
            apis=tuple(
                api for api in contract.apis if api.id != "PSYCOPG_PGCONN_EXEC"
            ),
        )

    with monkeypatch.context() as mutation:
        mutation.setattr(checker, "load_contract", without_unrelated_api)
        baseline_checker, anchor_root, *_ = _declared_anchor_checker(
            tmp_path / "unrelated_api_preview_anchor"
        )
        _, removed = _compare_checker_census(
            baseline_checker,
            checker,
            repository_root=REPOSITORY_ROOT,
            source_root=source_root,
            reference_repository_root=anchor_root,
        )
        actual = next(
            identity
            for identity in removed
            if identity[0] == "pitchlog/authz/product_provisioning.py"
            and identity[3] == "pitchlog.authz.product_provisioning._run_product_operation"
            and identity[4] == "TB005"
            and identity[5] == "psycopg.pq.PGconn.exec_"
        )
        current_census = _checker_census(
            checker, repository_root=REPOSITORY_ROOT, source_root=source_root
        )
        assert actual not in current_census
        suppression, _, _ = _measured_allowlist_suppression(
            substituted_field=predicate["derivation"]["substituted_field"],
            substituted_from=predicate["derivation"]["substituted_from"],
            reference_repository_root=arguments["reference_repository_root"],
            source_root=source_root,
            current_census=current_census,
        )
        assert actual not in suppression
        with pytest.raises(AssertionError, match=re.escape(predicate["id"])):
            _run_declared_census_check(
                tmp_path / "unrelated_api_anchor", source_root=source_root
            )


def test_measured_suppression_rejects_unrelated_scope(
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """新規記号と無関係な scope の TB005 は入口から拒否する。"""
    _, arguments, data_sets = _suppression_arguments(census_predicate_context)
    indexes = {
        field: index
        for index, field in enumerate(_identity_fields(arguments["declaration"]))
    }
    original = next(
        identity
        for identity in data_sets["removed"]
        if identity[indexes["code"]] == "TB005"
    )
    unrelated = _replace_identity_field(
        original, index=indexes["scope"], value="mutation.unrelated_scope"
    )
    _run_with_extra_removed(
        unrelated,
        monkeypatch=monkeypatch,
        reference_root=tmp_path / "unrelated_scope_anchor",
    )


@pytest.mark.parametrize(
    ("node_type", "source"),
    tuple(_CONDITION_2_AST_CASES.items()),
    ids=tuple(_CONDITION_2_AST_CASES),
)
def test_independent_condition2_candidates_match_checker_for_each_ast_type(
    node_type: str,
    source: str,
    census_predicate_context: dict[str, Any],
) -> None:
    """8種ごとに独立右辺と checker の TB002 増分を exact-set 比較する。"""
    current_contract = census_predicate_context["current_contract"]
    anchor_contract = census_predicate_context["anchor_contract"]
    aliases = {
        "idempotency_key": "safe.value",
        "holder.idempotency_key": "safe.value",
    }
    current_contract = replace(
        current_contract,
        symbol_aliases={**current_contract.symbol_aliases, **aliases},
    )
    anchor_contract = replace(
        anchor_contract,
        symbol_aliases={**anchor_contract.symbol_aliases, **aliases},
    )
    baseline_checker = census_predicate_context["baseline_checker"]
    checker_added = _condition2_identities_for_source(
        checker,
        source=source,
        contract=current_contract,
    ) - _condition2_identities_for_source(
        baseline_checker,
        source=source,
        contract=anchor_contract,
    )
    independently_derived = _independent_condition2_identities_for_source(
        source=source,
        declaration=census_predicate_context["declaration"],
        current_contract=current_contract,
        anchor_contract=anchor_contract,
    )

    assert node_type in _CONDITION_2_AST_CASES
    assert independently_derived
    assert independently_derived == checker_added


def _replace_identity_field(
    identity: CensusIdentity,
    *,
    index: int,
    value: str,
) -> CensusIdentity:
    """変異テスト用に CensusIdentity の単一フィールドを差し替える。"""
    fields: list[str | int] = list(identity)
    fields[index] = value
    return cast(CensusIdentity, tuple(fields))


def _mutate_predicate_input(
    predicate: dict[str, Any],
    *,
    data_sets: dict[str, frozenset[CensusIdentity]],
    declaration: dict[str, Any],
) -> dict[str, frozenset[CensusIdentity]]:
    """述語の宣言形から、その述語だけを赤にする入力変異を作る。"""
    mutated = dict(data_sets)
    indexes = {
        field: index
        for index, field in enumerate(_identity_fields(declaration))
    }
    if predicate.get("derivation") is not None:
        set_name = _string(predicate["set"], "mutation.set")
        excluded_codes = frozenset(
            _string_array(
                predicate["applies_to_codes_outside"], "mutation.excluded_codes"
            )
        )
        original = next(
            identity
            for identity in mutated[set_name]
            if identity[indexes["code"]] not in excluded_codes
        )
        replacement = _replace_identity_field(
            original,
            index=indexes["symbol"],
            value="mutation.unrelated_symbol",
        )
        mutated[set_name] = (mutated[set_name] - {original}) | {replacement}
        return mutated
    if "allowed_codes" in predicate:
        set_name = _string_array(predicate["sets"], "mutation.sets")[0]
        original = next(iter(mutated[set_name]))
        replacement = _replace_identity_field(
            original,
            index=indexes["code"],
            value="MUTATED_CODE",
        )
        mutated[set_name] = (mutated[set_name] - {original}) | {replacement}
        return mutated
    if predicate.get("requirement") == "matches_declared_relaxation":
        set_name = _string(predicate["set"], "mutation.set")
        code = _string(predicate["code"], "mutation.code")
        original = next(
            identity
            for identity in mutated[set_name]
            if identity[indexes["code"]] == code
        )
        replacement = _replace_identity_field(
            original,
            index=indexes["symbol"],
            value="mutation.unresolvable",
        )
        mutated[set_name] = (mutated[set_name] - {original}) | {replacement}
        return mutated
    if "match_fields" in predicate:
        set_name = _string(predicate["set"], "mutation.set")
        code = _string(predicate["code"], "mutation.code")
        adjudications = _array(
            _load_json_pointer(
                _string(predicate["adjudications"], "mutation.adjudications")
            ),
            "mutation.adjudications",
        )
        adjudication_symbol_field = _string(
            predicate["adjudication_symbol_field"],
            "adjudication_symbol_field",
        )
        identity_symbol_field = _string(
            predicate["identity_symbol_field"],
            "identity_symbol_field",
        )
        adjudicated_symbols = {
            _string(
                _object(value, "mutation.adjudication")[
                    adjudication_symbol_field
                ],
                adjudication_symbol_field,
            )
            for value in adjudications
        }
        adjudicated_names = {
            symbol.rsplit(".", 1)[-1] for symbol in adjudicated_symbols
        }
        original = next(
            identity
            for identity in mutated[set_name]
            if identity[indexes["code"]] == code
            and identity[indexes[identity_symbol_field]]
            not in adjudicated_symbols | adjudicated_names
        )
        match_fields = _string_array(predicate["match_fields"], "match_fields")
        symbol_match = _object(predicate["symbol_match"], "symbol_match")
        symbol_field = _string(symbol_match["field"], "symbol_match.field")
        symbol_relation = _object(
            symbol_match["relation"],
            "symbol_match.relation",
        )
        _exact_keys(
            symbol_relation,
            {"kind", "delimiter"},
            "symbol_match.relation",
        )
        assert (
            _string(symbol_relation["kind"], "symbol_match.relation.kind")
            == "equal_or_bidirectional_delimited_prefix"
        )
        symbol_delimiter = _string(
            symbol_relation["delimiter"],
            "symbol_match.relation.delimiter",
        )
        required_code = _string(
            predicate["required_current_code"],
            "required_current_code",
        )
        current_set = _string(predicate["current_set"], "current_set")
        matching_current = frozenset(
            current
            for current in mutated[current_set]
            if all(
                current[indexes[field]]
                == (
                    required_code
                    if field == "code"
                    else original[indexes[field]]
                )
                for field in match_fields
            )
            and _matches_equal_or_delimited_prefix(
                str(current[indexes[symbol_field]]),
                str(original[indexes[symbol_field]]),
                delimiter=symbol_delimiter,
            )
        )
        assert matching_current
        unrelated = _replace_identity_field(
            next(iter(matching_current)),
            index=indexes[symbol_field],
            value="mutation.unrelated_symbol",
        )
        mutated[current_set] = (
            mutated[current_set] - matching_current
        ) | {unrelated}
        return mutated
    if predicate.get("relation") == "exact_set_equality":
        set_name = _string(predicate["set"], "mutation.set")
        mutated[set_name] = mutated[set_name] - {next(iter(mutated[set_name]))}
        return mutated
    set_name = _string_array(predicate["nonempty_sets"], "nonempty_sets")[0]
    mutated[set_name] = frozenset()
    return mutated


def test_measured_suppression_rejects_removed_current_allowed_entry(
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """anchor にない許可記号を現行から除いても残る TB005 を拒否する。"""
    predicate, arguments, data_sets = _suppression_arguments(
        census_predicate_context
    )
    indexes = {
        field: index
        for index, field in enumerate(_identity_fields(arguments["declaration"]))
    }
    locator = predicate["derivation"]["substituted_field"]
    rows = cast(
        list[dict[str, Any]],
        _load_json_pointer(locator),
    )
    anchor_rows = cast(
        list[dict[str, Any]],
        _load_json_pointer(
            locator, repository_root=arguments["reference_repository_root"]
        ),
    )
    anchor_symbols = {row["symbol"] for row in anchor_rows}
    added_symbols = {row["symbol"] for row in rows} - anchor_symbols
    original = next(
        identity
        for identity in data_sets["removed"]
        if identity[indexes["code"]] == "TB005"
        and identity[indexes["scope"]] in added_symbols
    )
    removed_entry = next(
        row for row in rows if row["symbol"] == original[indexes["scope"]]
    )
    current_root = tmp_path / "current_without_entry"
    _copy_current_contract_tree(current_root)
    _set_temporary_allowed_symbols(
        current_root,
        rows=[row for row in rows if row is not removed_entry],
        removed_fixtures={removed_entry["fixture"]},
    )
    current_census = _checker_census(
        checker,
        repository_root=current_root,
        source_root=arguments["source_root"],
    )
    assert original in current_census
    changed_sets = {**data_sets, "current_census": current_census}
    with monkeypatch.context() as mutation:
        mutation.setattr(sys.modules[__name__], "REPOSITORY_ROOT", current_root)
        with pytest.raises(AssertionError, match=re.escape(predicate["id"])):
            _assert_declared_predicate(predicate, data_sets=changed_sets, **arguments)


def test_measured_suppression_accepts_develop_without_growth(
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """増分のない develop 相当では旧述語も含む宣言全体を通す。"""
    predicate, arguments, data_sets = _suppression_arguments(
        census_predicate_context
    )
    indexes = {
        field: index
        for index, field in enumerate(_identity_fields(arguments["declaration"]))
    }
    field = predicate["derivation"]["substituted_field"]
    rows = cast(list[dict[str, Any]], _load_json_pointer(field))
    anchor_rows = cast(
        list[dict[str, Any]],
        _load_json_pointer(
            field, repository_root=arguments["reference_repository_root"]
        ),
    )
    anchor_symbols = {row["symbol"] for row in anchor_rows}
    current_root = tmp_path / "develop_without_growth"
    _copy_current_contract_tree(current_root)
    _set_temporary_allowed_symbols(
        current_root,
        rows=anchor_rows,
        removed_fixtures={
            row["fixture"] for row in rows if row["symbol"] not in anchor_symbols
        },
    )
    current_census = _checker_census(
        checker,
        repository_root=current_root,
        source_root=arguments["source_root"],
    )
    removed = frozenset(
        identity
        for identity in data_sets["removed"]
        if identity[indexes["code"]] in predicate["applies_to_codes_outside"]
    )
    with monkeypatch.context() as mutation:
        mutation.setattr(sys.modules[__name__], "REPOSITORY_ROOT", current_root)
        _assert_declared_pass_fail_mapping(
            declaration=arguments["declaration"],
            added=data_sets["added"],
            removed=removed,
            current_census=current_census,
            source_root=arguments["source_root"],
            current_contract=checker.load_contract(current_root),
            anchor_contract=arguments["anchor_contract"],
            reference_repository_root=arguments["reference_repository_root"],
        )


def test_measured_suppression_rejects_removed_fixture_path(
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """除いた fixture のパスを S_allow に注入すると入口から拒否する。"""
    predicate, arguments, data_sets = _suppression_arguments(
        census_predicate_context
    )
    field = predicate["derivation"]["substituted_field"]
    rows = cast(list[dict[str, Any]], _load_json_pointer(field))
    anchor_rows = cast(
        list[dict[str, Any]],
        _load_json_pointer(
            field, repository_root=arguments["reference_repository_root"]
        ),
    )
    anchor_symbols = {row["symbol"] for row in anchor_rows}
    fixture = next(
        row["fixture"] for row in rows if row["symbol"] not in anchor_symbols
    )
    mapped_path = Path(
        os.path.relpath(REPOSITORY_ROOT / fixture, arguments["source_root"])
    ).as_posix()
    original = next(
        identity for identity in data_sets["removed"] if identity[4] == "TB005"
    )
    injected = _replace_identity_field(original, index=0, value=mapped_path)
    original_census = _checker_census

    def with_fixture_violation(
        checker_module: ModuleType, *, repository_root: Path, source_root: Path
    ) -> frozenset[CensusIdentity]:
        measured = original_census(
            checker_module, repository_root=repository_root, source_root=source_root
        )
        if checker_module is checker and repository_root != REPOSITORY_ROOT:
            return measured | {injected}
        return measured

    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__], "_checker_census", with_fixture_violation
        )
        with pytest.raises(AssertionError, match="除いた fixture"):
            _run_declared_census_check(tmp_path / "fixture_path_anchor")


def test_measured_suppression_rejects_missing_fixture_field(
    census_predicate_context: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """新規許可記号の fixture 欄欠落は入口で fail-closed に停止する。"""
    predicate, arguments, _ = _suppression_arguments(census_predicate_context)
    field = predicate["derivation"]["substituted_field"]
    rows = cast(list[dict[str, Any]], _load_json_pointer(field))
    anchor_rows = cast(
        list[dict[str, Any]],
        _load_json_pointer(
            field, repository_root=arguments["reference_repository_root"]
        ),
    )
    anchor_symbols = {row["symbol"] for row in anchor_rows}
    new_symbol = next(
        row["symbol"] for row in rows if row["symbol"] not in anchor_symbols
    )
    original_loader = _load_json_pointer

    def without_fixture(
        locator: str, *, repository_root: Path | None = None
    ) -> object:
        loaded = original_loader(locator, repository_root=repository_root)
        if locator == field and repository_root is None:
            changed = cast(list[dict[str, Any]], copy.deepcopy(loaded))
            next(row for row in changed if row["symbol"] == new_symbol).pop(
                "fixture"
            )
            return changed
        return loaded

    with monkeypatch.context() as mutation:
        mutation.setattr(sys.modules[__name__], "_load_json_pointer", without_fixture)
        with pytest.raises(AssertionError, match="fixture"):
            _run_declared_census_check(tmp_path / "missing_fixture_anchor")


@pytest.mark.parametrize(
    "predicate_id",
    tuple(
        _string(predicate.get("id"), "predicate.id")
        for predicate in _declared_predicates(_load_census_baseline_declaration())
    ),
)
def test_each_declared_census_predicate_rejects_its_input_mutation(
    predicate_id: str,
    census_predicate_context: dict[str, Any],
) -> None:
    """各宣言述語が個別変異を拒否し、原入力へ戻すと再び通ることを示す。"""
    declaration = cast(
        dict[str, Any],
        census_predicate_context["declaration"],
    )
    predicate = next(
        item
        for item in _declared_predicates(declaration)
        if item["id"] == predicate_id
    )
    data_sets = cast(
        dict[str, frozenset[CensusIdentity]],
        census_predicate_context["data_sets"],
    )
    arguments = {
        "declaration": declaration,
        "source_root": census_predicate_context["source_root"],
        "current_contract": census_predicate_context["current_contract"],
        "anchor_contract": census_predicate_context["anchor_contract"],
        "reference_repository_root": census_predicate_context[
            "reference_repository_root"
        ],
    }
    _assert_declared_predicate(predicate, data_sets=data_sets, **arguments)
    mutated = _mutate_predicate_input(
        predicate,
        data_sets=data_sets,
        declaration=declaration,
    )
    with pytest.raises(AssertionError, match=re.escape(predicate_id)):
        _assert_declared_predicate(predicate, data_sets=mutated, **arguments)
    _assert_declared_predicate(predicate, data_sets=data_sets, **arguments)


def _unadjudicated_removed_tb002_predicate(
    declaration: dict[str, Any],
) -> dict[str, Any]:
    """非裁定 removed TB002 の残存を検査する述語を一意に取得する。"""
    matching = [
        predicate
        for predicate in _declared_predicates(declaration)
        if predicate.get("id")
        == "unadjudicated_removed_tb002_remains_in_current_census"
    ]
    assert len(matching) == 1
    return matching[0]


def test_removed_tb002_accepts_prefix_related_current_symbol(
    census_predicate_context: dict[str, Any],
) -> None:
    """非裁定 removed TB002 は接頭辞関係の現行 symbol で説明できる。"""
    declaration = cast(
        dict[str, Any],
        census_predicate_context["declaration"],
    )
    predicate = _unadjudicated_removed_tb002_predicate(declaration)
    data_sets = cast(
        dict[str, frozenset[CensusIdentity]],
        census_predicate_context["data_sets"],
    )

    _assert_declared_predicate(
        predicate,
        declaration=declaration,
        data_sets=data_sets,
        source_root=census_predicate_context["source_root"],
        current_contract=census_predicate_context["current_contract"],
        anchor_contract=census_predicate_context["anchor_contract"],
    )


def test_removed_tb002_rejects_unrelated_same_line_symbol(
    census_predicate_context: dict[str, Any],
) -> None:
    """同一行でも接頭辞関係のない symbol による身代わりを拒否する。"""
    declaration = cast(
        dict[str, Any],
        census_predicate_context["declaration"],
    )
    predicate = _unadjudicated_removed_tb002_predicate(declaration)
    data_sets = cast(
        dict[str, frozenset[CensusIdentity]],
        census_predicate_context["data_sets"],
    )
    mutated = _mutate_predicate_input(
        predicate,
        data_sets=data_sets,
        declaration=declaration,
    )

    with pytest.raises(AssertionError, match=re.escape(predicate["id"])):
        _assert_declared_predicate(
            predicate,
            declaration=declaration,
            data_sets=mutated,
            source_root=census_predicate_context["source_root"],
            current_contract=census_predicate_context["current_contract"],
            anchor_contract=census_predicate_context["anchor_contract"],
        )


@pytest.mark.parametrize(
    ("current_symbol", "accepted"),
    (
        pytest.param(
            "pitchlog.models.RecordingGeneration.__table__.c.tenant_id",
            True,
            id="attribute-chain",
        ),
        pytest.param(
            "pitchlog.models.RecordingGenerationShadow",
            False,
            id="identifier-shadow",
        ),
        pytest.param(
            "pitchlog.models.Other",
            False,
            id="unrelated-symbol",
        ),
    ),
)
def test_removed_tb002_symbol_relation_honors_identifier_boundary(
    current_symbol: str,
    accepted: bool,
    census_predicate_context: dict[str, Any],
) -> None:
    """属性チェーンの粒度差だけを許し、別識別子の身代わりを拒否する。"""
    declaration = cast(
        dict[str, Any],
        census_predicate_context["declaration"],
    )
    predicate = _unadjudicated_removed_tb002_predicate(declaration)
    removed: CensusIdentity = (
        "review_boundary.py",
        1,
        1,
        "<module>",
        "TB002",
        "pitchlog.models.RecordingGeneration",
        "条件 2 の禁止シンボルを検出",
    )
    current: CensusIdentity = (
        "review_boundary.py",
        1,
        1,
        "<module>",
        "TB002",
        current_symbol,
        "条件 2 の禁止シンボルを検出",
    )
    data_sets = {
        "added": frozenset[CensusIdentity](),
        "removed": frozenset({removed}),
        "current_census": frozenset({current}),
    }
    arguments = {
        "declaration": declaration,
        "data_sets": data_sets,
        "source_root": census_predicate_context["source_root"],
        "current_contract": census_predicate_context["current_contract"],
        "anchor_contract": census_predicate_context["anchor_contract"],
    }

    if accepted:
        _assert_declared_predicate(predicate, **arguments)
    else:
        with pytest.raises(AssertionError, match=re.escape(predicate["id"])):
            _assert_declared_predicate(predicate, **arguments)


def test_independent_added_predicate_rejects_candidate_checker_omission(
    monkeypatch: pytest.MonkeyPatch,
    census_predicate_context: dict[str, Any],
) -> None:
    """candidate checker 自体が1サイトを欠落すると独立 AST 述語が拒否する。"""
    declaration = cast(
        dict[str, Any],
        census_predicate_context["declaration"],
    )
    predicate = next(
        item
        for item in _declared_predicates(declaration)
        if "candidate_enumeration" in item
    )
    original_data_sets = cast(
        dict[str, frozenset[CensusIdentity]],
        census_predicate_context["data_sets"],
    )
    target = next(iter(original_data_sets["added"]))
    original_scan_directory = checker.scan_directory

    def scan_directory_missing_site(
        source_root: Path,
        *,
        contract: Any,
        reject_all_db_calls: bool = False,
    ) -> list[Any]:
        """candidate checker の走査出力から対象サイトそのものを欠落させる。"""
        violations = original_scan_directory(
            source_root,
            contract=contract,
            reject_all_db_calls=reject_all_db_calls,
        )
        result = []
        dropped = False
        for violation in violations:
            identity = cast(
                CensusIdentity,
                (
                    violation.path,
                    violation.line,
                    violation.end_line,
                    violation.scope,
                    violation.code,
                    violation.symbol,
                    violation.message,
                ),
            )
            if identity == target and not dropped:
                dropped = True
                continue
            result.append(violation)
        assert dropped
        return result

    monkeypatch.setattr(checker, "scan_directory", scan_directory_missing_site)
    baseline_checker = cast(
        ModuleType,
        census_predicate_context["baseline_checker"],
    )
    source_root = cast(Path, census_predicate_context["source_root"])
    mutated_added, mutated_removed = _compare_checker_census(
        baseline_checker,
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=source_root,
        reference_repository_root=cast(
            Path,
            census_predicate_context["reference_repository_root"],
        ),
    )
    assert target not in mutated_added
    mutated_data_sets = _predicate_data_sets(
        added=mutated_added,
        removed=mutated_removed,
        current_census=_checker_census(
            checker,
            repository_root=REPOSITORY_ROOT,
            source_root=source_root,
        ),
    )
    arguments = {
        "declaration": declaration,
        "source_root": source_root,
        "current_contract": census_predicate_context["current_contract"],
        "anchor_contract": census_predicate_context["anchor_contract"],
    }
    with pytest.raises(AssertionError, match=re.escape(cast(str, predicate["id"]))):
        _assert_declared_predicate(
            predicate,
            data_sets=mutated_data_sets,
            **arguments,
        )

    monkeypatch.undo()
    _assert_declared_predicate(
        predicate,
        data_sets=original_data_sets,
        **arguments,
    )


def _mutate_fail_closed_declaration(
    declaration: dict[str, Any],
    failure_mode: str,
) -> dict[str, Any]:
    """fail-closed 条件ごとの宣言変異を作る。"""
    mutated = copy.deepcopy(declaration)
    if failure_mode == "missing-required-field":
        del mutated["anchor"]
        return mutated
    if failure_mode == "unresolved-anchor":
        anchor = _object(mutated["anchor"], "mutation.anchor")
        commit = _string(anchor["commit"], "mutation.anchor.commit")
        replacement = "0" if commit[-1] != "0" else "1"
        anchor["commit"] = f"{commit[:-1]}{replacement}"
        return mutated
    if failure_mode == "tree-digest-mismatch":
        tree = _object(mutated["materialized_tree"], "mutation.tree")
        digest = _string(tree["digest"], "mutation.tree.digest")
        replacement = "0" if digest[-1] != "0" else "1"
        tree["digest"] = f"{digest[:-1]}{replacement}"
        return mutated
    if failure_mode == "file-count-mismatch":
        tree = _object(mutated["materialized_tree"], "mutation.tree")
        file_count = _integer(tree["file_count"], "mutation.tree.file_count")
        tree["file_count"] = file_count + 1
        return mutated
    if failure_mode == "acceptance-record-not-found":
        cross_check = _object(
            mutated["acceptance_cross_check"],
            "mutation.acceptance_cross_check",
        )
        cross_check["acceptance_id"] = "missing-acceptance-record"
        return mutated
    raise AssertionError(f"未知の fail-closed 変異: {failure_mode}")


def test_fail_closed_rejects_unreadable_declaration_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """① 宣言の不在・JSON 不正を拒否し、正本へ戻すと通ることを示す。"""
    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__],
            "CENSUS_BASELINE_PATH",
            tmp_path / "missing-census-baseline.json",
        )
        with pytest.raises(FileNotFoundError):
            _load_census_baseline_declaration()

    malformed = tmp_path / "malformed-census-baseline.json"
    malformed.write_text("{", encoding="utf-8")
    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__],
            "CENSUS_BASELINE_PATH",
            malformed,
        )
        with pytest.raises(json.JSONDecodeError):
            _load_census_baseline_declaration()

    _declared_anchor_checker(tmp_path / "restored-readable-declaration")


@pytest.mark.parametrize(
    "failure_mode",
    (
        "missing-required-field",
        "unresolved-anchor",
        "tree-digest-mismatch",
        "file-count-mismatch",
        "acceptance-record-not-found",
    ),
)
def test_fail_closed_rejects_declaration_mutation_and_recovers(
    failure_mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """②〜⑥ の宣言変異を拒否し、正本へ戻すと通ることを示す。"""
    declaration = _load_census_baseline_declaration()
    mutated = _mutate_fail_closed_declaration(declaration, failure_mode)
    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__],
            "_load_census_baseline_declaration",
            lambda: copy.deepcopy(mutated),
        )
        with pytest.raises((AssertionError, subprocess.CalledProcessError)):
            _declared_anchor_checker(tmp_path / f"red-{failure_mode}")

    _declared_anchor_checker(tmp_path / f"restored-{failure_mode}")


def test_fail_closed_rejects_nonunique_acceptance_record_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⑥ 同じ acceptance_id の受理記録が複数ある場合も拒否する。"""
    declaration = _load_census_baseline_declaration()
    mutated = copy.deepcopy(declaration)
    cross_check = _object(
        mutated["acceptance_cross_check"],
        "mutation.acceptance_cross_check",
    )
    history_path = REPOSITORY_ROOT / _string(
        cross_check["history_asset"],
        "mutation.history_asset",
    )
    history_asset = _object(
        json.loads(history_path.read_text(encoding="utf-8")),
        "mutation.history_asset",
    )
    control = _object(history_asset["baseline_control"], "mutation.control")
    history = cast(list[object], control["history"])
    acceptance_id = _string(
        cross_check["acceptance_id"],
        "mutation.acceptance_id",
    )
    matching = [
        record
        for record in history
        if isinstance(record, dict) and record.get("acceptance_id") == acceptance_id
    ]
    assert len(matching) == 1
    history.append(copy.deepcopy(matching[0]))
    duplicated_history_path = tmp_path / "duplicated-history.json"
    duplicated_history_path.write_text(
        json.dumps(history_asset, ensure_ascii=False),
        encoding="utf-8",
    )
    cross_check["history_asset"] = duplicated_history_path.as_posix()

    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__],
            "_load_census_baseline_declaration",
            lambda: copy.deepcopy(mutated),
        )
        with pytest.raises(AssertionError):
            _declared_anchor_checker(tmp_path / "red-nonunique-acceptance")

    _declared_anchor_checker(tmp_path / "restored-unique-acceptance")


def test_fail_closed_rejects_acceptance_digest_mismatch_and_recovers(
    tmp_path: Path,
) -> None:
    """⑦ 受理記録との digest 不一致を拒否し、元内容へ戻すと通ることを示す。"""
    declaration, contents, _ = _materialize_declared_anchor(
        tmp_path / "acceptance-digest-reference"
    )
    _cross_check_accepted_external_snapshots(declaration, contents)
    cross_check = _object(
        declaration["acceptance_cross_check"],
        "census.acceptance_cross_check",
    )
    checker_path = _string(cross_check["checker_path"], "checker_path")
    mutated_contents = dict(contents)
    mutated_contents[checker_path] = contents[checker_path] + b"\n"
    with pytest.raises(AssertionError):
        _cross_check_accepted_external_snapshots(
            declaration,
            mutated_contents,
        )
    _cross_check_accepted_external_snapshots(declaration, contents)


def test_fail_closed_rejects_module_cache_contamination_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⑧ 現行 helper の module-cache 混入を拒否し、隔離へ戻すと通る。"""
    reference_root = tmp_path / "module-cache-reference"
    declaration, _, _ = _materialize_declared_anchor(reference_root)
    _load_isolated_anchor_checker(reference_root, declaration)
    current_helper = sys.modules.get("frozen_history")
    assert current_helper is not None
    original_module_from_spec = importlib.util.module_from_spec

    def contaminated_module_from_spec(spec: Any) -> ModuleType:
        """旧 checker 実行直前に現行 helper を module cache へ混入する。"""
        sys.modules["frozen_history"] = current_helper
        return original_module_from_spec(spec)

    with monkeypatch.context() as mutation:
        mutation.setattr(
            importlib.util,
            "module_from_spec",
            contaminated_module_from_spec,
        )
        with pytest.raises(AssertionError):
            _load_isolated_anchor_checker(reference_root, declaration)

    _load_isolated_anchor_checker(reference_root, declaration)


@pytest.mark.parametrize(
    "regression",
    (
        "origin-develop-loader",
        "merge-base-loader",
        "current-worktree-checker",
    ),
)
def test_reference_checker_regressions_are_rejected(
    regression: str,
    tmp_path: Path,
) -> None:
    """可変参照または現行 worktree を比較 checker に戻す退行を拒否する。"""
    reference_root = tmp_path / "declared-reference"
    declaration, _, _ = _materialize_declared_anchor(reference_root)
    if regression == "origin-develop-loader":
        regressed_checker = _load_checker_from_revision(
            "origin/develop",
            tmp_path / "origin-develop-checker.py",
        )
    elif regression == "merge-base-loader":
        merge_base = subprocess.run(
            ["git", "merge-base", "origin/develop", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        regressed_checker = _load_checker_from_revision(
            merge_base,
            tmp_path / "merge-base-checker.py",
        )
    else:
        regressed_checker = checker

    with pytest.raises(AssertionError, match="materialize"):
        _assert_loaded_checker_from_materialized_anchor(
            regressed_checker,
            reference_root=reference_root,
            declaration=declaration,
        )

    restored_checker, _ = _load_isolated_anchor_checker(
        reference_root,
        declaration,
    )
    _assert_loaded_checker_from_materialized_anchor(
        restored_checker,
        reference_root=reference_root,
        declaration=declaration,
    )


def test_reference_regression_rejects_git_bytes_cached_before_monitoring(
    tmp_path: Path,
) -> None:
    """監視開始前に捕捉した git bytes を後から使う比較元退行を拒否する。"""
    source_root = tmp_path / "declared-source"
    declaration, contents, _ = _materialize_declared_anchor(source_root)
    anchor = _object(declaration["anchor"], "census.anchor")
    anchor_commit = _string(anchor["commit"], "census.anchor.commit")
    relative_paths = tuple(sorted(contents))

    collection_monitor = object()
    collection_cached_blobs = {
        path: _ObservedGitBlob(collection_monitor, anchor_commit, content)
        for path, content in contents.items()
    }

    def materialize_from_collection_cache(
        destination: Path,
    ) -> dict[str, _ObservedGitBlob]:
        """pytest collection 相当の閉包へ捕捉した bytes だけを書き出す退行。"""
        written: dict[str, _ObservedGitBlob] = {}
        for path, cached_blob in collection_cached_blobs.items():
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(cached_blob.content)
            written[path] = cached_blob
        return written

    active_monitor = object()
    observed_after_monitoring = {
        path: _ObservedGitBlob(active_monitor, anchor_commit, content)
        for path, content in contents.items()
    }
    cached_destination = tmp_path / "collection-cached-reference"
    cached_writes = materialize_from_collection_cache(cached_destination)
    with pytest.raises(AssertionError, match="書込み"):
        _assert_declared_anchor_materialization_provenance(
            declaration=declaration,
            destination=cached_destination,
            listed_revision=anchor_commit,
            relative_paths=relative_paths,
            monitor=active_monitor,
            observed_blobs=observed_after_monitoring,
            written_blobs=cached_writes,
        )

    restored_destination = tmp_path / "monitor-bound-reference"
    restored_writes: dict[str, _ObservedGitBlob] = {}
    for path, observed_blob in observed_after_monitoring.items():
        target = restored_destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(observed_blob.content)
        restored_writes[path] = observed_blob
    _assert_declared_anchor_materialization_provenance(
        declaration=declaration,
        destination=restored_destination,
        listed_revision=anchor_commit,
        relative_paths=relative_paths,
        monitor=active_monitor,
        observed_blobs=observed_after_monitoring,
        written_blobs=restored_writes,
    )


def test_declaration_to_implementation_rejects_unused_field_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """宣言へ全数表登録済みの未使用フィールドを足すと拒否する。"""
    declaration = _load_census_baseline_declaration()
    mutated = copy.deepcopy(declaration)
    anchor = _object(mutated["anchor"], "mutation.anchor")
    anchor["unused_wiring_field"] = "unused"
    inventory = cast(list[object], mutated["implementation_field_inventory"])
    inventory.append("anchor.unused_wiring_field")
    mutated_path = tmp_path / "unused-field-census-baseline.json"
    mutated_path.write_text(
        json.dumps(mutated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__],
            "CENSUS_BASELINE_PATH",
            mutated_path,
        )
        with pytest.raises(AssertionError, match="read 集合"):
            _run_declared_census_check(tmp_path / "red-unused-field")

    _run_declared_census_check(tmp_path / "restored-used-fields")


def test_implementation_to_declaration_rejects_undeclared_input_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """比較元構築が宣言外の値を使う変異を拒否する。"""
    original_materialize = _materialize_declared_anchor

    def materialize_with_undeclared_input(
        destination: Path,
    ) -> tuple[dict[str, Any], dict[str, bytes], str]:
        """正規の materialize に宣言外入力を混ぜる変異。"""
        result = original_materialize(destination)
        _record_undeclared_implementation_input("hardcoded-reference-input")
        return result

    with monkeypatch.context() as mutation:
        mutation.setattr(
            sys.modules[__name__],
            "_materialize_declared_anchor",
            materialize_with_undeclared_input,
        )
        with pytest.raises(AssertionError, match="宣言外の値"):
            _run_declared_census_check(tmp_path / "red-undeclared-input")

    _run_declared_census_check(tmp_path / "restored-declared-inputs")


if __name__ == "__main__":
    raise SystemExit(main())
