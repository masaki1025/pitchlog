"""テナント境界迂回検査のセンサス差分を検証する。"""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from test_check_tenant_boundary_bypass import (
    REPOSITORY_ROOT,
    checker,
)

CENSUS_BASELINE_PATH = (
    REPOSITORY_ROOT / "contracts" / "tenant_boundary" / "census-baseline.json"
)
CensusIdentity = tuple[str, int, int, str, str, str, str]


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
    return _object(value, CENSUS_BASELINE_PATH.as_posix())


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
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        contents[relative_path] = content
        content_digest = hashlib.sha256(content).hexdigest()
        digest_rows.append(
            relative_path.encode("utf-8")
            + b"\0"
            + content_digest.encode("ascii")
            + b"\n"
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

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """Name サイトを現行・アンカー両契約の候補規則へ照合する。"""
        current_resolved_symbol = self.current_resolver.resolve(node) or node.id
        anchor_resolved_symbol = self.anchor_resolver.resolve(node) or node.id
        current_candidate = self._projection(
            self.current_projection,
            identifier=node.id,
            resolved_symbol=current_resolved_symbol,
        )
        anchor_candidate = self._projection(
            self.anchor_projection,
            identifier=node.id,
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
            node.id,
            current_resolved_symbol,
            f"{self.module}.{node.id}",
        }
        if adjudication_candidates & self.adjudicated_symbols:
            return
        symbol = self._projection(
            self.identity_symbol_projection,
            identifier=node.id,
            resolved_symbol=current_resolved_symbol,
        )
        key = (node.lineno, self.condition, self.current_rule.error, symbol)
        if key in self.violation_keys:
            return
        self.violation_keys.add(key)
        values: dict[str, str | int] = {
            "path": self.path,
            "line": node.lineno,
            "end_line": node.end_lineno or node.lineno,
            "scope": self._scope(),
            "code": self.current_rule.error,
            "symbol": symbol,
            "message": self.message,
        }
        self.identities.add(
            cast(
                CensusIdentity,
                tuple(values[field] for field in self.identity_fields),
            )
        )

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
    assert enumeration.get("ast_node_type") == "Name"
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
    """減分が (iii) の宣言範囲への緩和だけで説明できると示す。"""
    source_root = REPOSITORY_ROOT / "backend" / "src"
    sources = {
        path.relative_to(source_root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.py"))
    }
    reexport_map = checker._build_reexport_map(sources)
    contract = checker.load_contract(REPOSITORY_ROOT)
    scanners: dict[str, tuple[ast.Module, Any]] = {}

    for identity in removed:
        path, line, end_line, _, code, symbol, _ = identity
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
                continue
            resolved = scanner.aliases.resolve(
                node.func
            ) or scanner._raw_expression(node.func)
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


def _load_json_pointer(locator: str) -> object:
    """リポジトリ相対 JSON path と RFC 6901 pointer の宣言値を読む。"""
    relative_path, separator, pointer = locator.partition("#")
    assert separator and pointer.startswith("/"), f"JSON pointer が不正: {locator}"
    value: object = json.loads(
        (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    )
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
        )


def test_checker_census_matches_declared_anchor(tmp_path: Path) -> None:
    """現行検査器と宣言アンカーを比べ、現行全文の差分を TB002・TB007 に拘束する。

    現行の検査器が、宣言されたアンカー時点の検査器と比べて、現行
    ``backend/src`` 全文に対する違反センサスの差分を対象コード内に収める。
    """
    (
        baseline_checker,
        reference_repository_root,
        _,
        _,
        _,
    ) = _declared_anchor_checker(
        tmp_path / "declared_anchor_repository",
    )

    added, removed = _compare_checker_census(
        baseline_checker,
        checker,
        repository_root=REPOSITORY_ROOT,
        source_root=REPOSITORY_ROOT / "backend" / "src",
        reference_repository_root=reference_repository_root,
    )

    declaration = _load_census_baseline_declaration()
    source_root = REPOSITORY_ROOT / "backend" / "src"
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
    )


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
        required_code = _string(
            predicate["required_current_code"],
            "required_current_code",
        )
        current_set = _string(predicate["current_set"], "current_set")
        mutated[current_set] = frozenset(
            current
            for current in mutated[current_set]
            if not all(
                current[indexes[field]]
                == (
                    required_code
                    if field == "code"
                    else original[indexes[field]]
                )
                for field in match_fields
            )
        )
        return mutated
    if predicate.get("relation") == "exact_set_equality":
        set_name = _string(predicate["set"], "mutation.set")
        mutated[set_name] = mutated[set_name] - {next(iter(mutated[set_name]))}
        return mutated
    set_name = _string_array(predicate["nonempty_sets"], "nonempty_sets")[0]
    mutated[set_name] = frozenset()
    return mutated


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
