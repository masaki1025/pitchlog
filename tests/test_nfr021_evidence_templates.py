"""NFR-021 受入証跡テンプレートの書式契約テスト。

テンプレートの複写用本文にある単一フェンスと、その先頭の frontmatter を
行単位で解析する。YAML パーサーや追加の依存関係は使わない。
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
TEMPLATE_DIRECTORY = REPO / "docs" / "ops" / "nfr021-acceptance"
RESERVATION_TEMPLATE = "reservation-template.md"
PHASE4_TEMPLATE = "evidence-phase4-template.md"
RELEASE_TEMPLATE = "evidence-release-template.md"
TEMPLATE_FILENAMES = (
    RESERVATION_TEMPLATE,
    PHASE4_TEMPLATE,
    RELEASE_TEMPLATE,
)

FRONTMATTER_DELIMITER = "---"
FENCE_OPENING_PATTERN = re.compile(r"^(?P<marker>`{3,}|~{3,}).*$")
FRONTMATTER_KEY_PATTERN = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:")
TABLE_SEPARATOR_CELL_PATTERN = re.compile(r"^:?-{3,}:?$")

RESERVATION_REQUIRED_KEYS = {
    "gate_key",
    "attempt_seq",
    "attempt_id",
    "started_at",
    "operator",
}
EVIDENCE_REQUIRED_KEYS = {
    "gate_kind",
    "tested_commit_sha",
    "onboarding_blob_sha",
    "result",
    "attempt_seq",
    "attempt_id",
}
RELEASE_REQUIRED_KEYS = EVIDENCE_REQUIRED_KEYS | {"release_version"}
REQUIRED_EVIDENCE_FIELD_NAMES = {
    "日時",
    "commit SHA",
    "Windows 版",
    "WSL 版",
    "ディストリビューション版",
    "onboarding 版",
    "主要ツールの版（python / uv / node / docker）",
    "実行コマンドと終了コード",
    "各合格項目の期待値と実測値",
    "標準出力またはログ成果物への参照",
    "判定者",
}
FORBIDDEN_CANDIDATE_SHA_MARKERS = {
    "candidate_sha",
    "候補 SHA",
    "phase4_base_sha",
}


def load_template(filename: str) -> str:
    """実リポジトリのテンプレートを読み込む。

    Args:
        filename: 受入証跡ディレクトリ直下のテンプレート名。

    Returns:
        UTF-8 で読み込んだテンプレート本文。
    """
    return (TEMPLATE_DIRECTORY / filename).read_text(encoding="utf-8")


def extract_single_fenced_block(text: str) -> str:
    """文字列から唯一のフェンス付きコードブロックの内容を取り出す。

    Args:
        text: 検査するテンプレート全体の文字列。

    Returns:
        フェンスを除いたコードブロックの内容。

    Raises:
        ValueError: フェンスが閉じていない、ちょうど 1 つでない、または
            内容が frontmatter の開始行で始まらない場合。
    """
    blocks: list[str] = []
    block_lines: list[str] = []
    opening_marker: str | None = None

    for line in text.splitlines():
        if opening_marker is None:
            opening_match = FENCE_OPENING_PATTERN.fullmatch(line)
            if opening_match is not None:
                opening_marker = opening_match.group("marker")
                block_lines = []
            continue

        closing_pattern = rf"{re.escape(opening_marker[0])}{{{len(opening_marker)},}}\s*"
        if re.fullmatch(closing_pattern, line) is not None:
            blocks.append("\n".join(block_lines))
            opening_marker = None
            continue

        block_lines.append(line)

    if opening_marker is not None:
        raise ValueError("フェンス付きコードブロックが閉じられていない")
    if len(blocks) != 1:
        raise ValueError(f"フェンス付きコードブロックは 1 つ必要: {len(blocks)} 個")

    content = blocks[0]
    if not content.splitlines() or content.splitlines()[0] != FRONTMATTER_DELIMITER:
        raise ValueError("フェンス内容の先頭が frontmatter の開始行ではない")
    return content


def parse_fenced_frontmatter(text: str) -> tuple[set[str], str]:
    """単一フェンス内の先頭 frontmatter のキー集合と本文を解析する。

    Args:
        text: 検査するテンプレート全体の文字列。

    Returns:
        frontmatter のキー集合と、終了区切り行より後の本文。

    Raises:
        ValueError: frontmatter の終了行またはキー行を解析できない場合。
    """
    content = extract_single_fenced_block(text)
    lines = content.splitlines()

    try:
        frontmatter_end = lines.index(FRONTMATTER_DELIMITER, 1)
    except ValueError as error:
        raise ValueError("フェンス内容の frontmatter が閉じられていない") from error

    keys: set[str] = set()
    for line in lines[1:frontmatter_end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key_match = FRONTMATTER_KEY_PATTERN.match(line)
        if key_match is None:
            raise ValueError(f"frontmatter のキー行を解析できない: {line}")
        keys.add(key_match.group("key"))

    return keys, "\n".join(lines[frontmatter_end + 1 :])


def require_frontmatter_keys(text: str, required_keys: set[str]) -> set[str]:
    """単一フェンス内の frontmatter に必要なキーが揃うことを検査する。

    Args:
        text: 検査するテンプレート全体の文字列。
        required_keys: 必須とする frontmatter キーの集合。

    Returns:
        解析した frontmatter キーの集合。

    Raises:
        ValueError: 必須キーが不足している場合。
    """
    keys, _ = parse_fenced_frontmatter(text)
    missing_keys = required_keys - keys
    if missing_keys:
        raise ValueError(f"必須キーが不足している: {', '.join(sorted(missing_keys))}")
    return keys


def require_frontmatter_keys_absent(text: str, forbidden_keys: set[str]) -> set[str]:
    """単一フェンス内の frontmatter に禁止キーがないことを検査する。

    Args:
        text: 検査するテンプレート全体の文字列。
        forbidden_keys: 存在してはならない frontmatter キーの集合。

    Returns:
        解析した frontmatter キーの集合。

    Raises:
        ValueError: 禁止キーが存在する場合。
    """
    keys, _ = parse_fenced_frontmatter(text)
    present_keys = forbidden_keys & keys
    if present_keys:
        raise ValueError(f"禁止キーが存在する: {', '.join(sorted(present_keys))}")
    return keys


def parse_table_row(line: str) -> list[str]:
    """Markdown 表の 1 行をセル配列へ分解する。

    Args:
        line: パイプで始まり終わる Markdown 表の行。

    Returns:
        前後の空白を除いたセル文字列の配列。

    Raises:
        ValueError: Markdown 表の行ではない場合。
    """
    stripped_line = line.strip()
    if not stripped_line.startswith("|") or not stripped_line.endswith("|"):
        raise ValueError(f"Markdown 表の行ではない: {line}")
    return [cell.strip() for cell in stripped_line[1:-1].split("|")]


def is_table_separator(line: str, column_count: int) -> bool:
    """Markdown 表の区切り行が指定列数に一致するかを判定する。

    Args:
        line: 検査する表の区切り行。
        column_count: ヘッダーに期待するセル数。

    Returns:
        区切り行として有効で、セル数も一致するとき ``True``。
    """
    try:
        cells = parse_table_row(line)
    except ValueError:
        return False
    return len(cells) == column_count and all(
        TABLE_SEPARATOR_CELL_PATTERN.fullmatch(cell) is not None for cell in cells
    )


def extract_named_table_rows(text: str, heading: str) -> list[list[str]]:
    """フェンス本文の指定見出し直下にある表のデータ行を取り出す。

    Args:
        text: 検査するテンプレート全体の文字列。
        heading: 表を持つ ``##`` 見出しの表示名。

    Returns:
        見出し直下の Markdown 表にあるデータ行のセル配列。

    Raises:
        ValueError: 見出し、表、または表の区切り行を見つけられない場合。
    """
    _, body = parse_fenced_frontmatter(text)
    lines = body.splitlines()
    heading_line = f"## {heading}"

    try:
        heading_index = lines.index(heading_line)
    except ValueError as error:
        raise ValueError(f"見出しがない: {heading_line}") from error

    table_index: int | None = None
    for index in range(heading_index + 1, len(lines)):
        line = lines[index]
        if line.startswith("#"):
            break
        if line.strip().startswith("|") and line.strip().endswith("|"):
            table_index = index
            break

    if table_index is None:
        raise ValueError(f"見出し「{heading}」の表がない")

    header_cells = parse_table_row(lines[table_index])
    separator_index = table_index + 1
    if separator_index >= len(lines) or not is_table_separator(
        lines[separator_index], len(header_cells)
    ):
        raise ValueError(f"見出し「{heading}」の表に有効な区切り行がない")

    rows: list[list[str]] = []
    for line in lines[separator_index + 1 :]:
        if not line.strip().startswith("|") or not line.strip().endswith("|"):
            break
        rows.append(parse_table_row(line))
    return rows


def require_evidence_field_names(text: str, required_names: set[str]) -> set[str]:
    """証跡表の項目列に必要な欄が揃うことを検査する。

    Args:
        text: 検査する結果証跡テンプレート全体の文字列。
        required_names: 証跡表の項目列に必要な名前の集合。

    Returns:
        証跡表の項目列から得た名前の集合。

    Raises:
        ValueError: 必須の証跡欄が不足している場合。
    """
    field_names = {
        row[0]
        for row in extract_named_table_rows(text, "証跡")
        if row
    }
    missing_names = required_names - field_names
    if missing_names:
        raise ValueError(f"証跡表の項目が不足している: {', '.join(sorted(missing_names))}")
    return field_names


def require_table_row_count(text: str, heading: str, expected_count: int) -> list[list[str]]:
    """指定表のデータ行数が期待値と一致することを検査する。

    Args:
        text: 検査するテンプレート全体の文字列。
        heading: 行数を検査する表を持つ ``##`` 見出しの表示名。
        expected_count: 期待するデータ行数。

    Returns:
        解析した表のデータ行。

    Raises:
        ValueError: データ行数が期待値と一致しない場合。
    """
    rows = extract_named_table_rows(text, heading)
    if len(rows) != expected_count:
        raise ValueError(
            f"見出し「{heading}」の表の行数が不正: "
            f"期待 {expected_count} 行、実際 {len(rows)} 行"
        )
    return rows


def candidate_sha_markers(text: str) -> set[str]:
    """frontmatter キーまたは本文にある候補 SHA 関連の印を返す。

    Args:
        text: 検査するテンプレート全体の文字列。

    Returns:
        frontmatter キーまたは本文に現れた禁止文字列の集合。
    """
    keys, body = parse_fenced_frontmatter(text)
    return {
        marker
        for marker in FORBIDDEN_CANDIDATE_SHA_MARKERS
        if marker in keys or marker in body
    }


def test_each_template_has_one_fence_with_leading_frontmatter() -> None:
    for filename in TEMPLATE_FILENAMES:
        content = extract_single_fenced_block(load_template(filename))

        assert content.startswith(FRONTMATTER_DELIMITER)


def test_reservation_template_includes_required_frontmatter_keys() -> None:
    keys = require_frontmatter_keys(
        load_template(RESERVATION_TEMPLATE),
        RESERVATION_REQUIRED_KEYS,
    )

    assert RESERVATION_REQUIRED_KEYS <= keys


def test_phase4_template_includes_required_keys_without_release_version() -> None:
    template = load_template(PHASE4_TEMPLATE)
    keys = require_frontmatter_keys(template, EVIDENCE_REQUIRED_KEYS)
    require_frontmatter_keys_absent(template, {"release_version"})

    assert EVIDENCE_REQUIRED_KEYS <= keys
    assert "release_version" not in keys


def test_release_template_includes_all_required_frontmatter_keys() -> None:
    keys = require_frontmatter_keys(
        load_template(RELEASE_TEMPLATE),
        RELEASE_REQUIRED_KEYS,
    )

    assert RELEASE_REQUIRED_KEYS <= keys


def test_result_templates_include_all_evidence_table_fields() -> None:
    for filename in (PHASE4_TEMPLATE, RELEASE_TEMPLATE):
        field_names = require_evidence_field_names(
            load_template(filename),
            REQUIRED_EVIDENCE_FIELD_NAMES,
        )

        assert REQUIRED_EVIDENCE_FIELD_NAMES <= field_names


def test_result_templates_have_expected_acceptance_item_row_counts() -> None:
    expected_row_counts = {
        PHASE4_TEMPLATE: 5,
        RELEASE_TEMPLATE: 8,
    }

    for filename, expected_count in expected_row_counts.items():
        rows = require_table_row_count(
            load_template(filename),
            "合格項目",
            expected_count,
        )

        assert len(rows) == expected_count


def test_templates_do_not_contain_candidate_sha_fields() -> None:
    for filename in TEMPLATE_FILENAMES:
        assert candidate_sha_markers(load_template(filename)) == set()


def test_required_key_check_rejects_a_removed_key() -> None:
    template = load_template(RESERVATION_TEMPLATE)
    modified_template = template.replace('operator: "<実施者>"\n', "", 1)

    assert modified_template != template
    with pytest.raises(ValueError, match="必須キーが不足"):
        require_frontmatter_keys(modified_template, RESERVATION_REQUIRED_KEYS)


def test_fence_check_rejects_two_fenced_blocks() -> None:
    template = load_template(RESERVATION_TEMPLATE)
    modified_template = f"{template}\n```\n追加のフェンス\n```\n"

    with pytest.raises(ValueError, match="1 つ必要"):
        extract_single_fenced_block(modified_template)


def test_phase4_key_check_rejects_release_version() -> None:
    template = load_template(PHASE4_TEMPLATE)
    modified_template = template.replace(
        'attempt_id: "<予約レコードの識別子>"\n---',
        'attempt_id: "<予約レコードの識別子>"\n'
        'release_version: "<vX.Y.Z>"\n---',
        1,
    )

    assert modified_template != template
    with pytest.raises(ValueError, match="禁止キーが存在"):
        require_frontmatter_keys_absent(modified_template, {"release_version"})


def test_acceptance_item_row_count_check_rejects_a_removed_row() -> None:
    template = load_template(PHASE4_TEMPLATE)
    modified_template = template.replace(
        "| 5 | backend・frontend が起動して疎通確認 | `<期待値>` | `<実測値>` |\n",
        "",
        1,
    )

    assert modified_template != template
    with pytest.raises(ValueError, match="表の行数が不正"):
        require_table_row_count(modified_template, "合格項目", 5)
