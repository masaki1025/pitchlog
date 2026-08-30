"""要件書の全構造行と要件主張母集合を双方向で検査する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Pattern, Sequence

DEFAULT_REQUIREMENTS = Path("docs/requirements/requirements-pitchlog-2026-07-22.md")
DEFAULT_CLAIMS = Path("contracts/authz/requirement-claims.json")
DEFAULT_LOCK = Path("contracts/authz/requirement-claims.lock.json")

CLASSIFICATIONS = frozenset({"auth_claim", "out_of_scope"})
DECIDABLE_LOCATIONS = frozenset({"db", "http", "cache"})
TEST_STATUSES = frozenset({"planned", "implemented"})
SOURCE_KINDS = frozenset(
    {
        "blockquote",
        "code_fence",
        "code_line",
        "frontmatter",
        "heading",
        "list_item",
        "paragraph",
        "table_delimiter",
        "table_header",
        "table_row",
        "thematic_break",
    }
)
HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
FR_HEADING_RE = re.compile(r"^(?P<id>(?:FR|NFR)-\d{3}):")
NUMBERED_HEADING_RE = re.compile(r"^(?P<id>\d+(?:\.\d+)*(?:-\d+)?)\b")
BLOCK_HEADING_RE = re.compile(r"^ブロック(?P<id>\d+):")
APPENDIX_HEADING_RE = re.compile(r"^付録(?P<id>[A-F]):")
APPENDIX_ITEM_RE = re.compile(r"^(?P<id>[A-F]-\d+[a-z]?)\b")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
TABLE_DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")
REQ_LINE_ID_RE = re.compile(r"(?:^|/)REQ:\d+(?:$|/)")
TEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ClassificationRule:
    """分類規則の宣言的な適用条件を表す。

    Attributes:
        classification: 規則が割り当てる分類。
        allowed_kinds: 適用できる構造種別。空集合は制限なし。
        allowed_heading_ids: 適用できる親見出し。空集合は制限なし。
        forbidden_source_text_patterns: 原文に一致すると適用できない補助罠。
    """

    classification: str
    allowed_kinds: frozenset[str]
    allowed_heading_ids: frozenset[str]
    forbidden_source_text_patterns: tuple[Pattern[str], ...]


@dataclass(frozen=True)
class BasisRule:
    """層判定の宣言的な根拠を表す。

    Attributes:
        location: 根拠が所有する判定層。
        allowed_classification_rule_ids: 組み合わせられる分類規則。
    """

    location: str
    allowed_classification_rule_ids: frozenset[str]


class CatalogError(Exception):
    """入力または母集合の構造不正を表す。"""


@dataclass(frozen=True)
class SourceItem:
    """要件書から内容非依存で採取した1行を表す。

    Attributes:
        source_id: 親見出しと節内連番からなる安定 ID。
        kind: Markdown 上の構造種別。
        heading_id: 行を所有する直近の見出し ID。
        text: 改行を除く原文。
        digest: 原文の SHA-256 digest。
    """

    source_id: str
    kind: str
    heading_id: str
    text: str
    digest: str


@dataclass(frozen=True)
class Extraction:
    """要件書全体の構造採取結果を表す。

    Attributes:
        items: 空行以外の全構造行。
        heading_ids: 文書順の全見出し ID。
    """

    items: tuple[SourceItem, ...]
    heading_ids: tuple[str, ...]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_blob_digest(data: bytes) -> str:
    """Git blob と同じ SHA-1 digest を返す。

    Args:
        data: 対象ファイルの生バイト列。

    Returns:
        ``git hash-object`` と一致する16進 digest。
    """
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _table_cells(line: str) -> tuple[str, ...] | None:
    if not line.startswith("|") or not line.endswith("|"):
        return None
    return tuple(cell.strip() for cell in line[1:-1].split("|"))


def _is_table_delimiter(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(TABLE_DELIMITER_CELL_RE.fullmatch(cell) for cell in cells)


def _is_table_header(lines: list[str], index: int) -> bool:
    if _table_cells(lines[index]) is None or index + 1 >= len(lines):
        return False
    return _is_table_delimiter(lines[index + 1])


def _explicit_heading_id(title: str) -> str | None:
    for pattern, prefix in (
        (FR_HEADING_RE, ""),
        (NUMBERED_HEADING_RE, "SECTION-"),
        (BLOCK_HEADING_RE, "BLOCK-"),
        (APPENDIX_HEADING_RE, "APPENDIX-"),
        (APPENDIX_ITEM_RE, "APPENDIX-ITEM-"),
    ):
        match = pattern.match(title)
        if match:
            return prefix + match.group("id")
    if title == "pitchlog 要件定義書":
        return "DOC"
    if title == "変更履歴":
        return "CHANGELOG"
    return None


def _heading_id(
    title: str,
    level: int,
    stack: dict[int, str],
    generic_counts: dict[str, int],
) -> str:
    explicit = _explicit_heading_id(title)
    if explicit is not None:
        return explicit
    parent = next((stack[parent_level] for parent_level in range(level - 1, 0, -1)), "DOC")
    generic_counts[parent] += 1
    return f"{parent}/heading-{generic_counts[parent]:03d}"


def _source_kind(lines: list[str], index: int, in_code: bool, in_frontmatter: bool) -> str:
    line = lines[index]
    if in_frontmatter:
        return "frontmatter"
    if line.startswith("```"):
        return "code_fence"
    if in_code:
        return "code_line"
    if HEADING_RE.match(line):
        return "heading"
    if LIST_ITEM_RE.match(line):
        return "list_item"
    if line.startswith(">"):
        return "blockquote"
    if _is_table_delimiter(line):
        return "table_delimiter"
    if _is_table_header(lines, index):
        return "table_header"
    if _table_cells(line) is not None:
        return "table_row"
    if line == "---":
        return "thematic_break"
    return "paragraph"


def extract_source(text: str) -> Extraction:
    """内容による選択をせず、空行以外を全数採取する。

    Args:
        text: 要件書全文。

    Returns:
        構造行と見出し集合。

    Raises:
        CatalogError: 見出し ID が重複する場合。
    """
    lines = text.splitlines()
    stack: dict[int, str] = {}
    generic_heading_counts: dict[str, int] = defaultdict(int)
    item_counts: dict[tuple[str, str], int] = defaultdict(int)
    current_heading = "PREAMBLE"
    headings: list[str] = []
    items: list[SourceItem] = []
    in_code = False
    in_frontmatter = bool(lines and lines[0] == "---")

    for index, line in enumerate(lines):
        if not line:
            continue
        kind = _source_kind(lines, index, in_code, in_frontmatter)
        heading_match = HEADING_RE.match(line)
        if heading_match and not in_code and not in_frontmatter:
            level = len(heading_match.group("marks"))
            heading_id = _heading_id(
                heading_match.group("title"), level, stack, generic_heading_counts
            )
            if heading_id in headings:
                raise CatalogError(f"見出し ID が重複している: {heading_id}")
            stack = {key: value for key, value in stack.items() if key < level}
            stack[level] = heading_id
            current_heading = heading_id
            headings.append(heading_id)

        item_counts[(current_heading, kind)] += 1
        ordinal = item_counts[(current_heading, kind)]
        source_id = f"{current_heading}/{kind}-{ordinal:03d}"
        items.append(
            SourceItem(
                source_id=source_id,
                kind=kind,
                heading_id=current_heading,
                text=line,
                digest=_sha256(line),
            )
        )

        if line.startswith("```") and not in_frontmatter:
            in_code = not in_code
        if in_frontmatter and index > 0 and line == "---":
            in_frontmatter = False

    if in_code:
        raise CatalogError("閉じていないコードフェンスがある")
    return Extraction(tuple(items), tuple(headings))


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise CatalogError(f"{label}を読めない: {path}: {error}") from error


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise CatalogError(f"{label}を読めない: {path}: {error}") from error


def _read_json(path: Path, label: str = "母集合") -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CatalogError(f"{label}を読めない: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise CatalogError(f"{label}の JSON が不正: {path}: {error}") from error


def _expect_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise CatalogError(
            f"{label}のキー不一致: 不足={missing}, 未知={unknown}"
        )


def _expect_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{label}は空でない文字列でなければならない")
    return value


def _expect_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CatalogError(f"{label}は文字列配列でなければならない")
    if len(value) != len(set(value)):
        raise CatalogError(f"{label}に重複がある")
    return value


def _validate_manifest(
    raw: object,
    extraction: Extraction,
    source_bytes: bytes,
    requirements_path: Path,
    root: Path,
) -> None:
    if not isinstance(raw, dict):
        raise CatalogError("input_manifest はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "commit",
            "source_path",
            "scan_start_heading_id",
            "scan_end_heading_id",
            "source_blob_digest",
            "heading_ids",
            "item_counts_by_kind",
        },
        "input_manifest",
    )
    commit = _expect_string(raw["commit"], "input_manifest.commit")
    if not COMMIT_RE.fullmatch(commit):
        raise CatalogError("input_manifest.commit は40桁の小文字16進SHAでなければならない")

    source_path = _expect_string(raw["source_path"], "input_manifest.source_path")
    try:
        actual_path = requirements_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise CatalogError("要件書はリポジトリルート配下でなければならない") from error
    if source_path != actual_path:
        raise CatalogError(
            f"input_manifest.source_path が入力と不一致: 期待={source_path}, 実際={actual_path}"
        )

    source_digest = _expect_string(raw["source_blob_digest"], "source_blob_digest")
    actual_digest = git_blob_digest(source_bytes)
    if source_digest != actual_digest:
        raise CatalogError(
            f"source blob digest が不一致: 期待={source_digest}, 実際={actual_digest}"
        )

    heading_ids = _expect_string_list(raw["heading_ids"], "input_manifest.heading_ids")
    if heading_ids != list(extraction.heading_ids):
        missing = sorted(set(heading_ids) - set(extraction.heading_ids))
        unknown = sorted(set(extraction.heading_ids) - set(heading_ids))
        raise CatalogError(f"走査見出し集合が不一致: 不足={missing}, 未登録={unknown}")
    if not heading_ids:
        raise CatalogError("走査見出し集合は空にできない")
    if raw["scan_start_heading_id"] != heading_ids[0]:
        raise CatalogError("scan_start_heading_id が見出し集合の先頭と一致しない")
    if raw["scan_end_heading_id"] != heading_ids[-1]:
        raise CatalogError("scan_end_heading_id が見出し集合の末尾と一致しない")

    counts = raw["item_counts_by_kind"]
    if not isinstance(counts, dict) or set(counts) != SOURCE_KINDS:
        raise CatalogError("item_counts_by_kind は全 source kind の閉集合でなければならない")
    actual_counts = Counter(item.kind for item in extraction.items)
    invalid_count = any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in counts.values()
    )
    if invalid_count:
        raise CatalogError("item_counts_by_kind の件数は0以上の整数でなければならない")
    if counts != {kind: actual_counts[kind] for kind in sorted(SOURCE_KINDS)}:
        raise CatalogError("item_counts_by_kind が全数採取結果と一致しない")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _table_digest(value: object) -> str:
    return _sha256(_canonical_json(value))


def _parse_classification_rules(raw: object) -> dict[str, ClassificationRule]:
    if not isinstance(raw, dict) or not raw:
        raise CatalogError("classification_rules は空でないオブジェクトでなければならない")
    rules: dict[str, ClassificationRule] = {}
    for rule_id, value in raw.items():
        label = f"classification_rules.{rule_id}"
        if not isinstance(rule_id, str) or not TEST_ID_RE.fullmatch(rule_id):
            raise CatalogError(f"不正な classification_rule_id: {rule_id!r}")
        if not isinstance(value, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(
            value,
            {
                "classification",
                "allowed_source_kinds",
                "allowed_heading_ids",
                "forbidden_source_text_patterns",
            },
            label,
        )
        classification = _expect_string(value["classification"], f"{label}.classification")
        if classification not in CLASSIFICATIONS:
            raise CatalogError(f"{label}.classification が閉じた値域にない")
        kinds = _expect_string_list(value["allowed_source_kinds"], f"{label}.allowed_source_kinds")
        unknown_kinds = sorted(set(kinds) - SOURCE_KINDS)
        if unknown_kinds:
            raise CatalogError(f"{label}.allowed_source_kinds に未知値がある: {unknown_kinds}")
        headings = _expect_string_list(value["allowed_heading_ids"], f"{label}.allowed_heading_ids")
        pattern_texts = _expect_string_list(
            value["forbidden_source_text_patterns"],
            f"{label}.forbidden_source_text_patterns",
        )
        try:
            patterns = tuple(re.compile(pattern) for pattern in pattern_texts)
        except re.error as error:
            raise CatalogError(f"{label}の正規表現が不正: {error}") from error
        rules[rule_id] = ClassificationRule(
            classification=classification,
            allowed_kinds=frozenset(kinds),
            allowed_heading_ids=frozenset(headings),
            forbidden_source_text_patterns=patterns,
        )
    if {rule.classification for rule in rules.values()} != CLASSIFICATIONS:
        raise CatalogError("classification_rules は2つの classification をすべて持たねばならない")
    return rules


def _parse_basis_rules(
    raw: object, classification_rules: dict[str, ClassificationRule]
) -> dict[str, BasisRule]:
    if not isinstance(raw, dict) or not raw:
        raise CatalogError("basis_rules は空でないオブジェクトでなければならない")
    auth_rule_ids = {
        rule_id
        for rule_id, rule in classification_rules.items()
        if rule.classification == "auth_claim"
    }
    rules: dict[str, BasisRule] = {}
    for basis_id, value in raw.items():
        label = f"basis_rules.{basis_id}"
        if not isinstance(basis_id, str) or not TEST_ID_RE.fullmatch(basis_id):
            raise CatalogError(f"不正な basis_rule_id: {basis_id!r}")
        if not isinstance(value, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(value, {"location", "allowed_classification_rule_ids"}, label)
        location = _expect_string(value["location"], f"{label}.location")
        if location not in DECIDABLE_LOCATIONS:
            raise CatalogError(f"{label}.location が閉じた値域にない: {location}")
        allowed = _expect_string_list(
            value["allowed_classification_rule_ids"],
            f"{label}.allowed_classification_rule_ids",
        )
        if not allowed or not set(allowed) <= auth_rule_ids:
            raise CatalogError(f"{label}は既知の AUTH 分類規則だけを指定しなければならない")
        rules[basis_id] = BasisRule(location, frozenset(allowed))
    if {rule.location for rule in rules.values()} != DECIDABLE_LOCATIONS:
        raise CatalogError("basis_rules は db/http/cache をすべて持たねばならない")
    return rules


def _validate_decidable_at(
    raw: object,
    source_id: str,
    classification_rule_id: str,
    basis_rules: dict[str, BasisRule],
) -> None:
    if not isinstance(raw, list) or not raw:
        raise CatalogError(f"{source_id}: decidable_at は空でない配列でなければならない")
    locations: list[str] = []
    for index, decision in enumerate(raw):
        label = f"{source_id}: decidable_at[{index}]"
        if not isinstance(decision, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(decision, {"location", "basis_rule_id", "test_owner"}, label)
        location = _expect_string(decision["location"], f"{label}.location")
        if location not in DECIDABLE_LOCATIONS:
            raise CatalogError(f"{label}.location が閉じた値域にない: {location}")
        locations.append(location)
        basis_id = _expect_string(decision["basis_rule_id"], f"{label}.basis_rule_id")
        basis = basis_rules.get(basis_id)
        if basis is None:
            raise CatalogError(f"{label}.basis_rule_id が閉じた値域にない: {basis_id}")
        if basis.location != location:
            raise CatalogError(f"{label}: location と basis_rule_id が不一致")
        if classification_rule_id not in basis.allowed_classification_rule_ids:
            raise CatalogError(
                f"{label}: {basis_id} を classification_rule_id="
                f"{classification_rule_id} へ適用できない"
            )
        test_owner = decision["test_owner"]
        if not isinstance(test_owner, dict):
            raise CatalogError(f"{label}.test_owner はオブジェクトでなければならない")
        _expect_keys(test_owner, {"id", "status"}, f"{label}.test_owner")
        test_id = _expect_string(test_owner["id"], f"{label}.test_owner.id")
        if not TEST_ID_RE.fullmatch(test_id):
            raise CatalogError(f"{label}.test_owner.id の形式が不正: {test_id}")
        status = _expect_string(test_owner["status"], f"{label}.test_owner.status")
        if status not in TEST_STATUSES:
            raise CatalogError(f"{label}.test_owner.status が閉じた値域にない: {status}")
    if len(locations) != len(set(locations)):
        raise CatalogError(f"{source_id}: decidable_at の location が重複している")


def _validate_rule_applicability(
    rule: ClassificationRule,
    rule_id: str,
    source_id: str,
    source_kind: str,
    heading_id: str,
    source_text: str,
) -> None:
    """データ側の宣言規則による補助罠を検査する。

    この罠はあからさまな取り違えを拾うだけで、分類の主たる防御ではない。
    分類と層の決定は、別ファイルの decision lock との完全一致で守る。

    Args:
        rule: 母集合に定義された分類規則。
        rule_id: 分類規則 ID。
        source_id: 対象行の安定 ID。
        source_kind: 対象行の構造種別。
        heading_id: 対象行の親見出し ID。
        source_text: 対象行の原文。
    """
    if rule.allowed_kinds and source_kind not in rule.allowed_kinds:
        raise CatalogError(
            f"{source_id}: {rule_id} を source_kind={source_kind} へ適用できない"
        )
    if rule.allowed_heading_ids and heading_id not in rule.allowed_heading_ids:
        raise CatalogError(
            f"{source_id}: {rule_id} を source_heading_id={heading_id} へ適用できない"
        )
    if any(pattern.search(source_text) for pattern in rule.forbidden_source_text_patterns):
        raise CatalogError(f"{source_id}: 宣言された認可規範罠により {rule_id} を適用できない")


def decision_projection(claim: dict[str, object]) -> dict[str, object]:
    """分類決定を順序非依存の表現へ正規化する。

    Args:
        claim: スキーマ検査済みの主張。

    Returns:
        digest と差分表示に使う決定投影。
    """
    projection: dict[str, object] = {
        "source_id": claim["source_id"],
        "classification": claim["classification"],
        "classification_rule_id": claim["classification_rule_id"],
        "source_text_digest": claim["source_text_digest"],
    }
    if claim["classification"] == "auth_claim":
        decisions = claim["decidable_at"]
        assert isinstance(decisions, list)
        normalized = sorted(
            (
                {
                    "location": decision["location"],
                    "basis_rule_id": decision["basis_rule_id"],
                    "test_owner": decision["test_owner"],
                }
                for decision in decisions
                if isinstance(decision, dict)
            ),
            key=lambda decision: str(decision["location"]),
        )
        projection["layer"] = claim["layer"]
        projection["decidable_at"] = normalized
    return projection


def compute_decision_digest(claim: dict[str, object]) -> str:
    """主張の分類決定 digest を返す。

    Args:
        claim: スキーマ検査済みの主張。

    Returns:
        正規化した決定の SHA-256 digest。
    """
    return _table_digest(decision_projection(claim))


def _validate_claim(
    raw: object,
    classification_rules: dict[str, ClassificationRule],
    basis_rules: dict[str, BasisRule],
    layer_ids: frozenset[str],
    *,
    verify_decision_digest: bool,
) -> tuple[str, str, str, str, str, str]:
    if not isinstance(raw, dict):
        raise CatalogError("claims の各要素はオブジェクトでなければならない")
    common = {
        "source_id",
        "source_kind",
        "source_heading_id",
        "source_text",
        "source_text_digest",
        "classification",
        "classification_rule_id",
    }
    if verify_decision_digest:
        common.add("decision_digest")
    elif "decision_digest" in raw:
        common.add("decision_digest")
    classification = raw.get("classification")
    if classification == "auth_claim":
        expected = common | {"layer", "decidable_at"}
    elif classification == "out_of_scope":
        expected = common
    else:
        raise CatalogError(f"classification が閉じた値域にない: {classification!r}")
    _expect_keys(raw, expected, "claim")

    source_id = _expect_string(raw["source_id"], "claim.source_id")
    if REQ_LINE_ID_RE.search(source_id):
        raise CatalogError(f"安定 ID に REQ:<行番号> を使っている: {source_id}")
    source_kind = _expect_string(raw["source_kind"], f"{source_id}.source_kind")
    if source_kind not in SOURCE_KINDS:
        raise CatalogError(f"{source_id}: source_kind が閉じた値域にない: {source_kind}")
    heading_id = _expect_string(raw["source_heading_id"], f"{source_id}.source_heading_id")
    source_text = _expect_string(raw["source_text"], f"{source_id}.source_text")
    digest = _expect_string(raw["source_text_digest"], f"{source_id}.source_text_digest")
    if not SHA256_RE.fullmatch(digest) or digest != _sha256(source_text):
        raise CatalogError(f"{source_id}: source_text_digest が原文と一致しない")

    rule_id = _expect_string(raw["classification_rule_id"], f"{source_id}.classification_rule_id")
    rule = classification_rules.get(rule_id)
    if rule is None:
        raise CatalogError(f"{source_id}: 未知の classification_rule_id: {rule_id}")
    if rule.classification != classification:
        raise CatalogError(
            f"{source_id}: classification と規則が不一致: {classification}/{rule_id}"
        )
    _validate_rule_applicability(
        rule, rule_id, source_id, source_kind, heading_id, source_text
    )

    if classification == "auth_claim":
        layer = _expect_string(raw["layer"], f"{source_id}.layer")
        if layer not in layer_ids:
            raise CatalogError(f"{source_id}: layer が閉じた値域にない: {layer}")
        _validate_decidable_at(raw["decidable_at"], source_id, rule_id, basis_rules)
    if verify_decision_digest:
        decision_digest = _expect_string(raw["decision_digest"], f"{source_id}.decision_digest")
        expected_digest = compute_decision_digest(raw)
        if not SHA256_RE.fullmatch(decision_digest) or decision_digest != expected_digest:
            raise CatalogError(
                f"{source_id}: decision_digest が現在の分類決定と一致しない"
            )
    return source_id, source_kind, heading_id, source_text, digest, classification


def _catalog_tables(
    raw: dict[str, object],
) -> tuple[dict[str, ClassificationRule], dict[str, BasisRule], frozenset[str]]:
    classification_rules = _parse_classification_rules(raw["classification_rules"])
    basis_rules = _parse_basis_rules(raw["basis_rules"], classification_rules)
    layer_values = _expect_string_list(raw["layer_ids"], "layer_ids")
    if not layer_values or layer_values != sorted(layer_values):
        raise CatalogError("layer_ids は空でないソート済み閉集合でなければならない")
    return classification_rules, basis_rules, frozenset(layer_values)


def validate_catalog(
    raw: object,
    extraction: Extraction,
    source_bytes: bytes,
    requirements_path: Path,
    root: Path,
    *,
    verify_decision_digests: bool = True,
) -> Counter[str]:
    """母集合のスキーマと全数採取結果との exact-set を検査する。

    Args:
        raw: JSON から読んだ母集合。
        extraction: 要件書の構造採取結果。
        source_bytes: 要件書の生バイト列。
        requirements_path: 検査対象要件書のパス。
        root: リポジトリルート。
        verify_decision_digests: 各行の既存凍結 digest を検査するか。

    Returns:
        classification ごとの件数。

    Raises:
        CatalogError: スキーマ不正または exact-set 不一致の場合。
    """
    if not isinstance(raw, dict):
        raise CatalogError("母集合のルートはオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "input_manifest",
            "classification_rules",
            "basis_rules",
            "layer_ids",
            "claims",
        },
        "母集合",
    )
    if raw["schema_version"] != 1:
        raise CatalogError("schema_version は1でなければならない")
    classification_rules, basis_rules, layer_ids = _catalog_tables(raw)
    _validate_manifest(raw["input_manifest"], extraction, source_bytes, requirements_path, root)

    claims = raw["claims"]
    if not isinstance(claims, list):
        raise CatalogError("claims は配列でなければならない")
    validated = [
        _validate_claim(
            claim,
            classification_rules,
            basis_rules,
            layer_ids,
            verify_decision_digest=verify_decision_digests,
        )
        for claim in claims
    ]
    claim_ids = [claim[0] for claim in validated]
    if len(claim_ids) != len(set(claim_ids)):
        duplicates = sorted(
            identifier for identifier, count in Counter(claim_ids).items() if count > 1
        )
        raise CatalogError(f"source_id が重複している: {duplicates}")

    expected_by_id = {item.source_id: item for item in extraction.items}
    actual_by_id = {claim[0]: claim for claim in validated}
    missing = sorted(set(expected_by_id) - set(actual_by_id))
    unknown = sorted(set(actual_by_id) - set(expected_by_id))
    if missing or unknown:
        raise CatalogError(
            f"全数採取行との exact-set 不一致: 母集合不足={missing}, 未登録入力={unknown}"
        )
    if claim_ids != [item.source_id for item in extraction.items]:
        raise CatalogError("claims は要件書の構造順と一致しなければならない")

    for source_id, kind, heading_id, text, digest, _classification in validated:
        expected = expected_by_id[source_id]
        actual = (kind, heading_id, text, digest)
        wanted = (expected.kind, expected.heading_id, expected.text, expected.digest)
        if actual != wanted:
            raise CatalogError(f"{source_id}: 構造属性または原文 digest が入力と一致しない")
    return Counter(claim[5] for claim in validated)


def _decision_entries(catalog: dict[str, object]) -> list[dict[str, object]]:
    claims = catalog["claims"]
    assert isinstance(claims, list)
    entries: list[dict[str, object]] = []
    for claim in claims:
        assert isinstance(claim, dict)
        projection = decision_projection(claim)
        entries.append({**projection, "decision_digest": _table_digest(projection)})
    return entries


def _aggregate_decision_digest(entries: Sequence[object]) -> str:
    digest_entries = [
        {
            "source_id": entry["source_id"],
            "decision_digest": entry["decision_digest"],
        }
        for entry in entries
        if isinstance(entry, dict)
    ]
    return _table_digest(digest_entries)


def build_decision_lock(
    catalog: dict[str, object], catalog_path: str
) -> dict[str, object]:
    """母集合の決定を別ファイル用の凍結値にする。

    Args:
        catalog: スキーマ検査済みの母集合。
        catalog_path: リポジトリ相対の母集合パス。

    Returns:
        行別 digest と全行集約 digest を持つ lock。
    """
    entries = _decision_entries(catalog)
    return {
        "schema_version": 1,
        "catalog_path": catalog_path,
        "classification_rules_digest": _table_digest(catalog["classification_rules"]),
        "basis_rules_digest": _table_digest(catalog["basis_rules"]),
        "layer_ids_digest": _table_digest(catalog["layer_ids"]),
        "decision_count": len(entries),
        "aggregate_decision_digest": _aggregate_decision_digest(entries),
        "decisions": entries,
    }


def _validate_lock_structure(raw: object, catalog_path: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise CatalogError("decision lock のルートはオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "catalog_path",
            "classification_rules_digest",
            "basis_rules_digest",
            "layer_ids_digest",
            "decision_count",
            "aggregate_decision_digest",
            "decisions",
        },
        "decision lock",
    )
    if raw["schema_version"] != 1:
        raise CatalogError("decision lock.schema_version は1でなければならない")
    if raw["catalog_path"] != catalog_path:
        raise CatalogError(
            f"decision lock.catalog_path が不一致: "
            f"期待={catalog_path}, 実際={raw['catalog_path']}"
        )
    for key in (
        "classification_rules_digest",
        "basis_rules_digest",
        "layer_ids_digest",
        "aggregate_decision_digest",
    ):
        value = _expect_string(raw[key], f"decision lock.{key}")
        if not SHA256_RE.fullmatch(value):
            raise CatalogError(f"decision lock.{key} は SHA-256 digest でなければならない")
    decisions = raw["decisions"]
    if not isinstance(decisions, list):
        raise CatalogError("decision lock.decisions は配列でなければならない")
    decision_count = raw["decision_count"]
    if (
        not isinstance(decision_count, int)
        or isinstance(decision_count, bool)
        or decision_count != len(decisions)
    ):
        raise CatalogError("decision lock.decision_count が decisions の件数と一致しない")
    source_ids: list[str] = []
    for index, entry in enumerate(decisions):
        label = f"decision lock.decisions[{index}]"
        if not isinstance(entry, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        classification = entry.get("classification")
        common = {
            "source_id",
            "classification",
            "classification_rule_id",
            "source_text_digest",
            "decision_digest",
        }
        expected = common | {"layer", "decidable_at"} if classification == "auth_claim" else common
        _expect_keys(entry, expected, label)
        source_id = _expect_string(entry["source_id"], f"{label}.source_id")
        source_ids.append(source_id)
        digest = _expect_string(entry["decision_digest"], f"{label}.decision_digest")
        projection = {key: value for key, value in entry.items() if key != "decision_digest"}
        if not SHA256_RE.fullmatch(digest) or digest != _table_digest(projection):
            raise CatalogError(f"{source_id}: lock 内の decision_digest が決定と一致しない")
    if len(source_ids) != len(set(source_ids)):
        raise CatalogError("decision lock の source_id が重複している")
    if raw["aggregate_decision_digest"] != _aggregate_decision_digest(decisions):
        raise CatalogError("decision lock の全行集約 digest が decisions と一致しない")
    return raw


def decision_lock_differences(
    catalog: dict[str, object], lock: dict[str, object]
) -> list[str]:
    """母集合と lock の決定差分を行 ID 単位で返す。

    Args:
        catalog: スキーマ検査済みの母集合。
        lock: 構造検査済みの decision lock。

    Returns:
        ``source_id`` と変更前後の値を含む差分。
    """
    expected_entries = lock["decisions"]
    assert isinstance(expected_entries, list)
    actual_entries = _decision_entries(catalog)
    expected_by_id = {
        str(entry["source_id"]): entry
        for entry in expected_entries
        if isinstance(entry, dict) and "source_id" in entry
    }
    actual_by_id = {str(entry["source_id"]): entry for entry in actual_entries}
    differences: list[str] = []
    missing = sorted(set(expected_by_id) - set(actual_by_id))
    added = sorted(set(actual_by_id) - set(expected_by_id))
    differences.extend(f"{source_id}: 決定が母集合から消失" for source_id in missing)
    differences.extend(f"{source_id}: lock にない決定が追加" for source_id in added)
    for source_id in sorted(set(expected_by_id) & set(actual_by_id)):
        expected = expected_by_id[source_id]
        actual = actual_by_id[source_id]
        fields = (set(expected) | set(actual)) - {"source_id", "decision_digest"}
        changed = [field for field in sorted(fields) if expected.get(field) != actual.get(field)]
        if not changed and expected.get("decision_digest") != actual.get("decision_digest"):
            changed = ["decision_digest"]
        for field in changed:
            differences.append(
                f"{source_id}: {field} が変更: "
                f"lock={expected.get(field)!r}, catalog={actual.get(field)!r}"
            )
    return differences


def validate_decision_lock(
    catalog: dict[str, object], raw_lock: object, catalog_path: str
) -> None:
    """母集合の規則表と全決定がlockに完全一致するか検査する。

    Args:
        catalog: スキーマ検査済みの母集合。
        raw_lock: JSON から読んだ decision lock。
        catalog_path: リポジトリ相対の母集合パス。

    Raises:
        CatalogError: lock 自体の破損または凍結決定との差分がある場合。
    """
    lock = _validate_lock_structure(raw_lock, catalog_path)
    table_checks = {
        "classification_rules": (
            lock["classification_rules_digest"],
            _table_digest(catalog["classification_rules"]),
        ),
        "basis_rules": (
            lock["basis_rules_digest"],
            _table_digest(catalog["basis_rules"]),
        ),
        "layer_ids": (
            lock["layer_ids_digest"],
            _table_digest(catalog["layer_ids"]),
        ),
    }
    table_differences = [
        f"{name} が凍結値から変更: lock={expected}, catalog={actual}"
        for name, (expected, actual) in table_checks.items()
        if expected != actual
    ]
    differences = table_differences + decision_lock_differences(catalog, lock)
    if differences:
        raise CatalogError("decision lock と不一致:\n" + "\n".join(differences))


def reseal_catalog(catalog: dict[str, object], catalog_path: str) -> dict[str, object]:
    """各行 digest を更新し、新しい decision lock を作る。

    Args:
        catalog: 構造検査済みの母集合。
        catalog_path: リポジトリ相対の母集合パス。

    Returns:
        更新した母集合に対応する decision lock。
    """
    claims = catalog["claims"]
    assert isinstance(claims, list)
    for claim in claims:
        assert isinstance(claim, dict)
        claim["decision_digest"] = compute_decision_digest(claim)
    return build_decision_lock(catalog, catalog_path)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        解釈済み引数。
    """
    parser = argparse.ArgumentParser(description="認可要件主張母集合を全数検査する")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="リポジトリルート")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--reseal",
        action="store_true",
        help="分類決定の査読後に限り、母集合と lock の digest を明示更新する",
    )
    return parser.parse_args(argv)


def _verify_manifest_commit(root: Path, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    manifest = raw.get("input_manifest")
    if not isinstance(manifest, dict):
        return
    commit = manifest.get("commit")
    source_path = manifest.get("source_path")
    if (
        not isinstance(commit, str)
        or not isinstance(source_path, str)
        or not (root / ".git").exists()
    ):
        return
    availability = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if availability.returncode != 0:
        # CI の shallow checkout では入力 commit 自体が手元にない。現物は blob digest で検査する。
        return
    result = subprocess.run(
        ["git", "rev-parse", f"{commit}:{source_path}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    expected = manifest.get("source_blob_digest")
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise CatalogError("input commit 上の source blob がマニフェストと一致しない")


def _relative_path(root: Path, path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise CatalogError(f"{label}はリポジトリルート配下でなければならない") from error


def _write_json(path: Path, value: object, label: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise CatalogError(f"{label}を書けない: {path}: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    """母集合検査を実行し、違反の有無に応じた終了コードを返す。

    Args:
        argv: テスト時に指定する引数列。省略時はコマンドライン引数を使う。

    Returns:
        違反なしなら0、入力または母集合が不正なら1。
    """
    try:
        args = parse_args(argv)
        root = args.root.resolve()
        requirements_path = _resolve(root, args.requirements)
        claims_path = _resolve(root, args.claims)
        lock_path = _resolve(root, args.lock)
        catalog_relative_path = _relative_path(root, claims_path, "母集合")
        source_bytes = _read_bytes(requirements_path, "要件書")
        try:
            source_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CatalogError(f"要件書がUTF-8でない: {requirements_path}: {error}") from error
        extraction = extract_source(source_text)
        raw = _read_json(claims_path)
        counts = validate_catalog(
            raw,
            extraction,
            source_bytes,
            requirements_path,
            root,
            verify_decision_digests=not args.reseal,
        )
        _verify_manifest_commit(root, raw)
        if not isinstance(raw, dict):
            raise CatalogError("母集合のルートはオブジェクトでなければならない")
        if args.reseal:
            lock = reseal_catalog(raw, catalog_relative_path)
            _write_json(claims_path, raw, "母集合")
            _write_json(lock_path, lock, "decision lock")
        else:
            raw_lock = _read_json(lock_path, "decision lock")
            validate_decision_lock(raw, raw_lock, catalog_relative_path)
    except CatalogError as error:
        print(f"check_authz_catalog.py: {error}", file=sys.stderr)
        return 1
    print(
        "check_authz_catalog.py: "
        f"ok total={sum(counts.values())} "
        f"auth_claim={counts['auth_claim']} out_of_scope={counts['out_of_scope']}"
        + (" resealed" if args.reseal else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
