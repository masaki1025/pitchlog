"""認可資産から適用可能な DDL 列を組み立てる。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DDL_ELEMENTS_PATH = PurePosixPath("contracts/authz/ddl-elements.json")
BODY_MANIFEST_PATH = PurePosixPath("contracts/authz/function-bodies/manifest.json")
BODY_CHECKER_PATH = PurePosixPath("scripts/check_authz_function_bodies.py")


class AuthzDDLGenerationError(Exception):
    """認可 DDL を安全に生成できない入力を表す。"""


@dataclass(frozen=True, slots=True)
class DDLStatement:
    """1 要素に対応する適用可能な SQL 単位を表す。

    Attributes:
        element_type: manifest が示す要素種別。
        element_id: checkpoint へ引き渡す資産要素 ID。
        source_path: SQL 実体を読んだ manifest 登録パス。
        sql: body ファイルを改変せず取り込んだ SQL。
    """

    element_type: str
    element_id: str
    source_path: PurePosixPath
    sql: str


@dataclass(frozen=True, slots=True)
class _BodyEntry:
    """digest 照合済みの manifest entry と SQL を保持する。"""

    element_type: str
    element_id: str
    source_path: PurePosixPath
    sql: str


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    """JSON object を読み、入力不正を単一例外へ変換する。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuthzDDLGenerationError(f"{label}を読めない: {path}: {error}") from error
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise AuthzDDLGenerationError(f"{label}はJSON objectでなければならない")
    return raw


def _expect_string(value: object, label: str) -> str:
    """空でない文字列だけを受け入れる。"""
    if not isinstance(value, str) or not value:
        raise AuthzDDLGenerationError(f"{label}は空でない文字列でなければならない")
    return value


def _validate_function_bodies(root: Path) -> None:
    """ステップ 2 の静的照合器で body と manifest を検証する。"""
    checker_path = root / BODY_CHECKER_PATH
    if not checker_path.is_file():
        raise AuthzDDLGenerationError(f"body静的照合器がない: {checker_path}")
    try:
        result = subprocess.run(
            [sys.executable, str(checker_path), "--root", str(root)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise AuthzDDLGenerationError(
            f"body静的照合器を実行できない: {error}"
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "詳細なし"
        raise AuthzDDLGenerationError(f"body静的照合に失敗した: {detail}")


def _read_verified_body_entries(root: Path) -> tuple[_BodyEntry, ...]:
    """静的照合済み manifest から digest 一致 body だけを読む。"""
    _validate_function_bodies(root)
    manifest = _read_json_object(root / BODY_MANIFEST_PATH, "body manifest")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise AuthzDDLGenerationError("body manifest.entriesはarrayでなければならない")

    entries: list[_BodyEntry] = []
    for index, raw_entry in enumerate(raw_entries):
        label = f"body manifest.entries[{index}]"
        if not isinstance(raw_entry, dict):
            raise AuthzDDLGenerationError(f"{label}はobjectでなければならない")
        path_text = _expect_string(raw_entry.get("path"), f"{label}.path")
        element_type = _expect_string(
            raw_entry.get("element_type"), f"{label}.element_type"
        )
        element_id = _expect_string(raw_entry.get("element_id"), f"{label}.element_id")
        source_path = PurePosixPath(path_text)
        body_path = root.joinpath(*source_path.parts)
        try:
            data = body_path.read_bytes()
            sql = data.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise AuthzDDLGenerationError(
                f"manifest登録bodyを読めない: {body_path}: {error}"
            ) from error
        entries.append(
            _BodyEntry(
                element_type=element_type,
                element_id=element_id,
                source_path=source_path,
                sql=sql,
            )
        )
    return tuple(entries)


def _section_element_ids(
    rows: object,
    expected_ids: set[str],
    label: str,
) -> tuple[str, ...]:
    """資産セクションから宣言 ID を順序付きで導出する。"""
    if not isinstance(rows, list):
        raise AuthzDDLGenerationError(f"{label}はarrayでなければならない")
    if not rows:
        return ()
    if not all(isinstance(row, dict) for row in rows):
        raise AuthzDDLGenerationError(f"{label}の全要素はobjectでなければならない")

    row_objects = [row for row in rows if isinstance(row, dict)]
    common_keys = set(row_objects[0])
    for row in row_objects[1:]:
        common_keys.intersection_update(row)
    candidates: list[tuple[str, ...]] = []
    for key in common_keys:
        values = tuple(row[key] for row in row_objects)
        if (
            all(isinstance(value, str) and value for value in values)
            and len(set(values)) == len(values)
            and set(values) <= expected_ids
        ):
            candidates.append(
                tuple(value for value in values if isinstance(value, str))
            )
    if len(candidates) != 1:
        raise AuthzDDLGenerationError(f"{label}の要素ID列を一意に導出できない")
    return candidates[0]


def _asset_section_name(element_type: str) -> str:
    """Manifest の単数形種別から資産セクション名を導出する。"""
    if element_type.endswith("y") and element_type[-2:-1] not in "aeiou":
        return f"{element_type[:-1]}ies"
    return f"{element_type}s"


def _assemble_statements(
    ddl_elements: dict[str, object],
    entries: tuple[_BodyEntry, ...],
) -> tuple[DDLStatement, ...]:
    """DDL 資産の宣言順に manifest body を並べる。"""
    entries_by_type: defaultdict[str, list[_BodyEntry]] = defaultdict(list)
    for entry in entries:
        entries_by_type[entry.element_type].append(entry)

    section_positions = {name: index for index, name in enumerate(ddl_elements)}
    element_positions: dict[tuple[str, str], tuple[int, int]] = {}
    for element_type, typed_entries in entries_by_type.items():
        section_name = _asset_section_name(element_type)
        if section_name not in section_positions:
            raise AuthzDDLGenerationError(
                f"DDL要素資産にmanifest種別のセクションがない: {element_type}"
            )
        expected_ids = {entry.element_id for entry in typed_entries}
        declared_ids = _section_element_ids(
            ddl_elements[section_name],
            expected_ids,
            f"ddl-elements.{section_name}",
        )
        for row_index, element_id in enumerate(declared_ids):
            key = (element_type, element_id)
            if key in element_positions:
                raise AuthzDDLGenerationError(f"DDL要素IDが重複している: {key}")
            element_positions[key] = (section_positions[section_name], row_index)

    ranked_entries = [
        (element_positions[(entry.element_type, entry.element_id)], entry)
        for entry in entries
        if (entry.element_type, entry.element_id) in element_positions
    ]
    ranked_entries.sort(key=lambda item: item[0])
    return tuple(
        DDLStatement(
            element_type=entry.element_type,
            element_id=entry.element_id,
            source_path=entry.source_path,
            sql=entry.sql,
        )
        for _, entry in ranked_entries
    )


def generate_authz_ddl(root: Path) -> tuple[DDLStatement, ...]:
    """認可資産から要素 ID 付きの適用可能な SQL 列を生成する。

    Args:
        root: ``contracts/authz`` と静的照合器を含むリポジトリルート。

    Returns:
        ``ddl-elements.json`` の依存順で並んだ SQL 単位。

    Raises:
        AuthzDDLGenerationError: 資産または manifest の照合・解釈に失敗した場合。
    """
    root = root.resolve()
    if not root.is_dir():
        raise AuthzDDLGenerationError(f"リポジトリルートがない: {root}")
    entries = _read_verified_body_entries(root)
    ddl_elements = _read_json_object(root / DDL_ELEMENTS_PATH, "ddl-elements")
    return _assemble_statements(ddl_elements, entries)
