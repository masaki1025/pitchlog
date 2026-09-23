"""Python・TypeScript・SQL の非表示系変異演算子を提供する。

`ADR-003 D-11 変異テスト規則` の言語別演算子だけを扱う。表示文字列・
テンプレート・写像・数値表示 primitive の変異は後続ステップの責務である。
"""

from __future__ import annotations

import ast
import copy
import re
from dataclasses import dataclass
from enum import StrEnum

from pitchlog.domainmut.engine import (
    Mutant,
    MutationGeneration,
    SyntheticMutationTarget,
    UnsupportedLocation,
)


class Language(StrEnum):
    """本ステップが変異する三つの言語。"""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    SQL = "sql"


@dataclass(frozen=True, slots=True)
class LanguageSource:
    """言語とソースを結び付けた合成変異対象の値。"""

    language: Language
    code: str

    def __post_init__(self) -> None:
        """未知言語と空ソースを拒否する。"""
        if not isinstance(self.language, Language):
            raise ValueError(f"未知の言語: {self.language}")
        if not self.code:
            raise ValueError("言語ソースが空")


@dataclass(frozen=True, slots=True)
class _TextMutation:
    """ソース上の一範囲を置き換える変異候補。"""

    location: str
    start: int
    end: int
    replacement: str


@dataclass(frozen=True, slots=True)
class _PythonCandidate:
    """Python AST 上の一変異候補。"""

    location: str
    line: int
    column: int
    kind: str
    replacement: str


_PYTHON_BINARY_REPLACEMENTS: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
}
_PYTHON_COMPARE_REPLACEMENTS: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}


def _source_for(
    target: SyntheticMutationTarget,
    language: Language,
) -> LanguageSource | None:
    """対象言語のソースだけを返し、他言語には適用しない。"""
    source = target.source
    if not isinstance(source, LanguageSource) or source.language is not language:
        return None
    return source


def _unsupported(
    target: SyntheticMutationTarget,
    operator_id: str,
    location: str,
    reason: str,
) -> UnsupportedLocation:
    """一つの未対応箇所をエンジンの型で返す。"""
    return UnsupportedLocation(
        calculation=target.calculation,
        target_id=target.target_id,
        location_id=location,
        operator_id=operator_id,
        reason=reason,
    )


def _mutant(
    target: SyntheticMutationTarget,
    operator_id: str,
    index: int,
    source: LanguageSource,
) -> Mutant:
    """言語ソースの一変異を安定 ID 付き mutant にする。"""
    return Mutant(
        mutant_id=(
            f"{target.calculation}.{target.target_id}.{source.language.value}.{index}"
        ),
        calculation=target.calculation,
        target_id=target.target_id,
        operator_id=operator_id,
        mutated=source,
    )


class _PythonTransformer(ast.NodeTransformer):
    """指定した一候補だけを変更する Python AST 変換器。"""

    def __init__(self, candidate: _PythonCandidate) -> None:
        self.candidate = candidate

    def _matches(self, node: ast.AST, kind: str) -> bool:
        """ノード位置と変異種別が候補に一致するか返す。"""
        return (
            getattr(node, "lineno", None) == self.candidate.line
            and getattr(node, "col_offset", None) == self.candidate.column
            and self.candidate.kind == kind
        )

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        """算術演算子を指定した型へ置換する。"""
        self.generic_visit(node)
        if self._matches(node, "binary"):
            replacement = next(
                operator
                for operator in _PYTHON_BINARY_REPLACEMENTS.values()
                if operator.__name__ == self.candidate.replacement
            )
            node.op = replacement()
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        """単項比較の境界または等号を置換する。"""
        self.generic_visit(node)
        if self._matches(node, "compare"):
            replacement = next(
                operator
                for operator in _PYTHON_COMPARE_REPLACEMENTS.values()
                if operator.__name__ == self.candidate.replacement
            )
            node.ops[0] = replacement()
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        """Boolean を反転し、数値定数を一つ増やす。"""
        if self._matches(node, "boolean"):
            return ast.copy_location(ast.Constant(not node.value), node)
        if self._matches(node, "number"):
            assert isinstance(node.value, (int, float))
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node

    def visit_If(self, node: ast.If) -> ast.AST | list[ast.stmt]:
        """条件分岐を選択済みの一方の文列へ置換する。"""
        self.generic_visit(node)
        if not self._matches(node, "branch"):
            return node
        selected = node.body if self.candidate.replacement == "body" else node.orelse
        return selected or [ast.copy_location(ast.Pass(), node)]


def _python_candidates(
    tree: ast.AST,
    target: SyntheticMutationTarget,
    operator_id: str,
) -> tuple[list[_PythonCandidate], list[UnsupportedLocation]]:
    """Python AST の変異候補と未対応演算子を全列挙する。"""
    candidates: list[_PythonCandidate] = []
    unsupported: list[UnsupportedLocation] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        column = getattr(node, "col_offset", 0)
        base = f"line-{line}-column-{column}"
        if isinstance(node, ast.BinOp):
            replacement = _PYTHON_BINARY_REPLACEMENTS.get(type(node.op))
            if replacement is None:
                unsupported.append(
                    _unsupported(
                        target,
                        operator_id,
                        f"{base}-binary",
                        f"未対応の Python 算術演算子: {type(node.op).__name__}",
                    )
                )
            else:
                candidates.append(
                    _PythonCandidate(
                        f"{base}-binary",
                        line,
                        column,
                        "binary",
                        replacement.__name__,
                    )
                )
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                unsupported.append(
                    _unsupported(
                        target,
                        operator_id,
                        f"{base}-compare",
                        "連鎖比較は未対応",
                    )
                )
                continue
            replacement = _PYTHON_COMPARE_REPLACEMENTS.get(type(node.ops[0]))
            if replacement is None:
                unsupported.append(
                    _unsupported(
                        target,
                        operator_id,
                        f"{base}-compare",
                        f"未対応の Python 比較: {type(node.ops[0]).__name__}",
                    )
                )
            else:
                candidates.append(
                    _PythonCandidate(
                        f"{base}-compare",
                        line,
                        column,
                        "compare",
                        replacement.__name__,
                    )
                )
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            candidates.append(
                _PythonCandidate(
                    f"{base}-boolean",
                    line,
                    column,
                    "boolean",
                    "invert",
                )
            )
        elif isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            candidates.append(
                _PythonCandidate(
                    f"{base}-number",
                    line,
                    column,
                    "number",
                    "increment",
                )
            )
        elif isinstance(node, ast.If):
            candidates.extend(
                (
                    _PythonCandidate(
                        f"{base}-branch-body",
                        line,
                        column,
                        "branch",
                        "body",
                    ),
                    _PythonCandidate(
                        f"{base}-branch-else",
                        line,
                        column,
                        "branch",
                        "else",
                    ),
                )
            )
    candidates.sort(key=lambda item: (item.line, item.column, item.location))
    return candidates, unsupported


@dataclass(frozen=True, slots=True)
class PythonMutationOperator:
    """Python AST の算術・比較・真偽・定数・分岐を変異する。"""

    operator_id: str = "python-language"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """Python AST の全候補を一件ずつ変異する。"""
        source = _source_for(target, Language.PYTHON)
        if source is None:
            return MutationGeneration((), ())
        try:
            tree = ast.parse(source.code)
        except SyntaxError as error:
            location = f"line-{error.lineno or 0}-parse"
            return MutationGeneration(
                (),
                (
                    _unsupported(
                        target,
                        self.operator_id,
                        location,
                        "Python 構文を解析できない",
                    ),
                ),
            )
        candidates, unsupported = _python_candidates(
            tree,
            target,
            self.operator_id,
        )
        mutants: list[Mutant] = []
        for index, candidate in enumerate(candidates, start=1):
            changed = _PythonTransformer(candidate).visit(copy.deepcopy(tree))
            ast.fix_missing_locations(changed)
            mutants.append(
                _mutant(
                    target,
                    self.operator_id,
                    index,
                    LanguageSource(Language.PYTHON, ast.unparse(changed) + "\n"),
                )
            )
        return MutationGeneration(tuple(mutants), tuple(unsupported))


_TS_UNSUPPORTED = (
    (re.compile(r"\*\*"), "exponentiation"),
    (re.compile(r"(?<![=!])==(?!=)"), "loose-equality"),
    (re.compile(r"(?<![=!])!=(?!=)"), "loose-inequality"),
    (re.compile(r"\?\?"), "nullish-coalescing"),
    (re.compile(r"\bswitch\s*\("), "switch"),
)
_TS_TOKEN_REPLACEMENTS = (
    (re.compile(r"(?<!\+)\+(?!\+)"), "-", "arithmetic-add"),
    (re.compile(r"(?<!-)-(?!-)"), "+", "arithmetic-subtract"),
    (re.compile(r"(?<!\*)\*(?!\*)"), "/", "arithmetic-multiply"),
    (re.compile(r"/"), "*", "arithmetic-divide"),
    (re.compile(r"<="), "<", "comparison-less-equal"),
    (re.compile(r">="), ">", "comparison-greater-equal"),
    (re.compile(r"(?<![<])<(?![=])"), "<=", "comparison-less"),
    (re.compile(r"(?<![>])>(?![=])"), ">=", "comparison-greater"),
    (re.compile(r"==="), "!==", "comparison-equal"),
    (re.compile(r"!=="), "===", "comparison-not-equal"),
    (re.compile(r"\btrue\b"), "false", "boolean-true"),
    (re.compile(r"\bfalse\b"), "true", "boolean-false"),
)
_TS_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])([0-9]+)(?![A-Za-z0-9_.])")
_TS_IF_ELSE = re.compile(
    r"if\s*\((?P<condition>[^()]*)\)\s*"
    r"\{(?P<body>[^{}]*)\}\s*else\s*\{(?P<else>[^{}]*)\}",
    re.DOTALL,
)


def _typescript_mutations(code: str) -> list[_TextMutation]:
    """TypeScript の対応構文を文字位置つきで全列挙する。"""
    mutations: list[_TextMutation] = []
    for pattern, replacement, kind in _TS_TOKEN_REPLACEMENTS:
        for match in pattern.finditer(code):
            mutations.append(
                _TextMutation(
                    f"offset-{match.start()}-{kind}",
                    match.start(),
                    match.end(),
                    replacement,
                )
            )
    for match in _TS_NUMBER.finditer(code):
        value = int(match.group(1)) + 1
        mutations.append(
            _TextMutation(
                f"offset-{match.start()}-number",
                match.start(),
                match.end(),
                str(value),
            )
        )
    for match in _TS_IF_ELSE.finditer(code):
        mutations.extend(
            (
                _TextMutation(
                    f"offset-{match.start()}-branch-body",
                    match.start(),
                    match.end(),
                    match.group("body").strip(),
                ),
                _TextMutation(
                    f"offset-{match.start()}-branch-else",
                    match.start(),
                    match.end(),
                    match.group("else").strip(),
                ),
            )
        )
    mutations.sort(key=lambda item: (item.start, item.location))
    return mutations


@dataclass(frozen=True, slots=True)
class TypeScriptMutationOperator:
    """TypeScript の算術・比較・真偽・定数・分岐を変異する。"""

    operator_id: str = "typescript-language"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """TypeScript の全候補を一件ずつ変異し未対応構文を列挙する。"""
        source = _source_for(target, Language.TYPESCRIPT)
        if source is None:
            return MutationGeneration((), ())
        unsupported = [
            _unsupported(
                target,
                self.operator_id,
                f"offset-{match.start()}-{kind}",
                f"未対応の TypeScript 構文: {kind}",
            )
            for pattern, kind in _TS_UNSUPPORTED
            for match in pattern.finditer(source.code)
        ]
        if source.code.count("{") != source.code.count("}"):
            unsupported.append(
                _unsupported(
                    target,
                    self.operator_id,
                    "source-braces",
                    "TypeScript の波括弧が対応しない",
                )
            )
        mutations = _typescript_mutations(source.code)
        mutants = tuple(
            _mutant(
                target,
                self.operator_id,
                index,
                LanguageSource(
                    Language.TYPESCRIPT,
                    source.code[: item.start]
                    + item.replacement
                    + source.code[item.end :],
                ),
            )
            for index, item in enumerate(mutations, start=1)
        )
        return MutationGeneration(mutants, tuple(unsupported))


_SQL_AGGREGATE = re.compile(r"\b(SUM|COUNT|AVG|MIN|MAX)\s*\(", re.IGNORECASE)
_SQL_AGGREGATE_REPLACEMENT = {
    "SUM": "COUNT",
    "COUNT": "SUM",
    "AVG": "SUM",
    "MIN": "MAX",
    "MAX": "MIN",
}
_SQL_WHERE = re.compile(
    r"\bWHERE\s+(?P<predicate>.+?)(?=\bGROUP\s+BY\b|\bORDER\s+BY\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_SQL_GROUP_BY = re.compile(
    r"\bGROUP\s+BY\s+(?P<keys>.+?)(?=\bORDER\s+BY\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_SQL_JOIN = re.compile(r"\b(?:INNER\s+)?JOIN\b", re.IGNORECASE)
_SQL_UNSUPPORTED = (
    (re.compile(r"\bQUALIFY\b", re.IGNORECASE), "qualify"),
    (re.compile(r"\bHAVING\b", re.IGNORECASE), "having"),
    (re.compile(r"\bOVER\s*\(", re.IGNORECASE), "window"),
    (re.compile(r"\b(?:FULL|CROSS)\s+JOIN\b", re.IGNORECASE), "join-kind"),
)


def _sql_mutations(code: str) -> list[_TextMutation]:
    """SQL の集計・WHERE・GROUP BY・JOIN 変異を全列挙する。"""
    mutations: list[_TextMutation] = []
    for match in _SQL_AGGREGATE.finditer(code):
        name = match.group(1).upper()
        mutations.append(
            _TextMutation(
                f"offset-{match.start(1)}-aggregate",
                match.start(1),
                match.end(1),
                _SQL_AGGREGATE_REPLACEMENT[name],
            )
        )
    for match in _SQL_WHERE.finditer(code):
        predicate = match.group("predicate").strip()
        mutations.append(
            _TextMutation(
                f"offset-{match.start()}-where",
                match.start(),
                match.end(),
                f"WHERE NOT ({predicate}) ",
            )
        )
    for match in _SQL_GROUP_BY.finditer(code):
        keys = [key.strip() for key in match.group("keys").split(",")]
        for key_index in range(len(keys)):
            remaining = [key for index, key in enumerate(keys) if index != key_index]
            replacement = f"GROUP BY {', '.join(remaining)}" if remaining else ""
            mutations.append(
                _TextMutation(
                    f"offset-{match.start()}-group-key-{key_index}",
                    match.start(),
                    match.end(),
                    replacement,
                )
            )
    for match in _SQL_JOIN.finditer(code):
        mutations.append(
            _TextMutation(
                f"offset-{match.start()}-join",
                match.start(),
                match.end(),
                "LEFT JOIN",
            )
        )
    mutations.sort(key=lambda item: (item.start, item.location))
    return mutations


@dataclass(frozen=True, slots=True)
class SqlMutationOperator:
    """SQL の集計・WHERE・GROUP BY・JOIN を変異する。"""

    operator_id: str = "sql-language"

    def generate(self, target: SyntheticMutationTarget) -> MutationGeneration:
        """SQL の全候補を一件ずつ変異し未対応構文を列挙する。"""
        source = _source_for(target, Language.SQL)
        if source is None:
            return MutationGeneration((), ())
        unsupported = [
            _unsupported(
                target,
                self.operator_id,
                f"offset-{match.start()}-{kind}",
                f"未対応の SQL 構文: {kind}",
            )
            for pattern, kind in _SQL_UNSUPPORTED
            for match in pattern.finditer(source.code)
        ]
        if re.match(r"\s*SELECT\b", source.code, re.IGNORECASE) is None:
            unsupported.append(
                _unsupported(
                    target,
                    self.operator_id,
                    "statement-root",
                    "SELECT 以外の SQL 文は未対応",
                )
            )
        mutations = _sql_mutations(source.code)
        mutants = tuple(
            _mutant(
                target,
                self.operator_id,
                index,
                LanguageSource(
                    Language.SQL,
                    source.code[: item.start]
                    + item.replacement
                    + source.code[item.end :],
                ),
            )
            for index, item in enumerate(mutations, start=1)
        )
        return MutationGeneration(mutants, tuple(unsupported))


LANGUAGE_OPERATORS = {
    Language.PYTHON: PythonMutationOperator(),
    Language.TYPESCRIPT: TypeScriptMutationOperator(),
    Language.SQL: SqlMutationOperator(),
}


__all__ = [
    "LANGUAGE_OPERATORS",
    "Language",
    "LanguageSource",
    "PythonMutationOperator",
    "SqlMutationOperator",
    "TypeScriptMutationOperator",
]
