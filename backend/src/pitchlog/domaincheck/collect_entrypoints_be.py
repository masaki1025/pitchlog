"""Backend の実在入口と import graph を独立収集する。"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn, Sequence

from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    CheckerExecutionError,
    canonical_json,
)


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを送出する。"""
        raise CheckerExecutionError(message)


@dataclass(frozen=True, slots=True)
class _Binding:
    """ローカル名が参照するモジュールと属性を表す。"""

    module: str
    attribute: str | None = None


@dataclass(frozen=True, slots=True)
class _Module:
    """解析済み Python モジュールを保持する。"""

    name: str
    path: Path
    tree: ast.Module
    imports: tuple[ast.Import | ast.ImportFrom, ...]
    calls: tuple[ast.Call, ...]
    bindings: dict[str, _Binding]


@dataclass(frozen=True, slots=True)
class _DynamicUse:
    """動的解決構文の解析結果を保持する。"""

    module: str
    path: Path
    construct: str
    expression: str
    target: str | None
    reason: str | None
    imported_module: str | None = None


@dataclass(slots=True)
class _CollectionState:
    """1 回の backend 収集で蓄積する状態。"""

    root: Path
    source_root: Path
    pyproject: Path
    modules: dict[str, _Module] = field(default_factory=dict)
    edges: dict[str, set[tuple[str, str]]] = field(default_factory=dict)
    dynamic_uses: list[_DynamicUse] = field(default_factory=list)
    metadata_issues: list[dict[str, object]] = field(default_factory=list)
    entries: list[dict[str, str]] = field(default_factory=list)
    seeds: set[str] = field(default_factory=set)

    def relative(self, path: Path) -> str:
        """パスをリポジトリ相対の POSIX 表記へ変換する。"""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError as error:
            raise CheckerExecutionError(
                f"収集対象がリポジトリ外を指している: {path}"
            ) from error

    def add_metadata_issue(self, construct: str, expression: str, reason: str) -> None:
        """プロジェクトメタデータの解析不能を記録する。"""
        self.metadata_issues.append(
            {
                "module": "project-metadata",
                "path": self.relative(self.pyproject),
                "construct": construct,
                "expression": _compact(expression),
                "reason": reason,
                "reachable": True,
            }
        )


class _RuntimeVisitor(ast.NodeVisitor):
    """型検査専用分岐を除く import と call を収集する。"""

    def __init__(self) -> None:
        """空の収集結果を初期化する。"""
        self.imports: list[ast.Import | ast.ImportFrom] = []
        self.calls: list[ast.Call] = []

    def visit_If(self, node: ast.If) -> None:
        """`TYPE_CHECKING` 本体を本番 import graph から除外する。"""
        if _is_type_checking(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """通常 import を記録する。"""
        self.imports.append(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """From import を記録する。"""
        self.imports.append(node)

    def visit_Call(self, node: ast.Call) -> None:
        """動的解決候補となる call を記録する。"""
        self.calls.append(node)
        self.generic_visit(node)


def _is_type_checking(node: ast.expr) -> bool:
    """型検査専用条件なら `True` を返す。"""
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    return isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"


def _compact(value: str) -> str:
    """機械可読な表示用に空白と長さを正規化する。"""
    return " ".join(value.split())[:160]


def _read_text(path: Path) -> str:
    """UTF-8 の監査対象を読み込む。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CheckerExecutionError(f"監査対象を読めない: {path}: {error}") from error


def _module_name(source_root: Path, path: Path) -> str:
    """Python ファイルの配置からモジュール名を導出する。"""
    relative = path.relative_to(source_root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not parts:
        raise CheckerExecutionError(f"モジュール名を導出できない: {path}")
    return ".".join(parts)


def _absolute_from(module: _Module, node: ast.ImportFrom) -> str:
    """相対 From import を絶対モジュール名へ変換する。"""
    if node.level == 0:
        return node.module or ""
    package = (
        module.name
        if module.path.name == "__init__.py"
        else module.name.rpartition(".")[0]
    )
    parts = package.split(".") if package else []
    parents = node.level - 1
    if parents > len(parts):
        return ""
    prefix = parts[: len(parts) - parents]
    if node.module:
        prefix.extend(node.module.split("."))
    return ".".join(prefix)


def _binding_for_import(alias: ast.alias) -> tuple[str, _Binding]:
    """通常 import のローカル束縛を返す。"""
    if alias.asname:
        return alias.asname, _Binding(alias.name)
    root_name = alias.name.split(".", maxsplit=1)[0]
    return root_name, _Binding(root_name)


def _binding_for_from(
    base: str, alias: ast.alias, module_names: set[str]
) -> tuple[str, _Binding]:
    """From import のローカル束縛を返す。"""
    local_name = alias.asname or alias.name
    candidate = f"{base}.{alias.name}" if base else alias.name
    if candidate in module_names or (
        base == "importlib" and alias.name in {"metadata", "resources"}
    ):
        return local_name, _Binding(candidate)
    return local_name, _Binding(base, alias.name)


def _build_bindings(module: _Module, module_names: set[str]) -> dict[str, _Binding]:
    """モジュール内の import 束縛を構築する。"""
    bindings: dict[str, _Binding] = {}
    for node in module.imports:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name, binding = _binding_for_import(alias)
                bindings[name] = binding
            continue
        base = _absolute_from(module, node)
        for alias in node.names:
            if alias.name == "*":
                continue
            name, binding = _binding_for_from(base, alias, module_names)
            bindings[name] = binding
    return bindings


def _load_modules(state: _CollectionState) -> None:
    """Source root の全 Python ファイルを構文解析する。"""
    paths = sorted(path for path in state.source_root.rglob("*.py") if path.is_file())
    preliminary: dict[str, _Module] = {}
    for path in paths:
        source = _read_text(path)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as error:
            raise CheckerExecutionError(
                f"Python 構文を解析できない: {state.relative(path)}: {error.msg}"
            ) from error
        visitor = _RuntimeVisitor()
        visitor.visit(tree)
        name = _module_name(state.source_root, path)
        preliminary[name] = _Module(
            name=name,
            path=path.resolve(),
            tree=tree,
            imports=tuple(visitor.imports),
            calls=tuple(visitor.calls),
            bindings={},
        )
    module_names = set(preliminary)
    state.modules = {
        name: _Module(
            name=module.name,
            path=module.path,
            tree=module.tree,
            imports=module.imports,
            calls=module.calls,
            bindings=_build_bindings(module, module_names),
        )
        for name, module in preliminary.items()
    }


def _import_target(
    state: _CollectionState, module: _Module, node: ast.Import | ast.ImportFrom
) -> set[str]:
    """Import 文からローカル依存先を導出する。"""
    targets: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in state.modules:
                targets.add(alias.name)
        return targets
    base = _absolute_from(module, node)
    for alias in node.names:
        candidate = f"{base}.{alias.name}" if base else alias.name
        if alias.name != "*" and candidate in state.modules:
            targets.add(candidate)
        elif base in state.modules:
            targets.add(base)
    return targets


def _collect_static_edges(state: _CollectionState) -> None:
    """全モジュールの静的 import 辺を導出する。"""
    for module in state.modules.values():
        for node in module.imports:
            for target in _import_target(state, module, node):
                state.edges.setdefault(module.name, set()).add((target, "import"))


def _callable_name(node: ast.expr, bindings: dict[str, _Binding]) -> str | None:
    """Call 対象を import 束縛に基づく完全名へ解決する。"""
    if isinstance(node, ast.Name):
        binding = bindings.get(node.id)
        if binding is None:
            return None
        suffix = f".{binding.attribute}" if binding.attribute else ""
        return f"{binding.module}{suffix}"
    if isinstance(node, ast.Attribute):
        base = _callable_name(node.value, bindings)
        if base is not None:
            return f"{base}.{node.attr}"
    return None


def _static_string(node: ast.expr | None) -> str | None:
    """式が静的文字列なら値を返す。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _all_arguments_are_literal(call: ast.Call) -> bool:
    """Call の全引数がリテラルだけなら `True` を返す。"""
    nodes = [*call.args, *(keyword.value for keyword in call.keywords)]
    try:
        for node in nodes:
            ast.literal_eval(node)
    except (ValueError, TypeError):
        return False
    return True


def _imported_module_name(owner: _Module, target: str) -> str:
    """`import_module` の相対名を所有モジュール基準で解決する。"""
    if not target.startswith("."):
        return target
    package = (
        owner.name
        if owner.path.name == "__init__.py"
        else owner.name.rpartition(".")[0]
    )
    level = len(target) - len(target.lstrip("."))
    suffix = target[level:]
    parts = package.split(".") if package else []
    parents = level - 1
    if parents > len(parts):
        return target
    resolved = parts[: len(parts) - parents]
    if suffix:
        resolved.extend(suffix.split("."))
    return ".".join(resolved)


def _dynamic_use(module: _Module, call: ast.Call) -> _DynamicUse | None:
    """動的構文 1 件を解決済みまたは解析不能へ分類する。"""
    expression = _compact(ast.unparse(call))
    function = _callable_name(call.func, module.bindings)
    if function == "importlib.import_module":
        argument = call.args[0] if call.args else None
        target = _static_string(argument)
        if target is None:
            return _DynamicUse(
                module.name,
                module.path,
                function,
                expression,
                None,
                "第 1 引数が静的文字列でない",
            )
        imported = _imported_module_name(module, target)
        return _DynamicUse(
            module.name,
            module.path,
            function,
            expression,
            imported,
            None,
            imported,
        )
    if function is not None and function.startswith("importlib."):
        if _all_arguments_are_literal(call):
            return _DynamicUse(
                module.name,
                module.path,
                function,
                expression,
                expression,
                None,
            )
        return _DynamicUse(
            module.name,
            module.path,
            function,
            expression,
            None,
            "引数がリテラルだけではない",
        )
    if isinstance(call.func, ast.Name) and call.func.id == "getattr":
        attribute = _static_string(call.args[1] if len(call.args) > 1 else None)
        if attribute is not None:
            return _DynamicUse(
                module.name,
                module.path,
                "getattr",
                expression,
                attribute,
                None,
            )
        return _DynamicUse(
            module.name,
            module.path,
            "getattr",
            expression,
            None,
            "属性名が静的文字列でない",
        )
    return None


def _collect_dynamic_uses(state: _CollectionState) -> None:
    """全 Python ファイルから動的解決構文を列挙する。"""
    for module in state.modules.values():
        for call in module.calls:
            use = _dynamic_use(module, call)
            if use is None:
                continue
            state.dynamic_uses.append(use)
            if use.imported_module in state.modules:
                state.edges.setdefault(module.name, set()).add(
                    (use.imported_module, "importlib")
                )


def _parse_target(value: object) -> tuple[str, str | None] | None:
    """メタデータの `module:attribute` を分解する。"""
    if not isinstance(value, str) or not value.strip():
        return None
    target = value.split("[", maxsplit=1)[0].strip()
    module, separator, attribute = target.partition(":")
    if not module or (separator and not attribute):
        return None
    return module, attribute or None


def _add_entry(
    state: _CollectionState,
    *,
    kind: str,
    name: str,
    value: object,
    origin: str,
) -> None:
    """プロジェクトメタデータ由来の入口を登録する。"""
    parsed = _parse_target(value)
    if parsed is None:
        state.add_metadata_issue(kind, repr(value), "入口指定が静的でない")
        return
    module, attribute = parsed
    row = {
        "kind": kind,
        "name": name,
        "module": module,
        "attribute": attribute or "",
        "origin": origin,
    }
    state.entries.append(row)
    state.seeds.add(module)
    if module not in state.modules:
        state.add_metadata_issue(kind, str(value), "実在モジュールへ解決できない")


def _mapping(value: object, label: str) -> dict[str, object]:
    """TOML table を文字列キーの辞書として返す。"""
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckerExecutionError(f"{label}は table でなければならない")
    return value


def _collect_project_entries(state: _CollectionState) -> None:
    """Pyproject の本番起点と配布入口を列挙する。"""
    try:
        document = tomllib.loads(_read_text(state.pyproject))
    except tomllib.TOMLDecodeError as error:
        raise CheckerExecutionError(
            f"pyproject.toml を解析できない: {error}"
        ) from error
    project = _mapping(document.get("project"), "project")
    tool = _mapping(document.get("tool"), "tool")
    fastapi = _mapping(tool.get("fastapi"), "tool.fastapi")
    application = fastapi.get("entrypoint", "pitchlog.main:app")
    _add_entry(
        state,
        kind="application",
        name="fastapi",
        value=application,
        origin="tool.fastapi.entrypoint",
    )

    sections = (
        ("scripts", "project-script"),
        ("gui-scripts", "project-gui-script"),
    )
    for section, kind in sections:
        for name, value in _mapping(project.get(section), f"project.{section}").items():
            _add_entry(
                state,
                kind=kind,
                name=name,
                value=value,
                origin=f"project.{section}",
            )
    groups = _mapping(project.get("entry-points"), "project.entry-points")
    for group, raw_entries in groups.items():
        entries = _mapping(raw_entries, f"project.entry-points.{group}")
        for name, value in entries.items():
            _add_entry(
                state,
                kind="project-entry-point",
                name=f"{group}:{name}",
                value=value,
                origin=f"project.entry-points.{group}",
            )


def _with_packages(state: _CollectionState, module_name: str) -> set[str]:
    """対象モジュールと実在する親 package を返す。"""
    parts = module_name.split(".")
    return {
        ".".join(parts[:index])
        for index in range(1, len(parts) + 1)
        if ".".join(parts[:index]) in state.modules
    }


def _reachable_modules(state: _CollectionState) -> set[str]:
    """宣言された起点から到達可能なローカルモジュールを返す。"""
    queue: deque[str] = deque()
    for seed in state.seeds:
        queue.extend(sorted(_with_packages(state, seed)))
    reachable: set[str] = set()
    while queue:
        module_name = queue.popleft()
        if module_name in reachable or module_name not in state.modules:
            continue
        reachable.add(module_name)
        for target, _kind in sorted(state.edges.get(module_name, set())):
            queue.extend(sorted(_with_packages(state, target)))
    return reachable


def _resolve_reference(
    node: ast.expr, bindings: dict[str, _Binding]
) -> tuple[str, str | None] | None:
    """ROUTERS 要素をモジュールと属性へ解決する。"""
    if isinstance(node, ast.Name):
        binding = bindings.get(node.id)
        if binding is not None:
            return binding.module, binding.attribute
        return None
    if isinstance(node, ast.Attribute):
        resolved = _resolve_reference(node.value, bindings)
        if resolved is None:
            return None
        module, attribute = resolved
        suffix = f"{attribute}.{node.attr}" if attribute else node.attr
        return module, suffix
    return None


def _router_elements(tree: ast.Module) -> list[ast.expr]:
    """トップレベルの `ROUTERS` 配列要素を返す。"""
    for statement in tree.body:
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ROUTERS"
            for target in statement.targets
        ):
            value = statement.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "ROUTERS"
        ):
            value = statement.value
        if isinstance(value, (ast.Tuple, ast.List)):
            return list(value.elts)
    return []


def _collect_routers(
    state: _CollectionState, reachable: set[str]
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    """到達可能な静的 `ROUTERS` の各要素を解決する。"""
    routers: list[dict[str, str]] = []
    issues: list[dict[str, object]] = []
    for module_name in sorted(reachable):
        module = state.modules[module_name]
        for element in _router_elements(module.tree):
            expression = _compact(ast.unparse(element))
            resolved = _resolve_reference(element, module.bindings)
            if resolved is None:
                issues.append(
                    {
                        "module": module.name,
                        "path": state.relative(module.path),
                        "construct": "ROUTERS",
                        "expression": expression,
                        "reason": "静的なモジュール属性へ解決できない",
                        "reachable": True,
                    }
                )
                continue
            target_module, attribute = resolved
            routers.append(
                {
                    "ownerModule": module.name,
                    "reference": expression,
                    "module": target_module,
                    "attribute": attribute or "",
                }
            )
    return routers, issues


def collect_backend_entries(
    root: Path, source_root: Path, pyproject: Path
) -> dict[str, object]:
    """Backend の入口と到達可能 graph を実ファイルから独立導出する。

    Args:
        root: リポジトリルート。
        source_root: Python パッケージの source root。
        pyproject: 配布入口を宣言する pyproject.toml。

    Returns:
        入口、graph、動的解決、走査回数を持つ機械可読な収集結果。

    Raises:
        CheckerExecutionError: 収集対象を読み取れない場合。
    """
    resolved_root = root.resolve()
    resolved_source = source_root.resolve()
    resolved_pyproject = pyproject.resolve()
    if not resolved_source.is_dir():
        raise CheckerExecutionError(f"Python source root を読めない: {source_root}")
    if not resolved_pyproject.is_file():
        raise CheckerExecutionError(f"pyproject.toml を読めない: {pyproject}")
    state = _CollectionState(
        root=resolved_root,
        source_root=resolved_source,
        pyproject=resolved_pyproject,
    )
    state.relative(resolved_source)
    state.relative(resolved_pyproject)
    _load_modules(state)
    _collect_static_edges(state)
    _collect_dynamic_uses(state)
    _collect_project_entries(state)
    reachable = _reachable_modules(state)
    routers, router_issues = _collect_routers(state, reachable)

    resolved_dynamic: list[dict[str, object]] = []
    unresolved_dynamic: list[dict[str, object]] = []
    for use in state.dynamic_uses:
        row: dict[str, object] = {
            "module": use.module,
            "path": state.relative(use.path),
            "construct": use.construct,
            "expression": use.expression,
            "reachable": use.module in reachable,
        }
        if use.reason is None and use.target is not None:
            row["target"] = use.target
            resolved_dynamic.append(row)
        else:
            row["reason"] = use.reason or "静的に解決できない"
            unresolved_dynamic.append(row)

    graph = [
        {"from": owner, "to": target, "kind": kind}
        for owner in sorted(reachable)
        for target, kind in sorted(state.edges.get(owner, set()))
        if target in reachable
    ]
    unresolved = [
        *state.metadata_issues,
        *unresolved_dynamic,
        *router_issues,
    ]
    attempts_by_kind = {
        "projectMetadata": 1,
        "pythonFiles": len(state.modules),
    }
    return {
        "schemaVersion": 1,
        "sourceRoot": state.relative(resolved_source),
        "attempts": sum(attempts_by_kind.values()),
        "attemptsByKind": attempts_by_kind,
        "entries": sorted(
            state.entries,
            key=lambda row: (row["kind"], row["name"], row["module"]),
        ),
        "reachableModules": [
            {
                "module": name,
                "path": state.relative(state.modules[name].path),
            }
            for name in sorted(reachable)
        ],
        "importGraph": graph,
        "routers": sorted(
            routers,
            key=lambda row: (row["ownerModule"], row["reference"]),
        ),
        "resolvedDynamic": sorted(
            resolved_dynamic,
            key=lambda row: (
                str(row["path"]),
                str(row["construct"]),
                str(row["expression"]),
            ),
        ),
        "unresolved": sorted(
            unresolved,
            key=lambda row: (
                str(row["path"]),
                str(row["construct"]),
                str(row["expression"]),
            ),
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    """収集 CLI の引数パーサを作る。"""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
    )
    parser.add_argument("--source-root", type=Path, default=Path("backend/src"))
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("backend/pyproject.toml"),
    )
    return parser


def _resolve_path(root: Path, path: Path) -> Path:
    """相対パスをリポジトリルート基準で解決する。"""
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main(argv: Sequence[str] | None = None) -> int:
    """Backend の実在入口を列挙し、解析不能なら exit 2 を返す。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        収集完了は 0、判定不能は 2。
    """
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        result = collect_backend_entries(
            root,
            _resolve_path(root, arguments.source_root),
            _resolve_path(root, arguments.pyproject),
        )
        print(canonical_json(result), end="")
        unresolved = result["unresolved"]
        if isinstance(unresolved, list) and unresolved:
            print(
                f"判定不能: 静的に解決できない入口が {len(unresolved)} 件ある",
                file=sys.stderr,
            )
            return EXIT_INDETERMINATE
    except CheckerExecutionError as error:
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE
    return EXIT_CONFORMING


if __name__ == "__main__":
    raise SystemExit(main())
