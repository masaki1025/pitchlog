"""ポート実装の登録と import 閉包を、呼び出し前に検証する。

この静的検査は補助であり、安全の境界ではない。境界は core-areas の sync-protocol に
属する sync/ports.py の登録変更への敵対レビュー・人間の逐行確認と、U-X1 が本物の
投影ポートで設ける、適用核の印を要求する DB トリガである。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from collections.abc import Collection
from pathlib import Path

from pitchlog.sync import ports
from pitchlog.sync.ports import PortRegistrationError

_PITCHLOG_ROOT = Path(__file__).resolve().parents[1]
# 標準ライブラリも公開名ごとに固定する。文字列を評価する名前は許可しない。
_ALLOWED_STANDARD_NAMES: dict[str, frozenset[str]] = {
    "__future__": frozenset({"annotations"}),
    "typing": frozenset(
        {"Protocol", "Literal", "final", "cast", "TYPE_CHECKING", "Any"}
    ),
    "dataclasses": frozenset({"dataclass", "field", "fields", "replace"}),
    "enum": frozenset({"Enum"}),
    "abc": frozenset({"ABC", "abstractmethod"}),
    "collections": frozenset({"abc"}),
    "collections.abc": frozenset(
        {"Callable", "Mapping", "Collection", "Iterable", "Sequence"}
    ),
    "types": frozenset({"MappingProxyType"}),
    "uuid": frozenset({"UUID"}),
    "datetime": frozenset({"date", "datetime", "time"}),
    "decimal": frozenset({"Decimal"}),
    "functools": frozenset({"cache", "partial", "wraps"}),
    "itertools": frozenset({"chain", "islice", "count"}),
    "re": frozenset({"fullmatch", "match", "search"}),
}
_FORBIDDEN_NAMES = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "__builtins__",
        "__loader__",
        "__spec__",
        "setattr",
        "delattr",
        "sys",
        "importlib",
        "builtins",
        "os",
        "pkgutil",
        "subprocess",
        "socket",
        "ctypes",
        "threading",
        "asyncio",
        "multiprocessing",
        "sqlalchemy",
        "psycopg",
    }
)
_FORBIDDEN_ATTRIBUTES = _FORBIDDEN_NAMES | frozenset(
    {
        "sys",
        "importlib",
        "builtins",
        "os",
        "pkgutil",
        "subprocess",
        "socket",
        "ctypes",
        "threading",
        "asyncio",
        "multiprocessing",
        "sqlalchemy",
        "psycopg",
        "__dict__",
        "__getattribute__",
        "__subclasses__",
        "__globals__",
        "__mro__",
        "__code__",
        "__closure__",
        "getattr",
        "import_module",
        "resolve_name",
    }
)
_PORT_INTERNAL_NAMES = frozenset(
    {
        "_WRITER_CREATION_TOKEN",
        "_issue_port_writer",
        "PORT_IMPLEMENTATIONS",
        "_PORT_VERIFIER",
        "_execute",
        "_active",
        "_close",
    }
)
# 検査器自身は権限付きの入口であり、ポートの import 閉包からは到達させない。
_PRIVILEGED_MODULE = "pitchlog.sync.port_guard"
_FORBIDDEN_PITCHLOG_MODULES = frozenset(
    {
        "pitchlog.db",
        "pitchlog.repositories.transaction",
        "pitchlog.repositories.context",
        _PRIVILEGED_MODULE,
    }
)


def _pitchlog_module_file(module_name: str) -> Path | None:
    """Pitchlog 内のソースを実行せずに解決する。"""
    if module_name != "pitchlog" and not module_name.startswith("pitchlog."):
        return None
    target = _PITCHLOG_ROOT.joinpath(*module_name.split(".")[1:])
    file_path = target.with_suffix(".py")
    if file_path.is_file():
        return file_path
    init_path = target / "__init__.py"
    if init_path.is_file():
        return init_path
    return None


def _plain_export_value(
    value: ast.expr, local_classes: dict[str, ast.ClassDef]
) -> bool:
    """Module object を作らないことが構文から分かる定数だけを認める。"""
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
        owner = local_classes.get(value.value.id)
        if owner is None or not any(
            isinstance(base, ast.Name) and base.id == "Enum" for base in owner.bases
        ):
            return False
        return any(
            isinstance(member, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == value.attr
                for target in member.targets
            )
            and isinstance(member.value, ast.Constant)
            for member in owner.body
        )
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return all(_plain_export_value(item, local_classes) for item in value.elts)
    if isinstance(value, ast.Dict):
        return all(
            key is not None
            and _plain_export_value(key, local_classes)
            and _plain_export_value(item, local_classes)
            for key, item in zip(value.keys, value.values, strict=True)
        )
    return False


def _pitchlog_value_export(
    module_name: str,
    export_name: str,
    visited: frozenset[tuple[str, str]] = frozenset(),
) -> bool:
    """Pitchlog の公開名が module object ではないと静的に確認する。"""
    key = (module_name, export_name)
    path = _pitchlog_module_file(module_name)
    if key in visited or path is None:
        return False
    try:
        source = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    local_classes = {
        node.name: node for node in source.body if isinstance(node, ast.ClassDef)
    }
    declarations: list[bool] = []
    package = (
        module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
    )
    for node in source.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == export_name:
                declarations.append(True)
        elif isinstance(node, ast.TypeAlias):
            if isinstance(node.name, ast.Name) and node.name.id == export_name:
                declarations.append(True)
        elif isinstance(node, ast.Import):
            declarations.extend(
                False
                for alias in node.names
                if (alias.asname or alias.name.split(".")[0]) == export_name
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except ImportError:
                    return False
            else:
                base = node.module or ""
            for alias in node.names:
                if (alias.asname or alias.name) != export_name:
                    continue
                child = f"{base}.{alias.name}"
                if _pitchlog_module_file(child) is not None:
                    declarations.append(False)
                elif base in _ALLOWED_STANDARD_NAMES:
                    declarations.append(
                        alias.name in _ALLOWED_STANDARD_NAMES[base]
                        and child not in _ALLOWED_STANDARD_NAMES
                    )
                elif base.startswith("pitchlog."):
                    declarations.append(
                        _pitchlog_value_export(base, alias.name, visited | {key})
                    )
                else:
                    declarations.append(False)
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == export_name
                for target in node.targets
            ):
                declarations.append(_plain_export_value(node.value, local_classes))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == export_name:
                declarations.append(
                    node.value is not None
                    and _plain_export_value(node.value, local_classes)
                )
    return bool(declarations) and all(declarations)


def _module_file(module_name: str) -> Path:
    """登録対象のソース位置を実行せずに解決する。"""
    pitchlog_file = _pitchlog_module_file(module_name)
    if pitchlog_file is not None:
        return pitchlog_file
    if module_name == "pitchlog" or module_name.startswith("pitchlog."):
        raise PortRegistrationError(f"ポート実装のソースがない: {module_name}")
    loaded = sys.modules.get(module_name)
    location = getattr(loaded, "__file__", None)
    if not isinstance(location, str):
        try:
            location = getattr(importlib.util.find_spec(module_name), "origin", None)
        except (ImportError, ValueError, AttributeError) as error:
            raise PortRegistrationError(
                f"ポート実装のソースを解決できない: {module_name}"
            ) from error
    if not isinstance(location, str) or not location.endswith(".py"):
        raise PortRegistrationError(f"ポート実装の Python ソースがない: {module_name}")
    path = Path(location)
    if not path.is_file():
        raise PortRegistrationError(f"ポート実装のソースがない: {module_name}")
    return path


def _standard_module_of(
    expression: ast.expr, module_aliases: dict[str, str]
) -> str | None:
    """式が指す許可済み標準モジュールを、静的に分かる範囲で返す。"""
    if isinstance(expression, ast.Name):
        return module_aliases.get(expression.id)
    if isinstance(expression, ast.Attribute):
        parent = _standard_module_of(expression.value, module_aliases)
        if (
            parent is not None
            and f"{parent}.{expression.attr}" in _ALLOWED_STANDARD_NAMES
        ):
            return f"{parent}.{expression.attr}"
    return None


def _validate_standard_symbols(
    module_name: str, source: ast.AST, module_aliases: dict[str, str]
) -> None:
    """モジュールオブジェクトの属性・getattr・別名への受け渡しを検査する。"""
    parents = {
        child: parent
        for parent in ast.walk(source)
        for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(source):
        if isinstance(node, ast.Attribute):
            base = _standard_module_of(node.value, module_aliases)
            if base is not None and node.attr not in _ALLOWED_STANDARD_NAMES[base]:
                raise PortRegistrationError(
                    f"禁止された標準ライブラリ名: {module_name}: {base}.{node.attr}"
                )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "getattr":
                base = (
                    _standard_module_of(node.args[0], module_aliases)
                    if len(node.args) == 2 and not node.keywords
                    else None
                )
                name = node.args[1] if len(node.args) == 2 else None
                if (
                    base is None
                    or not isinstance(name, ast.Constant)
                    or type(name.value) is not str
                    or name.value not in _ALLOWED_STANDARD_NAMES[base]
                ):
                    raise PortRegistrationError(f"禁止された getattr: {module_name}")
        if isinstance(node, ast.Name) and node.id == "getattr":
            parent = parents.get(node)
            if not isinstance(parent, ast.Call) or parent.func is not node:
                raise PortRegistrationError(f"getattr の別名化は禁止: {module_name}")
        if isinstance(node, ast.Name) and node.id in module_aliases:
            parent = parents.get(node)
            allowed_attribute = (
                isinstance(parent, ast.Attribute) and parent.value is node
            )
            allowed_getattr = (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id == "getattr"
                and bool(parent.args)
                and parent.args[0] is node
            )
            if not (allowed_attribute or allowed_getattr):
                raise PortRegistrationError(
                    f"標準モジュールの受け渡しは禁止: {module_name}: {node.id}"
                )


def _imported_modules(module_name: str, source: ast.AST, file_path: Path) -> set[str]:
    """静的 import を絶対名へ変換し、標準名の使用を検査する。"""
    imported: set[str] = set()
    module_aliases: dict[str, str] = {}
    package = (
        module_name
        if file_path.name == "__init__.py"
        else module_name.rpartition(".")[0]
    )
    for node in ast.walk(source):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise PortRegistrationError(
                f"禁止名を参照するポート実装: {module_name}: {node.id}"
            )
        if isinstance(node, ast.Attribute) and (
            node.attr in _FORBIDDEN_ATTRIBUTES
            or (
                module_name != "pitchlog.sync.ports"
                and node.attr in _PORT_INTERNAL_NAMES
            )
        ):
            raise PortRegistrationError(
                f"禁止属性を参照するポート実装: {module_name}: {node.attr}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pitchlog" or alias.name.startswith("pitchlog."):
                    raise PortRegistrationError(
                        f"Pitchlog モジュールのオブジェクト import は禁止: {alias.name}"
                    )
                imported.add(alias.name)
                if alias.name in _ALLOWED_STANDARD_NAMES:
                    bound_name = alias.asname or alias.name.split(".")[0]
                    module_aliases[bound_name] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except ImportError as error:
                    raise PortRegistrationError(
                        f"相対 import を解決できない: {module_name}"
                    ) from error
            else:
                base = node.module or ""
            if base == "pitchlog":
                raise PortRegistrationError("Pitchlog のルートからの import は禁止")
            if base.startswith("pitchlog."):
                for alias in node.names:
                    if (
                        alias.name == "*"
                        or _pitchlog_module_file(f"{base}.{alias.name}") is not None
                    ):
                        raise PortRegistrationError(
                            f"Pitchlog モジュールのオブジェクト import は禁止: "
                            f"{base}.{alias.name}"
                        )
                    if not _pitchlog_value_export(base, alias.name):
                        raise PortRegistrationError(
                            f"Pitchlog の非モジュール名と確認できないため import 禁止: "
                            f"{base}.{alias.name}"
                        )
            if any(alias.name in _FORBIDDEN_ATTRIBUTES for alias in node.names):
                raise PortRegistrationError(
                    f"禁止 import 属性を含むポート実装: {module_name}"
                )
            if base in _ALLOWED_STANDARD_NAMES:
                for alias in node.names:
                    if alias.name not in _ALLOWED_STANDARD_NAMES[base]:
                        raise PortRegistrationError(
                            f"禁止された標準ライブラリ名: {base}.{alias.name}"
                        )
                    child = f"{base}.{alias.name}"
                    if child in _ALLOWED_STANDARD_NAMES:
                        imported.add(child)
                        module_aliases[alias.asname or alias.name] = child
            if (
                base == "pitchlog.sync.ports"
                and module_name != base
                and any(alias.name in _PORT_INTERNAL_NAMES for alias in node.names)
            ):
                raise PortRegistrationError(
                    f"書き手の発行情報を参照するポート実装: {module_name}"
                )
            if base:
                imported.add(base)
    _validate_standard_symbols(module_name, source, module_aliases)
    return imported


def _validate_source(module_name: str, source: ast.AST, file_path: Path) -> set[str]:
    """単一モジュールの名前と import を固定 allowlist で検査する。"""
    imported = _imported_modules(module_name, source, file_path)
    for target in imported:
        if any(
            target == forbidden or target.startswith(f"{forbidden}.")
            for forbidden in _FORBIDDEN_PITCHLOG_MODULES
        ):
            raise PortRegistrationError(f"禁止 import を含むポート実装: {target}")
        if target == "pitchlog" or target.startswith("pitchlog."):
            if _pitchlog_module_file(target) is None:
                raise PortRegistrationError(f"ソースのない import: {target}")
        elif target not in _ALLOWED_STANDARD_NAMES:
            raise PortRegistrationError(f"禁止 import を含むポート実装: {target}")
    return imported


def validate_port_source(source_text: str, module_name: str = "synthetic_port") -> None:
    """合成ソースにも実登録と同じ名前・import 規則を適用する。"""
    try:
        parsed = ast.parse(source_text)
    except SyntaxError as error:
        raise PortRegistrationError("ポート実装の構文を検査できない") from error
    _validate_source(module_name, parsed, Path(f"{module_name}.py"))


def validate_port_modules(modules: Collection[str] | None = None) -> None:
    """登録モジュールと pitchlog 内の推移的 import を静的に検査する。"""
    pending = list(
        {module for module, _ in ports.PORT_IMPLEMENTATIONS}
        if modules is None
        else modules
    )
    visited: set[str] = set()
    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        visited.add(module_name)
        try:
            file_path = _module_file(module_name)
            source = ast.parse(file_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as error:
            raise PortRegistrationError(
                f"ポート実装のソースを検査できない: {module_name}"
            ) from error
        for imported in _validate_source(module_name, source, file_path):
            if imported == "pitchlog" or imported.startswith("pitchlog."):
                parts = imported.split(".")
                for size in range(1, len(parts) + 1):
                    candidate = ".".join(parts[:size])
                    if _pitchlog_module_file(candidate) is not None:
                        pending.append(candidate)


def require_registered_port(port: object) -> None:
    """登録済みクラスとの同一性を、ポート呼び出し前に照合する。"""
    validate_port_modules()
    for module_name, class_name in ports.PORT_IMPLEMENTATIONS:
        module = sys.modules.get(module_name)
        if module is None:
            raise PortRegistrationError(
                f"登録モジュールが読み込まれていない: {module_name}"
            )
        registered_type = vars(module).get(class_name)
        if isinstance(registered_type, type) and type(port) is registered_type:
            return
    raise PortRegistrationError(f"未登録のポート実装: {type(port).__name__}")


def _load_first_ball_port_classes() -> tuple[type[object], ...]:
    """固定3実装だけを検査後に読み込み、集合の巡回順に依存させない。"""
    validate_port_modules()
    from pitchlog.sync.first_ball_ports import FirstBallContentValidationPort
    from pitchlog.sync.first_ball_projection import FirstBallProjectionPort
    from pitchlog.sync.first_ball_recording_rights import FirstBallRecordingRightsPort

    return (
        FirstBallContentValidationPort,
        FirstBallProjectionPort,
        FirstBallRecordingRightsPort,
    )


_BOOTSTRAPPED_FIRST_BALL_TYPES = _load_first_ball_port_classes()


# ports 自身は解析ライブラリを import しない。検査器の導入前は入口が閉じている。
ports._PORT_VERIFIER = require_registered_port
