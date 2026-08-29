"""同期プロトコル設計の表間伝播、参照、残存欠陥を検査する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

CHECK_IDS = (
    "manifest-consistency",
    "element-coverage",
    "enum-propagation",
    "condition-key",
    "route-matrix",
    "scope-declaration",
    "order-use",
    "citation-format",
    "noncanonical-reference",
    "link-target",
    "emphasis",
    "draft-metadata",
)
CHECK_ID_SET = frozenset(CHECK_IDS)
GLOBAL_CHECK_IDS = frozenset(
    {
        "manifest-consistency",
        "citation-format",
        "noncanonical-reference",
        "link-target",
    }
)
DEFAULT_DOCUMENT = Path("docs/design/sync-protocol.md")
DEFAULT_DEFECTS = Path("scripts/design_relations/defects.json")
DEFAULT_MANIFEST = Path("scripts/design_relations/sync-protocol.json")

HEADING_RE = re.compile(r"^(?P<marks>#{2,6})\s+(?P<title>.+)$")
MARKDOWN_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)"
)
REQ_LINE_CITATION_RE = re.compile(r"\bREQ:\d+\b")
PATH_LINE_CITATION_RE = re.compile(r"[^\s`\[\]()]+\.md:\d+\b")
BARE_LINE_CITATION_RE = re.compile(r"(?<![A-Za-z0-9_]):\d+\b")
NONCANONICAL_PATH_RE = re.compile(r"(?:docs/features/|\.\./features/)")


class CheckError(Exception):
    """入力・セレクタ・oracle の不正を表す。"""


@dataclass(frozen=True)
class ManifestRelation:
    """関係マニフェストの1関係を表す。

    Attributes:
        id: 関係ID。
        source_table: 正本となる表の識別子。
        targets: 伝播先となる表の完全集合。
        compare_key: 表間で比較する構造。
        source_elements: 正本の表に存在する要素IDの全集合。
        expected_elements: 伝播先ごとの要素IDの期待部分集合。
    """

    id: str
    source_table: str
    targets: tuple[str, ...]
    compare_key: str
    source_elements: tuple[str, ...]
    expected_elements: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class Invariant:
    """機械欠陥に固定された不変条件を表す。

    Attributes:
        positive: 検査ロジックが満たす肯定条件の仕様。
        forbidden: スコープ内で禁止するliteral部分文字列。
        scope: 評価対象の節。
        mapping: 表間対応の仕様。対応なしなら ``None``。
    """

    positive: str
    forbidden: tuple[str, ...]
    scope: str
    mapping: str | None


@dataclass(frozen=True)
class Defect:
    """欠陥oracleの1件を表す。

    Attributes:
        id: 欠陥ID。
        detection: ``machine`` または ``human``。
        check: 対応する検査ID。人間照合では ``None``。
        invariant: 機械不変条件。人間照合では ``None``。
    """

    id: str
    detection: str
    check: str | None
    invariant: Invariant | None


@dataclass(frozen=True)
class Finding:
    """1件の検査違反を表す。

    Attributes:
        identifier: 欠陥ID、または欠陥IDを持たない検査ID。
        check: 検出した検査ID。
        reason: 違反理由。
    """

    identifier: str
    check: str
    reason: str


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CheckError(f"JSONを読めない: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise CheckError(f"JSONが不正: {path}: {error}") from error


def _as_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise CheckError(f"{field} は文字列でなければならない")
    return value


def _as_string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CheckError(f"{field} は文字列配列でなければならない")
    return tuple(value)


def _as_expected_elements(
    value: object,
    targets: tuple[str, ...],
    source_elements: tuple[str, ...],
    field: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """伝播先ごとの期待部分集合を検証する。

    Args:
        value: JSONから読んだ値。
        targets: 宣言済みの伝播先。
        source_elements: 正本の要素全集合。
        field: エラー表示用のフィールド名。

    Returns:
        ``targets`` と同じ順序に正規化した期待部分集合。

    Raises:
        CheckError: 伝播先、要素、または孤立要素が不正な場合。
    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckError(f"{field} は伝播先をキーとするオブジェクトでなければならない")
    missing_targets = sorted(set(targets) - set(value))
    unknown_targets = sorted(set(value) - set(targets))
    if missing_targets or unknown_targets:
        raise CheckError(
            f"{field} の伝播先がtargetsと一致しない"
            f" (不足={missing_targets}, 未知={unknown_targets})"
        )
    source_set = set(source_elements)
    expected: list[tuple[str, tuple[str, ...]]] = []
    propagated: set[str] = set()
    for target in targets:
        elements = _as_string_tuple(value[target], f"{field}.{target}")
        if len(elements) != len(set(elements)):
            raise CheckError(f"{field}.{target} に要素IDの重複がある")
        unknown_elements = sorted(set(elements) - source_set)
        if unknown_elements:
            raise CheckError(
                f"{field}.{target} に正本外の要素IDがある: {','.join(unknown_elements)}"
            )
        expected.append((target, elements))
        propagated.update(elements)
    orphaned = sorted(source_set - propagated)
    if orphaned:
        raise CheckError(f"{field} にどこへも伝播しない要素IDがある: {','.join(orphaned)}")
    return tuple(expected)


def load_manifest(path: Path) -> dict[str, ManifestRelation]:
    """関係マニフェストを読み、6フィールドを検証する。

    Args:
        path: ``sync-protocol.json`` のパス。

    Returns:
        関係IDをキーとする検証済み関係。

    Raises:
        CheckError: JSONまたは関係の形が不正な場合。
    """
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise CheckError("関係マニフェストのルートはオブジェクトでなければならない")
    relations: dict[str, ManifestRelation] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise CheckError("関係マニフェストの各関係が不正")
        relation_id = _as_string(value.get("id"), f"{key}.id")
        if relation_id != key:
            raise CheckError(f"関係キーとidが一致しない: {key}")
        targets = _as_string_tuple(value.get("targets"), f"{key}.targets")
        source_elements = _as_string_tuple(
            value.get("source_elements"), f"{key}.source_elements"
        )
        if len(source_elements) != len(set(source_elements)):
            raise CheckError(f"{key}.source_elements に要素IDの重複がある")
        relations[key] = ManifestRelation(
            id=relation_id,
            source_table=_as_string(value.get("source_table"), f"{key}.source_table"),
            targets=targets,
            compare_key=_as_string(value.get("compare_key"), f"{key}.compare_key"),
            source_elements=source_elements,
            expected_elements=_as_expected_elements(
                value.get("expected_elements"),
                targets,
                source_elements,
                f"{key}.expected_elements",
            ),
        )
    return relations


def load_defects(path: Path) -> dict[str, Defect]:
    """欠陥oracleを読み、機械欠陥と人間照合欠陥を検証する。

    Args:
        path: ``defects.json`` のパス。

    Returns:
        欠陥IDをキーとする検証済み欠陥。

    Raises:
        CheckError: JSONまたは欠陥の形が不正な場合。
    """
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise CheckError("欠陥oracleのルートはオブジェクトでなければならない")
    defects: dict[str, Defect] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue
        if not isinstance(value, dict):
            raise CheckError(f"欠陥がオブジェクトでない: {key}")
        defect_id = _as_string(value.get("id"), f"{key}.id")
        if defect_id != key:
            raise CheckError(f"欠陥キーとidが一致しない: {key}")
        detection = _as_string(value.get("detection"), f"{key}.detection")
        if detection == "machine":
            check_id = _as_string(value.get("check"), f"{key}.check")
            if check_id not in CHECK_ID_SET or check_id in GLOBAL_CHECK_IDS:
                raise CheckError(f"機械欠陥の検査IDが不正: {key}: {check_id}")
            raw_invariant = value.get("invariant")
            if not isinstance(raw_invariant, dict):
                raise CheckError(f"機械欠陥にinvariantがない: {key}")
            mapping = raw_invariant.get("mapping")
            if mapping is not None and not isinstance(mapping, str):
                raise CheckError(f"{key}.invariant.mapping が不正")
            invariant = Invariant(
                positive=_as_string(
                    raw_invariant.get("positive"), f"{key}.invariant.positive"
                ),
                forbidden=_as_string_tuple(
                    raw_invariant.get("forbidden"), f"{key}.invariant.forbidden"
                ),
                scope=_as_string(raw_invariant.get("scope"), f"{key}.invariant.scope"),
                mapping=mapping,
            )
        elif detection == "human":
            check_id = None
            invariant = None
        else:
            raise CheckError(f"欠陥のdetectionが不正: {key}: {detection}")
        defects[key] = Defect(
            id=defect_id,
            detection=detection,
            check=check_id,
            invariant=invariant,
        )
    return defects


def _heading_section(text: str, label: str) -> str:
    lines = text.splitlines()
    start: int | None = None
    level = 0
    label_re = re.compile(rf"^{re.escape(label)}(?:[.\s(]|$)")
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match is None or label_re.match(match.group("title")) is None:
            continue
        start = index
        level = len(match.group("marks"))
        break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = HEADING_RE.match(lines[index])
        if match is not None and len(match.group("marks")) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def extract_scope(text: str, scope: str) -> str:
    """不変条件のscopeに列挙された節だけを本文から切り出す。

    Args:
        text: 検査対象のMarkdown本文。
        scope: ``2-1、4-2`` や ``冒頭、1節`` 形式の節指定。

    Returns:
        指定された節を出現順に連結した文字列。存在しない節は空として扱う。
    """
    sections: list[str] = []
    for raw_token in scope.split("、"):
        token = raw_token.strip()
        if token == "冒頭":
            sections.append(text.split("\n## ", 1)[0])
            continue
        token = token.split(" の", 1)[0].removesuffix("節").strip()
        if re.fullmatch(r"\d+(?:-\d+(?:-[A-Z])?)?", token) is not None:
            sections.append(_heading_section(text, token))
    return "\n".join(sections)


def _table_row(section: str, *needles: str) -> str | None:
    for line in section.splitlines():
        if line.lstrip().startswith("|") and all(needle in line for needle in needles):
            return line
    return None


def _table_cells(line: str) -> tuple[str, ...]:
    if not line.lstrip().startswith("|"):
        return ()
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def _plain_cell(cell: str) -> str:
    return cell.replace("**", "").replace("`", "").strip()


def _identified_row(section: str, identifier: str) -> str | None:
    for line in section.splitlines():
        cells = _table_cells(line)
        if cells and _plain_cell(cells[0]) == identifier:
            return line
    return None


def _element_has_row(section: str, element: str) -> bool:
    return any(
        element in line
        for line in section.splitlines()
        if _table_cells(line) and not re.match(r"^\s*[-:]+\s*$", _table_cells(line)[0])
    )


def _numbered_ids(value: str, prefix: str) -> frozenset[str]:
    identifiers = {
        f"{prefix}{number}"
        for number in re.findall(rf"(?<![A-Za-z0-9]){re.escape(prefix)}(\d+)", value)
    }
    for match in re.finditer(
        rf"{re.escape(prefix)}(\d+)\s*[〜～-]\s*(?:{re.escape(prefix)})?(\d+)",
        value,
    ):
        start, end = (int(number) for number in match.groups())
        identifiers.update(f"{prefix}{number}" for number in range(start, end + 1))
    return frozenset(identifiers)


def _expected_route_elements(
    manifest: dict[str, ManifestRelation],
) -> dict[str, frozenset[str]]:
    routes: dict[str, frozenset[str]] = {}
    for element in manifest["R-TXN-ROUTE"].source_elements:
        match = re.match(r"(?P<route>P\d+):[^=]+=(?P<elements>.+)", element)
        if match is not None:
            routes[match.group("route")] = _numbered_ids(match.group("elements"), "T")
    return routes


def _route_row_matches(section: str, route: str, expected: frozenset[str]) -> bool:
    row = _identified_row(section, route)
    return row is not None and _numbered_ids(row, "T") == expected


def check_emphasis(text: str) -> tuple[int, ...]:
    """Markdown表セルで対になっていない強調記号の行番号を返す。

    Args:
        text: 検査対象のMarkdown本文。

    Returns:
        ``**`` の個数が奇数である表行の1始まり行番号。
    """
    return tuple(
        index
        for index, line in enumerate(text.splitlines(), start=1)
        if line.lstrip().startswith("|") and line.count("**") % 2 == 1
    )


def _has_exclusion(section: str, *terms: str) -> bool:
    return all(term in section for term in terms) and any(
        word in section for word in ("対象外", "対象にならない", "含めない")
    )


def _structural_reason(
    defect_id: str,
    text: str,
    manifest: dict[str, ManifestRelation],
) -> str | None:
    if defect_id == "SP-01":
        row = _table_row(_heading_section(text, "7-2"), "未送信", "退避済み")
        boundary = _identified_row(_heading_section(text, "6-3"), "B4")
        if (
            row is None
            or "A5" not in row
            or "退避" not in row
            or boundary is None
            or "A5" not in boundary
            or "退避" not in boundary
        ):
            return "退避済みへの遷移条件がA5の退避でない"
    elif defect_id == "SP-02":
        elements = manifest["R-ACK-STATE"].source_elements
        source = _identified_row(_heading_section(text, "7-1"), "A5")
        if source is None or any(element not in source for element in elements):
            return "A5の正本行に結果集合5状態がない"
        for label in ("6-3", "7-2"):
            section = _heading_section(text, label)
            if any(not _element_has_row(section, element) for element in elements):
                return f"A5の結果集合が{label}へ全件伝播していない"
    elif defect_id == "SP-03":
        states = manifest["R-QUEUE-LIFE"].source_elements
        for label in ("6-3", "7-2", "9-5"):
            section = _heading_section(text, label)
            if any(not _element_has_row(section, state) for state in states):
                return f"キュー状態の保持・破棄契機が{label}へ全件伝播していない"
    elif defect_id == "SP-06":
        routes = _expected_route_elements(manifest)
        for label in ("8-1", "10-2", "11-2"):
            section = _heading_section(text, label)
            if any(
                not _route_row_matches(section, route, routes[route])
                for route in ("P1", "P2", "P3")
            ):
                return f"P1〜P3の経路別T要素集合が{label}にない"
    elif defect_id == "SP-07":
        routes = _expected_route_elements(manifest)
        if not _route_row_matches(_heading_section(text, "8-1"), "P4", routes["P4"]):
            return "8-1に旧世代からB4応答へ至るP4経路がない"
        required = {
            "9-2": ("旧世代", "退避", "B4", "原子"),
            "10-2": ("退避", "B4", "原子"),
            "11-2": ("P4", "退避", "B4"),
        }
        for label, terms in required.items():
            if _table_row(_heading_section(text, label), *terms) is None:
                return f"P4の原子性が{label}へ伝播していない"
    elif defect_id == "SP-08":
        expected = next(
            element
            for element in manifest["R-TXN-ROUTE"].source_elements
            if element.startswith("T6:")
        )
        semantic = expected.split(":", 1)[1]
        section = _heading_section(text, "8-1")
        element_row = _identified_row(section, "T6")
        routes = _expected_route_elements(manifest)
        source_mapping = all(
            terms[0] in _heading_section(text, label)
            and terms[1] in _heading_section(text, label)
            for label, terms in {
                "4-4": ("一時 ID", "写像"),
                "7-1": ("D5", "確定結果"),
            }.items()
        )
        route_mapping = all(
            _route_row_matches(section, route, elements)
            for route, elements in routes.items()
            if "T6" in elements
        )
        if (
            element_row is None
            or semantic not in element_row
            or not source_mapping
            or not route_mapping
        ):
            return "T6の確定結果・一時ID写像保存が8-1にない"
    elif defect_id == "SP-09":
        routes = _expected_route_elements(manifest)
        row = _identified_row(_heading_section(text, "8-1"), "P3")
        if (
            row is None
            or _numbered_ids(row, "T") != routes["P3"]
            or "T5" in row
            or not ("T7" in row or "V11" in row)
        ):
            return "D1を持たない変更イベントのT要素集合が不正"
    elif defect_id == "SP-10":
        section = _heading_section(text, "7-1")
        route = _identified_row(_heading_section(text, "8-1"), "P3")
        response = _table_row(section, "P3", "応答")
        if route is None or response is None:
            return "P3に適用する独立した応答保証が7-1にない"
    elif defect_id == "SP-11":
        for label in ("6-2", "6-3", "8-3"):
            if _table_row(_heading_section(text, label), "期待版不一致") is None:
                return f"期待版不一致が{label}へ伝播していない"
    elif defect_id == "SP-12":
        boundary = _identified_row(_heading_section(text, "6-3"), "B3")
        if boundary is None or not _has_exclusion(
            boundary, "D1 を持たない変更イベント", "D5"
        ):
            return "D5衝突の再開2択除外が6-3にない"
        for label in ("6-4",):
            row = _table_row(
                _heading_section(text, label), "D1 を持たない変更イベント", "D5"
            )
            if row is None or not _has_exclusion(row, "D5"):
                return f"D5衝突の再開2択除外が{label}にない"
    elif defect_id == "SP-13":
        elements = manifest["R-EVENT-FIELD"].source_elements
        source = _heading_section(text, "4-3")
        if any(_identified_row(source, element) is None for element in elements):
            return "V1〜V11の正本集合が4-3にない"
        for label in ("4-3-A", "11-2"):
            section = _heading_section(text, label)
            if any(not _element_has_row(section, element) for element in elements):
                return f"V1〜V11の必須区分が{label}にない"
    elif defect_id == "SP-14":
        source = _heading_section(text, "4-3-A")
        if not all(term in source for term in ("W3-a", "W3-b", "変更版順")):
            return "変更版順の正本規則が4-3-Aにない"
        for label in ("5-5", "11-2"):
            section = _heading_section(text, label)
            if not all(term in section for term in ("変更版順", "D1・D2", "論理再生順")):
                return f"変更版順が{label}に伝播していない"
    elif defect_id == "SP-16":
        for label in ("6-1", "6-2"):
            section = _heading_section(text, label)
            if not _has_exclusion(section, "D1 を持たない変更イベント", "prefix"):
                return f"{label}にD1なし変更イベントのprefix射程除外がない"
    elif defect_id == "SP-18":
        if check_emphasis(extract_scope(text, "4-3-A")):
            return "W3表セルの強調記号が閉じていない"
    elif defect_id == "SP-19":
        if "`D1=5` の位置には" in extract_scope(text, "10-2"):
            return "D1をプレイ列の位置として使っている"
    elif defect_id == "SP-20":
        row = _table_row(_heading_section(text, "2-1"), "| D1 |")
        roles = _heading_section(text, "4-2")
        role_row = _table_row(roles, "D1", "順序", "欠落")
        idempotency_row = _table_row(roles, "D5", "再送", "二重適用")
        dedup_is_explicitly_excluded = (
            row is not None
            and "再送の重複排除" in row
            and "D5 の用途" in row
            and "D1 の用途ではない" in row
        )
        if (
            row is None
            or "順序と欠落" not in row
            or "undo の逆順" not in row
            or role_row is None
            or idempotency_row is None
            or ("再送の重複排除" in row and not dedup_is_explicitly_excluded)
        ):
            return "D1の用途が順序・欠落に限定されていない"
    return None


def defect_violation_reason(
    defect: Defect,
    text: str,
    manifest: dict[str, ManifestRelation],
) -> str | None:
    """1件の機械欠陥についてliteralと構造的不変条件を評価する。

    ``positive`` と ``mapping`` は散文のまま評価せず、本関数から呼ぶID別の
    構造ロジックの仕様として実装している。

    Args:
        defect: 評価する機械欠陥。
        text: 検査対象のMarkdown本文。
        manifest: 関係マニフェスト。

    Returns:
        違反理由。適合していれば ``None``。

    Raises:
        CheckError: 人間照合欠陥を渡した場合。
    """
    if defect.detection != "machine" or defect.invariant is None:
        raise CheckError(f"人間照合欠陥は機械評価できない: {defect.id}")
    scoped = extract_scope(text, defect.invariant.scope)
    for forbidden in defect.invariant.forbidden:
        if forbidden in scoped:
            return f"禁止literalが残存: {forbidden}"
    return _structural_reason(defect.id, text, manifest)


def _strip_code_span(value: str) -> str:
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def parse_manifest_declaration(
    text: str,
) -> tuple[dict[str, ManifestRelation], tuple[str, ...]]:
    """2-5の表間参照宣言表を6フィールドで解析する。

    Args:
        text: 検査対象のMarkdown本文。

    Returns:
        ``(関係ID別の宣言, 解析違反)``。
    """
    section = _heading_section(text, "2-5")
    if not section:
        return {}, ("2-5の表間参照宣言表がない",)
    relations: dict[str, ManifestRelation] = {}
    errors: list[str] = []
    for line in section.splitlines():
        if not line.startswith("| **R-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            errors.append("宣言表の列数が6でない")
            continue
        relation_id = cells[0].removeprefix("**").removesuffix("**")
        if relation_id in relations:
            errors.append(f"関係IDが重複: {relation_id}")
            continue
        try:
            targets_raw = json.loads(_strip_code_span(cells[2]))
            source_elements_raw = json.loads(_strip_code_span(cells[4]))
            expected_elements_raw = json.loads(_strip_code_span(cells[5]))
            targets = _as_string_tuple(targets_raw, f"{relation_id}.targets")
            source_elements = _as_string_tuple(
                source_elements_raw, f"{relation_id}.source_elements"
            )
            expected_elements = _as_expected_elements(
                expected_elements_raw,
                targets,
                source_elements,
                f"{relation_id}.expected_elements",
            )
        except (json.JSONDecodeError, CheckError) as error:
            errors.append(f"{relation_id}のJSONセルが不正: {error}")
            continue
        relations[relation_id] = ManifestRelation(
            id=relation_id,
            source_table=_strip_code_span(cells[1]),
            targets=targets,
            compare_key=_strip_code_span(cells[3]),
            source_elements=source_elements,
            expected_elements=expected_elements,
        )
    if not relations and not errors:
        errors.append("表間参照宣言表に関係行がない")
    return relations, tuple(errors)


def check_manifest_consistency(
    text: str,
    manifest: dict[str, ManifestRelation],
) -> tuple[str, ...]:
    """本文宣言表とJSONを6フィールドすべてで双方向突合する。

    Args:
        text: 検査対象のMarkdown本文。
        manifest: JSONから読んだ関係マニフェスト。

    Returns:
        不一致理由。完全一致なら空タプル。
    """
    declared, errors = parse_manifest_declaration(text)
    reasons = list(errors)
    missing = sorted(set(manifest) - set(declared))
    unknown = sorted(set(declared) - set(manifest))
    if missing:
        reasons.append(f"本文にない関係ID: {','.join(missing)}")
    if unknown:
        reasons.append(f"JSONにない関係ID: {','.join(unknown)}")
    for relation_id in sorted(set(manifest) & set(declared)):
        if manifest[relation_id] != declared[relation_id]:
            reasons.append(f"6フィールドが不一致: {relation_id}")
    return tuple(reasons)


def _reference_section(text: str, reference: str) -> str:
    """表参照の先頭にある節IDから本文を切り出す。

    Args:
        text: 検査対象のMarkdown本文。
        reference: ``6-3 の境界結果表`` のような表参照。

    Returns:
        対応する節。節IDを読めない場合は空文字列。
    """
    match = re.match(r"(?P<label>\d+(?:-\d+(?:-[A-Z])?)?)(?:\s|$)", reference)
    return _heading_section(text, match.group("label")) if match is not None else ""


def _element_markers(element: str) -> tuple[str, ...]:
    """要素宣言から本文で照合できる安定IDと意味語を取り出す。

    Args:
        element: ``B5:認証失効`` などの要素宣言。

    Returns:
        いずれかが本文にあれば要素が現れたとみなせるマーカー。
    """
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


def _semantic_text(value: str) -> str:
    """意味句の照合用にMarkdown装飾・空白・区切り記号を除く。

    Args:
        value: 要素宣言の意味句、またはMarkdown表の1行。

    Returns:
        語順と文字列を保った正規化文字列。

    Notes:
        逐語一致ではMarkdown装飾や和文の空白差まで伝播漏れにしてしまうため、
        意味を担わない装飾・空白・区切りだけを除く。一方、語の置換や語順は
        正規化しないので、右辺を別の値へ変えた場合は一致しない。
    """
    return re.sub(r"[\s`*_「」『』（）()、，,。．・:：/／—→]+", "", value)


def _identifier_set(value: str) -> tuple[str, frozenset[str]] | None:
    """右辺が同一接頭辞のID集合なら接頭辞と全集合を返す。"""
    compact = re.sub(r"\s+", "", value)
    parts = re.split(r"[,、・]", compact)
    matches = [re.fullmatch(r"(?P<prefix>[A-Z]+)(?P<number>\d+)", part) for part in parts]
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


def _data_table_rows(section: str) -> tuple[str, ...]:
    """節からMarkdown表の区切り行を除く候補行を返す。"""
    return tuple(
        row
        for row in section.splitlines()
        if _table_cells(row)
        and not all(re.fullmatch(r"\s*[-:]+\s*", cell) for cell in _table_cells(row))
    )


def _element_table_row_occurs(section: str, element: str) -> bool:
    """``=`` を持つ要素の識別子側と右辺が同じ表行にあるかを返す。

    ``ID:意味名=右辺`` のIDで候補行を構造的に特定する。IDは英字を含むものだけで
    なく、参加区分表の番号IDも必須とする。右辺が ``T1,T2,...`` のようなID集合
    なら候補行の同じ接頭辞の集合と完全一致させ、1要素の欠落・余分・別行への
    移動を検出する。それ以外は ``+`` で分けた意味句ごとに、Markdown装飾・
    空白・区切りを除いた部分文字列として同じ行に存在することを求める。この粒度は
    表記差を許しつつ、IDの欠落・交換・置換と意味句の置換を検出するためである。

    Args:
        section: 参照先の節本文。
        element: ``1:毎球入力=論理位置を持つ`` などの要素宣言。

    Returns:
        識別子側と右辺の対応全体が1つのMarkdown表行にあれば ``True``。
    """
    identifier, separator, description = element.partition(":")
    left, equals, right = description.partition("=")
    if not separator or not equals or not left or not right:
        return False

    rows = _data_table_rows(section)
    normalized_left = _semantic_text(left)
    candidate_rows = [
        row for row in rows if _identifier_occurs(row, identifier)
    ]

    identifier_set = _identifier_set(right)
    if identifier_set is not None:
        prefix, expected = identifier_set
        return any(
            normalized_left in _semantic_text(row)
            and _numbered_ids(row, prefix) == expected
            for row in candidate_rows
        )

    expected_parts = tuple(
        _semantic_text(part) for part in right.split("+") if _semantic_text(part)
    )
    return bool(expected_parts) and any(
        normalized_left in _semantic_text(row)
        and all(part in _semantic_text(row) for part in expected_parts)
        for row in candidate_rows
    )


def _identifier_occurs(text: str, identifier: str) -> bool:
    """英数字IDが単独または範囲表記で本文に現れるかを返す。

    Args:
        text: 調べる節本文。
        identifier: ``B5`` や ``W3-a`` のようなID。

    Returns:
        IDを識別子として確認できた場合は ``True``。
    """
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


def _element_occurs(section: str, element: str) -> bool:
    """宣言要素が節本文に出現するかを返す。

    ``=`` を持つ対応要素は表行単位でID・左辺・右辺を照合する。``ID:意味句``
    は意味句だけで代替させず、IDの節内出現を必須にする。単独IDやIDを持たない
    列挙語は、従来どおり節内のID・語の出現を照合する。
    """
    if "=" in element:
        return _element_table_row_occurs(section, element)
    identifier, separator, _ = element.partition(":")
    if separator and re.fullmatch(
        r"(?:[A-Z]+\d+(?:-[a-z])?|\d+)", identifier
    ) is not None:
        return _identifier_occurs(section, identifier)
    return any(
        _identifier_occurs(section, marker)
        if re.fullmatch(r"[A-Z]+\d+(?:-[a-z])?", marker)
        else marker in section
        for marker in _element_markers(element)
    )


def check_element_coverage(
    text: str,
    manifest: dict[str, ManifestRelation],
) -> tuple[str, ...]:
    """全関係の正本要素と伝播先ごとの期待部分集合を照合する。

    関係IDには依存せず、マニフェストへ関係を追加すれば自動的に検査する。

    Args:
        text: 検査対象のMarkdown本文。
        manifest: 関係マニフェスト。

    Returns:
        欠落した正本要素または伝播要素の理由。適合時は空タプル。
    """
    reasons: list[str] = []
    for relation in manifest.values():
        source = _reference_section(text, relation.source_table)
        if not source:
            reasons.append(f"{relation.id}: 正本の節を解決できない: {relation.source_table}")
        else:
            missing_source = [
                element
                for element in relation.source_elements
                if not _element_occurs(source, element)
            ]
            if missing_source:
                reasons.append(
                    f"{relation.id}: 正本にない要素: {','.join(missing_source)}"
                )
        for target, elements in relation.expected_elements:
            target_section = _reference_section(text, target)
            if not target_section:
                reasons.append(f"{relation.id}: 伝播先の節を解決できない: {target}")
                continue
            missing_target = [
                element
                for element in elements
                if not _element_occurs(target_section, element)
            ]
            if missing_target:
                reasons.append(
                    f"{relation.id}: {target} にない要素: {','.join(missing_target)}"
                )
    return tuple(reasons)


def check_citation_format(text: str) -> tuple[str, ...]:
    """可変文書で禁止する3形式の行番号引用を検出する。

    版固定アーカイブ ``docs/legacy/`` への行番号引用は逐語証拠として許容する。
    裸の行番号は同じ主張行で直前に現れた参照先を引き継ぎ、参照先が
    不明な場合は違反として扱う。

    Args:
        text: 検査対象のMarkdown本文。

    Returns:
        残存した引用形式の識別子。
    """
    found: set[str] = set()
    for line in text.splitlines():
        events: list[tuple[int, int, int, str, re.Match[str]]] = []
        patterns = (
            (0, "markdown", MARKDOWN_LINK_RE),
            (1, "requirement-line", REQ_LINE_CITATION_RE),
            (2, "path-line", PATH_LINE_CITATION_RE),
            (3, "bare-line", BARE_LINE_CITATION_RE),
        )
        for priority, event_kind, pattern in patterns:
            events.extend(
                (match.start(), match.end(), priority, event_kind, match)
                for match in pattern.finditer(line)
            )
        events.sort(key=lambda event: (event[0], event[2], -(event[1] - event[0])))

        occupied: list[tuple[int, int]] = []
        last_path: str | None = None
        for start, end, _, event_kind, match in events:
            if any(start < right and left < end for left, right in occupied):
                continue
            occupied.append((start, end))
            if event_kind == "markdown":
                last_path = match.group("target").strip("<>").split("#", 1)[0]
                continue
            if event_kind == "requirement-line":
                found.add("REQ:<行番号>")
                last_path = "docs/requirements/requirements-pitchlog-2026-07-22.md"
                continue
            if event_kind == "path-line":
                last_path = match.group(0).rsplit(":", 1)[0]
                if not _is_legacy_citation_path(last_path):
                    found.add("<パス>.md:<行番号>")
                continue
            if last_path is None or not _is_legacy_citation_path(last_path):
                found.add("裸の行番号")
    return tuple(
        identifier
        for identifier in ("REQ:<行番号>", "<パス>.md:<行番号>", "裸の行番号")
        if identifier in found
    )


def _is_legacy_citation_path(path: str) -> bool:
    """引用先が版固定のlegacyアーカイブかを返す。

    Args:
        path: リポジトリ相対または文書相対のMarkdownパス。

    Returns:
        ``docs/legacy/`` 配下を指す場合は ``True``。
    """
    normalized = path.replace("\\", "/")
    return (
        normalized.startswith("docs/legacy/")
        or normalized.startswith("../legacy/")
        or "/docs/legacy/" in normalized
    )


def check_noncanonical_reference(text: str) -> tuple[int, ...]:
    """本文中のdocs/features配下への規範参照を検出する。

    変更履歴は経緯の記録なので対象外とし、2章以降を規範本文として走査する。

    Args:
        text: 検査対象のMarkdown本文。

    Returns:
        非正本参照がある1始まり行番号。
    """
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if re.match(r"^##\s+2(?:[.\s]|$)", line)),
        len(lines),
    )
    return tuple(
        index + 1
        for index, line in enumerate(lines)
        if index >= start and NONCANONICAL_PATH_RE.search(line) is not None
    )


def check_link_targets(text: str, root: Path) -> tuple[str, ...]:
    """本文の相対Markdownリンクがリポジトリ内に実在するか検査する。

    fixtureも正本文書のコピーとして扱うため、解決基準は常に
    ``docs/design`` とする。

    Args:
        text: 検査対象のMarkdown本文。
        root: リポジトリルート。

    Returns:
        不正または実在しないリンク先。
    """
    base = (root / "docs" / "design").resolve()
    root = root.resolve()
    missing: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group("target").strip("<>")
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        path_part = target.split("#", 1)[0]
        candidate = (root / path_part.lstrip("/")) if target.startswith("/") else (base / path_part)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or not resolved.exists():
            missing.append(target)
    return tuple(dict.fromkeys(missing))


def _global_findings(
    text: str,
    root: Path,
    manifest: dict[str, ManifestRelation],
    checks: frozenset[str],
) -> list[Finding]:
    findings: list[Finding] = []
    if "element-coverage" in checks:
        reasons = check_element_coverage(text, manifest)
        if reasons:
            findings.append(
                Finding("element-coverage", "element-coverage", "; ".join(reasons))
            )
    if "manifest-consistency" in checks:
        reasons = check_manifest_consistency(text, manifest)
        if reasons:
            findings.append(
                Finding("manifest-consistency", "manifest-consistency", "; ".join(reasons))
            )
    if "citation-format" in checks:
        formats = check_citation_format(text)
        if formats:
            findings.append(
                Finding("citation-format", "citation-format", ", ".join(formats))
            )
    if "noncanonical-reference" in checks:
        lines = check_noncanonical_reference(text)
        if lines:
            findings.append(
                Finding(
                    "noncanonical-reference",
                    "noncanonical-reference",
                    "docs/features/配下への規範参照が残存: "
                    + ",".join(str(line) for line in lines),
                )
            )
    if "link-target" in checks:
        targets = check_link_targets(text, root)
        if targets:
            findings.append(
                Finding("link-target", "link-target", "実在しないリンク: " + ",".join(targets))
            )
    return findings


def _parse_csv(value: str | None, option: str) -> frozenset[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise CheckError(f"{option} にIDがない")
    return frozenset(items)


def select_checks_and_defects(
    defects: dict[str, Defect],
    defect_csv: str | None,
    check_csv: str | None,
) -> tuple[frozenset[str], tuple[Defect, ...], bool]:
    """CLIセレクタを検証し、実行する検査と欠陥を決める。

    ``--defects`` と ``--checks`` の併用時は和集合ではなく積集合とする。
    欠陥IDを持たない4検査は ``--defects`` 条件を満たせないため実行しない。

    Args:
        defects: 欠陥oracle。
        defect_csv: カンマ区切り欠陥ID。未指定なら ``None``。
        check_csv: カンマ区切り検査ID。未指定なら ``None``。

    Returns:
        ``(実行検査ID, 実行欠陥, 全体検査を許可するか)``。

    Raises:
        CheckError: 未知IDまたは人間照合IDを指定した場合。
    """
    selected_defect_ids = _parse_csv(defect_csv, "--defects")
    selected_check_ids = _parse_csv(check_csv, "--checks")
    if selected_check_ids is not None:
        unknown_checks = sorted(selected_check_ids - CHECK_ID_SET)
        if unknown_checks:
            raise CheckError("未知の検査ID: " + ",".join(unknown_checks))

    if selected_defect_ids is not None:
        unknown_defects = sorted(selected_defect_ids - set(defects))
        if unknown_defects:
            raise CheckError("未知の欠陥ID: " + ",".join(unknown_defects))
        human = sorted(
            defect_id
            for defect_id in selected_defect_ids
            if defects[defect_id].detection != "machine"
        )
        if human:
            raise CheckError("人間照合の欠陥IDは指定できない: " + ",".join(human))
        candidates = [defects[defect_id] for defect_id in selected_defect_ids]
    else:
        candidates = [defect for defect in defects.values() if defect.detection == "machine"]

    if selected_check_ids is not None:
        active_checks = selected_check_ids
    elif selected_defect_ids is not None:
        active_checks = frozenset(
            defect.check for defect in candidates if defect.check is not None
        )
    else:
        active_checks = CHECK_ID_SET

    selected_defects = tuple(
        sorted(
            (
                defect
                for defect in candidates
                if defect.check is not None and defect.check in active_checks
            ),
            key=lambda defect: defect.id,
        )
    )
    return active_checks, selected_defects, selected_defect_ids is None


def run_checks(
    text: str,
    root: Path,
    manifest: dict[str, ManifestRelation],
    defects: dict[str, Defect],
    defect_csv: str | None = None,
    check_csv: str | None = None,
) -> tuple[Finding, ...]:
    """選択条件に従って設計伝播検査を実行する。

    Args:
        text: 検査対象のMarkdown本文。
        root: リポジトリルート。
        manifest: 関係マニフェスト。
        defects: 欠陥oracle。
        defect_csv: ``--defects`` 相当のカンマ区切りID。
        check_csv: ``--checks`` 相当のカンマ区切りID。

    Returns:
        欠陥IDまたは全体検査ID単位の違反。
    """
    checks, selected_defects, allow_global = select_checks_and_defects(
        defects, defect_csv, check_csv
    )
    findings: list[Finding] = []
    for defect in selected_defects:
        reason = defect_violation_reason(defect, text, manifest)
        if reason is not None:
            assert defect.check is not None
            findings.append(Finding(defect.id, defect.check, reason))
    if allow_global:
        findings.extend(_global_findings(text, root, manifest, checks))
    return tuple(sorted(findings, key=lambda finding: finding.identifier))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        解釈済み引数。
    """
    parser = argparse.ArgumentParser(description="同期プロトコル設計の伝播を突合する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument(
        "--document",
        type=Path,
        default=DEFAULT_DOCUMENT,
        help="検査対象文書(既定: docs/design/sync-protocol.md)",
    )
    parser.add_argument("--defects", help="実行する機械欠陥IDのカンマ区切り")
    parser.add_argument("--checks", help="実行する検査IDのカンマ区切り")
    return parser.parse_args(argv)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    """検査を実行し、違反の有無に応じた終了コードを返す。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        違反なしなら0、違反ありなら1、入力やセレクタの不正なら2。
    """
    try:
        args = parse_args(argv)
        root = args.root.resolve()
        document = _resolve(root, args.document)
        try:
            text = document.read_text(encoding="utf-8")
        except OSError as error:
            raise CheckError(f"検査対象を読めない: {document}: {error}") from error
        manifest = load_manifest(root / DEFAULT_MANIFEST)
        defects = load_defects(root / DEFAULT_DEFECTS)
        findings = run_checks(
            text,
            root,
            manifest,
            defects,
            defect_csv=args.defects,
            check_csv=args.checks,
        )
    except CheckError as error:
        print(f"check_design_propagation.py: {error}", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding.identifier}: [{finding.check}] {finding.reason}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
