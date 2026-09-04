"""文書検査の宣言的不変条件を評価する。"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _load_profile_module() -> Any:
    """隣接する共通プロファイルローダーをファイルパスから読む。"""
    path = Path(__file__).resolve().parent / "doc_check_profile.py"
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


def evaluate_declaration(
    declaration: Mapping[str, Any],
    *,
    text: str,
    manifest: Mapping[str, Any],
    profile: Any,
    sections: Mapping[str, str],
) -> StructuredReason | None:
    """1件の宣言を評価する。

    Args:
        declaration: kindと引数を持つ宣言。
        text: 検査対象のMarkdown本文。
        manifest: 関係マニフェスト。
        profile: 検証済みプロファイル。
        sections: 事前に解決した節IDと本文の対応。

    Returns:
        違反時の構造化理由。適合時は ``None``。

    Raises:
        ProfileError: kindが未実装か、宣言または節指定が不正な場合。
    """
    kind = declaration.get("kind")
    if kind != "forbidden-element":
        raise doc_check_profile.ProfileError(f"未実装の kind です: {kind!r}")
    doc_check_profile.validate_declaration(declaration)
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
