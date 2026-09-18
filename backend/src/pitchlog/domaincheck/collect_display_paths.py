"""Schema 閉包と製品の表示呼出箇所を独立収集する。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, NoReturn, Sequence

from pitchlog.domaincheck.cli import (
    EXIT_CONFORMING,
    EXIT_INDETERMINATE,
    CheckerExecutionError,
    canonical_json,
    read_json,
)

_CODE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".vue"})
_IMPORT_FROM = re.compile(
    r"\bimport\s+(?P<bindings>[^;]*?)\s+from\s*"
    r"(?P<quote>['\"])(?P<path>[^'\"]+)(?P=quote)",
    re.MULTILINE,
)
_EXPORTED_FUNCTION = re.compile(
    r"\bexport\s+(?:async\s+)?function\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\("
)
_EXPORTED_CONSTANT = re.compile(
    r"\bexport\s+const\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*="
)
_DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(\s*(?P<argument>[^)]*)\)")
_DYNAMIC_DISPATCH = re.compile(
    r"\b(?P<base>[A-Za-z_$][A-Za-z0-9_$]*)\s*"
    r"\[\s*(?P<key>[^\]]+)\]\s*\("
)
_VUE_INTERPOLATION = re.compile(r"\{\{(?P<expression>.*?)\}\}", re.DOTALL)
_BUILTIN_DISPLAY_CALLS = {
    "language-stringification": re.compile(r"\bString\s*\([^)]*\)"),
    "fixed-decimal-call": re.compile(r"\.\s*toFixed\s*\([^)]*\)"),
    "locale-number-call": re.compile(r"\.\s*toLocaleString\s*\([^)]*\)"),
    "intl-number-format": re.compile(r"\bIntl\.NumberFormat\s*\([^)]*\)"),
}


class _ArgumentParser(argparse.ArgumentParser):
    """引数不備を判定不能へ変換するパーサ。"""

    def error(self, message: str) -> NoReturn:
        """引数エラーを送出する。"""
        raise CheckerExecutionError(message)


@dataclass(frozen=True, slots=True)
class _FormatterDefinition:
    """静的に発見した formatter 定義を表す。"""

    path: Path
    symbol: str


@dataclass(slots=True)
class _CollectionState:
    """1 回の表示経路収集で蓄積する状態。"""

    root: Path
    frontend: Path
    definitions: list[_FormatterDefinition] = field(default_factory=list)
    calls: list[dict[str, object]] = field(default_factory=list)
    unresolved: list[dict[str, object]] = field(default_factory=list)

    def relative(self, path: Path) -> str:
        """パスをリポジトリ相対の POSIX 表記へ変換する。"""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError as error:
            raise CheckerExecutionError(
                f"収集対象がリポジトリ外を指している: {path}"
            ) from error

    def add_call(
        self,
        path: Path,
        kind: str,
        expression: str,
        occurrence: int,
        *,
        symbol: str = "",
        formatter: str = "",
    ) -> None:
        """表示呼出箇所を追加する。"""
        self.calls.append(
            {
                "path": self.relative(path),
                "kind": kind,
                "expression": _compact(expression),
                "occurrence": occurrence,
                "symbol": symbol,
                "formatter": formatter,
            }
        )

    def add_unresolved(
        self,
        path: Path,
        construct: str,
        expression: str,
        reason: str,
    ) -> None:
        """静的に解決できない表示経路を追加する。"""
        self.unresolved.append(
            {
                "path": self.relative(path),
                "construct": construct,
                "expression": _compact(expression),
                "reason": reason,
            }
        )


def _compact(value: str) -> str:
    """機械可読な表示用に空白と長さを正規化する。"""
    return " ".join(value.split())[:160]


def _read_text(path: Path) -> str:
    """UTF-8 の監査対象を読み込む。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CheckerExecutionError(
            f"監査対象を読めない: {path}: {error}"
        ) from error


def _mapping(value: object, label: str) -> dict[str, object]:
    """文字列キーの JSON object を返す。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckerExecutionError(f"{label}は JSON object でなければならない")
    return value


def _schema_document(path: Path) -> dict[str, object]:
    """Schema を JSON object として読み込む。"""
    return _mapping(read_json(path), str(path))


def _resolve_ref(document: Mapping[str, object], reference: str) -> object:
    """同じ文書内の JSON Pointer を解決する。"""
    if not reference.startswith("#/"):
        raise CheckerExecutionError(f"外部または不正な $ref: {reference}")
    node: object = document
    try:
        for raw_token in reference[2:].split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict):
                raise KeyError(token)
            node = node[token]
    except KeyError as error:
        raise CheckerExecutionError(f"解決できない $ref: {reference}") from error
    return node


def _dereference(
    document: Mapping[str, object], node: object, seen: frozenset[str] = frozenset()
) -> dict[str, object]:
    """参照を辿って schema object を返す。"""
    mapping = _mapping(node, "schema node")
    reference = mapping.get("$ref")
    if reference is None:
        return mapping
    if not isinstance(reference, str) or reference in seen:
        raise CheckerExecutionError(f"循環または不正な $ref: {reference}")
    return _dereference(
        document,
        _resolve_ref(document, reference),
        seen | {reference},
    )


def _property(
    document: Mapping[str, object], node: object, name: str
) -> dict[str, object]:
    """参照解決後の object schema からプロパティを返す。"""
    mapping = _dereference(document, node)
    properties = _mapping(mapping.get("properties"), "schema properties")
    if name not in properties:
        raise CheckerExecutionError(f"schema property が存在しない: {name}")
    return _mapping(properties[name], f"schema property {name}")


def _finite_strings(
    document: Mapping[str, object],
    node: object,
    seen: frozenset[str] = frozenset(),
) -> set[str] | None:
    """Schema が受理する有限文字列集合を導出する。"""
    mapping = _mapping(node, "finite string schema")
    reference = mapping.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or reference in seen:
            return None
        return _finite_strings(
            document,
            _resolve_ref(document, reference),
            seen | {reference},
        )
    constant = mapping.get("const")
    if isinstance(constant, str):
        return {constant}
    enum = mapping.get("enum")
    if isinstance(enum, list) and enum and all(isinstance(item, str) for item in enum):
        return set(enum)
    for keyword in ("oneOf", "anyOf"):
        alternatives = mapping.get(keyword)
        if not isinstance(alternatives, list) or not alternatives:
            continue
        result: set[str] = set()
        for alternative in alternatives:
            values = _finite_strings(document, alternative, seen)
            if values is None:
                return None
            result.update(values)
        return result
    return None


def _union_kind_values(
    document: Mapping[str, object], definition_name: str
) -> set[str]:
    """OneOf の各 object が持つ `kind` の有限集合を返す。"""
    definitions = _mapping(document.get("$defs"), "$defs")
    return _union_kind_values_from_schema(document, definitions.get(definition_name))


def _union_kind_values_from_schema(
    document: Mapping[str, object], node: object
) -> set[str]:
    """指定 schema の OneOf が持つ `kind` の有限集合を返す。"""
    union = _dereference(document, node)
    alternatives = union.get("oneOf")
    if not isinstance(alternatives, list) or not alternatives:
        return set()
    result: set[str] = set()
    for alternative in alternatives:
        resolved = _dereference(document, alternative)
        if resolved.get("type") == "null":
            continue
        try:
            kind = _property(document, resolved, "kind")
        except CheckerExecutionError:
            continue
        values = _finite_strings(document, kind)
        if values is not None:
            result.update(values)
    return result


def _model_target_fields(
    model: Mapping[str, object],
) -> tuple[set[str], list[dict[str, str]]]:
    """宣言モデルの構造化 selector から対象フィールド集合を導出する。"""
    metadata = _mapping(model.get("x-pitchlog"), "x-pitchlog")
    selectors = metadata.get("targetFieldSelectors")
    if not isinstance(selectors, list) or not selectors:
        return set(), [
            {
                "construct": "schema-closure",
                "expression": "#/x-pitchlog/targetFieldSelectors",
                "reason": "利用者可視の数値出力を選ぶ宣言が空である",
            }
        ]

    expected_keys = {
        "id",
        "collection",
        "itemSchema",
        "fieldIdProperty",
        "visibilityProperty",
        "visibleValue",
        "typeKindProperty",
        "numericTypeKinds",
    }
    target_fields: set[str] = set()
    issues: list[dict[str, str]] = []
    for index, raw_selector in enumerate(selectors):
        expression = f"#/x-pitchlog/targetFieldSelectors/{index}"
        try:
            selector = _mapping(raw_selector, expression)
            if set(selector) != expected_keys:
                raise CheckerExecutionError("selector のキー集合が閉じていない")
            text_keys = expected_keys - {"numericTypeKinds"}
            if not all(isinstance(selector.get(key), str) for key in text_keys):
                raise CheckerExecutionError("selector の文字列フィールドが不正である")
            numeric_kinds = selector["numericTypeKinds"]
            if (
                not isinstance(numeric_kinds, list)
                or not numeric_kinds
                or not all(isinstance(kind, str) for kind in numeric_kinds)
                or len(set(numeric_kinds)) != len(numeric_kinds)
            ):
                raise CheckerExecutionError("numericTypeKinds が有限集合でない")

            collection_ref = str(selector["collection"])
            collection = _dereference(model, _resolve_ref(model, collection_ref))
            if collection.get("type") != "array" or "items" not in collection:
                raise CheckerExecutionError("collection が配列 schema でない")
            item_ref = str(selector["itemSchema"])
            item_schema = _dereference(model, _resolve_ref(model, item_ref))
            collection_item_schema = _dereference(model, collection["items"])
            if collection_item_schema != item_schema:
                raise CheckerExecutionError(
                    "collection.items と itemSchema が同じ型を指していない"
                )
            _property(model, item_schema, str(selector["fieldIdProperty"]))
            visibility = _property(
                model, item_schema, str(selector["visibilityProperty"])
            )
            visible_values = _finite_strings(model, visibility)
            if visible_values is None or selector["visibleValue"] not in visible_values:
                raise CheckerExecutionError("visibility の有限集合と選択値が整合しない")
            type_path = str(selector["typeKindProperty"]).split(".")
            if type_path != ["type", "kind"]:
                raise CheckerExecutionError("型判定経路が type.kind でない")
            field_type = _property(model, item_schema, type_path[0])
            declared_kinds = _union_kind_values_from_schema(model, field_type)
            if not set(numeric_kinds) <= declared_kinds:
                raise CheckerExecutionError("数値型集合が出力型の閉包に含まれない")
            identifier = str(selector["id"])
            if identifier in target_fields:
                raise CheckerExecutionError("selector id が重複している")
            target_fields.add(identifier)
        except CheckerExecutionError as error:
            issues.append(
                {
                    "construct": "schema-closure",
                    "expression": expression,
                    "reason": str(error),
                }
            )
    return target_fields, issues


def _resolved_name_is_structured(document: Mapping[str, object]) -> bool:
    """語彙 snapshot の ID 解決型が閉じていれば `True` を返す。"""
    definitions = _mapping(document.get("$defs"), "$defs")
    raw = definitions.get("ResolvedName")
    if raw is None:
        return False
    resolved = _dereference(document, raw)
    required = resolved.get("required")
    return (
        resolved.get("type") == "object"
        and resolved.get("additionalProperties") is False
        and isinstance(required, list)
        and {"kind", "vocabularyId", "entityId"} <= set(required)
    )


def _named_schema_paths(document: object, token: str) -> list[str]:
    """型定義内で指定語を名前に含むノードの JSON Pointer を返す。"""
    paths: list[str] = []

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}/{key}"
                if token in key.casefold():
                    paths.append(child_path)
                visit(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}/{index}")

    mapping = _mapping(document, "schema document")
    for root_name in ("properties", "$defs"):
        root_node = mapping.get(root_name)
        if root_node is not None:
            visit(root_node, f"#/{root_name}")
    return sorted(set(paths))


def derive_schema_closure(
    model: Mapping[str, object], vocabulary: Mapping[str, object]
) -> tuple[dict[str, object], list[dict[str, str]]]:
    """両 schema から利用者可視数値フィールドの閉包を導出する。

    Args:
        model: 宣言モデルの JSON Schema。
        vocabulary: 表示語彙の JSON Schema。

    Returns:
        閉包と、有限集合を得られない場合の解析不能理由。
    """
    metadata = model.get("x-pitchlog")
    if isinstance(metadata, dict) and "targetFieldSelectors" in metadata:
        target_fields, issues = _model_target_fields(model)
        target_root = "#/x-pitchlog/targetFieldSelectors"
        root_name = "modelRoot"
        rule = (
            "出力配列・可視性・型 kind の schema を辿り、"
            "利用者可視数値フィールドの構造的 selector を採用する"
        )
    else:
        display_bindings = _property(model, model, "displayBindings")
        items = display_bindings.get("items")
        if items is None:
            raise CheckerExecutionError("displayBindings.items が存在しない")
        display_item = _property(model, items, "displayItem")
        finite_fields = _finite_strings(model, display_item)
        target_fields = finite_fields or set()
        target_root = "#/properties/displayBindings/items/displayItem"
        root_name = "manifestRoot"
        rule = "const / enum と oneOf の参照閉包だけを有限集合として採用する"
        issues = []
        if finite_fields is None or not finite_fields:
            issues.append(
                {
                    "construct": "schema-closure",
                    "expression": target_root,
                    "reason": "表示項目が有限の const / enum 閉包でない",
                }
            )
    numeric_forms = _union_kind_values(vocabulary, "NumericValue")
    primitives = _union_kind_values(vocabulary, "NumericPrimitive")
    atom_sources = _union_kind_values(vocabulary, "DisplayAtomSource")

    closed_sets = {
        "numericValueForms": sorted(numeric_forms),
        "numericPrimitives": sorted(primitives),
        "displayAtomSources": sorted(atom_sources),
    }
    for name, values in closed_sets.items():
        if not values:
            issues.append(
                {
                    "construct": "schema-closure",
                    "expression": f"vocabulary.$defs.{name}",
                    "reason": "表示語彙の有限閉包を導出できない",
                }
            )
    closure = {
        "derivation": {
            root_name: target_root,
            "vocabularyRoots": [
                "#/$defs/NumericValue",
                "#/$defs/NumericPrimitive",
                "#/$defs/DisplayAtomSource",
            ],
            "rule": rule,
        },
        "complete": not issues,
        "targetFields": sorted(target_fields),
        **closed_sets,
    }
    return closure, issues


def _trigger_one_materials(
    model: Mapping[str, object],
    vocabulary: Mapping[str, object],
    closure: Mapping[str, object],
) -> dict[str, object]:
    """PO が型語彙の表現可能性を判断する材料を返す。"""
    target_fields = closure.get("targetFields")
    has_targets = isinstance(target_fields, list) and bool(target_fields)
    history_evidence = _named_schema_paths(model, "history")
    rule_evidence = _named_schema_paths(model, "rules")
    snapshot_evidence = [
        *_named_schema_paths(model, "vocabularysnapshot"),
        *_named_schema_paths(vocabulary, "resolvedname"),
    ]
    primitives = closure.get("numericPrimitives")
    forms = closure.get("numericValueForms")
    sources = closure.get("displayAtomSources")
    derivation = closure.get("derivation")
    evidence_root = "#/properties/displayBindings/items/displayItem"
    if isinstance(derivation, dict):
        root = derivation.get("modelRoot", derivation.get("manifestRoot"))
        if isinstance(root, str):
            evidence_root = root
    return {
        "judge": "山田正輝",
        "status": "pending-po-evaluation",
        "items": [
            {
                "construct": "scoreboard-all-fields",
                "representable": has_targets,
                "evidence": [evidence_root],
            },
            {
                "construct": "vocabulary-snapshot-map",
                "representable": _resolved_name_is_structured(vocabulary),
                "evidence": snapshot_evidence,
            },
            {
                "construct": "history-stack",
                "representable": bool(history_evidence),
                "evidence": history_evidence,
            },
            {
                "construct": "rule-arrays",
                "representable": bool(rule_evidence),
                "evidence": rule_evidence,
            },
            {
                "construct": "numeric-display-type-vocabulary",
                "representable": all(
                    isinstance(values, list) and bool(values)
                    for values in (primitives, forms, sources)
                ),
                "evidence": [
                    "#/$defs/NumericValue",
                    "#/$defs/NumericPrimitive",
                    "#/$defs/DisplayAtomSource",
                ],
            },
        ],
    }


def _product_files(frontend: Path) -> list[Path]:
    """テスト支援コードを除く frontend 製品コードを列挙する。"""
    files: list[Path] = []
    for path in frontend.rglob("*"):
        if not path.is_file() or path.suffix not in _CODE_SUFFIXES:
            continue
        relative = path.relative_to(frontend)
        if "testing" in relative.parts:
            continue
        if ".spec." in path.name or ".test." in path.name:
            continue
        files.append(path.resolve())
    return sorted(files)


def _is_formatter_module(path: Path) -> bool:
    """ファイル名が formatter の役割を明示していれば `True` を返す。"""
    return "format" in path.stem.casefold()


def _collect_definitions(
    state: _CollectionState, files: Sequence[Path], sources: Mapping[Path, str]
) -> dict[Path, set[str]]:
    """Formatter module の export を定義集合として収集する。"""
    by_path: dict[Path, set[str]] = {}
    for path in files:
        if not _is_formatter_module(path):
            continue
        names = {
            match.group("name")
            for pattern in (_EXPORTED_FUNCTION, _EXPORTED_CONSTANT)
            for match in pattern.finditer(sources[path])
        }
        by_path[path] = names
        state.definitions.extend(
            _FormatterDefinition(path=path, symbol=name) for name in sorted(names)
        )
    return by_path


def _resolve_module(source: Path, specifier: str, frontend: Path) -> Path | None:
    """相対 module specifier を frontend 内の実ファイルへ解決する。"""
    if not specifier.startswith("."):
        return None
    base = (source.parent / specifier).resolve()
    candidates = [
        base,
        *(base.with_suffix(suffix) for suffix in _CODE_SUFFIXES),
        *(base / f"index{suffix}" for suffix in _CODE_SUFFIXES),
    ]
    matches: list[Path] = []
    for candidate in candidates:
        try:
            candidate.relative_to(frontend)
        except ValueError:
            continue
        if candidate.is_file() and candidate not in matches:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _imported_names(bindings: str) -> dict[str, str]:
    """ES module import のローカル名と export 名を返す。"""
    result: dict[str, str] = {}
    named_match = re.search(r"\{(?P<names>[^}]*)\}", bindings, re.DOTALL)
    if named_match is not None:
        for item in named_match.group("names").split(","):
            parts = item.strip().split()
            if not parts:
                continue
            exported = parts[0]
            local = parts[2] if len(parts) == 3 and parts[1] == "as" else exported
            result[local] = exported
    namespace = re.search(
        r"\*\s+as\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)", bindings
    )
    if namespace is not None:
        result[namespace.group("name")] = "*"
    default_part = bindings.split(",", maxsplit=1)[0].strip()
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", default_part):
        result[default_part] = "default"
    return result


def _collect_imported_calls(
    state: _CollectionState,
    path: Path,
    source: str,
    definitions: Mapping[Path, set[str]],
) -> None:
    """Formatter module から静的 import した関数呼出しを収集する。"""
    for import_match in _IMPORT_FROM.finditer(source):
        specifier = import_match.group("path")
        target = _resolve_module(path, specifier, state.frontend)
        looks_like_formatter = "format" in Path(specifier).stem.casefold()
        if target is None:
            if looks_like_formatter:
                state.add_unresolved(
                    path,
                    "formatter-import",
                    import_match.group(0),
                    "Formatter module を実ファイルへ一意に解決できない",
                )
            continue
        exported = definitions.get(target)
        if exported is None:
            continue
        for local_name, exported_name in _imported_names(
            import_match.group("bindings")
        ).items():
            if exported_name == "*":
                state.add_unresolved(
                    path,
                    "formatter-namespace",
                    import_match.group(0),
                    "Namespace 経由の呼出し先を一意に確定できない",
                )
                continue
            if exported_name != "default" and exported_name not in exported:
                state.add_unresolved(
                    path,
                    "formatter-import",
                    import_match.group(0),
                    "宣言された export が formatter module に存在しない",
                )
                continue
            call_pattern = re.compile(rf"\b{re.escape(local_name)}\s*\(")
            for occurrence, match in enumerate(call_pattern.finditer(source), start=1):
                state.add_call(
                    path,
                    "formatter-call",
                    match.group(0),
                    occurrence,
                    symbol=exported_name,
                    formatter=state.relative(target),
                )


def _collect_file_paths(
    state: _CollectionState,
    path: Path,
    source: str,
    definitions: Mapping[Path, set[str]],
) -> None:
    """1 製品ファイルの表示経路と解析不能構文を収集する。"""
    _collect_imported_calls(state, path, source, definitions)
    if path.suffix == ".vue":
        matches = list(_VUE_INTERPOLATION.finditer(source))
        if source.count("{{") != len(matches):
            state.add_unresolved(
                path,
                "vue-interpolation",
                "{{",
                "閉じていない interpolation がある",
            )
        for occurrence, match in enumerate(matches, start=1):
            state.add_call(
                path,
                "vue-interpolation",
                match.group("expression"),
                occurrence,
            )
    for kind, pattern in _BUILTIN_DISPLAY_CALLS.items():
        for occurrence, match in enumerate(pattern.finditer(source), start=1):
            state.add_call(path, kind, match.group(0), occurrence)
    for match in _DYNAMIC_IMPORT.finditer(source):
        argument = match.group("argument").strip()
        if not re.fullmatch(r"(['\"])[^'\"]+\1", argument):
            state.add_unresolved(
                path,
                "dynamic-import",
                match.group(0),
                "Import 先が静的文字列でない",
            )
    for match in _DYNAMIC_DISPATCH.finditer(source):
        state.add_unresolved(
            path,
            "dynamic-call",
            match.group(0),
            "Bracket 記法の呼出し先を静的に確定できない",
        )


def collect_display_paths(
    root: Path,
    frontend: Path,
    model_path: Path,
    vocabulary_path: Path,
) -> dict[str, object]:
    """Schema 閉包と frontend の表示呼出箇所を独立導出する。

    Args:
        root: リポジトリルート。
        frontend: 製品 frontend の source root。
        model_path: 宣言モデル schema のパス。
        vocabulary_path: 表示語彙 schema のパス。

    Returns:
        Schema 閉包、表示呼出箇所、解析不能、走査回数。

    Raises:
        CheckerExecutionError: 入力を読み取れないか schema が不正な場合。
    """
    resolved_root = root.resolve()
    resolved_frontend = frontend.resolve()
    resolved_model = model_path.resolve()
    resolved_vocabulary = vocabulary_path.resolve()
    if not resolved_frontend.is_dir():
        raise CheckerExecutionError(f"frontend source root を読めない: {frontend}")
    state = _CollectionState(root=resolved_root, frontend=resolved_frontend)
    for path in (resolved_frontend, resolved_model, resolved_vocabulary):
        state.relative(path)
    model = _schema_document(resolved_model)
    vocabulary = _schema_document(resolved_vocabulary)
    closure, closure_issues = derive_schema_closure(model, vocabulary)
    files = _product_files(resolved_frontend)
    sources = {path: _read_text(path) for path in files}
    definitions = _collect_definitions(state, files, sources)
    for path in files:
        _collect_file_paths(state, path, sources[path], definitions)

    schema_unresolved = [
        {
            "path": state.relative(resolved_model),
            **issue,
        }
        for issue in closure_issues
    ]
    attempts_by_kind = {
        "frontendFiles": len(files),
        "schemaDocuments": 2,
    }
    return {
        "schemaVersion": 1,
        "attempts": sum(attempts_by_kind.values()),
        "attemptsByKind": attempts_by_kind,
        "schemaClosure": closure,
        "trigger1AssessmentMaterials": _trigger_one_materials(
            model, vocabulary, closure
        ),
        "formatterDefinitions": [
            {
                "path": state.relative(definition.path),
                "symbol": definition.symbol,
            }
            for definition in sorted(
                state.definitions,
                key=lambda item: (state.relative(item.path), item.symbol),
            )
        ],
        "displayCalls": sorted(
            state.calls,
            key=lambda row: (
                str(row["path"]),
                str(row["kind"]),
                str(row["occurrence"]),
            ),
        ),
        "unresolved": sorted(
            [*schema_unresolved, *state.unresolved],
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
    parser.add_argument("--frontend", type=Path, default=Path("frontend/src"))
    schema_group = parser.add_mutually_exclusive_group()
    schema_group.add_argument(
        "--model-schema",
        type=Path,
        default=Path("backend/domain/model.schema.json"),
    )
    schema_group.add_argument(
        "--manifest-schema",
        type=Path,
        default=None,
        help="旧形式の合成 fixture を検査する互換引数",
    )
    parser.add_argument(
        "--vocabulary-schema",
        type=Path,
        default=Path("backend/domain/vocabulary.schema.json"),
    )
    return parser


def _resolve_path(root: Path, path: Path) -> Path:
    """相対パスをリポジトリルート基準で解決する。"""
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main(argv: Sequence[str] | None = None) -> int:
    """表示経路を列挙し、解析不能があれば exit 2 を返す。

    Args:
        argv: CLI 引数。`None` ならプロセス引数を使う。

    Returns:
        収集完了は 0、判定不能は 2。
    """
    try:
        arguments = _build_parser().parse_args(argv)
        root = arguments.root.resolve()
        schema_path = arguments.manifest_schema or arguments.model_schema
        result = collect_display_paths(
            root,
            _resolve_path(root, arguments.frontend),
            _resolve_path(root, schema_path),
            _resolve_path(root, arguments.vocabulary_schema),
        )
        print(canonical_json(result), end="")
        unresolved = result["unresolved"]
        if isinstance(unresolved, list) and unresolved:
            print(
                f"判定不能: 静的に解決できない表示経路が {len(unresolved)} 件ある",
                file=sys.stderr,
            )
            return EXIT_INDETERMINATE
    except CheckerExecutionError as error:
        print(f"判定不能: {error}", file=sys.stderr)
        return EXIT_INDETERMINATE
    return EXIT_CONFORMING


if __name__ == "__main__":
    raise SystemExit(main())
