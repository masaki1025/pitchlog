"""Frontend の実在入口と import graph を独立収集する。"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import NoReturn, Sequence

from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    CheckerExecutionError,
    canonical_json,
)

_CODE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})
_RESOLUTION_SUFFIXES = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".vue",
    ".json",
    ".css",
)
_IGNORED_DIRECTORIES = frozenset({".git", "node_modules", "dist", "coverage"})
_FROM_IMPORT = re.compile(
    r"\b(?:import|export)\s+(?:type\s+)?[^;]*?\s+from\s*"
    r"(?P<quote>['\"])(?P<path>[^'\"]+)(?P=quote)",
    re.MULTILINE,
)
_SIDE_EFFECT_IMPORT = re.compile(
    r"\bimport\s*(?!\()(?P<quote>['\"])(?P<path>[^'\"]+)(?P=quote)"
)
_CSS_REFERENCE = re.compile(
    r"(?:@import\s+|url\()\s*(?P<quote>['\"]?)(?P<path>[^'\")\s]+)"
    r"(?P=quote)\s*\)?"
)
_CALL_MARKERS = {
    "dynamic-import": re.compile(r"\bimport\s*\("),
    "require": re.compile(r"\brequire\s*\("),
    "worker": re.compile(r"\bnew\s+Worker\s*\("),
    "shared-worker": re.compile(r"\bnew\s+SharedWorker\s*\("),
    "service-worker": re.compile(
        r"\bnavigator\s*\.\s*serviceWorker\s*\.\s*register\s*\("
    ),
    "import-meta-glob": re.compile(r"\bimport\s*\.\s*meta\s*\.\s*glob\s*\("),
}


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを送出する。"""
        raise CheckerExecutionError(message)


class _HtmlScripts(HTMLParser):
    """HTML の script と link を字句どおり収集する。"""

    def __init__(self) -> None:
        """空の収集結果を初期化する。"""
        super().__init__(convert_charrefs=True)
        self.scripts: list[tuple[dict[str, str], str]] = []
        self.links: list[dict[str, str]] = []
        self._script_attributes: dict[str, str] | None = None
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Script または link の属性を記録する。"""
        attributes = {key: value or "" for key, value in attrs}
        if tag.casefold() == "script":
            self._script_attributes = attributes
            self._script_parts = []
        elif tag.casefold() == "link":
            self.links.append(attributes)

    def handle_data(self, data: str) -> None:
        """Script 要素のインライン本文を記録する。"""
        if self._script_attributes is not None:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Script 要素の収集を確定する。"""
        if tag.casefold() != "script" or self._script_attributes is None:
            return
        self.scripts.append((self._script_attributes, "".join(self._script_parts)))
        self._script_attributes = None
        self._script_parts = []


@dataclass(slots=True)
class _Entry:
    """同一パスへ集約した入口の分類と由来。"""

    kinds: set[str] = field(default_factory=set)
    origins: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _CollectionState:
    """1 回の frontend 収集で蓄積する状態。"""

    root: Path
    frontend: Path
    attempts: dict[str, int] = field(
        default_factory=lambda: {
            "viteConfig": 0,
            "htmlFiles": 0,
            "publicFiles": 0,
            "graphFiles": 0,
        }
    )
    entries: dict[str, _Entry] = field(default_factory=dict)
    edges: set[tuple[str, str, str]] = field(default_factory=set)
    unresolved: list[dict[str, str]] = field(default_factory=list)
    scanned_graph_files: set[Path] = field(default_factory=set)

    def relative(self, path: Path) -> str:
        """パスをリポジトリ相対の POSIX 表記へ変換する。"""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError as error:
            raise CheckerExecutionError(
                f"収集対象がリポジトリ外を指している: {path}"
            ) from error

    def add_entry(self, path: Path, kind: str, origin: str) -> None:
        """入口をパス単位で重複なく登録する。"""
        relative = self.relative(path)
        entry = self.entries.setdefault(relative, _Entry())
        entry.kinds.add(kind)
        entry.origins.add(origin)

    def add_edge(self, source: Path, target: Path, kind: str) -> None:
        """Import graph の辺を登録する。"""
        self.edges.add((self.relative(source), self.relative(target), kind))

    def add_unresolved(
        self, path: Path, construct: str, expression: str, reason: str
    ) -> None:
        """静的に解決できない構文を記録する。"""
        self.unresolved.append(
            {
                "path": self.relative(path),
                "construct": construct,
                "expression": " ".join(expression.split())[:160],
                "reason": reason,
            }
        )


def _read_text(path: Path) -> str:
    """UTF-8 の監査対象を読み込む。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CheckerExecutionError(f"監査対象を読めない: {path}: {error}") from error


def _walk_files(root: Path) -> list[Path]:
    """無視対象ディレクトリを除いてファイルを全列挙する。"""
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in _IGNORED_DIRECTORIES for part in path.parts):
            continue
        if path.is_file():
            files.append(path.resolve())
    return sorted(files)


def _mask_javascript(text: str, *, strings: bool) -> str:
    """位置を保ったままコメントと必要なら文字列を空白化する。"""
    result = list(text)
    index = 0
    state = "code"
    quote = ""
    while index < len(text):
        current = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code" and current == "/" and following == "/":
            result[index] = result[index + 1] = " "
            state = "line-comment"
            index += 2
            continue
        if state == "code" and current == "/" and following == "*":
            result[index] = result[index + 1] = " "
            state = "block-comment"
            index += 2
            continue
        if state == "code" and current in {"'", '"', "`"}:
            state = "string"
            quote = current
            if strings:
                result[index] = " "
            index += 1
            continue
        if state == "line-comment":
            if current == "\n":
                state = "code"
            else:
                result[index] = " "
            index += 1
            continue
        if state == "block-comment":
            result[index] = " "
            if current == "*" and following == "/":
                result[index + 1] = " "
                state = "code"
                index += 2
            else:
                index += 1
            continue
        if state == "string":
            if strings:
                result[index] = " "
            if current == "\\":
                if index + 1 < len(text) and strings:
                    result[index + 1] = " "
                index += 2
                continue
            if current == quote:
                state = "code"
                quote = ""
            index += 1
            continue
        index += 1
    return "".join(result)


def _balanced_end(text: str, start: int, opening: str, closing: str) -> int | None:
    """文字列とコメントを無視して対応する閉じ括弧の位置を返す。"""
    depth = 0
    masked = _mask_javascript(text, strings=True)
    for index in range(start, len(masked)):
        if masked[index] == opening:
            depth += 1
        elif masked[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _split_top_level(text: str, delimiter: str = ",") -> list[str]:
    """括弧内を除外し、最上位の区切り文字で分割する。"""
    masked = _mask_javascript(text, strings=True)
    depth = 0
    start = 0
    parts: list[str] = []
    pairs = {"(": ")", "[": "]", "{": "}"}
    closings = set(pairs.values())
    for index, character in enumerate(masked):
        if character in pairs:
            depth += 1
        elif character in closings:
            depth -= 1
        elif character == delimiter and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _first_argument(arguments: str) -> str:
    """呼出し引数から第 1 引数の式を返す。"""
    parts = _split_top_level(arguments)
    return parts[0] if parts else ""


def _static_string(expression: str) -> str | None:
    """静的な JavaScript 文字列式の値を返す。"""
    candidate = expression.strip()
    if len(candidate) < 2 or candidate[0] not in {"'", '"', "`"}:
        return None
    if candidate[-1] != candidate[0]:
        return None
    if candidate[0] == "`":
        if "${" in candidate:
            return None
        return candidate[1:-1]
    try:
        value = ast.literal_eval(candidate)
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _static_url(expression: str) -> tuple[str, bool] | None:
    """静的 URL と、モジュール相対かどうかを返す。"""
    direct = _static_string(expression)
    if direct is not None:
        return direct, False
    candidate = expression.strip()
    match = re.fullmatch(r"new\s+URL\s*\((.*)\)", candidate, re.DOTALL)
    if match is None:
        return None
    arguments = _split_top_level(match.group(1))
    if len(arguments) != 2:
        return None
    path = _static_string(arguments[0])
    base = "".join(arguments[1].split())
    if path is None or base != "import.meta.url":
        return None
    return path, True


def _find_calls(text: str, marker: re.Pattern[str]) -> list[str | None]:
    """指定した呼出しの引数本文を列挙する。"""
    masked = _mask_javascript(text, strings=True)
    arguments: list[str | None] = []
    for match in marker.finditer(masked):
        opening = masked.find("(", match.start(), match.end())
        # str.find の不在値は -1 で直接判定する。
        # 0 との比較はセンチネル変換の契約検査に該当するため使わない。
        if opening == -1:
            arguments.append(None)
            continue
        closing = _balanced_end(text, opening, "(", ")")
        arguments.append(None if closing is None else text[opening + 1 : closing])
    return arguments


def _property_expression(text: str, property_name: str) -> str | None:
    """Object 本文にある最上位プロパティの値式を返す。"""
    masked = _mask_javascript(text, strings=True)
    depth = 0
    index = 0
    while index < len(masked):
        character = masked[index]
        if character in "([{":
            depth += 1
            index += 1
            continue
        if character in ")]}]":
            depth -= 1
            index += 1
            continue
        if depth == 0 and (character.isalpha() or character in "_$"):
            end = index + 1
            while end < len(masked) and (masked[end].isalnum() or masked[end] in "_$"):
                end += 1
            name = masked[index:end]
            cursor = end
            while cursor < len(masked) and masked[cursor].isspace():
                cursor += 1
            if name == property_name and cursor < len(masked) and masked[cursor] == ":":
                value_start = cursor + 1
                remainder = text[value_start:]
                values = _split_top_level(remainder)
                return values[0] if values else ""
            index = end
            continue
        index += 1
    return None


def _object_expression(text: str, property_name: str) -> tuple[bool, str] | None:
    """任意位置の object プロパティについて静的可否と本文を返す。"""
    masked = _mask_javascript(text, strings=True)
    match = re.search(rf"\b{re.escape(property_name)}\s*:", masked)
    if match is None:
        return None
    start = match.end()
    while start < len(masked) and masked[start].isspace():
        start += 1
    if start >= len(masked) or masked[start] != "{":
        return False, ""
    end = _balanced_end(text, start, "{", "}")
    if end is None:
        return False, ""
    return True, text[start + 1 : end]


def _vite_input_value(expression: str) -> str | None:
    """静的な Vite input 値から frontend 相対パスを返す。"""
    direct = _static_string(expression)
    if direct is not None:
        return direct
    url = re.search(r"new\s+URL\s*\((.*)\)", expression, re.DOTALL)
    if url is not None:
        resolved = _static_url(url.group(0))
        return resolved[0] if resolved is not None else None
    call = re.fullmatch(r"(?:path\.)?resolve\s*\((.*)\)", expression, re.DOTALL)
    if call is None:
        return None
    arguments = _split_top_level(call.group(1))
    return _static_string(arguments[-1]) if arguments else None


def _vite_inputs(state: _CollectionState) -> list[tuple[Path, str]]:
    """Vite 設定から全 input、未指定なら既定 HTML を導出する。"""
    state.attempts["viteConfig"] += 1
    config = state.frontend / "vite.config.ts"
    if not config.is_file():
        return [(state.frontend / "index.html", "vite-default")]
    source = _read_text(config)
    rollup_result = _object_expression(source, "rollupOptions")
    if rollup_result is None:
        return [(state.frontend / "index.html", "vite-default")]
    rollup_is_static, rollup = rollup_result
    if not rollup_is_static:
        state.add_unresolved(config, "vite-input", "rollupOptions", "object でない")
        return []
    input_expression = _property_expression(rollup, "input")
    if input_expression is None:
        return [(state.frontend / "index.html", "vite-default")]

    expressions: list[str]
    stripped = input_expression.strip()
    if stripped.startswith("["):
        end = _balanced_end(stripped, 0, "[", "]")
        expressions = [] if end is None else _split_top_level(stripped[1:end])
    elif stripped.startswith("{"):
        end = _balanced_end(stripped, 0, "{", "}")
        rows = [] if end is None else _split_top_level(stripped[1:end])
        expressions = []
        for row in rows:
            if ":" not in row:
                expressions.append("")
                continue
            expressions.append(row.split(":", maxsplit=1)[1].strip())
    else:
        expressions = [stripped]

    inputs: list[tuple[Path, str]] = []
    if not expressions:
        state.add_unresolved(config, "vite-input", input_expression, "空または構文不正")
    for expression in expressions:
        relative = _vite_input_value(expression)
        if relative is None:
            state.add_unresolved(config, "vite-input", expression, "静的に解決できない")
            continue
        path = Path(relative)
        resolved = (
            path.resolve() if path.is_absolute() else (state.frontend / path).resolve()
        )
        inputs.append((resolved, "vite-input"))
    return inputs


def _local_reference(specifier: str) -> bool:
    """Import 指定が frontend 内のローカル参照かを返す。"""
    return specifier.startswith((".", "/"))


def _external_url(specifier: str) -> bool:
    """指定がリポジトリ外の URL または fragment かを返す。"""
    lowered = specifier.casefold()
    return lowered.startswith(("http://", "https://", "//", "data:", "blob:", "#"))


def _resolve_file(base: Path, specifier: str, frontend: Path) -> Path | None:
    """静的指定を frontend 内の実ファイルへ解決する。"""
    clean = specifier.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if clean.startswith("/"):
        direct = frontend / clean.lstrip("/")
        public = frontend / "public" / clean.lstrip("/")
        candidates = [direct, public]
    else:
        candidates = [base / clean]
    expanded: list[Path] = []
    for candidate in candidates:
        expanded.append(candidate)
        if not candidate.suffix:
            expanded.extend(
                Path(f"{candidate}{suffix}") for suffix in _RESOLUTION_SUFFIXES
            )
            expanded.extend(
                candidate / f"index{suffix}" for suffix in _RESOLUTION_SUFFIXES
            )
    matches = [candidate.resolve() for candidate in expanded if candidate.is_file()]
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def _resolve_reference(
    state: _CollectionState,
    source: Path,
    specifier: str,
    *,
    module_relative: bool,
    construct: str,
    bare_is_local: bool = False,
) -> Path | None:
    """参照先を解決し、曖昧または不在なら解析不能を記録する。"""
    if not _local_reference(specifier):
        if not bare_is_local:
            return None
        if _external_url(specifier):
            state.add_unresolved(
                source,
                construct,
                specifier,
                "frontend 外の URL を指している",
            )
            return None
    base = source.parent if module_relative else state.frontend
    resolved = _resolve_file(base, specifier, state.frontend)
    if resolved is None:
        state.add_unresolved(
            source,
            construct,
            specifier,
            "実ファイルへ一意に解決できない",
        )
        return None
    try:
        resolved.relative_to(state.frontend)
    except ValueError:
        state.add_unresolved(source, construct, specifier, "frontend 外を指している")
        return None
    return resolved


def _script_text(path: Path, source: str) -> str:
    """Vue SFC なら script 本文、通常ファイルなら全文を返す。"""
    if path.suffix != ".vue":
        return source
    parser = _HtmlScripts()
    parser.feed(source)
    return "\n".join(body for _attributes, body in parser.scripts)


def _scan_code(
    state: _CollectionState,
    source_path: Path,
    source: str,
    queue: deque[Path],
) -> None:
    """静的 import と Worker 系入口を解析する。"""
    code = _script_text(source_path, source)
    uncommented = _mask_javascript(code, strings=False)
    imports = {
        match.group("path")
        for pattern in (_FROM_IMPORT, _SIDE_EFFECT_IMPORT)
        for match in pattern.finditer(uncommented)
    }
    for specifier in sorted(imports):
        if not _local_reference(specifier):
            continue
        target = _resolve_reference(
            state,
            source_path,
            specifier,
            module_relative=True,
            construct="static-import",
        )
        if target is not None:
            state.add_edge(source_path, target, "import")
            queue.append(target)

    for construct in ("dynamic-import", "require"):
        for arguments in _find_calls(code, _CALL_MARKERS[construct]):
            expression = "" if arguments is None else _first_argument(arguments)
            specifier = _static_string(expression)
            if specifier is None:
                state.add_unresolved(
                    source_path,
                    construct,
                    expression,
                    "第 1 引数が静的文字列でない",
                )
                continue
            target = _resolve_reference(
                state,
                source_path,
                specifier,
                module_relative=True,
                construct=construct,
            )
            if target is not None:
                state.add_edge(source_path, target, construct)
                queue.append(target)

    for arguments in _find_calls(code, _CALL_MARKERS["import-meta-glob"]):
        expression = "" if arguments is None else _first_argument(arguments)
        state.add_unresolved(
            source_path,
            "import-meta-glob",
            expression,
            "glob 展開は静的な単一入口へ解決できない",
        )

    for construct in ("worker", "shared-worker", "service-worker"):
        for arguments in _find_calls(code, _CALL_MARKERS[construct]):
            expression = "" if arguments is None else _first_argument(arguments)
            resolved_url = _static_url(expression)
            if resolved_url is None:
                state.add_unresolved(
                    source_path,
                    construct,
                    expression,
                    "第 1 引数が静的 URL でない",
                )
                continue
            specifier, module_relative = resolved_url
            target = _resolve_reference(
                state,
                source_path,
                specifier,
                module_relative=module_relative,
                construct=construct,
                bare_is_local=True,
            )
            if target is not None:
                state.add_entry(target, construct, state.relative(source_path))
                state.add_edge(source_path, target, construct)
                queue.append(target)


def _scan_css(
    state: _CollectionState, source_path: Path, source: str, queue: deque[Path]
) -> None:
    """CSS の静的 import と url 参照を graph へ加える。"""
    for match in _CSS_REFERENCE.finditer(source):
        specifier = match.group("path")
        if _external_url(specifier):
            continue
        is_import = match.group(0).lstrip().startswith("@import")
        if is_import and not _local_reference(specifier):
            continue
        target = _resolve_reference(
            state,
            source_path,
            specifier,
            module_relative=True,
            construct="css-reference",
            bare_is_local=True,
        )
        if target is not None:
            state.add_edge(source_path, target, "css-reference")
            queue.append(target)


def _scan_graph(state: _CollectionState, roots: deque[Path]) -> None:
    """全 root から production import graph を幅優先走査する。"""
    while roots:
        path = roots.popleft().resolve()
        if path in state.scanned_graph_files:
            continue
        state.scanned_graph_files.add(path)
        state.attempts["graphFiles"] += 1
        if not path.is_file():
            state.add_unresolved(
                path,
                "graph-file",
                str(path),
                "実ファイルが存在しない",
            )
            continue
        if path.suffix in _CODE_SUFFIXES or path.suffix == ".vue":
            _scan_code(state, path, _read_text(path), roots)
        elif path.suffix == ".css":
            _scan_css(state, path, _read_text(path), roots)


def _scan_html(state: _CollectionState, html_path: Path, roots: deque[Path]) -> None:
    """HTML の script・link とインラインコードを graph へ加える。"""
    parser = _HtmlScripts()
    parser.feed(_read_text(html_path))
    for attributes, body in parser.scripts:
        source = attributes.get("src")
        if source:
            target = _resolve_reference(
                state,
                html_path,
                source,
                module_relative=True,
                construct="html-script",
                bare_is_local=True,
            )
            if target is not None:
                state.add_edge(html_path, target, "html-script")
                roots.append(target)
        elif body.strip():
            _scan_code(state, html_path, body, roots)
    for attributes in parser.links:
        reference = attributes.get("href")
        if not reference or _external_url(reference):
            continue
        target = _resolve_reference(
            state,
            html_path,
            reference,
            module_relative=True,
            construct="html-link",
            bare_is_local=True,
        )
        if target is not None:
            state.add_edge(html_path, target, "html-link")
            roots.append(target)


def collect_frontend_entries(root: Path, frontend: Path) -> dict[str, object]:
    """Frontend の入口と到達可能 graph を実ファイルから独立導出する。

    Args:
        root: リポジトリルート。
        frontend: frontend ディレクトリ。

    Returns:
        入口、graph、解析不能、走査回数を持つ機械可読な収集結果。

    Raises:
        CheckerExecutionError: 収集対象を読み取れない場合。
    """
    resolved_root = root.resolve()
    resolved_frontend = frontend.resolve()
    if not resolved_frontend.is_dir():
        raise CheckerExecutionError(f"frontend ディレクトリを読めない: {frontend}")
    try:
        resolved_frontend.relative_to(resolved_root)
    except ValueError as error:
        raise CheckerExecutionError("frontend がリポジトリ外を指している") from error

    state = _CollectionState(root=resolved_root, frontend=resolved_frontend)
    vite_inputs = _vite_inputs(state)
    html_files = [
        path for path in _walk_files(resolved_frontend) if path.suffix == ".html"
    ]
    state.attempts["htmlFiles"] += len(html_files)
    roots: deque[Path] = deque()

    for html_path in html_files:
        state.add_entry(html_path, "html", "html-file")
        _scan_html(state, html_path, roots)
    for input_path, origin in vite_inputs:
        kind = "html" if input_path.suffix == ".html" else "vite-input"
        state.add_entry(input_path, kind, origin)
        if not input_path.is_file():
            state.add_unresolved(
                input_path,
                "vite-input",
                state.relative(input_path),
                "実ファイルが存在しない",
            )
        elif input_path.suffix != ".html":
            roots.append(input_path)

    public_root = resolved_frontend / "public"
    public_files = _walk_files(public_root)
    state.attempts["publicFiles"] += len(public_files)
    for public_path in public_files:
        state.add_entry(public_path, "static-public", "public-directory")

    _scan_graph(state, roots)
    attempts = sum(state.attempts.values())
    return {
        "schemaVersion": 1,
        "frontendRoot": state.relative(resolved_frontend),
        "attempts": attempts,
        "attemptsByKind": dict(sorted(state.attempts.items())),
        "entries": [
            {
                "path": path,
                "kinds": sorted(entry.kinds),
                "origins": sorted(entry.origins),
            }
            for path, entry in sorted(state.entries.items())
        ],
        "importGraph": [
            {"from": source, "to": target, "kind": kind}
            for source, target, kind in sorted(state.edges)
        ],
        "unresolved": sorted(
            state.unresolved,
            key=lambda row: (
                row["path"],
                row["construct"],
                row["expression"],
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
    parser.add_argument("--frontend", type=Path, default=Path("frontend"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Frontend の実在入口を列挙し、解析不能なら exit 2 を返す。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        収集完了は 0、判定不能は 2。
    """
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        frontend = (
            arguments.frontend.resolve()
            if arguments.frontend.is_absolute()
            else (root / arguments.frontend).resolve()
        )
        result = collect_frontend_entries(root, frontend)
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
