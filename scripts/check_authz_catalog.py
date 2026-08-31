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
from itertools import combinations
from pathlib import Path
from typing import Pattern, Sequence

DEFAULT_REQUIREMENTS = Path("docs/requirements/requirements-pitchlog-2026-07-22.md")
DEFAULT_CLAIMS = Path("contracts/authz/requirement-claims.json")
DEFAULT_LOCK = Path("contracts/authz/requirement-claims.lock.json")
DEFAULT_ROUTE_REGISTRY = Path("contracts/authz/route-registry.json")
DEFAULT_ROUTE_REGISTRY_LOCK = Path("contracts/authz/route-registry.lock.json")
DEFAULT_AUTH_CATALOG = Path("contracts/authz/auth-catalog.json")
DEFAULT_AUTH_CATALOG_LOCK = Path("contracts/authz/auth-catalog.lock.json")
DEFAULT_HTTP_ROUTE_MATRIX = Path("contracts/authz/http-route-matrix.json")
DEFAULT_HTTP_ROUTE_MATRIX_LOCK = Path("contracts/authz/http-route-matrix.lock.json")
DEFAULT_DDL_ELEMENTS = Path("contracts/authz/ddl-elements.json")
DEFAULT_REJECTED_CONFIGS = Path("contracts/authz/rejected-configs.json")
DEFAULT_CLAIM_MUTANT_MAP = Path("contracts/authz/claim-mutant-map.json")
DEFAULT_ATTACK_TREE = Path("contracts/authz/attack-tree.json")
DEFAULT_BOUNDARY_PROPOSAL = Path("contracts/authz/boundary-proposal.json")
DEFAULT_VERIFICATION_EVIDENCE = Path("contracts/authz/verification-evidence.json")
DEFAULT_ORACLE_SEAL = Path("contracts/authz/oracle-seal.lock.json")

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
ROUTE_CLASSES = frozenset({"shared_screen", "shared_aggregate_export"})
RESOURCE_KINDS = frozenset({"team_metrics", "team_summary", "player_metrics"})
CHANNELS = frozenset({"screen", "export"})
ROUTE_KINDS = frozenset(
    {"legacy_route", "shared_data", "control_read", "management_operation"}
)
ORIGINS = frozenset({"requirement", "design"})
FORBIDDEN_RESOURCE_KINDS = frozenset(
    {
        "raw_pitch_events",
        "medical_notes",
        "third_party_data",
        "body_profile_distribution",
    }
)
FORBIDDEN_EVACUATED_IMPORT_TERMS = (
    "退避イベントの取り込み",
    "挿入位置を指定して取り込",
    "IMPORT_EVACUATED_EVENT",
)
ORACLE_CHANGE_POLICY_ID = "ORACLE_STEP5_REREVIEW"
ORACLE_EXECUTION_CLASSES = frozenset({"probe_executable", "contract_only"})
ORACLE_MUTANT_AXES = frozenset(
    {"configuration", "authorization_predicate", "r8_provisioning"}
)
REQUIRED_REJECTION_CONFIGS = {
    "REJ-001": "SECURITY_DEFINER_WITHOUT_BYPASSRLS_OWNER",
    "REJ-002": "FUNCTION_WITH_PUBLIC_EXECUTE_DEFAULT",
    "REJ-003": "SEARCH_PATH_WITHOUT_EXPLICIT_TRAILING_PG_TEMP",
}
REQUIRED_BASE_CONFIGURATION_MUTANT_IDS = frozenset(
    {
        "MUT:CONFIG:CFG_REMOVE_OWNER_BYPASSRLS",
        "MUT:CONFIG:CFG_SWAP_FUNCTION_OWNER",
        "MUT:CONFIG:CFG_OMIT_PUBLIC_REVOKE",
        "MUT:CONFIG:CFG_REMOVE_PG_TEMP_FROM_SEARCH_PATH",
        "MUT:CONFIG:CFG_DISABLE_FORCE_RLS",
        "MUT:CONFIG:CFG_GRANT_ROLE_MEMBERSHIP",
        "MUT:CONFIG:CFG_GRANT_APP_SCHEMA_CREATE",
        "MUT:CONFIG:CFG_GRANT_APP_DATABASE_TEMPORARY",
        "MUT:CONFIG:CFG_GRANT_MANAGEMENT_EXECUTE_TO_APP",
        "MUT:CONFIG:CFG_REMOVE_WITH_CHECK",
        "MUT:CONFIG:CFG_ADD_PERMISSIVE_USING_TRUE",
        "MUT:CONFIG:CFG_SPLIT_MANAGEMENT_AUTHORIZATION_AND_SIDE_EFFECT",
    }
)
REQUIRED_R8_MUTANT_IDS = frozenset(
    {
        "MUT:R8:OMIT-PROVISION-STEP-5-REVOKE",
        "MUT:R8:MOVE-PROVISION-STEP-2-AFTER-STEP-3",
    }
)
REQUIRED_MCDC_OPERATOR_IDS = frozenset(
    {
        "REMOVE_GROUP_ACTIVE",
        "REMOVE_REQUESTER_MEMBERSHIP",
        "REMOVE_TARGET_ACTIVE",
        "USE_OTHER_GROUP_GRANT",
        "OVERAPPLY_SELF_TENANT_EXCEPTION",
        "REMOVE_KIND_SELF_GUARD",
        "REMOVE_EXPORT_SUBORDINATE_GRANT",
        "REMOVE_CONTROL_COMMON_PRECONDITION",
        "REMOVE_OPERATION_ROLE_CONDITION",
        "REMOVE_LAST_ADMIN_INVARIANT",
    }
)
MANAGEMENT_PROBE_CLAIM_IDS = frozenset(
    {
        "ORACLE:MANAGEMENT-PROBE:NO-BASE-TABLE-DML",
        "ORACLE:MANAGEMENT-PROBE:ATOMIC-AUTHORIZATION-SIDE-EFFECT",
    }
)
POSITIVE_CASE_SCOPE_ID = "POSITIVE-CASE-SCOPE:ALL-ALLOW-CELLS"
TABLE_PRIVILEGE_MUTANT_PREFIX = "MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_"
POSITIVE_KILL_MUTANT_IDS = frozenset(
    {
        "MUT:CONFIG:CFG_REMOVE_OWNER_BYPASSRLS",
        "MUT:CONFIG:CFG_SWAP_FUNCTION_OWNER",
    }
)


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


def _expect_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CatalogError(f"{label}は boolean でなければならない")
    return value


def _expect_closed_value(
    value: object, allowed: frozenset[str], label: str
) -> str:
    text = _expect_string(value, label)
    if text not in allowed:
        raise CatalogError(f"{label}が閉じた値域にない: {text}")
    return text


def _auth_claims_by_id(catalog: dict[str, object]) -> dict[str, dict[str, object]]:
    claims = catalog["claims"]
    assert isinstance(claims, list)
    return {
        str(claim["source_id"]): claim
        for claim in claims
        if isinstance(claim, dict) and claim.get("classification") == "auth_claim"
    }


def _db_claims_by_id(catalog: dict[str, object]) -> dict[str, dict[str, object]]:
    auth_claims = _auth_claims_by_id(catalog)
    db_claims: dict[str, dict[str, object]] = {}
    for source_id, claim in auth_claims.items():
        decisions = claim.get("decidable_at")
        if isinstance(decisions, list) and any(
            isinstance(decision, dict) and decision.get("location") == "db"
            for decision in decisions
        ):
            db_claims[source_id] = claim
    return db_claims


def _validate_derived_input_manifest(raw: object, root: Path) -> None:
    if not isinstance(raw, dict):
        raise CatalogError("derived input_manifest はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "requirement_claims_path",
            "requirement_claims_blob_digest",
            "requirement_claims_lock_path",
            "requirement_claims_lock_blob_digest",
        },
        "derived input_manifest",
    )
    path_pairs = (
        ("requirement_claims_path", "requirement_claims_blob_digest"),
        ("requirement_claims_lock_path", "requirement_claims_lock_blob_digest"),
    )
    for path_key, digest_key in path_pairs:
        relative = _expect_string(raw[path_key], f"input_manifest.{path_key}")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as error:
            raise CatalogError(f"{path_key}がリポジトリ外を指している") from error
        digest = _expect_string(raw[digest_key], f"input_manifest.{digest_key}")
        if not path.is_file() or git_blob_digest(_read_bytes(path, path_key)) != digest:
            raise CatalogError(f"{digest_key}が入力資産と一致しない")


def _validate_test_owner(
    raw: object,
    label: str,
    implemented_test_ids: frozenset[str],
) -> None:
    if not isinstance(raw, dict):
        raise CatalogError(f"{label}はオブジェクトでなければならない")
    _expect_keys(raw, {"id", "status"}, label)
    test_id = _expect_string(raw["id"], f"{label}.id")
    if not TEST_ID_RE.fullmatch(test_id):
        raise CatalogError(f"{label}.id の形式が不正: {test_id}")
    status = _expect_closed_value(
        raw["status"], TEST_STATUSES, f"{label}.status"
    )
    if status == "implemented" and test_id not in implemented_test_ids:
        raise CatalogError(f"{label}: implemented test ID が pytest 収集結果にない: {test_id}")


def _validate_source_claim_ids(
    raw: object,
    label: str,
    auth_claims: dict[str, dict[str, object]],
    *,
    required: bool,
) -> list[str]:
    identifiers = _expect_string_list(raw, label)
    if required and not identifiers:
        raise CatalogError(f"{label}は1件以上必要")
    unknown = sorted(set(identifiers) - set(auth_claims))
    if unknown:
        raise CatalogError(f"{label}が母集合の AUTH 主張に存在しない: {unknown}")
    return identifiers


def _validate_design_provenance(raw: object, root: Path) -> frozenset[str]:
    if not isinstance(raw, list) or not raw:
        raise CatalogError("design_provenance は空でない配列でなければならない")
    provenance_ids: list[str] = []
    for index, entry in enumerate(raw):
        label = f"design_provenance[{index}]"
        if not isinstance(entry, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(entry, {"provenance_id", "path", "extracted_text"}, label)
        provenance_id = _expect_string(entry["provenance_id"], f"{label}.provenance_id")
        path_text = _expect_string(entry["path"], f"{label}.path")
        extracted = _expect_string(entry["extracted_text"], f"{label}.extracted_text")
        source_path = (root / path_text).resolve()
        try:
            source_path.relative_to(root.resolve())
        except ValueError as error:
            raise CatalogError(f"{label}.path がリポジトリ外を指している") from error
        source = _read_text(source_path, f"{label}.path")
        if "".join(extracted.split()) not in "".join(source.split()):
            raise CatalogError(f"{label}.extracted_text が原文に逐語一致しない")
        provenance_ids.append(provenance_id)
    if len(provenance_ids) != len(set(provenance_ids)):
        raise CatalogError("design_provenance.provenance_id が重複している")
    return frozenset(provenance_ids)


def validate_route_registry(
    raw: object,
    requirement_catalog: dict[str, object],
    root: Path,
    implemented_test_ids: frozenset[str],
) -> dict[str, object]:
    """閉じた論理経路と管理操作契約を検査する。

    Args:
        raw: route registry の JSON 値。
        requirement_catalog: 検査済み要件主張母集合。
        root: リポジトリルート。
        implemented_test_ids: pytest が実際に収集した node ID。

    Returns:
        route ID、route kind、origin 件数などの検査結果。

    Raises:
        CatalogError: スキーマ、閉集合、典拠、不変条件に違反した場合。
    """
    if not isinstance(raw, dict):
        raise CatalogError("route registry のルートはオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "input_manifest",
            "enums",
            "design_provenance",
            "routes",
            "management_operations",
        },
        "route registry",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_route_registry":
        raise CatalogError("route registry の schema_version または asset_kind が不正")
    _validate_derived_input_manifest(raw["input_manifest"], root)
    provenance_ids = _validate_design_provenance(raw["design_provenance"], root)
    auth_claims = _auth_claims_by_id(requirement_catalog)

    enums = raw["enums"]
    if not isinstance(enums, dict):
        raise CatalogError("route registry.enums はオブジェクトでなければならない")
    _expect_keys(
        enums,
        {
            "origins",
            "route_kinds",
            "route_classes",
            "resource_kinds",
            "channels",
            "control_read_ids",
            "operation_ids",
            "precondition_ids",
            "group_role_requirements",
            "legacy_route_ids",
        },
        "route registry.enums",
    )
    enum_expectations = {
        "origins": ORIGINS,
        "route_kinds": ROUTE_KINDS,
        "route_classes": ROUTE_CLASSES,
        "resource_kinds": RESOURCE_KINDS,
        "channels": CHANNELS,
        "group_role_requirements": frozenset({"none", "admin"}),
    }
    for key, expected in enum_expectations.items():
        values = _expect_string_list(enums[key], f"enums.{key}")
        if frozenset(values) != expected:
            raise CatalogError(f"enums.{key} が閉じた値域と不一致")
    if FORBIDDEN_RESOURCE_KINDS & set(enums["resource_kinds"]):
        raise CatalogError("常に404の資源が resource_kind の値域に存在する")
    control_read_ids = frozenset(
        _expect_string_list(enums["control_read_ids"], "enums.control_read_ids")
    )
    operation_ids = frozenset(
        _expect_string_list(enums["operation_ids"], "enums.operation_ids")
    )
    precondition_ids = frozenset(
        _expect_string_list(enums["precondition_ids"], "enums.precondition_ids")
    )
    legacy_route_ids = frozenset(
        _expect_string_list(enums["legacy_route_ids"], "enums.legacy_route_ids")
    )
    if (
        not control_read_ids
        or not operation_ids
        or not precondition_ids
        or not legacy_route_ids
    ):
        raise CatalogError("経路・制御読取・管理操作・前提条件の enum は空にできない")

    operations = raw["management_operations"]
    if not isinstance(operations, list):
        raise CatalogError("management_operations は配列でなければならない")
    operation_by_id: dict[str, dict[str, object]] = {}
    for index, operation in enumerate(operations):
        label = f"management_operations[{index}]"
        if not isinstance(operation, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(
            operation,
            {
                "operation_id",
                "route_id",
                "precondition_ids",
                "tenant_permission_required",
                "group_role_requirement",
                "source_claim_ids",
                "side_effect_status",
                "test_owner",
            },
            label,
        )
        operation_id = _expect_string(operation["operation_id"], f"{label}.operation_id")
        prerequisites = frozenset(
            _expect_string_list(operation["precondition_ids"], f"{label}.precondition_ids")
        )
        if not prerequisites or not prerequisites <= precondition_ids:
            raise CatalogError(f"{label}.precondition_ids が閉じた値域にない")
        tenant_permission_required = _expect_bool(
            operation["tenant_permission_required"],
            f"{label}.tenant_permission_required",
        )
        if not tenant_permission_required:
            raise CatalogError(f"{label}はテナント側権限を必須としなければならない")
        _expect_closed_value(
            operation["group_role_requirement"],
            frozenset({"none", "admin"}),
            f"{label}.group_role_requirement",
        )
        _validate_source_claim_ids(
            operation["source_claim_ids"],
            f"{label}.source_claim_ids",
            auth_claims,
            required=True,
        )
        if operation["side_effect_status"] != "deferred_tsk_250":
            raise CatalogError(f"{label}.side_effect_status が契約範囲外")
        _validate_test_owner(
            operation["test_owner"], f"{label}.test_owner", implemented_test_ids
        )
        if operation_id in operation_by_id:
            raise CatalogError(f"operation_id が重複している: {operation_id}")
        operation_by_id[operation_id] = operation
    if frozenset(operation_by_id) != operation_ids:
        raise CatalogError("operation_ids と management_operations が exact-set 不一致")

    routes = raw["routes"]
    if not isinstance(routes, list):
        raise CatalogError("routes は配列でなければならない")
    route_by_id: dict[str, dict[str, object]] = {}
    origin_counts: Counter[str] = Counter()
    for index, route in enumerate(routes):
        label = f"routes[{index}]"
        if not isinstance(route, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        common_keys = {"route_id", "route_kind", "origin", "source_claim_ids"}
        route_kind = _expect_closed_value(
            route.get("route_kind"), ROUTE_KINDS, f"{label}.route_kind"
        )
        expected_keys_by_kind = {
            "legacy_route": common_keys
            | {"route_class", "channel", "expected_default", "provenance_ids"},
            "shared_data": common_keys
            | {"route_class", "resource_kind", "channel"},
            "control_read": common_keys | {"control_read_id", "access_requirement"},
            "management_operation": common_keys | {"operation_id"},
        }
        _expect_keys(route, expected_keys_by_kind[route_kind], label)
        route_id = _expect_string(route["route_id"], f"{label}.route_id")
        origin = _expect_closed_value(route["origin"], ORIGINS, f"{label}.origin")
        source_claim_ids = _validate_source_claim_ids(
            route["source_claim_ids"],
            f"{label}.source_claim_ids",
            auth_claims,
            required=origin == "requirement",
        )
        if origin == "design":
            if source_claim_ids:
                raise CatalogError(f"{route_id}: design origin は要件主張を名乗れない")
            route_provenance = frozenset(
                _expect_string_list(route["provenance_ids"], f"{label}.provenance_ids")
            )
            if not route_provenance or not route_provenance <= provenance_ids:
                raise CatalogError(f"{route_id}: design provenance が閉じていない")
        origin_counts[origin] += 1
        if "route_class" in route:
            _expect_closed_value(route["route_class"], ROUTE_CLASSES, f"{label}.route_class")
        if "resource_kind" in route:
            _expect_closed_value(
                route["resource_kind"], RESOURCE_KINDS, f"{label}.resource_kind"
            )
        if "channel" in route:
            _expect_closed_value(route["channel"], CHANNELS, f"{label}.channel")
        if route_kind == "legacy_route" and route["expected_default"] != "deny_404":
            raise CatalogError(f"{route_id}: 既存経路は明示的 deny_404 が必要")
        if route_kind == "control_read":
            if route["control_read_id"] not in control_read_ids:
                raise CatalogError(f"{route_id}: control_read_id が閉じた値域にない")
            _expect_closed_value(
                route["access_requirement"],
                frozenset({"participant", "admin"}),
                f"{label}.access_requirement",
            )
        if route_kind == "management_operation":
            operation_id = route["operation_id"]
            if operation_id not in operation_by_id:
                raise CatalogError(f"{route_id}: operation_id が management contract にない")
            if operation_by_id[str(operation_id)]["route_id"] != route_id:
                raise CatalogError(f"{route_id}: operation の route_id が不一致")
        if route_id in route_by_id:
            raise CatalogError(f"route_id が重複している: {route_id}")
        route_by_id[route_id] = route

    actual_legacy_ids = {
        route_id
        for route_id, route in route_by_id.items()
        if route["route_kind"] == "legacy_route"
    }
    if actual_legacy_ids != legacy_route_ids:
        raise CatalogError("legacy_route_ids と既存経路が exact-set 不一致")
    for route_id in legacy_route_ids:
        route = route_by_id[route_id]
        if route["origin"] != "design":
            raise CatalogError(f"{route_id}: legacy route は design origin が必要")
        heading_id = route_id.removeprefix("ROUTE:")
        if any(
            claim.get("source_heading_id") == heading_id
            for claim in auth_claims.values()
        ):
            raise CatalogError(f"{route_id}: AUTH 主張0件という入力事実と不一致")

    expected_shared_axes = {
        (route_class, resource_kind, channel)
        for route_class in ROUTE_CLASSES
        for resource_kind in RESOURCE_KINDS
        for channel in CHANNELS
    }
    shared_routes = [
        route
        for route in route_by_id.values()
        if route["route_kind"] == "shared_data"
    ]
    actual_shared_axes = {
        (route["route_class"], route["resource_kind"], route["channel"])
        for route in shared_routes
    }
    if (
        actual_shared_axes != expected_shared_axes
        or len(shared_routes) != len(expected_shared_axes)
    ):
        raise CatalogError("shared_data route が3軸直積と exact-set 不一致")
    for route in shared_routes:
        expected_route_id = (
            f"ROUTE:SHARED:{route['route_class']}:"
            f"{route['resource_kind']}:{route['channel']}"
        )
        if route["route_id"] != expected_route_id:
            raise CatalogError(f"{route['route_id']}: 3軸から導出した route_id と不一致")

    control_routes = [
        str(route["control_read_id"])
        for route in route_by_id.values()
        if route["route_kind"] == "control_read"
    ]
    if frozenset(control_routes) != control_read_ids or len(control_routes) != len(
        control_read_ids
    ):
        raise CatalogError("control_read_ids と制御資源 route が exact-set 不一致")
    operation_routes = [
        str(route["operation_id"])
        for route in route_by_id.values()
        if route["route_kind"] == "management_operation"
    ]
    if frozenset(operation_routes) != operation_ids or len(operation_routes) != len(
        operation_ids
    ):
        raise CatalogError("operation_ids と管理 route が exact-set 不一致")
    return {
        "route_by_id": route_by_id,
        "operation_by_id": operation_by_id,
        "origin_counts": origin_counts,
    }


def validate_auth_catalog(
    raw: object,
    requirement_catalog: dict[str, object],
    registry_result: dict[str, object],
    root: Path,
    implemented_test_ids: frozenset[str],
) -> dict[str, object]:
    """DB 判定可能な母集合と AUTH catalog を exact-set で検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("AUTH catalog のルートはオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "input_manifest",
            "origins",
            "route_scopes",
            "entries",
        },
        "AUTH catalog",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_catalog":
        raise CatalogError("AUTH catalog の schema_version または asset_kind が不正")
    _validate_derived_input_manifest(raw["input_manifest"], root)
    if frozenset(_expect_string_list(raw["origins"], "AUTH catalog.origins")) != ORIGINS:
        raise CatalogError("AUTH catalog.origins が閉じた値域と不一致")

    route_scopes = raw["route_scopes"]
    if not isinstance(route_scopes, list) or not route_scopes:
        raise CatalogError("route_scopes は空でない配列でなければならない")
    scope_ids: list[str] = []
    for index, scope in enumerate(route_scopes):
        label = f"route_scopes[{index}]"
        if not isinstance(scope, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(scope, {"route_scope_id", "route_kinds"}, label)
        scope_id = _expect_string(scope["route_scope_id"], f"{label}.route_scope_id")
        kinds = frozenset(_expect_string_list(scope["route_kinds"], f"{label}.route_kinds"))
        if not kinds or not kinds <= ROUTE_KINDS:
            raise CatalogError(f"{label}.route_kinds が閉じた値域にない")
        scope_ids.append(scope_id)
    if len(scope_ids) != len(set(scope_ids)):
        raise CatalogError("route_scope_id が重複している")

    db_claims = _db_claims_by_id(requirement_catalog)
    entries = raw["entries"]
    if not isinstance(entries, list):
        raise CatalogError("AUTH catalog.entries は配列でなければならない")
    by_requirement: dict[str, dict[str, object]] = {}
    catalog_ids: list[str] = []
    for index, entry in enumerate(entries):
        label = f"AUTH catalog.entries[{index}]"
        if not isinstance(entry, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(
            entry,
            {
                "catalog_entry_id",
                "requirement_claim_id",
                "origin",
                "layer",
                "db_basis_rule_id",
                "source_text_digest",
                "route_scope_id",
                "catalog_test_owner",
                "enforcement_test_owner",
            },
            label,
        )
        catalog_id = _expect_string(entry["catalog_entry_id"], f"{label}.catalog_entry_id")
        requirement_id = _expect_string(
            entry["requirement_claim_id"], f"{label}.requirement_claim_id"
        )
        if entry["origin"] != "requirement":
            raise CatalogError(f"{catalog_id}: 母集合対応 entry は requirement origin が必要")
        claim = db_claims.get(requirement_id)
        if claim is None:
            raise CatalogError(f"{catalog_id}: requirement_claim_id が DB 主張に存在しない")
        decisions = claim["decidable_at"]
        assert isinstance(decisions, list)
        db_decisions = [
            decision
            for decision in decisions
            if isinstance(decision, dict) and decision.get("location") == "db"
        ]
        if len(db_decisions) != 1:
            raise CatalogError(f"{requirement_id}: DB decision が一意でない")
        expected_fields = {
            "layer": claim["layer"],
            "db_basis_rule_id": db_decisions[0]["basis_rule_id"],
            "source_text_digest": claim["source_text_digest"],
        }
        for key, expected in expected_fields.items():
            if entry[key] != expected:
                raise CatalogError(f"{catalog_id}: {key} が母集合と一致しない")
        if entry["route_scope_id"] not in scope_ids:
            raise CatalogError(f"{catalog_id}: route_scope_id が閉じた値域にない")
        _validate_test_owner(
            entry["catalog_test_owner"],
            f"{label}.catalog_test_owner",
            implemented_test_ids,
        )
        _validate_test_owner(
            entry["enforcement_test_owner"],
            f"{label}.enforcement_test_owner",
            implemented_test_ids,
        )
        if requirement_id in by_requirement:
            raise CatalogError(f"requirement_claim_id が重複している: {requirement_id}")
        by_requirement[requirement_id] = entry
        catalog_ids.append(catalog_id)
    if len(catalog_ids) != len(set(catalog_ids)):
        raise CatalogError("catalog_entry_id が重複している")
    missing = sorted(set(db_claims) - set(by_requirement))
    unknown = sorted(set(by_requirement) - set(db_claims))
    if missing or unknown:
        raise CatalogError(
            f"DB 主張との exact-set 不一致: 未対応={missing}, 未登録={unknown}"
        )
    route_by_id = registry_result["route_by_id"]
    assert isinstance(route_by_id, dict)
    if not route_by_id:
        raise CatalogError("AUTH catalog が参照する route registry が空")
    return {"entry_by_requirement": by_requirement, "db_claim_count": len(db_claims)}


def _expected_cell_decision(
    route_class: str, resource_kind: str, channel: str
) -> tuple[str, list[str]]:
    matched_channel = (
        route_class == "shared_screen" and channel == "screen"
    ) or (
        route_class == "shared_aggregate_export" and channel == "export"
    )
    if not matched_channel:
        return "deny", []
    grants = ["metrics"]
    if resource_kind == "player_metrics":
        grants.append("player")
    if channel == "export":
        grants.append("export")
    return "allow", grants


def validate_http_route_matrix(
    raw: object,
    registry_result: dict[str, object],
    root: Path,
    implemented_test_ids: frozenset[str],
) -> dict[str, object]:
    """HTTP route と3軸直積を閉集合として検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("HTTP route matrix のルートはオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "input_manifest",
            "route_classes",
            "resource_kinds",
            "channels",
            "grant_ids",
            "expected_results",
            "route_dispositions",
            "routes",
            "cells",
        },
        "HTTP route matrix",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_http_route_matrix":
        raise CatalogError("HTTP matrix の schema_version または asset_kind が不正")
    _validate_derived_input_manifest(raw["input_manifest"], root)
    closed_tables = {
        "route_classes": ROUTE_CLASSES,
        "resource_kinds": RESOURCE_KINDS,
        "channels": CHANNELS,
        "grant_ids": frozenset({"metrics", "player", "export"}),
        "expected_results": frozenset({"allow", "deny"}),
        "route_dispositions": frozenset({"product_cell", "conditional", "deny_404"}),
    }
    for key, expected in closed_tables.items():
        values = frozenset(_expect_string_list(raw[key], f"HTTP matrix.{key}"))
        if values != expected:
            raise CatalogError(f"HTTP matrix.{key} が閉じた値域と不一致")
    if FORBIDDEN_RESOURCE_KINDS & set(raw["resource_kinds"]):
        raise CatalogError("常に404の資源が HTTP resource_kind に存在する")

    route_by_id = registry_result["route_by_id"]
    assert isinstance(route_by_id, dict)
    matrix_routes = raw["routes"]
    if not isinstance(matrix_routes, list):
        raise CatalogError("HTTP matrix.routes は配列でなければならない")
    matrix_by_route: dict[str, dict[str, object]] = {}
    matrix_ids: list[str] = []
    disposition_by_kind = {
        "legacy_route": "deny_404",
        "shared_data": "product_cell",
        "control_read": "conditional",
        "management_operation": "conditional",
    }
    for index, entry in enumerate(matrix_routes):
        label = f"HTTP matrix.routes[{index}]"
        if not isinstance(entry, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(entry, {"matrix_route_id", "route_id", "disposition", "test_owner"}, label)
        matrix_id = _expect_string(entry["matrix_route_id"], f"{label}.matrix_route_id")
        route_id = _expect_string(entry["route_id"], f"{label}.route_id")
        registry_route = route_by_id.get(route_id)
        if not isinstance(registry_route, dict):
            raise CatalogError(f"{matrix_id}: route_id が registry に存在しない")
        expected_disposition = disposition_by_kind[str(registry_route["route_kind"])]
        if entry["disposition"] != expected_disposition:
            raise CatalogError(f"{matrix_id}: disposition が route kind と不一致")
        _validate_test_owner(entry["test_owner"], f"{label}.test_owner", implemented_test_ids)
        if route_id in matrix_by_route:
            raise CatalogError(f"HTTP matrix の route_id が重複している: {route_id}")
        matrix_by_route[route_id] = entry
        matrix_ids.append(matrix_id)
    if len(matrix_ids) != len(set(matrix_ids)):
        raise CatalogError("matrix_route_id が重複している")
    missing = sorted(set(route_by_id) - set(matrix_by_route))
    unknown = sorted(set(matrix_by_route) - set(route_by_id))
    if missing or unknown:
        raise CatalogError(
            f"route registry と HTTP matrix の exact-set 不一致: 不足={missing}, 未登録={unknown}"
        )

    cells = raw["cells"]
    if not isinstance(cells, list):
        raise CatalogError("HTTP matrix.cells は配列でなければならない")
    expected_axes = {
        (route_class, resource_kind, channel)
        for route_class in ROUTE_CLASSES
        for resource_kind in RESOURCE_KINDS
        for channel in CHANNELS
    }
    actual_axes: dict[tuple[str, str, str], dict[str, object]] = {}
    cell_ids: list[str] = []
    result_counts: Counter[str] = Counter()
    for index, cell in enumerate(cells):
        label = f"HTTP matrix.cells[{index}]"
        if not isinstance(cell, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(
            cell,
            {
                "cell_id",
                "route_id",
                "route_class",
                "resource_kind",
                "channel",
                "expected_result",
                "required_grant_ids",
                "expected_http_status",
                "test_owner",
            },
            label,
        )
        cell_id = _expect_string(cell["cell_id"], f"{label}.cell_id")
        route_class = _expect_closed_value(
            cell["route_class"], ROUTE_CLASSES, f"{label}.route_class"
        )
        resource_kind = _expect_closed_value(
            cell["resource_kind"], RESOURCE_KINDS, f"{label}.resource_kind"
        )
        channel = _expect_closed_value(cell["channel"], CHANNELS, f"{label}.channel")
        axes = (route_class, resource_kind, channel)
        expected_result, expected_grants = _expected_cell_decision(*axes)
        if cell["expected_result"] != expected_result:
            raise CatalogError(f"{cell_id}: 許可・拒否の決定が3軸規則と不一致")
        grants = _expect_string_list(cell["required_grant_ids"], f"{label}.required_grant_ids")
        if grants != expected_grants:
            raise CatalogError(f"{cell_id}: required_grant_ids が3軸規則と不一致")
        expected_status = 404 if expected_result == "deny" else 200
        if cell["expected_http_status"] != expected_status:
            raise CatalogError(f"{cell_id}: HTTP status が許可・拒否と不一致")
        route = route_by_id.get(str(cell["route_id"]))
        if not isinstance(route, dict) or route.get("route_kind") != "shared_data":
            raise CatalogError(f"{cell_id}: route_id が shared_data route でない")
        axis_keys = ("route_class", "resource_kind", "channel")
        if any(
            route.get(key) != value
            for key, value in zip(axis_keys, axes, strict=True)
        ):
            raise CatalogError(f"{cell_id}: route_id の3軸が cell と不一致")
        _validate_test_owner(cell["test_owner"], f"{label}.test_owner", implemented_test_ids)
        if axes in actual_axes:
            raise CatalogError(f"3軸 cell が重複している: {axes}")
        actual_axes[axes] = cell
        cell_ids.append(cell_id)
        result_counts[expected_result] += 1
    if len(cell_ids) != len(set(cell_ids)):
        raise CatalogError("cell_id が重複している")
    missing_axes = sorted(expected_axes - set(actual_axes))
    unknown_axes = sorted(set(actual_axes) - expected_axes)
    if missing_axes or unknown_axes:
        raise CatalogError(f"3軸直積が不完全: 不足={missing_axes}, 未登録={unknown_axes}")
    return {
        "matrix_by_route": matrix_by_route,
        "cell_count": len(cells),
        "result_counts": result_counts,
    }


def _derived_lock_entries(
    asset_kind: str, asset: dict[str, object]
) -> list[dict[str, object]]:
    table_specs = {
        "authz_route_registry": (
            ("routes", "route_id", "route"),
            ("management_operations", "operation_id", "operation"),
        ),
        "authz_catalog": (("entries", "catalog_entry_id", "catalog"),),
        "authz_http_route_matrix": (
            ("routes", "matrix_route_id", "route"),
            ("cells", "cell_id", "cell"),
        ),
    }
    entries: list[dict[str, object]] = []
    for table_name, id_key, prefix in table_specs[asset_kind]:
        table = asset[table_name]
        assert isinstance(table, list)
        for row in table:
            assert isinstance(row, dict)
            entry_id = f"{prefix}:{row[id_key]}"
            entries.append(
                {
                    "entry_id": entry_id,
                    "decision": row,
                    "decision_digest": _table_digest(row),
                }
            )
    return entries


def build_derived_lock(asset: dict[str, object], asset_path: str) -> dict[str, object]:
    """導出資産全体と安定行を別ファイル用の決定 lock にする。"""
    asset_kind = str(asset["asset_kind"])
    entries = _derived_lock_entries(asset_kind, asset)
    return {
        "schema_version": 1,
        "asset_kind": asset_kind,
        "asset_path": asset_path,
        "asset_digest": _table_digest(asset),
        "entry_count": len(entries),
        "aggregate_decision_digest": _table_digest(entries),
        "entries": entries,
    }


def validate_derived_lock(
    asset: dict[str, object], raw_lock: object, asset_path: str
) -> None:
    """導出資産と別ファイルの決定 lock を完全一致で検査する。"""
    if not isinstance(raw_lock, dict):
        raise CatalogError("derived decision lock はオブジェクトでなければならない")
    _expect_keys(
        raw_lock,
        {
            "schema_version",
            "asset_kind",
            "asset_path",
            "asset_digest",
            "entry_count",
            "aggregate_decision_digest",
            "entries",
        },
        "derived decision lock",
    )
    if raw_lock["schema_version"] != 1:
        raise CatalogError("derived decision lock.schema_version が不正")
    entries = raw_lock["entries"]
    if not isinstance(entries, list):
        raise CatalogError("derived decision lock.entries は配列でなければならない")
    lock_entries_by_id: dict[str, dict[str, object]] = {}
    for index, entry in enumerate(entries):
        label = f"derived decision lock.entries[{index}]"
        if not isinstance(entry, dict):
            raise CatalogError(f"{label}はオブジェクトでなければならない")
        _expect_keys(entry, {"entry_id", "decision", "decision_digest"}, label)
        entry_id = _expect_string(entry["entry_id"], f"{label}.entry_id")
        decision_digest = _expect_string(
            entry["decision_digest"], f"{label}.decision_digest"
        )
        if (
            not SHA256_RE.fullmatch(decision_digest)
            or decision_digest != _table_digest(entry["decision"])
        ):
            raise CatalogError(f"{entry_id}: lock 内の decision_digest が決定と不一致")
        if entry_id in lock_entries_by_id:
            raise CatalogError(f"derived decision lock.entry_id が重複: {entry_id}")
        lock_entries_by_id[entry_id] = entry
    for key in ("asset_digest", "aggregate_decision_digest"):
        value = _expect_string(raw_lock[key], f"derived decision lock.{key}")
        if not SHA256_RE.fullmatch(value):
            raise CatalogError(f"derived decision lock.{key} が SHA-256 でない")
    actual_asset_digest = _table_digest(asset)
    if raw_lock["asset_digest"] != actual_asset_digest:
        try:
            asset_kind = str(asset["asset_kind"])
            actual_entries_by_id = {
                str(entry["entry_id"]): entry
                for entry in _derived_lock_entries(asset_kind, asset)
            }
        except (AssertionError, KeyError, TypeError):
            actual_entries_by_id = {}
        differences: list[str] = []
        for entry_id in sorted(set(lock_entries_by_id) | set(actual_entries_by_id)):
            expected_entry = lock_entries_by_id.get(entry_id)
            actual_entry = actual_entries_by_id.get(entry_id)
            if expected_entry is None:
                differences.append(f"{entry_id}: lock にない行が追加")
                continue
            if actual_entry is None:
                differences.append(f"{entry_id}: 資産から行が消失")
                continue
            expected_decision = expected_entry["decision"]
            actual_decision = actual_entry["decision"]
            if isinstance(expected_decision, dict) and isinstance(actual_decision, dict):
                changed_fields = sorted(
                    key
                    for key in set(expected_decision) | set(actual_decision)
                    if expected_decision.get(key) != actual_decision.get(key)
                )
                if changed_fields:
                    differences.append(
                        f"{entry_id}: 変更フィールド={changed_fields}"
                    )
        detail = differences or ["top-level decision が変更"]
        raise CatalogError(
            f"{asset_path}: decision lock と不一致:\n" + "\n".join(detail)
        )
    expected = build_derived_lock(asset, asset_path)
    for key in ("asset_kind", "asset_path", "entry_count"):
        if raw_lock[key] != expected[key]:
            raise CatalogError(f"derived decision lock.{key} が不一致")
    if entries != expected["entries"] or raw_lock["aggregate_decision_digest"] != expected[
        "aggregate_decision_digest"
    ]:
        raise CatalogError(f"{asset_path}: lock entries または集約 digest が不一致")


def collect_pytest_node_ids(root: Path) -> frozenset[str]:
    """pytest の実収集結果から node ID を取得する。"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CatalogError(f"pytest のテスト ID を収集できない: {result.stderr}")
    return frozenset(line.strip() for line in result.stdout.splitlines() if "::" in line)


def validate_derived_assets(
    requirement_catalog: dict[str, object],
    route_registry: object,
    auth_catalog: object,
    http_matrix: object,
    locks: dict[str, object],
    paths: dict[str, str],
    root: Path,
    implemented_test_ids: frozenset[str],
) -> dict[str, object]:
    """ステップ4の3資産を相互参照・decision lock 込みで検査する。"""
    registry_result = validate_route_registry(
        route_registry, requirement_catalog, root, implemented_test_ids
    )
    assert isinstance(route_registry, dict)
    catalog_result = validate_auth_catalog(
        auth_catalog,
        requirement_catalog,
        registry_result,
        root,
        implemented_test_ids,
    )
    assert isinstance(auth_catalog, dict)
    matrix_result = validate_http_route_matrix(
        http_matrix, registry_result, root, implemented_test_ids
    )
    assert isinstance(http_matrix, dict)
    assets = {
        "route_registry": route_registry,
        "auth_catalog": auth_catalog,
        "http_matrix": http_matrix,
    }
    serialized = "\n".join(_canonical_json(asset) for asset in assets.values())
    if any(term in serialized for term in FORBIDDEN_EVACUATED_IMPORT_TERMS):
        raise CatalogError("退避イベントの取り込みがステップ4資産に存在する")
    for name, asset in assets.items():
        validate_derived_lock(asset, locks[name], paths[name])
    return {
        "registry": registry_result,
        "catalog": catalog_result,
        "matrix": matrix_result,
    }


def _expect_object_list(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise CatalogError(f"{label}は配列でなければならない")
    objects: list[dict[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise CatalogError(f"{label}[{index}]はオブジェクトでなければならない")
        objects.append(item)
    return objects


def _validate_oracle_context(raw: object, label: str) -> str:
    if not isinstance(raw, dict):
        raise CatalogError(f"{label}.oracle_context はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {"oracle_commit", "oracle_change_policy_id"},
        f"{label}.oracle_context",
    )
    commit = _expect_string(raw["oracle_commit"], f"{label}.oracle_commit")
    if not COMMIT_RE.fullmatch(commit):
        raise CatalogError(f"{label}.oracle_commit が commit SHA でない")
    if raw["oracle_change_policy_id"] != ORACLE_CHANGE_POLICY_ID:
        raise CatalogError(f"{label}.oracle_change_policy_id が不一致")
    return commit


def _validate_oracle_provenance(
    raw: object, root: Path, label: str
) -> frozenset[str]:
    entries = _expect_object_list(raw, f"{label}.provenance")
    if not entries:
        raise CatalogError(f"{label}.provenance は空にできない")
    identifiers: list[str] = []
    for index, entry in enumerate(entries):
        entry_label = f"{label}.provenance[{index}]"
        _expect_keys(entry, {"provenance_id", "path", "extracted_text"}, entry_label)
        identifier = _expect_string(entry["provenance_id"], f"{entry_label}.provenance_id")
        path_text = _expect_string(entry["path"], f"{entry_label}.path")
        extracted = _expect_string(
            entry["extracted_text"], f"{entry_label}.extracted_text"
        )
        source_path = (root / path_text).resolve()
        try:
            source_path.relative_to(root.resolve())
        except ValueError as error:
            raise CatalogError(f"{entry_label}.path がリポジトリ外を指している") from error
        source = _read_text(source_path, f"{entry_label}.path")
        if "".join(extracted.split()) not in "".join(source.split()):
            raise CatalogError(f"{entry_label}.extracted_text が原文に逐語一致しない")
        identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        raise CatalogError(f"{label}.provenance_id が重複している")
    return frozenset(identifiers)


def _validate_referenced_provenance(
    raw: object, allowed: frozenset[str], label: str
) -> None:
    identifiers = frozenset(_expect_string_list(raw, label))
    if not identifiers or not identifiers <= allowed:
        raise CatalogError(f"{label}が逐語典拠の閉集合にない")


def validate_ddl_elements(raw: object, root: Path) -> dict[str, object]:
    """第2群向けの宣言的 DDL 要素だけを検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("DDL manifest はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "oracle_context",
            "scope",
            "enums",
            "roles",
            "schemas",
            "tables",
            "policies",
            "functions",
            "acl_expectations",
            "column_acl_expectations",
            "table_privilege_probe_matrix",
            "representative_management_probe",
            "transaction_boundaries",
            "provisioning_claim",
            "provenance",
        },
        "DDL manifest",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_candidate_ddl_manifest":
        raise CatalogError("DDL manifest の schema_version または asset_kind が不正")
    oracle_commit = _validate_oracle_context(raw["oracle_context"], "DDL manifest")
    _validate_oracle_provenance(raw["provenance"], root, "DDL manifest")
    scope = raw["scope"]
    if not isinstance(scope, dict):
        raise CatalogError("DDL manifest.scope はオブジェクトでなければならない")
    _expect_keys(
        scope,
        {
            "status",
            "product_schema",
            "contains_sql_body",
            "second_group_approval_required",
        },
        "DDL manifest.scope",
    )
    if (
        scope["status"] != "candidate_probe_only"
        or scope["product_schema"] is not False
        or scope["contains_sql_body"] is not False
        or scope["second_group_approval_required"] is not True
    ):
        raise CatalogError("DDL manifest が宣言的 probe 候補の範囲を越えている")
    enums = raw["enums"]
    if not isinstance(enums, dict):
        raise CatalogError("DDL manifest.enums はオブジェクトでなければならない")
    _expect_keys(
        enums,
        {"table_privilege_ids", "role_kinds", "security_modes"},
        "DDL manifest.enums",
    )
    declared_privilege_list = _expect_string_list(
        enums["table_privilege_ids"], "table privilege"
    )
    declared_privileges = frozenset(declared_privilege_list)
    if (
        len(declared_privilege_list) != 8
        or len(declared_privileges) != 8
        or any(not re.fullmatch(r"[A-Z_]+", value) for value in declared_privileges)
    ):
        raise CatalogError("PostgreSQL 17 の表権限が8種の一意な機械可読集合でない")
    if _expect_string_list(enums["security_modes"], "security_modes") != ["definer"]:
        raise CatalogError("候補関数の security mode が閉じていない")

    roles = _expect_object_list(raw["roles"], "DDL manifest.roles")
    declared_role_kinds = frozenset(
        _expect_string_list(enums["role_kinds"], "role kinds")
    )
    role_by_id: dict[str, dict[str, object]] = {}
    for index, role in enumerate(roles):
        label = f"DDL manifest.roles[{index}]"
        _expect_keys(
            role,
            {
                "role_id",
                "role_kind",
                "login",
                "bypass_rls",
                "superuser",
                "create_role",
                "inherit",
            },
            label,
        )
        role_id = _expect_string(role["role_id"], f"{label}.role_id")
        if role["role_kind"] not in declared_role_kinds:
            raise CatalogError(f"{role_id}: role_kind が宣言集合にない")
        if role_id in role_by_id:
            raise CatalogError(f"role_id が重複している: {role_id}")
        for key in ("login", "bypass_rls", "superuser", "create_role", "inherit"):
            _expect_bool(role[key], f"{label}.{key}")
        if role["superuser"] is not False:
            raise CatalogError(f"{role_id}: probe role に superuser を許さない")
        if role["role_kind"] == "function_owner" and (
            role["login"] is not False or role["bypass_rls"] is not True
        ):
            raise CatalogError(f"{role_id}: 関数所有者は NOLOGIN + BYPASSRLS が必要")
        if role["role_kind"] in {
            "tested_caller",
            "management_caller",
            "negative_test_caller",
        } and role["bypass_rls"] is not False:
            raise CatalogError(f"{role_id}: 呼び出しロールに BYPASSRLS を許さない")
        role_by_id[role_id] = role
    management_caller = role_by_id.get("management_caller")
    table_owner = role_by_id.get("table_owner")
    if (
        not isinstance(management_caller, dict)
        or management_caller.get("role_kind") != "management_caller"
        or management_caller.get("login") is not True
        or not isinstance(table_owner, dict)
        or table_owner.get("login") is not True
    ):
        raise CatalogError("実接続行列の表所有者と管理callerは LOGIN でなければならない")

    schemas = _expect_object_list(raw["schemas"], "DDL manifest.schemas")
    schema_by_id: dict[str, dict[str, object]] = {}
    for index, schema in enumerate(schemas):
        label = f"DDL manifest.schemas[{index}]"
        _expect_keys(
            schema,
            {"schema_id", "owner_role_id", "usage_role_ids", "create_role_ids"},
            label,
        )
        schema_id = _expect_string(schema["schema_id"], f"{label}.schema_id")
        owner_id = _expect_string(schema["owner_role_id"], f"{label}.owner_role_id")
        usage_ids = _expect_string_list(schema["usage_role_ids"], f"{label}.usage_role_ids")
        create_ids = _expect_string_list(schema["create_role_ids"], f"{label}.create_role_ids")
        if owner_id not in role_by_id or set(usage_ids + create_ids) - set(role_by_id):
            raise CatalogError(f"{schema_id}: schema ACL が未知ロールを参照する")
        if create_ids:
            raise CatalogError(f"{schema_id}: 列挙 schema への CREATE は空でなければならない")
        if schema_id in schema_by_id:
            raise CatalogError(f"schema_id が重複している: {schema_id}")
        schema_by_id[schema_id] = schema

    tables = _expect_object_list(raw["tables"], "DDL manifest.tables")
    table_by_id: dict[str, dict[str, object]] = {}
    expected_policy_ids: set[str] = set()
    for index, table in enumerate(tables):
        label = f"DDL manifest.tables[{index}]"
        _expect_keys(
            table,
            {
                "table_id",
                "schema_id",
                "owner_role_id",
                "row_shape_ids",
                "rls_enabled",
                "force_rls",
                "policy_ids",
            },
            label,
        )
        table_id = _expect_string(table["table_id"], f"{label}.table_id")
        if table["schema_id"] not in schema_by_id or table["owner_role_id"] not in role_by_id:
            raise CatalogError(f"{table_id}: table 所有参照が不正")
        if table["rls_enabled"] is not True or table["force_rls"] is not True:
            raise CatalogError(f"{table_id}: RLS と FORCE RLS が必須")
        policy_ids = _expect_string_list(table["policy_ids"], f"{label}.policy_ids")
        if not policy_ids:
            raise CatalogError(f"{table_id}: policy は空にできない")
        expected_policy_ids.update(policy_ids)
        if table_id in table_by_id:
            raise CatalogError(f"table_id が重複している: {table_id}")
        table_by_id[table_id] = table

    policies = _expect_object_list(raw["policies"], "DDL manifest.policies")
    policy_by_id: dict[str, dict[str, object]] = {}
    for index, policy in enumerate(policies):
        label = f"DDL manifest.policies[{index}]"
        _expect_keys(
            policy,
            {
                "policy_id",
                "table_id",
                "command",
                "policy_mode",
                "role_ids",
                "using_predicate_id",
                "with_check_predicate_id",
            },
            label,
        )
        policy_id = _expect_string(policy["policy_id"], f"{label}.policy_id")
        if policy["table_id"] not in table_by_id:
            raise CatalogError(f"{policy_id}: 未知 table を参照する")
        if policy["policy_mode"] != "permissive":
            raise CatalogError(f"{policy_id}: policy mode が候補と不一致")
        if not _expect_string(policy["using_predicate_id"], f"{label}.using") or not _expect_string(
            policy["with_check_predicate_id"], f"{label}.with_check"
        ):
            raise CatalogError(f"{policy_id}: USING / WITH CHECK が必要")
        if policy_id in policy_by_id:
            raise CatalogError(f"policy_id が重複している: {policy_id}")
        policy_by_id[policy_id] = policy
    if set(policy_by_id) != expected_policy_ids:
        raise CatalogError("table と policy が exact-set 不一致")

    functions = _expect_object_list(raw["functions"], "DDL manifest.functions")
    function_by_id: dict[str, dict[str, object]] = {}
    for index, function in enumerate(functions):
        label = f"DDL manifest.functions[{index}]"
        _expect_keys(
            function,
            {
                "function_id",
                "function_class",
                "schema_id",
                "owner_role_id",
                "security_mode",
                "search_path",
                "return_contract",
                "aggregation_contract",
                "dependency_table_ids",
                "execute_role_ids",
                "public_execute",
            },
            label,
        )
        function_id = _expect_string(function["function_id"], f"{label}.function_id")
        if function["schema_id"] not in schema_by_id or function["owner_role_id"] not in role_by_id:
            raise CatalogError(f"{function_id}: function 所有参照が不正")
        owner_role = role_by_id[str(function["owner_role_id"])]
        if owner_role["role_kind"] != "function_owner" or function["security_mode"] != "definer":
            raise CatalogError(f"{function_id}: SECURITY DEFINER 所有契約が不正")
        search_path = _expect_string_list(function["search_path"], f"{label}.search_path")
        if not search_path or search_path[-1] != "pg_temp" or search_path.count("pg_temp") != 1:
            raise CatalogError(f"{function_id}: pg_temp を末尾に一意に置く必要がある")
        if function["public_execute"] is not False:
            raise CatalogError(f"{function_id}: PUBLIC EXECUTE を許さない")
        dependency_ids = set(
            _expect_string_list(function["dependency_table_ids"], f"{label}.dependencies")
        )
        execute_ids = set(
            _expect_string_list(function["execute_role_ids"], f"{label}.execute_role_ids")
        )
        if not dependency_ids <= set(table_by_id) or not execute_ids <= set(role_by_id):
            raise CatalogError(f"{function_id}: function 参照が閉じていない")
        if function["aggregation_contract"] != "none":
            raise CatalogError(f"{function_id}: 手書き集計を候補関数に含めない")
        if function_id in function_by_id:
            raise CatalogError(f"function_id が重複している: {function_id}")
        function_by_id[function_id] = function

    acl_rows = _expect_object_list(raw["acl_expectations"], "DDL manifest.acl_expectations")
    acl_ids: set[str] = set()
    for index, acl in enumerate(acl_rows):
        label = f"DDL manifest.acl_expectations[{index}]"
        _expect_keys(
            acl,
            {
                "acl_id",
                "object_kind",
                "object_id",
                "grantee_role_id",
                "privilege_ids",
                "grant_option",
            },
            label,
        )
        acl_id = _expect_string(acl["acl_id"], f"{label}.acl_id")
        privileges = set(_expect_string_list(acl["privilege_ids"], f"{label}.privilege_ids"))
        if acl["object_kind"] == "table":
            if acl["object_id"] not in table_by_id or not privileges <= declared_privileges:
                raise CatalogError(f"{acl_id}: table ACL が閉じていない")
            if privileges & {"TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"}:
                raise CatalogError(f"{acl_id}: アプリへ RLS 外権限を与えない")
        elif acl["object_kind"] == "function":
            if acl["object_id"] not in function_by_id or privileges != {"EXECUTE"}:
                raise CatalogError(f"{acl_id}: function ACL が閉じていない")
        else:
            raise CatalogError(f"{acl_id}: 未知 object_kind")
        if acl["grantee_role_id"] not in role_by_id or acl["grant_option"] is not False:
            raise CatalogError(f"{acl_id}: ACL grantee または grant option が不正")
        if acl_id in acl_ids:
            raise CatalogError(f"acl_id が重複している: {acl_id}")
        acl_ids.add(acl_id)

    column_acl_rows = _expect_object_list(
        raw["column_acl_expectations"], "DDL manifest.column_acl_expectations"
    )
    if len(column_acl_rows) != 1:
        raise CatalogError("管理callerの列ACL期待はexact-oneでなければならない")
    column_acl = column_acl_rows[0]
    _expect_keys(
        column_acl,
        {
            "expectation_id",
            "table_ids",
            "grantee_role_ids",
            "expected_entries",
        },
        "DDL manifest.column_acl_expectations[0]",
    )
    if (
        column_acl["expectation_id"]
        != "COLUMN-ACL:ALL-PROBE-TABLES:NO-EXPLICIT-GRANTS"
        or set(_expect_string_list(column_acl["table_ids"], "column ACL tables"))
        != set(table_by_id)
        or set(
            _expect_string_list(
                column_acl["grantee_role_ids"], "column ACL grantees"
            )
        )
        != set(role_by_id)
        or column_acl["expected_entries"] != []
    ):
        raise CatalogError("全probe表・ロールの列ACL exact-set が空に固定されていない")

    privilege_matrix = _expect_object_list(
        raw["table_privilege_probe_matrix"], "DDL manifest.table privilege matrix"
    )
    matrix_privileges: set[str] = set()
    for index, row in enumerate(privilege_matrix):
        label = f"DDL manifest.table_privilege_probe_matrix[{index}]"
        _expect_keys(
            row,
            {
                "privilege_id",
                "calling_role_id",
                "target_table_id",
                "expected_direct_access",
                "test_owner",
            },
            label,
        )
        privilege_id = _expect_string(row["privilege_id"], f"{label}.privilege_id")
        if (
            privilege_id not in declared_privileges
            or row["calling_role_id"] != "management_caller"
            or row["target_table_id"] != "probe_management_effects"
            or row["expected_direct_access"] != "deny"
        ):
            raise CatalogError(f"{label}: 8権限の直接実行期待が不正")
        _validate_test_owner(row["test_owner"], f"{label}.test_owner", frozenset())
        matrix_privileges.add(privilege_id)
    if matrix_privileges != declared_privileges or len(privilege_matrix) != len(
        declared_privileges
    ):
        raise CatalogError("表権限集合と実行行列が exact-set 不一致")

    management_probe = raw["representative_management_probe"]
    if not isinstance(management_probe, dict):
        raise CatalogError("representative_management_probe はオブジェクトでない")
    _expect_keys(
        management_probe,
        {
            "claim_ids",
            "function_id",
            "calling_role_id",
            "base_table_ids",
            "caller_table_privilege_ids",
            "caller_column_privilege_entries",
            "authorization_and_side_effect_same_function",
            "authorization_and_side_effect_same_transaction",
            "transaction_boundary_id",
        },
        "representative_management_probe",
    )
    management_claim_ids = frozenset(
        _expect_string_list(management_probe["claim_ids"], "management probe claims")
    )
    base_table_ids = frozenset(
        _expect_string_list(management_probe["base_table_ids"], "management base tables")
    )
    management_function_id = str(management_probe["function_id"])
    management_function = function_by_id.get(management_function_id)
    if (
        management_claim_ids != MANAGEMENT_PROBE_CLAIM_IDS
        or management_probe["calling_role_id"] != "management_caller"
        or not base_table_ids
        or not base_table_ids <= set(table_by_id)
        or management_probe["caller_table_privilege_ids"] != []
        or management_probe["caller_column_privilege_entries"] != []
        or management_probe["authorization_and_side_effect_same_function"] is not True
        or management_probe["authorization_and_side_effect_same_transaction"] is not True
        or management_probe["transaction_boundary_id"]
        != "TX:REPRESENTATIVE_MANAGEMENT"
        or not isinstance(management_function, dict)
        or management_function.get("execute_role_ids") != ["management_caller"]
    ):
        raise CatalogError("代表管理probeのDML遮断または原子性契約が不正")
    if any(
        acl.get("object_kind") == "table"
        and acl.get("object_id") in base_table_ids
        and acl.get("grantee_role_id") == "management_caller"
        for acl in acl_rows
    ):
        raise CatalogError("管理callerへ代表操作の基表権限を直接付与している")

    boundaries = _expect_object_list(
        raw["transaction_boundaries"], "DDL manifest.transaction_boundaries"
    )
    boundary_ids = {
        _expect_string(boundary["boundary_id"], "transaction boundary ID")
        for boundary in boundaries
    }
    if boundary_ids != {
        "TX:PROVISIONING",
        "TX:REPRESENTATIVE_MANAGEMENT",
        "TX:GLOBAL_MUTATION_ISOLATION",
    }:
        raise CatalogError("transaction boundary が閉じた期待値と不一致")
    management_boundary = next(
        boundary
        for boundary in boundaries
        if boundary["boundary_id"] == "TX:REPRESENTATIVE_MANAGEMENT"
    )
    if (
        management_boundary.get("boundary_kind")
        != "authorization_and_side_effect"
        or management_boundary.get("atomic") is not True
    ):
        raise CatalogError("代表管理probeの認可と副作用が同一原子境界にない")
    provisioning = raw["provisioning_claim"]
    if not isinstance(provisioning, dict):
        raise CatalogError("provisioning_claim はオブジェクトでなければならない")
    _expect_keys(
        provisioning,
        {"claim_id", "ordered_steps", "completion_catalog_expectations"},
        "provisioning_claim",
    )
    steps = _expect_object_list(provisioning["ordered_steps"], "provisioning steps")
    if [step.get("sequence") for step in steps] != list(range(1, 6)):
        raise CatalogError("プロビジョニング5手順の順序が不正")
    checks = _expect_object_list(
        provisioning["completion_catalog_expectations"], "provisioning checks"
    )
    predicates = {
        check.get("inspection_predicate")
        for check in checks
    }
    if predicates != {
        "pg_has_role(<provisioner>, <fn_owner>, 'SET') = false",
        "pg_has_role(<provisioner>, <fn_owner>, 'USAGE') = false",
    }:
        raise CatalogError("R-8 の SET / USAGE 閉鎖検査が exact-set 不一致")
    return {
        "oracle_commit": oracle_commit,
        "role_ids": frozenset(role_by_id),
        "table_ids": frozenset(table_by_id),
        "function_ids": frozenset(function_by_id),
        "provisioning_claim_id": provisioning["claim_id"],
        "management_probe_claim_ids": management_claim_ids,
        "table_privilege_ids": declared_privileges,
    }


def validate_rejected_configs(raw: object, root: Path) -> dict[str, object]:
    """実機で不採用となった構成と Supabase 0 件を区別して検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("不採用構成表はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "oracle_context",
            "required_initial_rejection_ids",
            "rejections",
            "supabase_verification",
            "provenance",
        },
        "不採用構成表",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_rejected_configurations":
        raise CatalogError("不採用構成表の schema_version または asset_kind が不正")
    oracle_commit = _validate_oracle_context(raw["oracle_context"], "不採用構成表")
    provenance_ids = _validate_oracle_provenance(raw["provenance"], root, "不採用構成表")
    required_ids = frozenset(
        _expect_string_list(raw["required_initial_rejection_ids"], "required rejection IDs")
    )
    if required_ids != frozenset(REQUIRED_REJECTION_CONFIGS):
        raise CatalogError("不採用構成表の初期3 ID が exact-set 不一致")
    rows = _expect_object_list(raw["rejections"], "不採用構成表.rejections")
    rows_by_id: dict[str, dict[str, object]] = {}
    for index, row in enumerate(rows):
        label = f"不採用構成表.rejections[{index}]"
        rejection_id = _expect_string(row.get("rejection_id"), f"{label}.rejection_id")
        configuration_id = _expect_string(
            row.get("configuration_id"), f"{label}.configuration_id"
        )
        if rejection_id not in REQUIRED_REJECTION_CONFIGS:
            raise CatalogError(f"未知の初期不採用構成: {rejection_id}")
        if configuration_id != REQUIRED_REJECTION_CONFIGS[rejection_id]:
            raise CatalogError(f"{rejection_id}: 構成 ID が初期期待値と不一致")
        _validate_referenced_provenance(
            row.get("provenance_ids"), provenance_ids, f"{label}.provenance_ids"
        )
        if rejection_id in rows_by_id:
            raise CatalogError(f"rejection_id が重複している: {rejection_id}")
        rows_by_id[rejection_id] = row
    if frozenset(rows_by_id) != required_ids:
        raise CatalogError("不採用構成表の初期3行が exact-set 不一致")
    pg_temp_row = rows_by_id["REJ-003"]
    if (
        pg_temp_row.get("candidate_statement_status") != "incorrect"
        or pg_temp_row.get("corrected_expectation") != "place_pg_temp_explicitly_last"
    ):
        raise CatalogError("候補案3-2の誤りと pg_temp 是正が固定されていない")
    supabase = raw["supabase_verification"]
    if not isinstance(supabase, dict):
        raise CatalogError("supabase_verification はオブジェクトでなければならない")
    if (
        supabase.get("rejected_configuration_count") != 0
        or supabase.get("additional_rejection_ids") != []
        or supabase.get("interpretation") != "supabase_had_zero_rejections_not_global_zero"
    ):
        raise CatalogError("Supabase の不成立0件という限定結果が不正")
    _validate_referenced_provenance(
        supabase.get("provenance_ids"), provenance_ids, "supabase provenance"
    )
    return {"oracle_commit": oracle_commit, "rejection_count": len(rows)}


def _has_db_decision(claim: dict[str, object]) -> bool:
    decisions = claim.get("decidable_at")
    return isinstance(decisions, list) and any(
        isinstance(decision, dict) and decision.get("location") == "db"
        for decision in decisions
    )


def validate_claim_mutant_map(
    raw: object,
    requirement_catalog: dict[str, object],
    route_registry: dict[str, object],
    http_matrix: dict[str, object],
    ddl_result: dict[str, object],
    root: Path,
    implemented_test_ids: frozenset[str],
) -> dict[str, object]:
    """全 AUTH claim、2系統 mutant、kill 条件を exact-set で検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("claim mutant map はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "oracle_context",
            "execution_classes",
            "classification_rules",
            "mutant_axes",
            "mcdc_decision_forms",
            "positive_cases",
            "table_privilege_mutation_rule",
            "claims",
            "mutants",
            "two_factor_interactions",
            "kill_contract",
            "provenance",
        },
        "claim mutant map",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_claim_mutant_map":
        raise CatalogError("claim mutant map の schema_version または asset_kind が不正")
    oracle_commit = _validate_oracle_context(raw["oracle_context"], "claim mutant map")
    _validate_oracle_provenance(raw["provenance"], root, "claim mutant map")
    execution_classes = frozenset(
        _expect_string_list(raw["execution_classes"], "execution classes")
    )
    if execution_classes != ORACLE_EXECUTION_CLASSES:
        raise CatalogError("execution_class が閉じた2値と不一致")
    if frozenset(_expect_string_list(raw["mutant_axes"], "mutant axes")) != ORACLE_MUTANT_AXES:
        raise CatalogError("mutant axis が閉じた3値と不一致")
    if frozenset(_expect_string_list(raw["mcdc_decision_forms"], "MC/DC forms")) != {
        "AND",
        "OR",
        "NOT",
        "CASE",
    }:
        raise CatalogError("MC/DC の AND / OR / NOT / CASE が exact-set 不一致")
    rules = raw["classification_rules"]
    if not isinstance(rules, dict) or not rules:
        raise CatalogError("execution classification rules は空にできない")

    positive_cases = raw["positive_cases"]
    if not isinstance(positive_cases, dict):
        raise CatalogError("positive_cases はオブジェクトでなければならない")
    _expect_keys(
        positive_cases,
        {"scope_id", "population_rule", "cases"},
        "positive_cases",
    )
    if (
        positive_cases["scope_id"] != POSITIVE_CASE_SCOPE_ID
        or positive_cases["population_rule"]
        != "all_http_matrix_cells_with_expected_result_allow"
    ):
        raise CatalogError("正例母集合の導出規則が不正")
    matrix_cells = _expect_object_list(http_matrix.get("cells"), "HTTP matrix.cells")
    expected_allow_cell_ids = {
        str(cell["cell_id"])
        for cell in matrix_cells
        if cell.get("expected_result") == "allow"
    }
    positive_rows = _expect_object_list(positive_cases["cases"], "positive cases")
    positive_test_ids: set[str] = set()
    actual_allow_cell_ids: set[str] = set()
    for index, positive_case in enumerate(positive_rows):
        label = f"positive_cases.cases[{index}]"
        _expect_keys(
            positive_case,
            {"cell_id", "expected_result", "test_owner"},
            label,
        )
        cell_id = _expect_string(positive_case["cell_id"], f"{label}.cell_id")
        if positive_case["expected_result"] != "allow":
            raise CatalogError(f"{cell_id}: 正例の期待結果が allow でない")
        owner = positive_case["test_owner"]
        _validate_test_owner(owner, f"{label}.test_owner", implemented_test_ids)
        assert isinstance(owner, dict)
        positive_test_ids.add(str(owner["id"]))
        actual_allow_cell_ids.add(cell_id)
    if (
        actual_allow_cell_ids != expected_allow_cell_ids
        or len(positive_rows) != len(expected_allow_cell_ids)
        or len(positive_test_ids) != len(positive_rows)
    ):
        raise CatalogError("許可セルと正例テストIDが exact-set / one-to-one 不一致")

    auth_claims = _auth_claims_by_id(requirement_catalog)
    operations = route_registry.get("management_operations")
    if not isinstance(operations, list):
        raise CatalogError("route registry の management_operations が不正")
    management_claim_ids = {
        str(claim_id)
        for operation in operations
        if isinstance(operation, dict)
        for claim_id in operation.get("source_claim_ids", [])
        if isinstance(operation.get("source_claim_ids"), list)
    }
    provisioning_claim_id = str(ddl_result["provisioning_claim_id"])
    management_probe_claim_ids = ddl_result["management_probe_claim_ids"]
    assert isinstance(management_probe_claim_ids, frozenset)
    expected_claim_ids = (
        set(auth_claims) | {provisioning_claim_id} | set(management_probe_claim_ids)
    )
    claim_rows = _expect_object_list(raw["claims"], "claim mutant map.claims")
    claim_by_id: dict[str, dict[str, object]] = {}
    execution_counts: Counter[str] = Counter()
    for index, claim_row in enumerate(claim_rows):
        label = f"claim mutant map.claims[{index}]"
        _expect_keys(
            claim_row,
            {
                "claim_id",
                "claim_origin",
                "execution_class",
                "classification_rule_id",
                "mutant_ids",
                "schema_drift_test_owner",
                "runtime_test_owner",
                "runtime_kill_required",
                "runtime_evidence_kind",
                "receiving_task_id",
            },
            label,
        )
        claim_id = _expect_string(claim_row["claim_id"], f"{label}.claim_id")
        execution_class = _expect_closed_value(
            claim_row["execution_class"], ORACLE_EXECUTION_CLASSES, f"{label}.execution_class"
        )
        rule_id = _expect_string(
            claim_row["classification_rule_id"], f"{label}.classification_rule_id"
        )
        rule = rules.get(rule_id)
        if not isinstance(rule, dict) or rule.get("execution_class") != execution_class:
            raise CatalogError(f"{claim_id}: classification rule が宣言表と不一致")
        if claim_id == provisioning_claim_id:
            expected_class = "probe_executable"
            expected_rule = "PROBE_EXECUTABLE_PROVISIONING_SEQUENCE"
            expected_origin = "design"
        elif claim_id in management_probe_claim_ids:
            expected_class = "probe_executable"
            expected_rule = "PROBE_EXECUTABLE_MANAGEMENT_PROBE"
            expected_origin = "design"
        else:
            source_claim = auth_claims.get(claim_id)
            if source_claim is None:
                raise CatalogError(f"未知 claim が mutant map にある: {claim_id}")
            if not _has_db_decision(source_claim):
                expected_class = "contract_only"
                expected_rule = "CONTRACT_ONLY_NO_DB_DECISION_POINT"
            elif claim_id in management_claim_ids:
                expected_class = "contract_only"
                expected_rule = "CONTRACT_ONLY_UNIMPLEMENTED_MANAGEMENT"
            else:
                expected_class = "probe_executable"
                expected_rule = "PROBE_EXECUTABLE_DB_DECISION_POINT"
            expected_origin = "requirement"
        if (
            execution_class != expected_class
            or rule_id != expected_rule
            or claim_row["claim_origin"] != expected_origin
        ):
            raise CatalogError(f"{claim_id}: probe/contract 分類が入力からの導出と不一致")
        mutant_ids = _expect_string_list(claim_row["mutant_ids"], f"{label}.mutant_ids")
        if not mutant_ids or len(mutant_ids) != len(set(mutant_ids)):
            raise CatalogError(f"{claim_id}: mutant 対応は空・重複不可")
        _validate_test_owner(
            claim_row["schema_drift_test_owner"],
            f"{label}.schema_drift_test_owner",
            implemented_test_ids,
        )
        _validate_test_owner(
            claim_row["runtime_test_owner"],
            f"{label}.runtime_test_owner",
            implemented_test_ids,
        )
        runtime_required = _expect_bool(
            claim_row["runtime_kill_required"], f"{label}.runtime_kill_required"
        )
        if execution_class == "contract_only":
            if runtime_required or claim_row["runtime_evidence_kind"] != "handoff_runtime_test":
                raise CatalogError(f"{claim_id}: contract_only に runtime kill を要求している")
            if not _expect_string(claim_row["receiving_task_id"], f"{label}.receiving_task_id"):
                raise CatalogError(f"{claim_id}: contract_only の受取先がない")
        elif not runtime_required or claim_row["runtime_evidence_kind"] == "schema_drift_only":
            raise CatalogError(f"{claim_id}: probe_executable の runtime kill 契約がない")
        if claim_id in claim_by_id:
            raise CatalogError(f"claim_id が重複している: {claim_id}")
        claim_by_id[claim_id] = claim_row
        execution_counts[execution_class] += 1
    if set(claim_by_id) != expected_claim_ids:
        missing = sorted(expected_claim_ids - set(claim_by_id))
        unknown = sorted(set(claim_by_id) - expected_claim_ids)
        raise CatalogError(f"全 claim が exact-set 不一致: 不足={missing}, 未登録={unknown}")

    mutants = _expect_object_list(raw["mutants"], "claim mutant map.mutants")
    mutant_by_id: dict[str, dict[str, object]] = {}
    reverse_claim_mutants: dict[str, set[str]] = defaultdict(set)
    axis_counts: Counter[str] = Counter()
    mcdc_operator_ids: set[str] = set()
    positive_kill_mutant_ids: set[str] = set()
    for index, mutant in enumerate(mutants):
        label = f"claim mutant map.mutants[{index}]"
        _expect_keys(
            mutant,
            {
                "mutant_id",
                "axis",
                "operator_id",
                "decision_form",
                "claim_ids",
                "target_element_ids",
                "expected_application_outcome",
                "expected_drift_outcome",
                "expected_runtime_outcome",
                "runtime_kill_required",
                "runtime_kill_waiver_reason",
                "expected_positive_outcome",
                "positive_kill_required",
                "positive_case_scope_id",
                "requires_disposable_cluster",
                "schema_drift_test_id",
                "runtime_test_id",
            },
            label,
        )
        mutant_id = _expect_string(mutant["mutant_id"], f"{label}.mutant_id")
        axis = _expect_closed_value(mutant["axis"], ORACLE_MUTANT_AXES, f"{label}.axis")
        claim_ids = _expect_string_list(mutant["claim_ids"], f"{label}.claim_ids")
        if not claim_ids or set(claim_ids) - set(claim_by_id):
            raise CatalogError(f"{mutant_id}: claim 参照が閉じていない")
        if not _expect_string_list(mutant["target_element_ids"], f"{label}.targets"):
            raise CatalogError(f"{mutant_id}: 変異対象がない")
        if mutant["expected_drift_outcome"] != "red":
            raise CatalogError(f"{mutant_id}: schema drift は必ず独立 red が必要")
        runtime_required = _expect_bool(
            mutant["runtime_kill_required"], f"{label}.runtime_kill_required"
        )
        positive_required = _expect_bool(
            mutant["positive_kill_required"], f"{label}.positive_kill_required"
        )
        waiver_reason = mutant["runtime_kill_waiver_reason"]
        if runtime_required:
            if waiver_reason is not None:
                raise CatalogError(f"{mutant_id}: runtime kill 必須なのに免除理由がある")
        elif waiver_reason not in {
            "contract_only_handoff",
            "covered_by_two_factor_cut_set",
            "positive_case_kill_only",
            "application_expected_to_fail",
        }:
            raise CatalogError(f"{mutant_id}: runtime kill 免除理由が閉じた列挙値でない")
        claim_classes = {
            claim_by_id[claim_id]["execution_class"] for claim_id in claim_ids
        }
        contract_only = claim_classes == {"contract_only"}
        application_failed = mutant["expected_application_outcome"] != "applies"
        if contract_only:
            if (
                positive_required
                or mutant["expected_positive_outcome"] != "handoff"
                or mutant["positive_case_scope_id"] is not None
                or waiver_reason != "contract_only_handoff"
            ):
                raise CatalogError(f"{mutant_id}: contract_only に正例runtimeを要求している")
        elif application_failed:
            if (
                positive_required
                or mutant["expected_positive_outcome"]
                != "not_run_application_failed"
                or mutant["positive_case_scope_id"] is not None
                or (not runtime_required and waiver_reason != "application_expected_to_fail")
            ):
                raise CatalogError(f"{mutant_id}: 適用失敗後の正例をkillに数えている")
        elif (
            mutant["positive_case_scope_id"] != POSITIVE_CASE_SCOPE_ID
            or mutant["expected_positive_outcome"]
            != ("kill" if positive_required else "pass")
        ):
            raise CatalogError(f"{mutant_id}: 正例チャネルの期待結果が不正")
        if (
            positive_required
            and not runtime_required
            and waiver_reason != "positive_case_kill_only"
        ):
            raise CatalogError(f"{mutant_id}: 正例だけでkillするruntime免除理由が不正")
        if positive_required:
            positive_kill_mutant_ids.add(mutant_id)
        _expect_bool(
            mutant["requires_disposable_cluster"], f"{label}.requires_disposable_cluster"
        )
        for key in ("schema_drift_test_id", "runtime_test_id"):
            test_id = _expect_string(mutant[key], f"{label}.{key}")
            if not TEST_ID_RE.fullmatch(test_id):
                raise CatalogError(f"{mutant_id}: {key} が test ID 形式でない")
        if axis == "authorization_predicate":
            if len(claim_ids) != 1:
                raise CatalogError(f"{mutant_id}: 認可述語 mutant は1 claim を所有する")
            claim_row = claim_by_id[claim_ids[0]]
            authorization_contract_only = (
                claim_row["execution_class"] == "contract_only"
            )
            if authorization_contract_only and (
                runtime_required or mutant["expected_runtime_outcome"] != "handoff"
            ):
                raise CatalogError(f"{mutant_id}: contract_only を runtime kill と数えている")
            if not authorization_contract_only and (
                not runtime_required or mutant["expected_runtime_outcome"] != "kill"
            ):
                raise CatalogError(f"{mutant_id}: probe executable の runtime kill がない")
            operator_id = str(mutant["operator_id"])
            if operator_id in REQUIRED_MCDC_OPERATOR_IDS:
                mcdc_operator_ids.add(operator_id)
        for claim_id in claim_ids:
            reverse_claim_mutants[claim_id].add(mutant_id)
        if mutant_id in mutant_by_id:
            raise CatalogError(f"mutant_id が重複している: {mutant_id}")
        mutant_by_id[mutant_id] = mutant
        axis_counts[axis] += 1
    for claim_id, claim_row in claim_by_id.items():
        declared = set(_expect_string_list(claim_row["mutant_ids"], f"{claim_id}.mutant_ids"))
        if declared != reverse_claim_mutants[claim_id]:
            raise CatalogError(f"{claim_id}: claim と mutant の双方向 exact-set が不一致")
    config_ids = {
        mutant_id
        for mutant_id, mutant in mutant_by_id.items()
        if mutant["axis"] == "configuration"
    }
    r8_ids = {
        mutant_id
        for mutant_id, mutant in mutant_by_id.items()
        if mutant["axis"] == "r8_provisioning"
    }
    privilege_ids = ddl_result["table_privilege_ids"]
    assert isinstance(privilege_ids, frozenset)
    privilege_rule = raw["table_privilege_mutation_rule"]
    if not isinstance(privilege_rule, dict):
        raise CatalogError("table_privilege_mutation_rule はオブジェクトでない")
    _expect_keys(
        privilege_rule,
        {
            "source_asset_path",
            "source_json_pointer",
            "mutant_id_template",
            "target_role_id",
            "target_table_id",
            "claim_ids",
        },
        "table_privilege_mutation_rule",
    )
    rule_claim_ids = set(
        _expect_string_list(privilege_rule["claim_ids"], "privilege mutation claims")
    )
    if (
        privilege_rule["source_asset_path"]
        != "contracts/authz/ddl-elements.json"
        or privilege_rule["source_json_pointer"] != "/enums/table_privilege_ids"
        or privilege_rule["mutant_id_template"]
        != f"{TABLE_PRIVILEGE_MUTANT_PREFIX}{{privilege_id}}"
        or privilege_rule["target_role_id"] != "management_caller"
        or privilege_rule["target_table_id"] != "probe_management_effects"
        or rule_claim_ids != MANAGEMENT_PROBE_CLAIM_IDS
    ):
        raise CatalogError("表権限mutantの単一集合からの導出規則が不正")
    privilege_mutant_ids = {
        f"{TABLE_PRIVILEGE_MUTANT_PREFIX}{privilege_id}"
        for privilege_id in privilege_ids
    }
    expected_config_ids = REQUIRED_BASE_CONFIGURATION_MUTANT_IDS | privilege_mutant_ids
    if config_ids != expected_config_ids:
        raise CatalogError("構成軸 mutant が基礎集合+表権限派生集合と exact-set 不一致")
    for privilege_id in privilege_ids:
        mutant_id = f"{TABLE_PRIVILEGE_MUTANT_PREFIX}{privilege_id}"
        privilege_mutant = mutant_by_id[mutant_id]
        privilege_claim_ids = set(
            _expect_string_list(
                privilege_mutant["claim_ids"], f"{mutant_id}.claim_ids"
            )
        )
        if (
            privilege_mutant["operator_id"]
            != "grant_management_caller_table_privilege"
            or privilege_claim_ids != MANAGEMENT_PROBE_CLAIM_IDS
            or privilege_mutant["target_element_ids"]
            != [
                "TABLE-PRIVILEGE:probe_management_effects:"
                f"management_caller:{privilege_id}"
            ]
            or privilege_mutant["runtime_kill_required"] is not True
        ):
            raise CatalogError(f"{mutant_id}: 表権限から派生したkill契約が不正")
    if positive_kill_mutant_ids != POSITIVE_KILL_MUTANT_IDS:
        raise CatalogError("正例を破壊する既知mutantが exact-set 不一致")
    if r8_ids != REQUIRED_R8_MUTANT_IDS:
        raise CatalogError("R-8 mutant が必須2種と exact-set 不一致")
    if mcdc_operator_ids != REQUIRED_MCDC_OPERATOR_IDS:
        raise CatalogError("計画4節の認可述語10種が exact-set 不一致")
    auth_mutant_claims: set[str] = set()
    for mutant in mutant_by_id.values():
        claim_ids = mutant["claim_ids"]
        if mutant["axis"] == "authorization_predicate" and isinstance(
            claim_ids, list
        ):
            auth_mutant_claims.update(str(claim_id) for claim_id in claim_ids)
    if auth_mutant_claims != set(auth_claims):
        raise CatalogError("要件 AUTH claim ごとの認可述語 mutant が不足")

    interactions = _expect_object_list(
        raw["two_factor_interactions"], "claim mutant map.two_factor_interactions"
    )
    expected_pairs = {tuple(pair) for pair in combinations(sorted(config_ids), 2)}
    actual_pairs: set[tuple[str, str]] = set()
    for index, interaction in enumerate(interactions):
        label = f"two_factor_interactions[{index}]"
        _expect_keys(
            interaction,
            {
                "interaction_id",
                "factor_mutant_ids",
                "expected_drift_outcome",
                "runtime_test_owner",
            },
            label,
        )
        factors = _expect_string_list(
            interaction["factor_mutant_ids"], f"{label}.factor_mutant_ids"
        )
        if len(factors) != 2 or factors != sorted(factors) or set(factors) - config_ids:
            raise CatalogError(f"{label}: 構成軸の順不同2因子でない")
        if interaction["expected_drift_outcome"] != "red":
            raise CatalogError(f"{label}: 2因子 drift は red が必要")
        _validate_test_owner(
            interaction["runtime_test_owner"],
            f"{label}.runtime_test_owner",
            implemented_test_ids,
        )
        actual_pairs.add((factors[0], factors[1]))
    if actual_pairs != expected_pairs or len(interactions) != len(expected_pairs):
        raise CatalogError("構成軸の全2因子相互作用が exact-set 不一致")

    kill_contract = raw["kill_contract"]
    if not isinstance(kill_contract, dict):
        raise CatalogError("kill_contract はオブジェクトでなければならない")
    _expect_keys(
        kill_contract,
        {
            "verdict_channels",
            "positive_case_rule",
            "conditions",
            "contract_only_runtime_rule",
        },
        "kill_contract",
    )
    channels = kill_contract["verdict_channels"]
    if not isinstance(channels, dict) or channels != {
        "schema_drift": "independent_required_result",
        "runtime_cross_tenant": "independent_required_result",
        "runtime_positive_case": "independent_required_result",
    }:
        raise CatalogError("drift・越境・正例の3チャネルが独立判定でない")
    if kill_contract["positive_case_rule"] != {
        "scope_id": POSITIVE_CASE_SCOPE_ID,
        "required_population": "all_allow_cells",
        "zero_row_result": "red",
        "exact_expected_rows_required": True,
    }:
        raise CatalogError("正例の0行破壊をredにする契約が不正")
    condition_rows = _expect_object_list(kill_contract["conditions"], "kill conditions")
    condition_ids = {str(condition.get("condition_id")) for condition in condition_rows}
    if condition_ids != {f"KILL-{number:02d}-{suffix}" for number, suffix in (
        (1, "TARGETED-CATALOG-DELTA"),
        (2, "TEST-EXECUTED"),
        (3, "EXPECTED-FAILURE"),
        (4, "NO-FIXTURE-FAILURE"),
        (5, "GLOBAL-STATE-ISOLATION"),
    )}:
        raise CatalogError("kill の5条件が exact-set 不一致")
    if (
        kill_contract["contract_only_runtime_rule"]
        != "runtime_kill_forbidden_handoff_test_required"
    ):
        raise CatalogError("R-7 の contract_only 規律が不正")
    return {
        "oracle_commit": oracle_commit,
        "claim_by_id": claim_by_id,
        "mutant_by_id": mutant_by_id,
        "execution_counts": execution_counts,
        "axis_counts": axis_counts,
        "config_pairs": expected_pairs,
        "positive_case_count": len(positive_rows),
        "positive_kill_mutant_ids": positive_kill_mutant_ids,
    }


def validate_attack_tree(
    raw: object,
    mutant_result: dict[str, object],
    root: Path,
) -> dict[str, object]:
    """攻撃木、最小 cut set、全2因子相互作用を検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("attack tree はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "oracle_context",
            "attack_goals",
            "minimal_cut_sets",
            "two_factor_scope",
            "two_factor_interactions",
            "provenance",
        },
        "attack tree",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_attack_tree":
        raise CatalogError("attack tree の schema_version または asset_kind が不正")
    oracle_commit = _validate_oracle_context(raw["oracle_context"], "attack tree")
    _validate_oracle_provenance(raw["provenance"], root, "attack tree")
    mutant_by_id = mutant_result["mutant_by_id"]
    assert isinstance(mutant_by_id, dict)
    goals = _expect_object_list(raw["attack_goals"], "attack_goals")
    goal_ids = {
        _expect_string(goal.get("attack_goal_id"), "attack_goal_id") for goal in goals
    }
    if not goal_ids or any(goal.get("logic") != "OR_OF_MINIMAL_CUT_SETS" for goal in goals):
        raise CatalogError("attack goal の OR 構造が不正")
    cut_rows = _expect_object_list(raw["minimal_cut_sets"], "minimal_cut_sets")
    cut_by_id: dict[str, dict[str, object]] = {}
    cuts_by_goal: dict[str, list[frozenset[str]]] = defaultdict(list)
    multi_factor_count = 0
    for index, cut in enumerate(cut_rows):
        label = f"minimal_cut_sets[{index}]"
        _expect_keys(
            cut,
            {
                "cut_set_id",
                "attack_goal_id",
                "mutant_ids",
                "minimal",
                "single_mutation_sufficient",
            },
            label,
        )
        cut_id = _expect_string(cut["cut_set_id"], f"{label}.cut_set_id")
        mutant_ids = frozenset(_expect_string_list(cut["mutant_ids"], f"{label}.mutant_ids"))
        if not mutant_ids or not mutant_ids <= set(mutant_by_id):
            raise CatalogError(f"{cut_id}: cut set の mutant 参照が閉じていない")
        if cut["attack_goal_id"] not in goal_ids or cut["minimal"] is not True:
            raise CatalogError(f"{cut_id}: attack goal または minimal 属性が不正")
        if cut["single_mutation_sufficient"] is not (len(mutant_ids) == 1):
            raise CatalogError(f"{cut_id}: 単独成立フラグが要素数と不一致")
        if len(mutant_ids) > 1:
            multi_factor_count += 1
        if cut_id in cut_by_id:
            raise CatalogError(f"cut_set_id が重複している: {cut_id}")
        cut_by_id[cut_id] = cut
        cuts_by_goal[str(cut["attack_goal_id"])].append(mutant_ids)
    if set(cuts_by_goal) != goal_ids or multi_factor_count == 0:
        raise CatalogError("cut set のない goal または多因子 cut set の欠落")
    for goal_id, cut_sets in cuts_by_goal.items():
        if any(left < right for left in cut_sets for right in cut_sets):
            raise CatalogError(f"{goal_id}: 非最小 cut set が含まれる")
    layered_mutant_ids = {
        str(mutant_id)
        for mutant_id, mutant in mutant_by_id.items()
        if isinstance(mutant, dict)
        and mutant.get("runtime_kill_waiver_reason")
        == "covered_by_two_factor_cut_set"
    }
    covered_by_multi_factor = {
        mutant_id
        for cut_sets in cuts_by_goal.values()
        for cut_set in cut_sets
        if len(cut_set) > 1
        for mutant_id in cut_set
    }
    if not layered_mutant_ids or not layered_mutant_ids <= covered_by_multi_factor:
        raise CatalogError("runtime kill免除mutantが多因子cut setで被覆されていない")
    privilege_mutant_ids = {
        mutant_id
        for mutant_id in mutant_by_id
        if str(mutant_id).startswith(TABLE_PRIVILEGE_MUTANT_PREFIX)
    }
    atomicity_mutant_id = (
        "MUT:CONFIG:CFG_SPLIT_MANAGEMENT_AUTHORIZATION_AND_SIDE_EFFECT"
    )
    singleton_cut_mutants = {
        next(iter(cut_set))
        for cut_sets in cuts_by_goal.values()
        for cut_set in cut_sets
        if len(cut_set) == 1
    }
    if (
        not privilege_mutant_ids
        or not privilege_mutant_ids <= singleton_cut_mutants
        or atomicity_mutant_id not in singleton_cut_mutants
    ):
        raise CatalogError("管理callerの表権限または原子性mutantに単独cut setがない")

    scope = raw["two_factor_scope"]
    if not isinstance(scope, dict) or scope != {
        "population_rule": "all_unordered_pairs_of_configuration_axis_mutants",
        "factor_count": 2,
    }:
        raise CatalogError("2因子母集合の導出規則が不正")
    expected_pairs = mutant_result["config_pairs"]
    assert isinstance(expected_pairs, set)
    interaction_rows = _expect_object_list(
        raw["two_factor_interactions"], "attack tree.two_factor_interactions"
    )
    actual_pairs: set[tuple[str, str]] = set()
    for index, interaction in enumerate(interaction_rows):
        label = f"attack tree.two_factor_interactions[{index}]"
        _expect_keys(
            interaction,
            {
                "interaction_id",
                "factor_mutant_ids",
                "activated_cut_set_ids",
                "expected_attack_established",
            },
            label,
        )
        factors = _expect_string_list(
            interaction["factor_mutant_ids"], f"{label}.factor_mutant_ids"
        )
        if len(factors) != 2 or factors != sorted(factors):
            raise CatalogError(f"{label}: 2因子が正規化されていない")
        factor_set = set(factors)
        expected_activated: list[str] = []
        for cut_id, cut in cut_by_id.items():
            cut_mutant_ids = cut["mutant_ids"]
            assert isinstance(cut_mutant_ids, list)
            if set(cut_mutant_ids) <= factor_set:
                expected_activated.append(cut_id)
        expected_activated.sort()
        if interaction["activated_cut_set_ids"] != expected_activated:
            raise CatalogError(f"{label}: cut set 活性化判定が不一致")
        if interaction["expected_attack_established"] is not bool(expected_activated):
            raise CatalogError(f"{label}: attack 成立期待が不一致")
        actual_pairs.add((factors[0], factors[1]))
    if actual_pairs != expected_pairs or len(interaction_rows) != len(expected_pairs):
        raise CatalogError("attack tree の全2因子が exact-set 不一致")
    return {
        "oracle_commit": oracle_commit,
        "cut_set_count": len(cut_rows),
        "multi_factor_cut_set_count": multi_factor_count,
    }


def validate_boundary_proposal(
    raw: object,
    auth_catalog: dict[str, object],
    root: Path,
) -> dict[str, object]:
    """関数・集計境界案と保留中の人間裁定を検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("boundary proposal はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "oracle_context",
            "proposal_status",
            "boundaries",
            "deferred_equivalence_contract",
            "trust_boundary",
            "pending_human_reviews",
            "provenance",
        },
        "boundary proposal",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_boundary_proposal":
        raise CatalogError("boundary proposal の schema_version または asset_kind が不正")
    oracle_commit = _validate_oracle_context(raw["oracle_context"], "boundary proposal")
    _validate_oracle_provenance(raw["provenance"], root, "boundary proposal")
    if raw["proposal_status"] != "pending_tsk_235_confirmation":
        raise CatalogError("境界案を確定済みにしてはならない")
    boundaries = _expect_object_list(raw["boundaries"], "boundaries")
    boundary_ids = {str(boundary.get("boundary_id")) for boundary in boundaries}
    if boundary_ids != {
        "BOUNDARY:SHARED-AUTHORIZED-ROWS",
        "BOUNDARY:CONTROL-READS",
        "BOUNDARY:REPRESENTATIVE-MANAGEMENT",
    }:
        raise CatalogError("境界案が閉じた3責務と不一致")
    shared = next(
        boundary
        for boundary in boundaries
        if boundary["boundary_id"] == "BOUNDARY:SHARED-AUTHORIZED-ROWS"
    )
    if (
        shared.get("aggregation_location") != "generated_sql_expression"
        or shared.get("returns_tenant_ids_only") is not False
    ):
        raise CatalogError("共有境界に集計または tenant ID だけを置いている")
    representative = next(
        boundary
        for boundary in boundaries
        if boundary["boundary_id"] == "BOUNDARY:REPRESENTATIVE-MANAGEMENT"
    )
    representative_claim_ids = frozenset(
        _expect_string_list(
            representative.get("claim_ids"), "representative management claims"
        )
    )
    if representative_claim_ids != MANAGEMENT_PROBE_CLAIM_IDS:
        raise CatalogError("代表管理境界が2件のprobe claimと exact-set 不一致")
    reviews = _expect_object_list(raw["pending_human_reviews"], "pending_human_reviews")
    review_by_id = {str(review.get("review_id")): review for review in reviews}
    if set(review_by_id) != {
        "PENDING-MANAGEMENT-COMMAND-COUNT",
        "PENDING-ALL-LOGICAL-SCOPE",
    }:
        raise CatalogError("保留中の人間裁定2件が exact-set 不一致")
    operation_review = review_by_id["PENDING-MANAGEMENT-COMMAND-COUNT"]
    if (
        operation_review.get("status") != "pending_human_decision"
        or operation_review.get("frozen_value") != 8
        or operation_review.get("alternative_value") != 7
        or not operation_review.get("affected_ids_if_changed")
    ):
        raise CatalogError("管理操作8/7の保留裁定または影響行が不正")
    entries = auth_catalog.get("entries")
    if not isinstance(entries, list):
        raise CatalogError("AUTH catalog.entries が不正")
    expected_all_logical = sorted(
        str(entry["requirement_claim_id"])
        for entry in entries
        if isinstance(entry, dict) and entry.get("route_scope_id") == "SCOPE:ALL_LOGICAL"
    )
    scope_review = review_by_id["PENDING-ALL-LOGICAL-SCOPE"]
    if (
        scope_review.get("status") != "pending_human_review"
        or scope_review.get("frozen_value") != len(expected_all_logical)
        or scope_review.get("affected_claim_ids") != expected_all_logical
    ):
        raise CatalogError("ALL_LOGICAL 査読対象が AUTH catalog と exact-set 不一致")
    for review in reviews:
        if review.get("oracle_change_action") != "return_to_step_5_and_re_review":
            raise CatalogError("保留裁定が oracle 再レビュー規律へ接続されていない")
    return {
        "oracle_commit": oracle_commit,
        "pending_review_count": len(reviews),
        "all_logical_count": len(expected_all_logical),
    }


def validate_verification_evidence(raw: object, root: Path) -> dict[str, object]:
    """Supabase 0件とDB検査不能な残余リスクを検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("verification evidence はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "oracle_context",
            "supabase_verification",
            "residual_risks",
            "provenance",
        },
        "verification evidence",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_verification_evidence":
        raise CatalogError("verification evidence の schema_version または asset_kind が不正")
    oracle_commit = _validate_oracle_context(raw["oracle_context"], "verification evidence")
    provenance_ids = _validate_oracle_provenance(
        raw["provenance"], root, "verification evidence"
    )
    supabase = raw["supabase_verification"]
    if not isinstance(supabase, dict) or (
        supabase.get("rejected_configuration_count") != 0
        or supabase.get("result") != "candidate_authorization_configuration_established"
        or supabase.get("interpretation")
        != "zero_supabase_rejections_does_not_remove_known_local_rejections"
    ):
        raise CatalogError("Supabase 実機の成立結果と0件の限定が不正")
    _validate_referenced_provenance(
        supabase.get("provenance_ids"), provenance_ids, "Supabase evidence provenance"
    )
    risks = _expect_object_list(raw["residual_risks"], "residual_risks")
    risk_by_id = {str(risk.get("risk_id")): risk for risk in risks}
    if set(risk_by_id) != {"RES-01", "RES-03"}:
        raise CatalogError("DB 層で検査不能な残余リスクが exact-set 不一致")
    expected_handoffs = {
        "RES-01": "operations_control",
        "RES-03": "production_project_creation_procedure",
    }
    for risk_id, risk in risk_by_id.items():
        if (
            risk.get("db_layer_verifiability") != "not_verifiable"
            or risk.get("handoff_destination") != expected_handoffs[risk_id]
        ):
            raise CatalogError(f"{risk_id}: DB 検査不能または申し送り先が不正")
        _validate_referenced_provenance(
            risk.get("provenance_ids"), provenance_ids, f"{risk_id}.provenance_ids"
        )
    return {"oracle_commit": oracle_commit, "residual_risk_count": len(risks)}


def _build_oracle_seal(
    existing_seal: dict[str, object],
    assets: dict[str, dict[str, object]],
    paths: dict[str, str],
    root: Path,
) -> dict[str, object]:
    seal = json.loads(json.dumps(existing_seal))
    input_assets = _expect_object_list(seal.get("input_assets"), "oracle seal.input_assets")
    for entry in input_assets:
        path_text = _expect_string(entry.get("path"), "oracle seal input path")
        path = (root / path_text).resolve()
        entry["git_blob_digest"] = git_blob_digest(_read_bytes(path, path_text))
    roles = {
        "ddl_elements": "expectation",
        "rejected_configs": "evidence",
        "claim_mutant_map": "expectation",
        "attack_tree": "expectation",
        "boundary_proposal": "expectation",
        "verification_evidence": "evidence",
    }
    seal["sealed_assets"] = [
        {
            "path": paths[name],
            "asset_role": roles[name],
            "asset_kind": assets[name]["asset_kind"],
            "canonical_sha256": _table_digest(assets[name]),
        }
        for name in roles
    ]
    return seal


def validate_oracle_seal(
    raw: object,
    assets: dict[str, dict[str, object]],
    paths: dict[str, str],
    root: Path,
) -> str:
    """oracle commit、入力 blob、各資産 canonical digest を検査する。"""
    if not isinstance(raw, dict):
        raise CatalogError("oracle seal はオブジェクトでなければならない")
    _expect_keys(
        raw,
        {
            "schema_version",
            "asset_kind",
            "oracle_commit",
            "oracle_commit_semantics",
            "input_assets",
            "sealed_assets",
            "review_policy",
            "reseal_policy",
        },
        "oracle seal",
    )
    if raw["schema_version"] != 1 or raw["asset_kind"] != "authz_oracle_seal":
        raise CatalogError("oracle seal の schema_version または asset_kind が不正")
    oracle_commit = _expect_string(raw["oracle_commit"], "oracle seal.oracle_commit")
    if not COMMIT_RE.fullmatch(oracle_commit):
        raise CatalogError("oracle_commit が commit SHA でない")
    if raw["oracle_commit_semantics"] != "last_committed_step_4_input_baseline":
        raise CatalogError("oracle_commit の意味が不正")
    for name, asset in assets.items():
        context_raw = asset.get("oracle_context")
        if not isinstance(context_raw, dict) or context_raw.get("oracle_commit") != oracle_commit:
            raise CatalogError(f"{name}: oracle_commit が seal と不一致")
    input_rows = _expect_object_list(raw["input_assets"], "oracle seal.input_assets")
    input_paths: set[str] = set()
    for index, entry in enumerate(input_rows):
        label = f"oracle seal.input_assets[{index}]"
        _expect_keys(entry, {"path", "git_blob_digest"}, label)
        path_text = _expect_string(entry["path"], f"{label}.path")
        path = (root / path_text).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as error:
            raise CatalogError(f"{label}.path がリポジトリ外") from error
        digest = _expect_string(entry["git_blob_digest"], f"{label}.git_blob_digest")
        if not path.is_file() or git_blob_digest(_read_bytes(path, path_text)) != digest:
            raise CatalogError(f"{path_text}: oracle input blob が不一致")
        input_paths.add(path_text)
        if (root / ".git").exists():
            result = subprocess.run(
                ["git", "rev-parse", f"{oracle_commit}:{path_text}"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip() != digest:
                raise CatalogError(f"{path_text}: oracle commit 上の blob が不一致")
    required_input_paths = {
        "contracts/authz/requirement-claims.json",
        "contracts/authz/requirement-claims.lock.json",
        "contracts/authz/route-registry.json",
        "contracts/authz/route-registry.lock.json",
        "contracts/authz/auth-catalog.json",
        "contracts/authz/auth-catalog.lock.json",
        "contracts/authz/http-route-matrix.json",
        "contracts/authz/http-route-matrix.lock.json",
    }
    if input_paths != required_input_paths:
        raise CatalogError("oracle 入力8資産が exact-set 不一致")
    sealed_rows = _expect_object_list(raw["sealed_assets"], "oracle seal.sealed_assets")
    sealed_by_path: dict[str, dict[str, object]] = {}
    for index, entry in enumerate(sealed_rows):
        label = f"oracle seal.sealed_assets[{index}]"
        _expect_keys(
            entry,
            {"path", "asset_role", "asset_kind", "canonical_sha256"},
            label,
        )
        path_text = _expect_string(entry["path"], f"{label}.path")
        digest = _expect_string(entry["canonical_sha256"], f"{label}.canonical_sha256")
        if not SHA256_RE.fullmatch(digest):
            raise CatalogError(f"{path_text}: canonical digest が SHA-256 でない")
        if entry["asset_role"] not in {"expectation", "evidence"}:
            raise CatalogError(f"{path_text}: 期待値と証跡の区分が不正")
        if path_text in sealed_by_path:
            raise CatalogError(f"sealed asset path が重複: {path_text}")
        sealed_by_path[path_text] = entry
    expected_paths = set(paths.values())
    if set(sealed_by_path) != expected_paths:
        raise CatalogError("oracle の封印対象が exact-set 不一致")
    for name, asset in assets.items():
        entry = sealed_by_path[paths[name]]
        if (
            entry["asset_kind"] != asset["asset_kind"]
            or entry["canonical_sha256"] != _table_digest(asset)
        ):
            raise CatalogError(f"{paths[name]}: canonical digest が oracle seal と不一致")
    review_policy = raw["review_policy"]
    if not isinstance(review_policy, dict) or review_policy != {
        "policy_id": ORACLE_CHANGE_POLICY_ID,
        "trigger": "oracle_change_in_revision_2_or_later",
        "required_action": "return_to_step_5_and_re_review",
        "statement": "改訂 2 以降で oracle を変えるなら本ステップまで戻って再レビューする",
    }:
        raise CatalogError("改訂2以降の oracle 再レビュー規律が不正")
    reseal_policy = raw["reseal_policy"]
    if not isinstance(reseal_policy, dict) or reseal_policy != {
        "normal_validation_reseals": False,
        "dedicated_flag": "--reseal-oracle",
        "human_review_required": True,
    }:
        raise CatalogError("oracle の再封印が専用操作に限定されていない")
    return oracle_commit


def validate_oracle_asset_seal(
    asset: dict[str, object],
    relative_path: str,
    seal: object,
) -> None:
    """単一 oracle 資産の canonical digest を封印値と照合する。

    全葉変異テストでは入力8 blob の Git 検査を繰り返さず、この純粋関数で
    変異対象の資産だけを検査する。通常経路は ``validate_oracle_seal`` で
    入力 blob と封印表全体も併せて検査する。

    Args:
        asset: 検査する oracle 資産。
        relative_path: 封印表でのリポジトリ相対パス。
        seal: oracle 封印資産。
    """
    if not isinstance(seal, dict):
        raise CatalogError("oracle seal はオブジェクトでなければならない")
    sealed_rows = _expect_object_list(
        seal.get("sealed_assets"), "oracle seal.sealed_assets"
    )
    matches = [row for row in sealed_rows if row.get("path") == relative_path]
    if len(matches) != 1:
        raise CatalogError(f"{relative_path}: 封印行が exact-one でない")
    entry = matches[0]
    _expect_keys(
        entry,
        {"path", "asset_role", "asset_kind", "canonical_sha256"},
        f"oracle seal[{relative_path}]",
    )
    if (
        entry["asset_kind"] != asset.get("asset_kind")
        or entry["canonical_sha256"] != _table_digest(asset)
    ):
        raise CatalogError(f"{relative_path}: canonical digest が oracle seal と不一致")


def validate_oracle_assets(
    requirement_catalog: dict[str, object],
    route_registry: dict[str, object],
    auth_catalog: dict[str, object],
    http_matrix: dict[str, object],
    assets: dict[str, dict[str, object]],
    seal: object,
    paths: dict[str, str],
    root: Path,
    implemented_test_ids: frozenset[str],
    *,
    verify_seal: bool = True,
) -> dict[str, dict[str, object]]:
    """ステップ5の期待値・証跡・封印を相互検査する。"""
    ddl_result = validate_ddl_elements(assets["ddl_elements"], root)
    rejected_result = validate_rejected_configs(assets["rejected_configs"], root)
    mutant_result = validate_claim_mutant_map(
        assets["claim_mutant_map"],
        requirement_catalog,
        route_registry,
        http_matrix,
        ddl_result,
        root,
        implemented_test_ids,
    )
    attack_result = validate_attack_tree(assets["attack_tree"], mutant_result, root)
    boundary_result = validate_boundary_proposal(
        assets["boundary_proposal"], auth_catalog, root
    )
    evidence_result = validate_verification_evidence(
        assets["verification_evidence"], root
    )
    results: dict[str, dict[str, object]] = {
        "ddl": ddl_result,
        "rejected": rejected_result,
        "mutants": mutant_result,
        "attack": attack_result,
        "boundary": boundary_result,
        "evidence": evidence_result,
    }
    commits = {str(result["oracle_commit"]) for result in results.values()}
    if len(commits) != 1:
        raise CatalogError("oracle 資産間で oracle_commit が不一致")
    if verify_seal:
        seal_commit = validate_oracle_seal(seal, assets, paths, root)
        if commits != {seal_commit}:
            raise CatalogError("oracle 資産と seal の commit が不一致")
    return results


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
    parser.add_argument("--route-registry", type=Path, default=DEFAULT_ROUTE_REGISTRY)
    parser.add_argument(
        "--route-registry-lock", type=Path, default=DEFAULT_ROUTE_REGISTRY_LOCK
    )
    parser.add_argument("--auth-catalog", type=Path, default=DEFAULT_AUTH_CATALOG)
    parser.add_argument(
        "--auth-catalog-lock", type=Path, default=DEFAULT_AUTH_CATALOG_LOCK
    )
    parser.add_argument(
        "--http-route-matrix", type=Path, default=DEFAULT_HTTP_ROUTE_MATRIX
    )
    parser.add_argument(
        "--http-route-matrix-lock",
        type=Path,
        default=DEFAULT_HTTP_ROUTE_MATRIX_LOCK,
    )
    parser.add_argument("--ddl-elements", type=Path, default=DEFAULT_DDL_ELEMENTS)
    parser.add_argument(
        "--rejected-configs", type=Path, default=DEFAULT_REJECTED_CONFIGS
    )
    parser.add_argument(
        "--claim-mutant-map", type=Path, default=DEFAULT_CLAIM_MUTANT_MAP
    )
    parser.add_argument("--attack-tree", type=Path, default=DEFAULT_ATTACK_TREE)
    parser.add_argument(
        "--boundary-proposal", type=Path, default=DEFAULT_BOUNDARY_PROPOSAL
    )
    parser.add_argument(
        "--verification-evidence",
        type=Path,
        default=DEFAULT_VERIFICATION_EVIDENCE,
    )
    parser.add_argument("--oracle-seal", type=Path, default=DEFAULT_ORACLE_SEAL)
    parser.add_argument(
        "--reseal",
        action="store_true",
        help="分類決定の査読後に限り、母集合と lock の digest を明示更新する",
    )
    parser.add_argument(
        "--reseal-derived",
        action="store_true",
        help="ステップ4の3資産を査読後に限り、各 decision lock を明示更新する",
    )
    parser.add_argument(
        "--reseal-oracle",
        action="store_true",
        help="ステップ5の全資産を査読後に限り、oracle seal を明示更新する",
    )
    parser.add_argument(
        "--skip-derived",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--skip-oracle",
        action="store_true",
        help=argparse.SUPPRESS,
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
        reseal_count = sum(
            (bool(args.reseal), bool(args.reseal_derived), bool(args.reseal_oracle))
        )
        if reseal_count > 1:
            raise CatalogError("3 種の再封印フラグは同時に使えない")
        if args.skip_derived and args.reseal_derived:
            raise CatalogError("--skip-derived と --reseal-derived は同時に使えない")
        if args.skip_oracle and args.reseal_oracle:
            raise CatalogError("--skip-oracle と --reseal-oracle は同時に使えない")
        if args.skip_derived and not args.skip_oracle:
            raise CatalogError("oracle 検査にはステップ4資産の検査が必要")
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
        derived_result: dict[str, object] | None = None
        derived_assets: dict[str, dict[str, object]] = {}
        implemented_test_ids = frozenset[str]()
        if not args.skip_derived:
            derived_path_args = {
                "route_registry": (args.route_registry, args.route_registry_lock),
                "auth_catalog": (args.auth_catalog, args.auth_catalog_lock),
                "http_matrix": (args.http_route_matrix, args.http_route_matrix_lock),
            }
            locks: dict[str, object] = {}
            relative_paths: dict[str, str] = {}
            lock_paths: dict[str, Path] = {}
            for name, (asset_argument, lock_argument) in derived_path_args.items():
                asset_path = _resolve(root, asset_argument)
                derived_lock_path = _resolve(root, lock_argument)
                asset = _read_json(asset_path, name)
                if not isinstance(asset, dict):
                    raise CatalogError(f"{name}のルートはオブジェクトでなければならない")
                derived_assets[name] = asset
                relative_paths[name] = _relative_path(root, asset_path, name)
                lock_paths[name] = derived_lock_path
                locks[name] = (
                    build_derived_lock(asset, relative_paths[name])
                    if args.reseal_derived
                    else _read_json(derived_lock_path, f"{name} decision lock")
                )
            implemented_test_ids = collect_pytest_node_ids(root)
            derived_result = validate_derived_assets(
                raw,
                derived_assets["route_registry"],
                derived_assets["auth_catalog"],
                derived_assets["http_matrix"],
                locks,
                relative_paths,
                root,
                implemented_test_ids,
            )
            if args.reseal_derived:
                for name, lock in locks.items():
                    _write_json(lock_paths[name], lock, f"{name} decision lock")
        oracle_result: dict[str, dict[str, object]] | None = None
        if not args.skip_oracle:
            oracle_path_args = {
                "ddl_elements": args.ddl_elements,
                "rejected_configs": args.rejected_configs,
                "claim_mutant_map": args.claim_mutant_map,
                "attack_tree": args.attack_tree,
                "boundary_proposal": args.boundary_proposal,
                "verification_evidence": args.verification_evidence,
            }
            oracle_assets: dict[str, dict[str, object]] = {}
            oracle_relative_paths: dict[str, str] = {}
            for name, asset_argument in oracle_path_args.items():
                asset_path = _resolve(root, asset_argument)
                asset = _read_json(asset_path, name)
                if not isinstance(asset, dict):
                    raise CatalogError(
                        f"{name}のルートはオブジェクトでなければならない"
                    )
                oracle_assets[name] = asset
                oracle_relative_paths[name] = _relative_path(root, asset_path, name)
            oracle_seal_path = _resolve(root, args.oracle_seal)
            oracle_seal = _read_json(oracle_seal_path, "oracle seal")
            oracle_result = validate_oracle_assets(
                raw,
                derived_assets["route_registry"],
                derived_assets["auth_catalog"],
                derived_assets["http_matrix"],
                oracle_assets,
                oracle_seal,
                oracle_relative_paths,
                root,
                implemented_test_ids,
                verify_seal=not args.reseal_oracle,
            )
            if args.reseal_oracle:
                if not isinstance(oracle_seal, dict):
                    raise CatalogError("oracle seal はオブジェクトでなければならない")
                new_seal = _build_oracle_seal(
                    oracle_seal,
                    oracle_assets,
                    oracle_relative_paths,
                    root,
                )
                validate_oracle_seal(
                    new_seal, oracle_assets, oracle_relative_paths, root
                )
                _write_json(oracle_seal_path, new_seal, "oracle seal")
    except CatalogError as error:
        print(f"check_authz_catalog.py: {error}", file=sys.stderr)
        return 1
    summary = (
        "check_authz_catalog.py: "
        f"ok total={sum(counts.values())} "
        f"auth_claim={counts['auth_claim']} out_of_scope={counts['out_of_scope']}"
    )
    if derived_result is not None:
        registry_result = derived_result["registry"]
        catalog_result = derived_result["catalog"]
        matrix_result = derived_result["matrix"]
        assert isinstance(registry_result, dict)
        assert isinstance(catalog_result, dict)
        assert isinstance(matrix_result, dict)
        route_by_id = registry_result["route_by_id"]
        assert isinstance(route_by_id, dict)
        summary += (
            f" db_claims={catalog_result['db_claim_count']}"
            f" routes={len(route_by_id)} cells={matrix_result['cell_count']}"
        )
    if oracle_result is not None:
        mutant_result = oracle_result["mutants"]
        attack_result = oracle_result["attack"]
        execution_counts = mutant_result["execution_counts"]
        axis_counts = mutant_result["axis_counts"]
        assert isinstance(execution_counts, Counter)
        assert isinstance(axis_counts, Counter)
        summary += (
            f" oracle_claims={sum(execution_counts.values())}"
            f" probe={execution_counts['probe_executable']}"
            f" contract={execution_counts['contract_only']}"
            f" mutants={sum(axis_counts.values())}"
            f" cut_sets={attack_result['cut_set_count']}"
        )
    if args.reseal:
        summary += " resealed"
    if args.reseal_derived:
        summary += " derived-resealed"
    if args.reseal_oracle:
        summary += " oracle-resealed"
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
