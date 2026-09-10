"""共有関数の前提条件資産を要件書および管理操作用IDと静的照合する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

try:
    from check_authz_catalog import git_blob_digest
except ModuleNotFoundError:  # pragma: no cover - モジュールとして読む場合だけ通る。
    from scripts.check_authz_catalog import git_blob_digest


ASSET_PATH = PurePosixPath("contracts/authz/shared-preconditions.json")
ROUTE_REGISTRY_PATH = PurePosixPath("contracts/authz/route-registry.json")
SOURCE_PATH_BY_ROLE = {
    "normative_source": PurePosixPath(
        "docs/requirements/requirements-pitchlog-2026-07-22.md"
    ),
    "mapping_target": PurePosixPath("docs/design/data-model.md"),
}
EXTRACTION_RULE = {
    "source_document_role": "normative_source",
    "section_heading": "FR-034: データ所有権制御",
    "list_heading": "全行に掛かる前提条件",
    "selection_rule": "numbered_list_all_items",
}
ASSET_KIND = "authz_shared_preconditions"
PRECONDITION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
BLOB_DIGEST_RE = re.compile(r"^[0-9a-f]{40}$")
MARKDOWN_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
NUMBERED_ITEM_RE = re.compile(r"^(?P<ordinal>[1-9]\d*)\. (?P<text>.+)$")
CLOSED_KINDS = frozenset({"通常", "例外"})
EXCEPTION_KIND = "例外"
REGULAR_KIND = "通常"
EXCEPTION_SOURCE_ORDINAL = 5


class SharedPreconditionCheckError(Exception):
    """検査を開始できない入力不正を表す。"""


@dataclass(frozen=True)
class SourceDocument:
    """前提条件資産が参照する文書を表す。"""

    path: PurePosixPath
    document_role: str
    git_blob_digest: str


@dataclass(frozen=True)
class Precondition:
    """共有関数の前提条件1行を表す。"""

    precondition_id: str
    verbatim_text: str
    kind: str
    equivalent_registry_precondition_id: str | None


@dataclass(frozen=True)
class ValidationResult:
    """静的照合の違反と資産由来の件数を表す。"""

    findings: tuple[str, ...]
    precondition_count: int
    equivalent_count: int
    independent_count: int


def _read_bytes(path: Path, label: str) -> bytes:
    """ファイルを生バイト列で読む。"""
    try:
        return path.read_bytes()
    except OSError as error:
        raise SharedPreconditionCheckError(
            f"{label}を読めない: {path}: {error}"
        ) from error


def _read_text(path: Path, label: str) -> str:
    """UTF-8ファイルを読む。"""
    data = _read_bytes(path, label)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SharedPreconditionCheckError(
            f"{label}がUTF-8でない: {path}: {error}"
        ) from error


def _read_json(path: Path, label: str) -> object:
    """JSONファイルを読む。"""
    try:
        return json.loads(_read_text(path, label))
    except json.JSONDecodeError as error:
        raise SharedPreconditionCheckError(
            f"{label}がJSONでない: {path}: {error}"
        ) from error


def _expect_object(value: object, label: str) -> dict[str, object]:
    """値がJSON objectであることを検査する。"""
    if not isinstance(value, dict):
        raise SharedPreconditionCheckError(f"{label}はobjectでなければならない")
    if not all(isinstance(key, str) for key in value):
        raise SharedPreconditionCheckError(f"{label}のkeyは文字列でなければならない")
    return value


def _expect_list(value: object, label: str) -> list[object]:
    """値がJSON arrayであることを検査する。"""
    if not isinstance(value, list):
        raise SharedPreconditionCheckError(f"{label}はarrayでなければならない")
    return value


def _expect_string(value: object, label: str) -> str:
    """値が空でない文字列であることを検査する。"""
    if not isinstance(value, str) or not value:
        raise SharedPreconditionCheckError(f"{label}は空でない文字列でなければならない")
    return value


def _expect_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    """JSON objectのkey集合を完全照合する。"""
    if set(value) != expected:
        raise SharedPreconditionCheckError(f"{label}のkey集合が不正")


def _parse_extraction_rule(raw: object) -> None:
    """抽出規則が固定した機械可読形式であることを検査する。"""
    rule = _expect_object(raw, "extraction_rule")
    _expect_keys(rule, set(EXTRACTION_RULE), "extraction_rule")
    for key, expected in EXTRACTION_RULE.items():
        actual = _expect_string(rule[key], f"extraction_rule.{key}")
        if actual != expected:
            raise SharedPreconditionCheckError(
                f"extraction_rule.{key}が対応する抽出規則でない"
            )


def _parse_source_documents(raw: object) -> tuple[SourceDocument, ...]:
    """出典文書の宣言を読む。"""
    documents: list[SourceDocument] = []
    for index, item in enumerate(_expect_list(raw, "source_documents")):
        label = f"source_documents[{index}]"
        document = _expect_object(item, label)
        _expect_keys(
            document,
            {"path", "document_role", "git_blob_digest"},
            label,
        )
        path_text = _expect_string(document["path"], f"{label}.path")
        role = _expect_string(document["document_role"], f"{label}.document_role")
        digest = _expect_string(
            document["git_blob_digest"], f"{label}.git_blob_digest"
        )
        if role not in SOURCE_PATH_BY_ROLE:
            raise SharedPreconditionCheckError(f"{label}.document_roleが不正")
        if PurePosixPath(path_text).as_posix() != path_text:
            raise SharedPreconditionCheckError(f"{label}.pathが正規相対パスでない")
        if PurePosixPath(path_text) != SOURCE_PATH_BY_ROLE[role]:
            raise SharedPreconditionCheckError(
                f"{label}.pathがdocument_roleの所定パスでない"
            )
        if BLOB_DIGEST_RE.fullmatch(digest) is None:
            raise SharedPreconditionCheckError(
                f"{label}.git_blob_digestがGit blob digest形式でない"
            )
        documents.append(SourceDocument(PurePosixPath(path_text), role, digest))

    role_counts = Counter(document.document_role for document in documents)
    if set(role_counts) != set(SOURCE_PATH_BY_ROLE) or any(
        count != 1 for count in role_counts.values()
    ):
        raise SharedPreconditionCheckError(
            "source_documentsは各document_roleを1件ずつ持たなければならない"
        )
    return tuple(documents)


def _parse_preconditions(raw: object) -> tuple[Precondition, ...]:
    """共有関数の前提条件行を読む。"""
    preconditions: list[Precondition] = []
    for index, item in enumerate(_expect_list(raw, "preconditions")):
        label = f"preconditions[{index}]"
        entry = _expect_object(item, label)
        _expect_keys(
            entry,
            {
                "precondition_id",
                "verbatim_text",
                "kind",
                "equivalent_registry_precondition_id",
            },
            label,
        )
        precondition_id = _expect_string(
            entry["precondition_id"], f"{label}.precondition_id"
        )
        if PRECONDITION_ID_RE.fullmatch(precondition_id) is None:
            raise SharedPreconditionCheckError(
                f"{label}.precondition_idの形式が不正"
            )
        equivalent = entry["equivalent_registry_precondition_id"]
        if equivalent is not None:
            equivalent = _expect_string(
                equivalent,
                f"{label}.equivalent_registry_precondition_id",
            )
            if PRECONDITION_ID_RE.fullmatch(equivalent) is None:
                raise SharedPreconditionCheckError(
                    f"{label}.equivalent_registry_precondition_idの形式が不正"
                )
        preconditions.append(
            Precondition(
                precondition_id=precondition_id,
                verbatim_text=_expect_string(
                    entry["verbatim_text"], f"{label}.verbatim_text"
                ),
                kind=_expect_string(entry["kind"], f"{label}.kind"),
                equivalent_registry_precondition_id=equivalent,
            )
        )
    return tuple(preconditions)


def _parse_asset(
    raw: object,
) -> tuple[tuple[SourceDocument, ...], tuple[Precondition, ...]]:
    """共有前提資産の構造を検査して値を読む。"""
    asset = _expect_object(raw, "共有前提資産")
    _expect_keys(
        asset,
        {
            "schema_version",
            "asset_kind",
            "extraction_rule",
            "source_documents",
            "preconditions",
        },
        "共有前提資産",
    )
    if type(asset["schema_version"]) is not int or asset["schema_version"] != 1:
        raise SharedPreconditionCheckError("schema_versionが未対応")
    if asset["asset_kind"] != ASSET_KIND:
        raise SharedPreconditionCheckError("asset_kindが不正")
    _parse_extraction_rule(asset["extraction_rule"])
    return (
        _parse_source_documents(asset["source_documents"]),
        _parse_preconditions(asset["preconditions"]),
    )


def _parse_registry_ids(raw: object) -> frozenset[str]:
    """route registryから管理操作用の前提条件ID集合を読む。"""
    registry = _expect_object(raw, "route-registry")
    enums = _expect_object(registry.get("enums"), "route-registry.enums")
    raw_ids = _expect_list(
        enums.get("precondition_ids"),
        "route-registry.enums.precondition_ids",
    )
    ids = tuple(
        _expect_string(value, f"route-registry.enums.precondition_ids[{index}]")
        for index, value in enumerate(raw_ids)
    )
    if len(set(ids)) != len(ids):
        raise SharedPreconditionCheckError(
            "route-registry.enums.precondition_idsが重複している"
        )
    return frozenset(ids)


def _section_lines(text: str, section_heading: str) -> tuple[str, ...]:
    """指定したMarkdown見出しの配下だけを返す。"""
    lines = text.splitlines()
    matches: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = MARKDOWN_HEADING_RE.fullmatch(line)
        if match is not None and match.group("title") == section_heading:
            matches.append((index, len(match.group("marks"))))
    if len(matches) != 1:
        raise SharedPreconditionCheckError(
            f"要件書の見出し「{section_heading}」が一意でない"
        )
    start, level = matches[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = MARKDOWN_HEADING_RE.fullmatch(lines[index])
        if match is not None and len(match.group("marks")) <= level:
            end = index
            break
    return tuple(lines[start + 1 : end])


def _extract_normative_items(text: str) -> tuple[str, ...]:
    """抽出規則に従いFR-034の番号付きリスト全項を逐語で返す。"""
    section = _section_lines(text, EXTRACTION_RULE["section_heading"])
    list_marker = f'**{EXTRACTION_RULE["list_heading"]}**'
    marker_indexes = [
        index for index, line in enumerate(section) if line.startswith(list_marker)
    ]
    if len(marker_indexes) != 1:
        raise SharedPreconditionCheckError(
            f"要件書のリスト見出し「{EXTRACTION_RULE['list_heading']}」が一意でない"
        )

    index = marker_indexes[0] + 1
    while index < len(section) and not section[index]:
        index += 1
    items: list[str] = []
    expected_ordinal = 1
    while index < len(section):
        match = NUMBERED_ITEM_RE.fullmatch(section[index])
        if match is None:
            break
        if int(match.group("ordinal")) != expected_ordinal:
            raise SharedPreconditionCheckError(
                "要件書の前提条件リストの番号が連続していない"
            )
        items.append(match.group("text"))
        expected_ordinal += 1
        index += 1
    if not items:
        raise SharedPreconditionCheckError(
            "要件書の前提条件リストに番号付き項目がない"
        )
    return tuple(items)


def _format_values(values: set[str]) -> str:
    """文字列集合を診断用に安定整列する。"""
    return ", ".join(sorted(values)) or "なし"


def validate_repository(root: Path) -> ValidationResult:
    """リポジトリ内の共有前提資産を静的照合する。

    Args:
        root: リポジトリルート。

    Returns:
        違反一覧と資産から導出した件数。
    """
    root = root.resolve()
    documents, preconditions = _parse_asset(
        _read_json(root / ASSET_PATH, "共有前提資産")
    )
    registry_ids = _parse_registry_ids(
        _read_json(root / ROUTE_REGISTRY_PATH, "route-registry")
    )
    findings: list[str] = []
    document_text_by_role: dict[str, str] = {}
    for document in documents:
        path = root / document.path
        data = _read_bytes(path, document.document_role)
        if git_blob_digest(data) != document.git_blob_digest:
            findings.append(
                f"{document.path}: git_blob_digestが現ファイルと不一致; "
                "digest の取り直しが必要"
            )
        try:
            document_text_by_role[document.document_role] = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SharedPreconditionCheckError(
                f"{document.document_role}がUTF-8でない: {path}: {error}"
            ) from error

    normative_items = _extract_normative_items(
        document_text_by_role[EXTRACTION_RULE["source_document_role"]]
    )
    if len(preconditions) != len(normative_items):
        findings.append(
            "preconditionsの行数が要件書から抽出した番号付きリスト全項と不一致: "
            f"資産={len(preconditions)} 要件書={len(normative_items)}"
        )
    for ordinal, (precondition, normative_text) in enumerate(
        zip(preconditions, normative_items, strict=False),
        start=1,
    ):
        if precondition.verbatim_text != normative_text:
            findings.append(
                f"preconditions[{ordinal}].verbatim_textが要件書本文と逐語不一致"
            )

    id_counts = Counter(item.precondition_id for item in preconditions)
    duplicate_ids = {value for value, count in id_counts.items() if count > 1}
    if duplicate_ids:
        findings.append(f"precondition_idが重複: {_format_values(duplicate_ids)}")
    overlap = set(id_counts) & registry_ids
    if overlap:
        findings.append(
            "precondition_idがroute-registryの管理操作用IDと交差: "
            f"{_format_values(overlap)}"
        )

    invalid_kinds = {item.kind for item in preconditions} - CLOSED_KINDS
    if invalid_kinds:
        findings.append(f"kindが閉じた値域の外: {_format_values(invalid_kinds)}")
    exception_ordinals = [
        ordinal
        for ordinal, item in enumerate(preconditions, start=1)
        if item.kind == EXCEPTION_KIND
    ]
    if len(exception_ordinals) != 1:
        findings.append(
            "kindが「例外」の行数が不正: "
            f"期待=1 実際={len(exception_ordinals)}"
        )
    for ordinal, item in enumerate(preconditions, start=1):
        expected_kind = (
            EXCEPTION_KIND
            if ordinal == EXCEPTION_SOURCE_ORDINAL
            else REGULAR_KIND
        )
        if item.kind != expected_kind:
            findings.append(
                f"preconditions[{ordinal}].kindが要件書の行種別と不一致: "
                f"期待={expected_kind} 実際={item.kind}"
            )

    unknown_equivalents = {
        equivalent
        for item in preconditions
        if (equivalent := item.equivalent_registry_precondition_id) is not None
        and equivalent not in registry_ids
    }
    if unknown_equivalents:
        findings.append(
            "equivalent_registry_precondition_idが実在しないroute-registry IDを参照: "
            f"{_format_values(unknown_equivalents)}"
        )

    equivalent_counts = Counter(
        item.equivalent_registry_precondition_id is not None
        for item in preconditions
    )
    return ValidationResult(
        findings=tuple(findings),
        precondition_count=len(preconditions),
        equivalent_count=equivalent_counts[True],
        independent_count=equivalent_counts[False],
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: 引数列。省略時はプロセスの引数を使う。

    Returns:
        解釈済みの引数。
    """
    parser = argparse.ArgumentParser(description="共有関数の前提条件資産を静的照合する")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="リポジトリルート")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """静的照合を実行して終了コードを返す。

    Args:
        argv: 引数列。省略時はプロセスの引数を使う。

    Returns:
        合格は0、規約違反は1、入力不正は2。
    """
    try:
        args = parse_args(argv)
        result = validate_repository(args.root)
    except SharedPreconditionCheckError as error:
        print(f"authz-shared-preconditions: 入力不正: {error}", file=sys.stderr)
        return 2
    if result.findings:
        for finding in result.findings:
            print(
                f"authz-shared-preconditions: 違反: {finding}",
                file=sys.stderr,
            )
        return 1
    print(
        "authz-shared-preconditions: OK "
        f"preconditions={result.precondition_count} "
        f"equivalent_registry={result.equivalent_count} "
        f"independent={result.independent_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
