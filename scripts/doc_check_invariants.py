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
        if "elements" in declaration:
            raise doc_check_profile.ProfileError(
                "row-contains の elements は未実装です"
            )
        section_id = context.selected_sections.get(row_id)
        if section_id is None:
            raise doc_check_profile.ProfileError(
                f"row-contains の参照先 row の節が未定義です: {row_id}"
            )
        row = context.selected_rows[row_id]
        for literal in declaration["literals"]:
            if literal not in row:
                return StructuredReason(
                    violated=True,
                    kind=kind,
                    section=section_id,
                    expected=literal,
                    actual=row,
                    token=literal,
                )
        return None
    del manifest, profile

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
