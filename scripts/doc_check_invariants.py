"""文書検査の宣言的不変条件を評価する。"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _load_profile_module() -> Any:
    """隣接する共通プロファイルローダーをファイルパスから読む。"""
    path = Path(__file__).resolve().parent / "doc_check_profile.py"
    loaded = sys.modules.get("check_design_propagation_doc_check_profile")
    loaded_file = getattr(loaded, "__file__", None)
    if (
        loaded is not None
        and loaded_file is not None
        and Path(loaded_file).resolve() == path
    ):
        return loaded
    spec = importlib.util.spec_from_file_location(
        "doc_check_invariants_doc_check_profile",
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"プロファイルローダーを読み込めない: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


doc_check_profile = _load_profile_module()

_HEADING_RE = re.compile(r"^(?P<marks>#{2,6})\s+(?P<title>.+)$")


@dataclass(frozen=True)
class StructuredReason:
    """宣言評価で得た構造化違反理由。

    Attributes:
        violated: 違反を表す場合は ``True``。
        kind: 評価した不変条件kind。
        section: 違反が見つかった節。特定できなければ ``None``。
        expected: 期待した状態。
        actual: 実際に観測した状態。
        token: 違反を生じたliteralまたは識別子。
    """

    violated: bool
    kind: str
    section: str | None
    expected: str | None
    actual: str | None
    token: str | None


@dataclass
class EvaluationContext:
    """同じ欠陥内の宣言間で共有する評価文脈。

    Attributes:
        selected_rows: ``row-selector`` のIDから選択行への対応。
        selected_sections: ``row-selector`` のIDから選択元の節IDへの対応。
    """

    selected_rows: dict[str, str] = field(default_factory=dict)
    selected_sections: dict[str, str] = field(default_factory=dict)


def table_row(section: str, *needles: str) -> str | None:
    """全needleを含む最初のMarkdown表行を返す。"""
    for line in section.splitlines():
        if line.lstrip().startswith("|") and all(needle in line for needle in needles):
            return line
    return None


def table_cells(line: str) -> tuple[str, ...]:
    """Markdown表行を前後空白除去済みのセルへ分割する。"""
    if not line.lstrip().startswith("|"):
        return ()
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def plain_cell(cell: str) -> str:
    """識別子比較のためセルから既存の装飾記号を除く。"""
    return cell.replace("**", "").replace("`", "").strip()


def identified_row(section: str, identifier: str) -> str | None:
    """第1セルが識別子に一致する最初のMarkdown表行を返す。"""
    for line in section.splitlines():
        cells = table_cells(line)
        if cells and plain_cell(cells[0]) == identifier:
            return line
    return None


def element_has_row(section: str, element: str) -> bool:
    """要素全体を含むデータ表行が節内にあるかを返す。"""
    return any(
        element in line
        for line in section.splitlines()
        if table_cells(line)
        and not re.match(r"^\s*[-:]+\s*$", table_cells(line)[0])
    )


def numbered_ids(value: str, prefix: str) -> frozenset[str]:
    """文字列から指定接頭辞の番号付きIDを範囲表記も含めて抽出する。"""
    identifiers = {
        f"{prefix}{number}"
        for number in re.findall(
            rf"(?<![A-Za-z0-9]){re.escape(prefix)}(\d+)", value
        )
    }
    for match in re.finditer(
        rf"{re.escape(prefix)}(\d+)\s*[〜～-]\s*(?:{re.escape(prefix)})?(\d+)",
        value,
    ):
        start, end = (int(number) for number in match.groups())
        identifiers.update(f"{prefix}{number}" for number in range(start, end + 1))
    return frozenset(identifiers)


def element_markers(element: str) -> tuple[str, ...]:
    """要素宣言から本文で照合できる安定IDと意味語を取り出す。"""
    identifier, separator, description = element.partition(":")
    markers: list[str] = []
    if identifier and not identifier.isdecimal():
        markers.append(identifier)
    if separator:
        semantic = description.split("=", 1)[0].strip()
        if semantic:
            markers.append(semantic)
    elif element:
        markers.append(element)
    return tuple(dict.fromkeys(markers))


def semantic_text(value: str) -> str:
    """意味句の照合用にMarkdown装飾・空白・区切り記号を除く。"""
    return re.sub(r"[\s`*_「」『』（）()、，,。．・:：/／—→]+", "", value)


def semantic_part_occurs(row: str, expected: str) -> bool:
    """意味句が直後の否定接尾辞で反転されずに行へ現れるかを返す。"""
    return any(
        not row[match.end() :].startswith("外")
        for match in re.finditer(re.escape(expected), row)
    )


def identifier_set(value: str) -> tuple[str, frozenset[str]] | None:
    """右辺が同一接頭辞のID集合なら接頭辞と全集合を返す。"""
    compact = re.sub(r"\s+", "", value)
    parts = re.split(r"[,、・]", compact)
    matches = [
        re.fullmatch(r"(?P<prefix>[A-Z]+)(?P<number>\d+)", part)
        for part in parts
    ]
    if not parts or any(match is None for match in matches):
        return None
    prefixes = {match.group("prefix") for match in matches if match is not None}
    if len(prefixes) != 1:
        return None
    prefix = prefixes.pop()
    identifiers = frozenset(
        f"{prefix}{match.group('number')}" for match in matches if match is not None
    )
    return prefix, identifiers


def data_table_rows(section: str) -> tuple[str, ...]:
    """節からMarkdown表の区切り行を除く候補行を返す。"""
    return tuple(
        row
        for row in section.splitlines()
        if table_cells(row)
        and not all(
            re.fullmatch(r"\s*[-:]+\s*", cell) for cell in table_cells(row)
        )
    )


def element_table_row_occurs(section: str, element: str) -> bool:
    """``=`` を持つ要素の識別子側と右辺が同じ表行にあるかを返す。"""
    identifier, separator, description = element.partition(":")
    left, equals, right = description.partition("=")
    if not separator or not equals or not left or not right:
        return False

    rows = data_table_rows(section)
    normalized_left = semantic_text(left)
    candidate_rows = [row for row in rows if identifier_occurs(row, identifier)]

    parsed_identifier_set = identifier_set(right)
    if parsed_identifier_set is not None:
        prefix, expected = parsed_identifier_set
        return any(
            normalized_left in semantic_text(row)
            and numbered_ids(row, prefix) == expected
            for row in candidate_rows
        )

    expected_parts = tuple(
        semantic_text(part) for part in right.split("+") if semantic_text(part)
    )
    return bool(expected_parts) and any(
        normalized_left in (normalized_row := semantic_text(row))
        and all(
            semantic_part_occurs(normalized_row, part) for part in expected_parts
        )
        for row in candidate_rows
    )


def identifier_occurs(text: str, identifier: str) -> bool:
    """英数字IDが単独または範囲表記で本文に現れるかを返す。"""
    exact = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(identifier)}(?![A-Za-z0-9-])"
    )
    if exact.search(text) is not None:
        return True
    match = re.fullmatch(r"(?P<prefix>[A-Z]+)(?P<number>\d+)", identifier)
    if match is None:
        return False
    number = int(match.group("number"))
    prefix = re.escape(match.group("prefix"))
    for range_match in re.finditer(
        rf"(?<![A-Za-z0-9]){prefix}(\d+)\s*[〜～-]\s*(?:{prefix})?(\d+)",
        text,
    ):
        start, end = (int(value) for value in range_match.groups())
        if start <= number <= end:
            return True
    return False


def element_occurs(section: str, element: str) -> bool:
    """宣言要素が旧構造判定と同じ意味で節本文に出現するかを返す。"""
    if "=" in element:
        return element_table_row_occurs(section, element)
    identifier, separator, description = element.partition(":")
    if separator and re.fullmatch(
        r"(?:[A-Z]+\d+(?:-[a-z])?|\d+)", identifier
    ) is not None:
        if "+" not in description:
            return identifier_occurs(section, identifier)
        expected_parts = tuple(
            semantic_text(part)
            for part in description.split("+")
            if semantic_text(part)
        )
        return bool(expected_parts) and any(
            identifier_occurs(line, identifier)
            and all(
                semantic_part_occurs(normalized_line, part)
                for part in expected_parts
            )
            for line in section.splitlines()
            if (normalized_line := semantic_text(line))
        )
    return any(
        identifier_occurs(section, marker)
        if re.fullmatch(r"[A-Z]+\d+(?:-[a-z])?", marker)
        else marker in section
        for marker in element_markers(element)
    )


def _relation_field(
    manifest: Mapping[str, Any], relation_id: str, field_name: str
) -> tuple[str, ...]:
    """マニフェスト関係の文字列配列フィールドをfail-closedで取得する。"""
    if relation_id not in manifest:
        raise doc_check_profile.ProfileError(
            f"宣言の relation がマニフェストにありません: {relation_id}"
        )
    relation = manifest[relation_id]
    value = (
        relation.get(field_name)
        if isinstance(relation, Mapping)
        else getattr(relation, field_name, None)
    )
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise doc_check_profile.ProfileError(
            f"relation {relation_id} の field が文字列配列ではありません: {field_name}"
        )
    return tuple(value)


def _declared_items(
    declaration: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[str, ...]:
    """宣言のliteralまたはマニフェスト要素を取得する。"""
    literals = declaration.get("literals")
    if literals is not None:
        return tuple(literals)
    elements = declaration["elements"]
    return _relation_field(manifest, elements["relation"], elements["field"])


def expected_route_elements(
    manifest: Mapping[str, Any],
    relation_id: str,
    *,
    field: str = "source_elements",
    prefix: str = "T",
) -> dict[str, frozenset[str]]:
    """指定関係から経路別の番号付き要素期待集合を導く。"""
    routes: dict[str, frozenset[str]] = {}
    for element in _relation_field(manifest, relation_id, field):
        match = re.match(r"(?P<route>P\d+):[^=]+=(?P<elements>.+)", element)
        if match is not None:
            routes[match.group("route")] = numbered_ids(
                match.group("elements"), prefix
            )
    if not routes:
        raise doc_check_profile.ProfileError(
            f"relation {relation_id} から経路別期待集合を導けません"
        )
    return routes


def route_row_matches(
    section: str,
    route: str,
    expected: frozenset[str],
    *,
    prefix: str = "T",
) -> bool:
    """識別経路行の番号付きID集合が期待集合と完全一致するかを返す。"""
    row = identified_row(section, route)
    return row is not None and numbered_ids(row, prefix) == expected


def _heading_exists(text: str, section_id: str) -> bool:
    """既存検査器と同じ規則で節見出しの存在を判定する。"""
    title_re = re.compile(rf"^{re.escape(section_id)}(?:[.\s(]|$)")
    return any(
        match is not None and title_re.match(match.group("title")) is not None
        for line in text.splitlines()
        if (match := _HEADING_RE.match(line)) is not None
    )


def evaluate_declaration(
    declaration: Mapping[str, Any],
    *,
    text: str,
    manifest: Mapping[str, Any],
    profile: Any,
    sections: Mapping[str, str],
    context: EvaluationContext | None = None,
) -> StructuredReason | None:
    """1件の宣言を評価する。

    Args:
        declaration: kindと引数を持つ宣言。
        text: 検査対象のMarkdown本文。
        manifest: 関係マニフェスト。
        profile: 検証済みプロファイル。
        sections: 事前に解決した節IDと本文の対応。
        context: 同じ欠陥内の宣言間で共有する評価文脈。

    Returns:
        違反時の構造化理由。適合時は ``None``。

    Raises:
        ProfileError: kindが未実装か、宣言または節指定が不正な場合。
    """
    kind = declaration.get("kind")
    if kind not in {
        "forbidden-element",
        "row-selector",
        "row-contains",
        "section-contains",
        "exact-set",
        "element-lookup",
        "row-scoped-forbidden",
        "absent-section",
    }:
        raise doc_check_profile.ProfileError(f"未実装の kind です: {kind!r}")
    doc_check_profile.validate_declaration(declaration)

    if kind == "absent-section":
        section_id = declaration["section"]
        if not _heading_exists(text, section_id):
            return None
        return StructuredReason(
            violated=True,
            kind=kind,
            section=section_id,
            expected="節が存在しない",
            actual="節が存在する",
            token=None,
        )
    if kind == "row-selector":
        section_id = declaration["section"]
        section_text = sections.get(section_id)
        if section_text is None:
            raise doc_check_profile.ProfileError(
                f"row-selector の節を解決できません: {section_id}"
            )
        keys = declaration["keys"]
        mode = declaration["mode"]
        row = (
            table_row(section_text, *keys)
            if mode == "needle"
            else identified_row(section_text, keys[0])
        )
        if row is None:
            expected = (
                f"{'・'.join(keys)} をすべて含む表行"
                if mode == "needle"
                else f"第1セルが {keys[0]} の表行"
            )
            return StructuredReason(
                violated=True,
                kind=kind,
                section=section_id,
                expected=expected,
                actual=None,
                token=None,
            )
        if context is not None:
            context.selected_rows[declaration["id"]] = row
            context.selected_sections[declaration["id"]] = section_id
        return None
    if kind == "row-contains":
        row_id = declaration["row"]
        if context is None or row_id not in context.selected_rows:
            raise doc_check_profile.ProfileError(
                f"row-contains の参照先 row が未定義です: {row_id}"
            )
        section_id = context.selected_sections.get(row_id)
        if section_id is None:
            raise doc_check_profile.ProfileError(
                f"row-contains の参照先 row の節が未定義です: {row_id}"
            )
        row = context.selected_rows[row_id]
        for item in _declared_items(declaration, manifest):
            if item not in row:
                return StructuredReason(
                    violated=True,
                    kind=kind,
                    section=section_id,
                    expected=item,
                    actual=row,
                    token=item,
                )
        return None
    if kind == "row-scoped-forbidden":
        row_id = declaration["row"]
        if context is None or row_id not in context.selected_rows:
            raise doc_check_profile.ProfileError(
                f"row-scoped-forbidden の参照先 row が未定義です: {row_id}"
            )
        section_id = context.selected_sections.get(row_id)
        if section_id is None:
            raise doc_check_profile.ProfileError(
                f"row-scoped-forbidden の参照先 row の節が未定義です: {row_id}"
            )
        row = context.selected_rows[row_id]
        for literal in declaration["literals"]:
            if literal in row:
                return StructuredReason(
                    violated=True,
                    kind=kind,
                    section=section_id,
                    expected=f"{literal} が選択行に無い",
                    actual=row,
                    token=literal,
                )
        return None
    if kind == "section-contains":
        requested_sections = declaration["sections"]
        missing = set(requested_sections) - set(sections)
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise doc_check_profile.ProfileError(
                f"section-contains の節を解決できません: {missing_text}"
            )
        mode = declaration["as"]
        for section_id in requested_sections:
            section_text = sections.get(section_id)
            if section_text is None:
                raise doc_check_profile.ProfileError(
                    f"section-contains の節を解決できません: {section_id}"
                )
            for item in _declared_items(declaration, manifest):
                key = (
                    item.partition(":")[0]
                    if declaration.get("key") == "id-part"
                    else item
                )
                if mode == "text":
                    matched = item in section_text
                elif mode == "identifier":
                    matched = element_occurs(section_text, item)
                elif mode == "identified-row":
                    matched = identified_row(section_text, key) is not None
                else:
                    matched = element_has_row(section_text, item)
                if not matched:
                    token = item.partition(":")[0] if ":" in item else item
                    return StructuredReason(
                        violated=True,
                        kind=kind,
                        section=section_id,
                        expected=token,
                        actual=f"{token} が節 {section_id} に無い",
                        token=token,
                    )
        return None
    if kind == "exact-set":
        relation_id = declaration["relation"]
        prefix = declaration.get("prefix", "T")
        routes = expected_route_elements(
            manifest,
            relation_id,
            field=declaration.get("field", "source_elements"),
            prefix=prefix,
        )
        requested_routes = declaration["routes"]
        if isinstance(requested_routes, Mapping):
            containing = requested_routes["containing"]
            route_ids = tuple(
                route for route, elements in routes.items() if containing in elements
            )
            if not route_ids:
                raise doc_check_profile.ProfileError(
                    f"relation {relation_id} に {containing} を含む経路がありません"
                )
        else:
            route_ids = tuple(requested_routes)
        unknown_routes = set(route_ids) - set(routes)
        if unknown_routes:
            unknown_text = ", ".join(sorted(unknown_routes))
            raise doc_check_profile.ProfileError(
                f"relation {relation_id} に宣言経路がありません: {unknown_text}"
            )

        row_id = declaration.get("row")
        if row_id is not None:
            if context is None or row_id not in context.selected_rows:
                raise doc_check_profile.ProfileError(
                    f"exact-set の参照先 row が未定義です: {row_id}"
                )
            section_id = context.selected_sections.get(row_id)
            if section_id is None:
                raise doc_check_profile.ProfileError(
                    f"exact-set の参照先 row の節が未定義です: {row_id}"
                )
            targets = ((section_id, context.selected_rows[row_id]),)
        else:
            requested_sections = declaration["sections"]
            missing = set(requested_sections) - set(sections)
            if missing:
                missing_text = ", ".join(sorted(missing))
                raise doc_check_profile.ProfileError(
                    f"exact-set の節を解決できません: {missing_text}"
                )
            targets = tuple(
                (section_id, sections[section_id])
                for section_id in requested_sections
            )

        for section_id, target in targets:
            for route in route_ids:
                row = target if row_id is not None else identified_row(target, route)
                actual = frozenset() if row is None else numbered_ids(row, prefix)
                expected = routes[route]
                if actual != expected:
                    expected_text = f"{route}: {','.join(sorted(expected))}"
                    actual_text = None if row is None else row
                    return StructuredReason(
                        violated=True,
                        kind=kind,
                        section=section_id,
                        expected=expected_text,
                        actual=actual_text,
                        token=route,
                    )
        return None
    if kind == "element-lookup":
        relation_id = declaration["relation"]
        prefix = declaration["prefix"]
        elements = tuple(
            element
            for element in _relation_field(
                manifest, relation_id, "source_elements"
            )
            if element.startswith(prefix)
        )
        if len(elements) != 1:
            raise doc_check_profile.ProfileError(
                f"relation {relation_id} の prefix {prefix!r} は"
                f"1要素を特定できません: {len(elements)}件"
            )
        _, separator, semantic = elements[0].partition(":")
        if not separator or not semantic:
            raise doc_check_profile.ProfileError(
                f"relation {relation_id} の要素に意味部がありません: {elements[0]}"
            )
        section_id = declaration["section"]
        section_text = sections.get(section_id)
        if section_text is None:
            raise doc_check_profile.ProfileError(
                f"element-lookup の節を解決できません: {section_id}"
            )
        row = identified_row(section_text, declaration["row_identifier"])
        if row is None or semantic not in row:
            return StructuredReason(
                violated=True,
                kind=kind,
                section=section_id,
                expected=semantic,
                actual=row,
                token=prefix,
            )
        return None
    del profile

    requested_sections = declaration.get("sections")
    if requested_sections is None:
        selected_sections = tuple(sections.items()) or ((None, text),)
    else:
        missing = set(requested_sections) - set(sections)
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise doc_check_profile.ProfileError(
                f"forbidden-element の節を解決できません: {missing_text}"
            )
        selected_sections = tuple(
            (section_id, sections[section_id]) for section_id in requested_sections
        )

    for section_id, section_text in selected_sections:
        for literal in declaration["literals"]:
            if literal in section_text:
                return StructuredReason(
                    violated=True,
                    kind=kind,
                    section=section_id,
                    expected="literal が対象範囲に無い",
                    actual=f"禁止literalが残存: {literal}",
                    token=literal,
                )
    return None
