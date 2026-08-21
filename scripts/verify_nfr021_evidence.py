"""NFR-021 受入証跡の命名・スキーマ・ゲート条件を検査する。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping, NoReturn, Sequence

try:
    from core_guard import GuardError
except ModuleNotFoundError:  # pragma: no cover - モジュールとして読み込む場合だけ通る。
    from scripts.core_guard import GuardError


KIND_CANONICAL = "canonical"
KIND_RESERVATION = "reservation"
KIND_EVIDENCE = "evidence"
KIND_INVALID = "invalid"
RECORD_KINDS = frozenset({KIND_RESERVATION, KIND_EVIDENCE})
CANONICAL_FILENAMES = frozenset(
    {
        "README.md",
        "reservation-template.md",
        "evidence-phase4-template.md",
        "evidence-release-template.md",
    }
)
TIMESTAMP_PATTERN = r"\d{4}-\d{2}-\d{2}T\d{6}Z"
COMPACT_TIMESTAMP_PATTERN = r"\d{8}T\d{6}Z"
RELEASE_VERSION_PATTERN = r"v[0-9]+\.[0-9]+\.[0-9]+"
GATE_PAIR_PATTERN = rf"(?:phase4-phase4|release-{RELEASE_VERSION_PATTERN})"
ATTEMPT_SEQUENCE_PATTERN = r"[0-9]+"
SHORT_SHA_PATTERN = r"[0-9a-f]{12}"
FULL_OID_PATTERN = r"[0-9a-f]{40}"
TIMESTAMP_RE = re.compile(TIMESTAMP_PATTERN)
COMPACT_TIMESTAMP_RE = re.compile(COMPACT_TIMESTAMP_PATTERN)
RELEASE_VERSION_RE = re.compile(RELEASE_VERSION_PATTERN)
GATE_PAIR_RE = re.compile(GATE_PAIR_PATTERN)
ATTEMPT_SEQUENCE_RE = re.compile(ATTEMPT_SEQUENCE_PATTERN)
SHORT_SHA_RE = re.compile(SHORT_SHA_PATTERN)
FULL_OID_RE = re.compile(FULL_OID_PATTERN)
RECORD_FILENAME_RE = re.compile(
    rf"(?P<timestamp>{TIMESTAMP_PATTERN})-"
    r"(?P<gate_kind>phase4|release)-"
    rf"(?P<gate_value>phase4|{RELEASE_VERSION_PATTERN})-"
    rf"seq(?P<attempt_sequence>{ATTEMPT_SEQUENCE_PATTERN})-"
    rf"(?P<suffix>reservation|{SHORT_SHA_PATTERN})\.md"
)
ATTEMPT_ID_RE = re.compile(
    rf"(?P<gate_key>phase4|release-{RELEASE_VERSION_PATTERN})-"
    rf"(?P<attempt_sequence>{ATTEMPT_SEQUENCE_PATTERN})-"
    rf"(?P<timestamp>{COMPACT_TIMESTAMP_PATTERN})"
)
FRONTMATTER_KEY_RE = re.compile(
    r"(?P<key>[a-z][a-z0-9_]*)\s*:\s*(?P<value>.*)"
)
BODY_FIELD_ROW_RE = re.compile(
    r"^[ \t]*\|[ \t]*(?P<label>commit SHA|onboarding blob SHA)[ \t]*\|"
    r"[ \t]*(?P<value>[^|]*)\|",
    re.MULTILINE,
)
INTEGER_RE = re.compile(ATTEMPT_SEQUENCE_PATTERN)
QUOTE_CHARACTERS = frozenset({'"', "'"})
MARKDOWN_CODE_DELIMITER = chr(96)
GATE_KINDS = frozenset({"phase4", "release"})
RESULT_VALUES = frozenset({"passed", "failed"})
RESERVATION_KEYS = frozenset(
    {
        "gate_key",
        "attempt_seq",
        "attempt_id",
        "started_at",
        "operator",
    }
)
EVIDENCE_COMMON_KEYS = frozenset(
    {
        "gate_kind",
        "tested_commit_sha",
        "onboarding_blob_sha",
        "result",
        "attempt_seq",
        "attempt_id",
    }
)
EVIDENCE_ALLOWED_KEYS = EVIDENCE_COMMON_KEYS | {"release_version"}
RELEASE_EVIDENCE_KEYS = EVIDENCE_COMMON_KEYS | {"release_version"}
BODY_FIELD_KEYS = (
    ("commit SHA", "tested_commit_sha"),
    ("onboarding blob SHA", "onboarding_blob_sha"),
)
REASON_NOT_DIRECT_CHILD = "受入証跡ディレクトリ直下の項目ではない"
REASON_INVALID_FILENAME = "閉じた命名文法に一致しない"
REASON_INVALID_TIMESTAMP = "タイムスタンプが実在時刻ではない"
REASON_INVALID_GATE_PAIR = "ゲート組が許可された組合せではない"
REASON_INVALID_SEQUENCE = "seq の数値部が正規形ではない"
REASON_INVALID_SHORT_SHA = "short SHA が小文字 16 進 12 桁ではない"
REASON_FRONTMATTER_START = "frontmatter の開始記号がない"
REASON_FRONTMATTER_END = "frontmatter の終端記号がない"
REASON_FRONTMATTER_LINE = "frontmatter の {line_number} 行目の形式が不正"
REASON_FRONTMATTER_DUPLICATE = "frontmatter のキーが重複している: {key}"
REASON_FRONTMATTER_QUOTE = "frontmatter の引用符が不正"
REASON_RECORD_KIND = "正本または不正な項目をレコードとして解析できない"
REASON_MISSING_KEYS = "frontmatter の必須キーがない: {keys}"
REASON_UNKNOWN_KEYS = "frontmatter に未知のキーがある: {keys}"
REASON_STRING_TYPE = "{key} が文字列ではない"
REASON_EMPTY_STRING = "{key} が空である"
REASON_ATTEMPT_SEQUENCE_TYPE = "attempt_seq が引用符なしの 10 進整数ではない"
REASON_ATTEMPT_SEQUENCE_VALUE = "attempt_seq が 1 以上ではない"
REASON_INVALID_GATE_KEY = "gate_key が許可されたゲートキーではない"
REASON_INVALID_GATE_KIND = "gate_kind が許可値ではない"
REASON_MISSING_RELEASE_VERSION = "release の結果証跡に release_version がない"
REASON_PHASE4_RELEASE_VERSION = "phase4 の結果証跡に release_version がある"
REASON_INVALID_RELEASE_VERSION = "release_version が vX.Y.Z 形式ではない"
REASON_INVALID_RESULT = "result が passed または failed ではない"
REASON_INVALID_OID = "{key} が完全な小文字 16 進 40 桁ではない"
REASON_INVALID_STARTED_AT = "started_at が実在時刻ではない"
REASON_INVALID_ATTEMPT_ID = "attempt_id の形式が不正"
REASON_INVALID_ATTEMPT_ID_TIMESTAMP = "attempt_id の時刻が実在時刻ではない"
REASON_ATTEMPT_ID_GATE_KEY = "attempt_id のゲートキーがレコードと一致しない"
REASON_ATTEMPT_ID_SEQUENCE = "attempt_id の連番が record の attempt_seq と一致しない"
REASON_FILENAME_GATE_KIND = "ファイル名の gate_kind が frontmatter と一致しない"
REASON_FILENAME_RELEASE_VERSION = "ファイル名の release_version が frontmatter と一致しない"
REASON_FILENAME_GATE_KEY = "ファイル名のゲート組が gate_key と一致しない"
REASON_FILENAME_SEQUENCE = "ファイル名の seq が frontmatter の attempt_seq と一致しない"
REASON_FILENAME_SHORT_SHA = "ファイル名の short SHA が tested_commit_sha と一致しない"
REASON_BODY_FIELD_MISSING = "本文に {label} の行がない"
REASON_BODY_FIELD_DUPLICATE = "本文の {label} の行が一意ではない"
REASON_BODY_FIELD_MISMATCH = "本文の {label} が frontmatter の {key} と一致しない"
REASON_CONTRACT_GATE_KEY = "同一 attempt_id の予約と結果でゲートキーが一致しない"
REASON_CONTRACT_SEQUENCE = "同一 attempt_id の予約と結果で attempt_seq が一致しない"
REASON_CONTRACT_RELEASE_VERSION = (
    "同一 attempt_id の予約と結果で release_version が一致しない"
)
DIFF_TIMEOUT_SECONDS = 30
INVALIDATING_PATHS_CONFIG_PATH = Path(".claude/nfr021-invalidating-paths.json")
INVALIDATING_PATHS_SYNTAX = "gitignore-root-relative-v1"
CONFIG_KEY_SYNTAX = "syntax"
CONFIG_KEY_DEFAULT = "default"
CONFIG_KEY_INVALIDATING = "invalidating"
CONFIG_KEY_ALLOWLIST = "allowlist"
DEFAULT_POLICY_INVALIDATING = "invalidating"
DEFAULT_POLICY_ALLOWLIST = "allowlist"
DEFAULT_POLICIES = frozenset(
    {DEFAULT_POLICY_INVALIDATING, DEFAULT_POLICY_ALLOWLIST}
)
CLASSIFICATION_INVALIDATING = "invalidating"
CLASSIFICATION_ALLOWLIST = "allowlist"
CLASSIFICATION_DEFAULT = "default"
ROOT_PATH_PREFIX = "/"
PATH_SEPARATOR = "/"
NEGATION_PATTERN_PREFIX = "!"
WILDCARD = "*"
RECURSIVE_WILDCARD = "**"
GIT_EXECUTABLE = "git"
GIT_MERGE_BASE_COMMAND = "merge-base"
GIT_LOG_COMMAND = "log"
GIT_IS_ANCESTOR_OPTION = "--is-ancestor"
GIT_FORMAT_EMPTY_OPTION = "--format="
GIT_NAME_ONLY_OPTION = "--name-only"
GIT_MERGE_SEPARATE_OPTION = "-m"
GIT_NO_RENAMES_OPTION = "--no-renames"
OPERATION_ANCESTOR = "git merge-base --is-ancestor"
OPERATION_CHANGED_PATHS = "git log による変更パスの取得"
REASON_INVALIDATING_CONFIG_READ = "失効パス設定を読み込めない: {error}"
REASON_INVALIDATING_CONFIG_ENCODING = "失効パス設定が UTF-8 ではない"
REASON_INVALIDATING_CONFIG_JSON = "失効パス設定の JSON が不正"
REASON_INVALIDATING_CONFIG_OBJECT = "失効パス設定の最上位がオブジェクトではない"
REASON_INVALIDATING_CONFIG_STRING = "失効パス設定の {key} が文字列ではない"
REASON_INVALIDATING_CONFIG_LIST = "失効パス設定の {key} が文字列配列ではない"
REASON_INVALIDATING_SYNTAX = "失効パス設定の syntax が未対応である"
REASON_INVALIDATING_DEFAULT = "失効パス設定の default が未対応である"
REASON_NEGATION_PATTERN = "失効パス設定に否定パターンがある: {pattern}"
REASON_NON_ROOT_PATTERN = "失効パス設定のパターンがルート相対ではない: {pattern}"
REASON_INVALID_PATTERN = "失効パス設定のパターンが不正である: {pattern}"
REASON_INVALID_CHANGED_PATH = "変更パスがリポジトリ相対の正規形ではない: {path}"
REASON_GIT_TIMEOUT = "{operation} がタイムアウトした"
REASON_GIT_START = "{operation} を起動できない: {error}"
REASON_GIT_FAILURE = "{operation} に失敗した: {returncode}"
REASON_GIT_ANCESTOR_UNRESOLVED = (
    "git merge-base --is-ancestor が解決不能な終了コードを返した: {returncode}"
)
SCRIPT_NAME = "verify_nfr021_evidence"
ACCEPTANCE_DIRECTORY_RELATIVE_PATH = PurePosixPath("docs/ops/nfr021-acceptance")
ONBOARDING_RELATIVE_PATH = "docs/development/onboarding.md"
GIT_CAT_FILE_COMMAND = "cat-file"
GIT_REV_PARSE_COMMAND = "rev-parse"
GIT_SHOW_COMMAND = "show"
GIT_LS_TREE_COMMAND = "ls-tree"
GIT_OBJECT_TYPE_OPTION = "-t"
GIT_NAME_ONLY_OUTPUT_OPTION = "--name-only"
GIT_RECURSIVE_OPTION = "-r"
GIT_NULL_TERMINATE_OPTION = "-z"
GIT_PATHSPEC_SEPARATOR = "--"
GIT_OBJECT_COMMIT = "commit"
GIT_OBJECT_BLOB = "blob"
PASSED_RESULT = "passed"
APPROVED_STATUS = "approved"
ONBOARDING_STATUS_VALUES = frozenset(
    {"draft", "in-review", APPROVED_STATUS, "superseded"}
)
ONBOARDING_STATUS_RE = re.compile(r"^status: (?P<status>[^\s#]+)$")
OPERATION_OBJECT_TYPE = "git cat-file -t"
OPERATION_TREE_PATH = "git ls-tree"
OPERATION_TREE_OBJECT = "git rev-parse"
OPERATION_BLOB_CONTENT = "git show"
OPERATION_ACCEPTANCE_TREE = "git ls-tree による受入証跡の列挙"
REASON_ARGUMENT_ERROR = "コマンドライン引数が不正: {message}"
REASON_CANDIDATE_SHA_LEXICAL = "candidate_sha が完全な小文字 16 進 40 桁ではない"
REASON_CANDIDATE_SHA_TYPE = "candidate_sha が commit オブジェクトではない"
REASON_RELEASE_VERSION_REQUIRED = "release では --release-version が必須である"
REASON_PHASE4_RELEASE_ARGUMENT = "phase4 では --release-version を指定できない"
REASON_RELEASE_VERSION_ARGUMENT = "--release-version が vX.Y.Z 形式ではない"
REASON_GIT_OBJECT_UNRESOLVED = "{label} の Git オブジェクトを解決できない"
REASON_GIT_OBJECT_TYPE_OUTPUT = "{label} の Git オブジェクト種別を解釈できない"
REASON_TREE_OBJECT_OUTPUT = "Git ツリー内の {path} の OID を解釈できない"
REASON_EVIDENCE_PATH_OUTSIDE = (
    "evidence_path が docs/ops/nfr021-acceptance/直下のパスではない"
)
REASON_EVIDENCE_PATH_MISSING = "evidence_path が candidate_sha のツリーに収録されていない"
REASON_EVIDENCE_NOT_RESULT = "evidence_path が結果証跡ではない"
REASON_GATE_KIND_MISMATCH = "gate_kind が要求されたゲート種別と一致しない"
REASON_RESULT_NOT_PASSED = "result が passed ではない"
REASON_TESTED_OBJECT_TYPE = "tested_commit_sha が commit オブジェクトではない"
REASON_ONBOARDING_OBJECT_TYPE = "onboarding_blob_sha が blob オブジェクトではない"
REASON_TESTED_NOT_ANCESTOR = "tested_commit_sha が candidate_sha の祖先ではない"
REASON_ONBOARDING_TREE_MISSING = (
    "tested_commit_sha のツリーに docs/development/onboarding.md がない"
)
REASON_ONBOARDING_TREE_TYPE = "onboarding.md が blob オブジェクトではない"
REASON_ONBOARDING_BLOB_MISMATCH = (
    "onboarding_blob_sha が tested_commit_sha 時点の onboarding.md の blob と一致しない"
)
REASON_ONBOARDING_FRONTMATTER = "onboarding.md の先頭 3 行 frontmatter が不正である"
REASON_ONBOARDING_STATUS = "onboarding.md の status が approved ではない"
REASON_RELEASE_VERSION_MISMATCH = "release_version が要求された版と一致しない"
REASON_INELIGIBLE_PATH = "失効対象の変更がある: {path} ({source})"
REASON_INELIGIBLE_DEFAULT_PATH = "失効対象の変更がある: {path} (default)"
REASON_EVIDENCE_VALUE_UNAVAILABLE = "証跡の {key} を取得できない"
REASON_ACCEPTANCE_TREE_PATH = "受入証跡ツリーのパスが不正である: {path}"
REASON_ACCEPTANCE_TREE_ITEM_TYPE = "受入証跡ツリー項目が blob オブジェクトではない"
REASON_ATTEMPT_VALUE_UNAVAILABLE = "試行への畳み込みに必要な {key} を取得できない"
REASON_NAMED_ATTEMPT_MISSING = "名指しされた結果証跡の試行を候補ツリーから取得できない"
REASON_NAMED_ATTEMPT_NOT_MAXIMUM = "名指しされた証跡の attempt_seq が最大ではない"
REASON_ATTEMPT_MAXIMUM_NOT_UNIQUE = "最大 attempt_seq を持つ試行が一意ではない"
REASON_RESERVATION_UNCLOSED = "予約が結果証跡で閉じられていない: {attempt_id}"
REASON_NAMED_RESERVATION_COUNT = (
    "名指しされた結果証跡に対応する予約がちょうど 1 件ではない"
)
REASON_ORPHAN_EVIDENCE = "結果証跡に対応する予約がない: {attempt_id}"
REASON_MULTIPLE_RESERVATIONS = "同一 attempt_id の予約が複数ある: {attempt_id}"
REASON_MULTIPLE_EVIDENCES = "同一 attempt_id の結果証跡が複数ある: {attempt_id}"

# 字句規則の正は docs/ops/nfr021-acceptance/README.md である。索引カバレッジ用の
# 述語は scripts/check_docs_status.py:151-194 にあり、対象範囲が異なる。


@dataclass(frozen=True)
class AcceptancePath:
    """受入証跡ディレクトリからの相対パスを分類した結果を表す。

    Attributes:
        kind: canonical、reservation、evidence、invalid のいずれか。
        timestamp: ファイル名にあるハイフン付き UTC 時刻。該当しなければ None。
        gate_kind: 結果証跡のゲート種別。該当しなければ None。
        release_version: 結果証跡の release 版。phase4 などでは None。
        gate_key: 予約レコードの合成ゲートキー。該当しなければ None。
        attempt_seq: ファイル名から得た連番。該当しなければ None。
        short_sha: 結果証跡の小文字 16 進 12 桁 SHA。該当しなければ None。
        reason: invalid の不合格理由。その他では None。
    """

    kind: str
    timestamp: str | None
    gate_kind: str | None
    release_version: str | None
    gate_key: str | None
    attempt_seq: int | None
    short_sha: str | None
    reason: str | None


@dataclass(frozen=True)
class Frontmatter:
    """行単位で解析した証跡 frontmatter と本文を表す。

    Attributes:
        values: キーと、文字列または引用符なし整数の対応。
        body: frontmatter 終端より後の本文。
    """

    values: Mapping[str, str | int]
    body: str


@dataclass(frozen=True)
class AcceptanceRecord:
    """スキーマ検査に必要な 1 件の予約または結果証跡を表す。

    Attributes:
        path: 命名文法を解析した結果。
        display_path: 違反出力に用いる表示パス。
        frontmatter: 行単位で解析した frontmatter と本文。
    """

    path: AcceptancePath
    display_path: str
    frontmatter: Frontmatter


@dataclass(frozen=True)
class CandidateGateRecords:
    """候補ツリーから列挙した同一ゲートキーのレコードを表す。

    Attributes:
        records: 正規名であり、対象ゲートキーに属する解析済みレコード。
        violations: 非正規ツリー項目、解析失敗、スキーマ違反を示すメッセージ。
    """

    records: tuple[AcceptanceRecord, ...]
    violations: tuple[str, ...]


@dataclass(frozen=True)
class AcceptanceAttempt:
    """同一 attempt_id の予約と結果証跡を畳み込んだ試行を表す。

    Attributes:
        attempt_id: 予約と結果証跡を対応付ける識別子。
        attempt_seq: 畳み込んだ試行の連番。
        reservations: この試行に属する予約レコード。
        evidences: この試行に属する結果証跡。
        result: 結果証跡が 1 件だけのときの result。その他では None。
    """

    attempt_id: str
    attempt_seq: int
    reservations: tuple[AcceptanceRecord, ...]
    evidences: tuple[AcceptanceRecord, ...]
    result: str | None


def invalid_acceptance_path(reason: str) -> AcceptancePath:
    """不正なツリー項目を表す解析結果を作る。

    Args:
        reason: 不正と判定した理由。

    Returns:
        kind が invalid で、成分を持たない解析結果。
    """
    return AcceptancePath(
        kind=KIND_INVALID,
        timestamp=None,
        gate_kind=None,
        release_version=None,
        gate_key=None,
        attempt_seq=None,
        short_sha=None,
        reason=reason,
    )


def is_valid_timestamp(value: str) -> bool:
    """ハイフン付き UTC 時刻が字句と実在時刻の両方を満たすか判定する。

    Args:
        value: YYYY-MM-DDTHHMMSSZ 形式であるべき値。

    Returns:
        字句と実在時刻の両方を満たす場合は True、それ以外は False。
    """
    if TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H%M%SZ")
    except ValueError:
        return False
    return True


def is_valid_compact_timestamp(value: str) -> bool:
    """日付ハイフンなし UTC 時刻が字句と実在時刻の両方を満たすか判定する。

    Args:
        value: YYYYMMDDTHHMMSSZ 形式であるべき値。

    Returns:
        字句と実在時刻の両方を満たす場合は True、それ以外は False。
    """
    if COMPACT_TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return False
    return True


def is_canonical_attempt_sequence(value: str) -> bool:
    """seq の数値部が最低 3 桁の正規形かを判定する。

    Args:
        value: seq 接頭辞を除いた数値部。

    Returns:
        ASCII 10 進、1 以上、かつ zfill(3) と一致する場合は True。
    """
    if len(value) < 3 or not value.isascii() or not value.isdecimal():
        return False
    number = int(value)
    return number >= 1 and str(number).zfill(3) == value


def format_attempt_sequence(value: int) -> str:
    """attempt_seq をファイル名と attempt_id に使う正規表記へ変換する。

    Args:
        value: 1 以上であるべき attempt_seq。

    Returns:
        最低 3 桁へゼロ詰めした 10 進表記。
    """
    return str(value).zfill(3)


def is_release_version(value: str) -> bool:
    """release_version が許可された vX.Y.Z 形式かを判定する。

    Args:
        value: 検査する release 版。

    Returns:
        v + 数値 3 連の形式なら True、それ以外なら False。
    """
    return RELEASE_VERSION_RE.fullmatch(value) is not None


def is_gate_key(value: str) -> bool:
    """合成形 gate_key が phase4 または release-vX.Y.Z かを判定する。

    Args:
        value: 検査する合成ゲートキー。

    Returns:
        許可された合成ゲートキーなら True、それ以外なら False。
    """
    return value == "phase4" or value.startswith("release-") and is_release_version(
        value.removeprefix("release-")
    )


def derive_gate_key(gate_kind: str, release_version: str | None) -> str | None:
    """結果証跡の種別と版から合成形 gate_key を導出する。

    Args:
        gate_kind: frontmatter の gate_kind。
        release_version: release の場合の frontmatter の版。

    Returns:
        導出できる gate_key。入力の組合せが不正なら None。
    """
    if gate_kind == "phase4" and release_version is None:
        return "phase4"
    if gate_kind == "release" and release_version is not None:
        if is_release_version(release_version):
            return f"release-{release_version}"
    return None


def parse_acceptance_path(relative_path: str | Path) -> AcceptancePath:
    """受入証跡ディレクトリからの相対パスを閉じた命名文法で分類する。

    Args:
        relative_path: docs/ops/nfr021-acceptance からの相対パス。

    Returns:
        種別、抽出成分、または invalid の不合格理由を持つ解析結果。
    """
    path = PurePosixPath(str(relative_path))
    if path.is_absolute() or len(path.parts) != 1:
        return invalid_acceptance_path(REASON_NOT_DIRECT_CHILD)

    filename = path.name
    if filename in CANONICAL_FILENAMES:
        return AcceptancePath(
            kind=KIND_CANONICAL,
            timestamp=None,
            gate_kind=None,
            release_version=None,
            gate_key=None,
            attempt_seq=None,
            short_sha=None,
            reason=None,
        )

    match = RECORD_FILENAME_RE.fullmatch(filename)
    if match is None:
        return invalid_acceptance_path(REASON_INVALID_FILENAME)

    timestamp = match.group("timestamp")
    if not is_valid_timestamp(timestamp):
        return invalid_acceptance_path(REASON_INVALID_TIMESTAMP)

    gate_kind = match.group("gate_kind")
    gate_value = match.group("gate_value")
    if GATE_PAIR_RE.fullmatch(f"{gate_kind}-{gate_value}") is None:
        return invalid_acceptance_path(REASON_INVALID_GATE_PAIR)

    attempt_sequence = match.group("attempt_sequence")
    if not is_canonical_attempt_sequence(attempt_sequence):
        return invalid_acceptance_path(REASON_INVALID_SEQUENCE)
    attempt_seq = int(attempt_sequence)

    suffix = match.group("suffix")
    if suffix == KIND_RESERVATION:
        gate_key = "phase4" if gate_kind == "phase4" else f"release-{gate_value}"
        return AcceptancePath(
            kind=KIND_RESERVATION,
            timestamp=timestamp,
            gate_kind=None,
            release_version=None,
            gate_key=gate_key,
            attempt_seq=attempt_seq,
            short_sha=None,
            reason=None,
        )

    if SHORT_SHA_RE.fullmatch(suffix) is None:
        return invalid_acceptance_path(REASON_INVALID_SHORT_SHA)
    return AcceptancePath(
        kind=KIND_EVIDENCE,
        timestamp=timestamp,
        gate_kind=gate_kind,
        release_version=None if gate_kind == "phase4" else gate_value,
        gate_key=None,
        attempt_seq=attempt_seq,
        short_sha=suffix,
        reason=None,
    )


def strip_inline_comment(value: str) -> str:
    """引用符の外側にある YAML 形式の行末コメントを取り除く。

    Args:
        value: コロンより後の frontmatter 値。

    Returns:
        引用符の外側にある # 以降を除いた値。
    """
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote is not None:
            if character == "\\" and not escaped:
                escaped = True
                continue
            if character == quote and not escaped:
                quote = None
            escaped = False
            continue
        if character in QUOTE_CHARACTERS:
            quote = character
        elif character == "#":
            return value[:index].rstrip()
    return value.rstrip()


def parse_frontmatter_value(value: str) -> str | int:
    """単純な frontmatter 値を文字列または引用符なし整数として解析する。

    Args:
        value: コメント除去後の frontmatter 値。

    Returns:
        引用符付き値なら文字列、ASCII 10 進値なら整数、それ以外なら文字列。

    Raises:
        GuardError: 引用符が閉じていない、または不正な位置にある場合。
    """
    if not value:
        return ""
    if value[0] in QUOTE_CHARACTERS:
        if len(value) < 2 or value[-1] != value[0]:
            raise GuardError(REASON_FRONTMATTER_QUOTE)
        return value[1:-1]
    if value[-1] in QUOTE_CHARACTERS:
        raise GuardError(REASON_FRONTMATTER_QUOTE)
    if INTEGER_RE.fullmatch(value) is not None:
        return int(value)
    return value


def parse_frontmatter(text: str) -> Frontmatter:
    """証跡本文の先頭 frontmatter を行単位で解析する。

    Args:
        text: UTF-8 として読み込んだ証跡ファイル全体の文字列。

    Returns:
        frontmatter の値と、その終端より後の本文。

    Raises:
        GuardError: 区切り記号、キー行、重複キー、または引用符が不正な場合。
    """
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise GuardError(REASON_FRONTMATTER_START)

    frontmatter_end: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            frontmatter_end = index
            break
    if frontmatter_end is None:
        raise GuardError(REASON_FRONTMATTER_END)

    values: dict[str, str | int] = {}
    for line_number, line in enumerate(lines[1:frontmatter_end], start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = FRONTMATTER_KEY_RE.fullmatch(line)
        if match is None:
            raise GuardError(REASON_FRONTMATTER_LINE.format(line_number=line_number))
        key = match.group("key")
        if key in values:
            raise GuardError(REASON_FRONTMATTER_DUPLICATE.format(key=key))
        value = strip_inline_comment(match.group("value")).strip()
        values[key] = parse_frontmatter_value(value)

    return Frontmatter(
        values=MappingProxyType(values),
        body="\n".join(lines[frontmatter_end + 1 :]),
    )


def parse_acceptance_record(
    relative_path: str | Path,
    text: str,
    display_path: str | None = None,
) -> AcceptanceRecord:
    """予約または結果証跡を、命名成分と frontmatter に分解する。

    Args:
        relative_path: docs/ops/nfr021-acceptance からの相対パス。
        text: UTF-8 として読み込んだ証跡ファイル全体の文字列。
        display_path: 違反出力に使う表示パス。省略時は relative_path を使う。

    Returns:
        スキーマ検査に渡せる予約または結果証跡。

    Raises:
        GuardError: パスが正本または不正項目、あるいは frontmatter が不正な場合。
    """
    parsed_path = parse_acceptance_path(relative_path)
    if parsed_path.kind not in RECORD_KINDS:
        raise GuardError(parsed_path.reason or REASON_RECORD_KIND)
    path_text = PurePosixPath(str(relative_path)).as_posix()
    return AcceptanceRecord(
        path=parsed_path,
        display_path=display_path or path_text,
        frontmatter=parse_frontmatter(text),
    )


def format_violation(display_path: str, reason: str) -> str:
    """既存スクリプトと同じパス付き違反メッセージを作る。

    Args:
        display_path: 違反対象を示す表示パス。
        reason: 日本語の不合格理由。

    Returns:
        パス、コロン、理由を連結した違反メッセージ。
    """
    return f"{display_path}: {reason}"


def validate_frontmatter_keys(
    record: AcceptanceRecord,
    required_keys: frozenset[str],
    allowed_keys: frozenset[str],
) -> list[str]:
    """frontmatter の必須キー不足と未知キーを検査する。

    Args:
        record: 検査する予約または結果証跡。
        required_keys: 必ず存在しなければならないキー。
        allowed_keys: 存在を許可する閉じたキー集合。

    Returns:
        パス付きの違反メッセージ配列。
    """
    values = record.frontmatter.values
    violations: list[str] = []
    missing_keys = sorted(required_keys - values.keys())
    if missing_keys:
        violations.append(
            format_violation(
                record.display_path,
                REASON_MISSING_KEYS.format(keys=", ".join(missing_keys)),
            )
        )
    unknown_keys = sorted(values.keys() - allowed_keys)
    if unknown_keys:
        violations.append(
            format_violation(
                record.display_path,
                REASON_UNKNOWN_KEYS.format(keys=", ".join(unknown_keys)),
            )
        )
    return violations


def frontmatter_string(
    record: AcceptanceRecord,
    key: str,
    violations: list[str],
) -> str | None:
    """frontmatter の非空文字列を取り出し、型違反を追加する。

    Args:
        record: 値を取り出す予約または結果証跡。
        key: 取り出す frontmatter キー。
        violations: 検出した違反を追記する配列。

    Returns:
        非空文字列ならその値。不在、型違反、空文字列なら None。
    """
    value = record.frontmatter.values.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        violations.append(
            format_violation(
                record.display_path,
                REASON_STRING_TYPE.format(key=key),
            )
        )
        return None
    if not value:
        violations.append(
            format_violation(
                record.display_path,
                REASON_EMPTY_STRING.format(key=key),
            )
        )
        return None
    return value


def frontmatter_attempt_sequence(
    record: AcceptanceRecord,
    violations: list[str],
) -> int | None:
    """frontmatter の attempt_seq を引用符なしの 1 以上整数として取り出す。

    Args:
        record: 値を取り出す予約または結果証跡。
        violations: 検出した違反を追記する配列。

    Returns:
        1 以上の整数ならその値。それ以外なら None。
    """
    value = record.frontmatter.values.get("attempt_seq")
    if value is None:
        return None
    if type(value) is not int:
        violations.append(
            format_violation(record.display_path, REASON_ATTEMPT_SEQUENCE_TYPE)
        )
        return None
    if value < 1:
        violations.append(
            format_violation(record.display_path, REASON_ATTEMPT_SEQUENCE_VALUE)
        )
        return None
    return value


def validate_oid(
    record: AcceptanceRecord,
    key: str,
    value: str | None,
    violations: list[str],
) -> None:
    """OID が完全な小文字 16 進 40 桁かを字句だけで検査する。

    Args:
        record: 検査する結果証跡。
        key: OID を持つ frontmatter キー。
        value: frontmatter から得た文字列。取得不能なら None。
        violations: 検出した違反を追記する配列。

    Returns:
        なし。違反は violations へ追記する。
    """
    if value is not None and FULL_OID_RE.fullmatch(value) is None:
        violations.append(
            format_violation(
                record.display_path,
                REASON_INVALID_OID.format(key=key),
            )
        )


def validate_attempt_id(
    record: AcceptanceRecord,
    attempt_id: str | None,
    gate_key: str | None,
    attempt_seq: int | None,
    violations: list[str],
) -> None:
    """attempt_id の字句とレコード自身のゲートキー・連番との一致を検査する。

    Args:
        record: 検査する予約または結果証跡。
        attempt_id: frontmatter から得た attempt_id。
        gate_key: そのレコードから得た合成ゲートキー。
        attempt_seq: そのレコードから得た連番。
        violations: 検出した違反を追記する配列。

    Returns:
        なし。違反は violations へ追記する。
    """
    if attempt_id is None:
        return
    match = ATTEMPT_ID_RE.fullmatch(attempt_id)
    if match is None:
        violations.append(format_violation(record.display_path, REASON_INVALID_ATTEMPT_ID))
        return
    if not is_valid_compact_timestamp(match.group("timestamp")):
        violations.append(
            format_violation(record.display_path, REASON_INVALID_ATTEMPT_ID_TIMESTAMP)
        )
    if gate_key is not None and match.group("gate_key") != gate_key:
        violations.append(
            format_violation(record.display_path, REASON_ATTEMPT_ID_GATE_KEY)
        )
    if attempt_seq is not None:
        expected_sequence = format_attempt_sequence(attempt_seq)
        if match.group("attempt_sequence") != expected_sequence:
            violations.append(
                format_violation(record.display_path, REASON_ATTEMPT_ID_SEQUENCE)
            )


def extract_body_field(body: str, label: str) -> str:
    """本文の Markdown 表から指定ラベルの記録値を一意に取り出す。

    Args:
        body: frontmatter 終端より後の証跡本文。
        label: 取り出す表の項目名。

    Returns:
        前後空白と外側の単一コード区切り記号を除いた記録値。

    Raises:
        GuardError: 指定ラベルの行がない、または複数ある場合。
    """
    values = [
        match.group("value")
        for match in BODY_FIELD_ROW_RE.finditer(body)
        if match.group("label") == label
    ]
    if not values:
        raise GuardError(REASON_BODY_FIELD_MISSING.format(label=label))
    if len(values) != 1:
        raise GuardError(REASON_BODY_FIELD_DUPLICATE.format(label=label))
    value = values[0].strip()
    if (
        len(value) >= 2
        and value.startswith(MARKDOWN_CODE_DELIMITER)
        and value.endswith(MARKDOWN_CODE_DELIMITER)
    ):
        value = value[1:-1].strip()
    return value


def validate_evidence_body(
    record: AcceptanceRecord,
    tested_commit_sha: str | None,
    onboarding_blob_sha: str | None,
    violations: list[str],
) -> None:
    """結果証跡本文の 2 つの二重記録が frontmatter と一致するか検査する。

    Args:
        record: 検査する結果証跡。
        tested_commit_sha: frontmatter の tested_commit_sha。
        onboarding_blob_sha: frontmatter の onboarding_blob_sha。
        violations: 検出した違反を追記する配列。

    Returns:
        なし。違反は violations へ追記する。
    """
    values = {
        "commit SHA": tested_commit_sha,
        "onboarding blob SHA": onboarding_blob_sha,
    }
    for label, key in BODY_FIELD_KEYS:
        expected_value = values[label]
        if expected_value is None:
            continue
        try:
            actual_value = extract_body_field(record.frontmatter.body, label)
        except GuardError as error:
            violations.append(format_violation(record.display_path, str(error)))
            continue
        if actual_value != expected_value:
            violations.append(
                format_violation(
                    record.display_path,
                    REASON_BODY_FIELD_MISMATCH.format(label=label, key=key),
                )
            )


def validate_reservation_schema(
    record: AcceptanceRecord,
    violations: list[str],
) -> None:
    """予約レコードの閉じたスキーマとファイル名対応を検査する。

    Args:
        record: kind が reservation の予約レコード。
        violations: 検出した違反を追記する配列。

    Returns:
        なし。違反は violations へ追記する。
    """
    violations.extend(
        validate_frontmatter_keys(record, RESERVATION_KEYS, RESERVATION_KEYS)
    )
    gate_key = frontmatter_string(record, "gate_key", violations)
    attempt_seq = frontmatter_attempt_sequence(record, violations)
    attempt_id = frontmatter_string(record, "attempt_id", violations)
    started_at = frontmatter_string(record, "started_at", violations)
    frontmatter_string(record, "operator", violations)

    if gate_key is not None and not is_gate_key(gate_key):
        violations.append(
            format_violation(record.display_path, REASON_INVALID_GATE_KEY)
        )
    if started_at is not None and not is_valid_timestamp(started_at):
        violations.append(
            format_violation(record.display_path, REASON_INVALID_STARTED_AT)
        )
    validate_attempt_id(record, attempt_id, gate_key, attempt_seq, violations)

    if gate_key is not None and record.path.gate_key != gate_key:
        violations.append(
            format_violation(record.display_path, REASON_FILENAME_GATE_KEY)
        )
    if attempt_seq is not None and record.path.attempt_seq != attempt_seq:
        violations.append(
            format_violation(record.display_path, REASON_FILENAME_SEQUENCE)
        )


def validate_evidence_schema(
    record: AcceptanceRecord,
    violations: list[str],
) -> None:
    """結果証跡の閉じたスキーマ、本文二重記録、ファイル名対応を検査する。

    Args:
        record: kind が evidence の結果証跡。
        violations: 検出した違反を追記する配列。

    Returns:
        なし。違反は violations へ追記する。
    """
    gate_kind_value = record.frontmatter.values.get("gate_kind")
    required_keys = (
        RELEASE_EVIDENCE_KEYS
        if gate_kind_value == "release"
        else EVIDENCE_COMMON_KEYS
    )
    violations.extend(
        validate_frontmatter_keys(record, required_keys, EVIDENCE_ALLOWED_KEYS)
    )
    gate_kind = frontmatter_string(record, "gate_kind", violations)
    tested_commit_sha = frontmatter_string(record, "tested_commit_sha", violations)
    onboarding_blob_sha = frontmatter_string(record, "onboarding_blob_sha", violations)
    result = frontmatter_string(record, "result", violations)
    attempt_seq = frontmatter_attempt_sequence(record, violations)
    attempt_id = frontmatter_string(record, "attempt_id", violations)

    if gate_kind is not None and gate_kind not in GATE_KINDS:
        violations.append(
            format_violation(record.display_path, REASON_INVALID_GATE_KIND)
        )
    if result is not None and result not in RESULT_VALUES:
        violations.append(format_violation(record.display_path, REASON_INVALID_RESULT))
    validate_oid(record, "tested_commit_sha", tested_commit_sha, violations)
    validate_oid(record, "onboarding_blob_sha", onboarding_blob_sha, violations)

    release_version: str | None = None
    if gate_kind == "release":
        release_version = frontmatter_string(record, "release_version", violations)
        if release_version is not None and not is_release_version(release_version):
            violations.append(
                format_violation(record.display_path, REASON_INVALID_RELEASE_VERSION)
            )
    elif gate_kind == "phase4" and "release_version" in record.frontmatter.values:
        violations.append(
            format_violation(record.display_path, REASON_PHASE4_RELEASE_VERSION)
        )

    gate_key = derive_gate_key(gate_kind or "", release_version)
    validate_attempt_id(record, attempt_id, gate_key, attempt_seq, violations)

    if gate_kind is not None and record.path.gate_kind != gate_kind:
        violations.append(
            format_violation(record.display_path, REASON_FILENAME_GATE_KIND)
        )
    if record.path.release_version is None:
        if "release_version" in record.frontmatter.values:
            violations.append(
                format_violation(record.display_path, REASON_FILENAME_RELEASE_VERSION)
            )
    elif release_version is not None and record.path.release_version != release_version:
        violations.append(
            format_violation(record.display_path, REASON_FILENAME_RELEASE_VERSION)
        )
    if attempt_seq is not None and record.path.attempt_seq != attempt_seq:
        violations.append(
            format_violation(record.display_path, REASON_FILENAME_SEQUENCE)
        )
    if tested_commit_sha is not None and record.path.short_sha != tested_commit_sha[:12]:
        violations.append(
            format_violation(record.display_path, REASON_FILENAME_SHORT_SHA)
        )
    validate_evidence_body(
        record,
        tested_commit_sha,
        onboarding_blob_sha,
        violations,
    )


def validate_record_schema(record: AcceptanceRecord) -> tuple[str, ...]:
    """予約または結果証跡 1 件のスキーマ適合を検査する。

    Args:
        record: 命名成分と frontmatter を解析済みの受入証跡。

    Returns:
        パス付きの違反メッセージ。適合していれば空のタプル。
    """
    violations: list[str] = []
    if record.path.kind == KIND_RESERVATION:
        validate_reservation_schema(record, violations)
    elif record.path.kind == KIND_EVIDENCE:
        validate_evidence_schema(record, violations)
    else:
        violations.append(format_violation(record.display_path, REASON_RECORD_KIND))
    return tuple(violations)


def record_attempt_id(record: AcceptanceRecord) -> str | None:
    """レコード間契約の比較に使える文字列の attempt_id を得る。

    Args:
        record: attempt_id を持つ予約または結果証跡。

    Returns:
        非空文字列の attempt_id。型違反などで得られなければ None。
    """
    value = record.frontmatter.values.get("attempt_id")
    if isinstance(value, str) and value:
        return value
    return None


def record_gate_key(record: AcceptanceRecord) -> str | None:
    """レコード間契約の比較に使える合成 gate_key を得る。

    Args:
        record: gate_key または gate_kind を持つ予約または結果証跡。

    Returns:
        導出可能な合成 gate_key。型違反などで得られなければ None。
    """
    values = record.frontmatter.values
    if record.path.kind == KIND_RESERVATION:
        value = values.get("gate_key")
        return value if isinstance(value, str) and value else None
    gate_kind = values.get("gate_kind")
    release_version = values.get("release_version")
    if not isinstance(gate_kind, str):
        return None
    if release_version is not None and not isinstance(release_version, str):
        return None
    return derive_gate_key(gate_kind, release_version)


def record_release_version(record: AcceptanceRecord) -> str | None:
    """レコード間契約の比較に使える release_version を得る。

    Args:
        record: release_version を直接または gate_key に持つ受入証跡。

    Returns:
        release の版。phase4 または型違反などでは None。
    """
    if record.path.kind == KIND_RESERVATION:
        gate_key = record_gate_key(record)
        if gate_key is not None and gate_key.startswith("release-"):
            return gate_key.removeprefix("release-")
        return None
    value = record.frontmatter.values.get("release_version")
    return value if isinstance(value, str) and value else None


def record_attempt_sequence(record: AcceptanceRecord) -> int | None:
    """レコード間契約の比較に使える整数の attempt_seq を得る。

    Args:
        record: attempt_seq を持つ受入証跡。

    Returns:
        整数の attempt_seq。型違反などで得られなければ None。
    """
    value = record.frontmatter.values.get("attempt_seq")
    return value if type(value) is int else None


def validate_record_relationships(
    records: Sequence[AcceptanceRecord],
) -> tuple[str, ...]:
    """同一 attempt_id の予約と結果が一致契約を満たすか検査する。

    Args:
        records: 同じツリーから得た予約と結果証跡の列。

    Returns:
        ゲートキー、連番、release_version の不一致を示す違反メッセージ。
    """
    reservations = [
        record for record in records if record.path.kind == KIND_RESERVATION
    ]
    evidences = [
        record for record in records if record.path.kind == KIND_EVIDENCE
    ]
    violations: list[str] = []
    for reservation in reservations:
        reservation_id = record_attempt_id(reservation)
        if reservation_id is None:
            continue
        for evidence in evidences:
            if record_attempt_id(evidence) != reservation_id:
                continue
            if record_gate_key(reservation) != record_gate_key(evidence):
                violations.append(
                    format_violation(
                        evidence.display_path,
                        REASON_CONTRACT_GATE_KEY,
                    )
                )
            if record_attempt_sequence(reservation) != record_attempt_sequence(evidence):
                violations.append(
                    format_violation(
                        evidence.display_path,
                        REASON_CONTRACT_SEQUENCE,
                    )
                )
            if record_release_version(reservation) != record_release_version(evidence):
                violations.append(
                    format_violation(
                        evidence.display_path,
                        REASON_CONTRACT_RELEASE_VERSION,
                    )
                )
    return tuple(violations)


def validate_records(records: Sequence[AcceptanceRecord]) -> tuple[str, ...]:
    """レコードごとのスキーマとレコード間の一致契約をまとめて検査する。

    Args:
        records: 同じツリーから得た予約と結果証跡の列。

    Returns:
        パス付きの全違反メッセージ。適合していれば空のタプル。
    """
    violations = [
        violation
        for record in records
        for violation in validate_record_schema(record)
    ]
    violations.extend(validate_record_relationships(records))
    return tuple(violations)


@dataclass(frozen=True)
class InvalidationSettings:
    """失効判定用 JSON 設定を検証済みの形で表す。

    Attributes:
        syntax: パターン照合の意味論を識別する文字列。
        default: どちらのリストにも一致しないパスの分類方針。
        invalidating_patterns: 一致時に失効させるルート相対パターン。
        allowlist_patterns: 一致時に失効させないルート相対パターン。
    """

    syntax: str
    default: str
    invalidating_patterns: tuple[str, ...]
    allowlist_patterns: tuple[str, ...]


@dataclass(frozen=True)
class PathClassification:
    """変更パスを失効設定へ照合した結果を表す。

    Attributes:
        path: リポジトリルートからの変更パス。
        classification: invalidating、allowlist、default のいずれか。
        matched_pattern: 一致した設定パターン。既定分類なら None。
        invalidating: このパスが証跡を失効させるか。
    """

    path: str
    classification: str
    matched_pattern: str | None
    invalidating: bool


@dataclass(frozen=True)
class InvalidationResult:
    """祖先条件と変更パスから得た失効判定を表す。

    Attributes:
        invalidated: 証跡を失効として扱うべきか。
        ancestor: tested_commit_sha が candidate_sha の祖先か。
        classifications: 祖先の場合の変更パス別照合結果。
    """

    invalidated: bool
    ancestor: bool
    classifications: tuple[PathClassification, ...]


def require_invalidation_string(value: object, key: str) -> str:
    """失効パス設定の文字列項目を fail-closed で取り出す。

    Args:
        value: JSON から得た項目値。
        key: エラーメッセージに表示する設定キー。

    Returns:
        空文字列でない文字列値。

    Raises:
        GuardError: 項目が空文字列でない文字列ではない場合。
    """
    if not isinstance(value, str) or not value:
        raise GuardError(REASON_INVALIDATING_CONFIG_STRING.format(key=key))
    return value


def require_invalidation_pattern_list(value: object, key: str) -> tuple[str, ...]:
    """失効パス設定の文字列配列を fail-closed で取り出す。

    Args:
        value: JSON から得た項目値。
        key: エラーメッセージに表示する設定キー。

    Returns:
        空文字列を含まないパターンのタプル。

    Raises:
        GuardError: 項目が文字列配列ではない場合。
    """
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise GuardError(REASON_INVALIDATING_CONFIG_LIST.format(key=key))
    return tuple(value)


def validate_root_relative_pattern(pattern: str) -> None:
    """gitignore-root-relative-v1 の 1 パターンを検証する。

    Args:
        pattern: 検証するルート相対パターン。

    Returns:
        戻り値はない。

    Raises:
        GuardError: 否定、非ルート相対、または未対応のパターンの場合。
    """
    if pattern.startswith(NEGATION_PATTERN_PREFIX):
        raise GuardError(REASON_NEGATION_PATTERN.format(pattern=pattern))
    if not pattern.startswith(ROOT_PATH_PREFIX):
        raise GuardError(REASON_NON_ROOT_PATTERN.format(pattern=pattern))
    segments = pattern.removeprefix(ROOT_PATH_PREFIX).split(PATH_SEPARATOR)
    if not pattern.removeprefix(ROOT_PATH_PREFIX) or any(not segment for segment in segments):
        raise GuardError(REASON_INVALID_PATTERN.format(pattern=pattern))
    if any(
        RECURSIVE_WILDCARD in segment and segment != RECURSIVE_WILDCARD
        for segment in segments
    ):
        raise GuardError(REASON_INVALID_PATTERN.format(pattern=pattern))


def parse_invalidation_settings(value: object) -> InvalidationSettings:
    """JSON 値を検証済みの失効パス設定へ変換する。

    Args:
        value: JSON としてデコードした設定値。

    Returns:
        パターン文法と全パターンを検証済みの設定。

    Raises:
        GuardError: 設定の構造、文法、または既定方針が未対応の場合。
    """
    if not isinstance(value, dict):
        raise GuardError(REASON_INVALIDATING_CONFIG_OBJECT)
    syntax = require_invalidation_string(value.get(CONFIG_KEY_SYNTAX), CONFIG_KEY_SYNTAX)
    default = require_invalidation_string(
        value.get(CONFIG_KEY_DEFAULT),
        CONFIG_KEY_DEFAULT,
    )
    invalidating_patterns = require_invalidation_pattern_list(
        value.get(CONFIG_KEY_INVALIDATING),
        CONFIG_KEY_INVALIDATING,
    )
    allowlist_patterns = require_invalidation_pattern_list(
        value.get(CONFIG_KEY_ALLOWLIST),
        CONFIG_KEY_ALLOWLIST,
    )
    if syntax != INVALIDATING_PATHS_SYNTAX:
        raise GuardError(REASON_INVALIDATING_SYNTAX)
    if default not in DEFAULT_POLICIES:
        raise GuardError(REASON_INVALIDATING_DEFAULT)
    for pattern in (*invalidating_patterns, *allowlist_patterns):
        validate_root_relative_pattern(pattern)
    return InvalidationSettings(
        syntax=syntax,
        default=default,
        invalidating_patterns=invalidating_patterns,
        allowlist_patterns=allowlist_patterns,
    )


def load_invalidation_settings(path: Path) -> InvalidationSettings:
    """JSON ファイルから失効パス設定を読み込む。

    Args:
        path: 読み込む失効パス設定ファイルの絶対または相対パス。

    Returns:
        検証済みの失効パス設定。

    Raises:
        GuardError: ファイルの読込、UTF-8 復号、JSON 解析、または設定検証に失敗した場合。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise GuardError(REASON_INVALIDATING_CONFIG_READ.format(error=error)) from error
    except UnicodeDecodeError as error:
        raise GuardError(REASON_INVALIDATING_CONFIG_ENCODING) from error
    try:
        return parse_invalidation_settings(json.loads(text))
    except json.JSONDecodeError as error:
        raise GuardError(REASON_INVALIDATING_CONFIG_JSON) from error


def changed_path_segments(path: str) -> tuple[str, ...]:
    """リポジトリ相対の変更パスをセグメント列へ分解する。

    Args:
        path: 先頭スラッシュを持たない変更パス。

    Returns:
        スラッシュ区切りの空でないセグメント列。

    Raises:
        GuardError: 変更パスがリポジトリ相対の正規形ではない場合。
    """
    if (
        not path
        or path.startswith(ROOT_PATH_PREFIX)
        or any(segment in {"", ".", ".."} for segment in path.split(PATH_SEPARATOR))
    ):
        raise GuardError(REASON_INVALID_CHANGED_PATH.format(path=path))
    return tuple(path.split(PATH_SEPARATOR))


def pattern_segments(pattern: str) -> tuple[str, ...]:
    """検証済みのルート相対パターンをセグメント列へ分解する。

    Args:
        pattern: 検証するルート相対パターン。

    Returns:
        先頭スラッシュを除いたパターンセグメント列。

    Raises:
        GuardError: パターンが gitignore-root-relative-v1 の制約を満たさない場合。
    """
    validate_root_relative_pattern(pattern)
    return tuple(pattern.removeprefix(ROOT_PATH_PREFIX).split(PATH_SEPARATOR))


def matches_path_segment(pattern: str, value: str) -> bool:
    """スラッシュを含まない 1 セグメントの * ワイルドカードを照合する。

    Args:
        pattern: * を含み得るパターンセグメント。
        value: 照合対象のパスセグメント。

    Returns:
        パターンが value 全体に一致すれば True。

    Raises:
        発生しない。
    """
    pattern_index = 0
    value_index = 0
    wildcard_index = -1
    resume_value_index = 0
    while value_index < len(value):
        if (
            pattern_index < len(pattern)
            and pattern[pattern_index] == value[value_index]
        ):
            pattern_index += 1
            value_index += 1
        elif pattern_index < len(pattern) and pattern[pattern_index] == WILDCARD:
            wildcard_index = pattern_index
            pattern_index += 1
            resume_value_index = value_index
        elif wildcard_index >= 0:
            pattern_index = wildcard_index + 1
            resume_value_index += 1
            value_index = resume_value_index
        else:
            return False
    while pattern_index < len(pattern) and pattern[pattern_index] == WILDCARD:
        pattern_index += 1
    return pattern_index == len(pattern)


def matches_path_segments(
    patterns: tuple[str, ...],
    paths: tuple[str, ...],
    pattern_index: int = 0,
    path_index: int = 0,
) -> bool:
    """セグメント列に * と ** の意味論を適用して完全一致を判定する。

    Args:
        patterns: 先頭スラッシュを除いたパターンセグメント列。
        paths: リポジトリ相対パスのセグメント列。
        pattern_index: 次に評価するパターンセグメントの添字。
        path_index: 次に評価するパスセグメントの添字。

    Returns:
        パターンがパス全体に一致すれば True。

    Raises:
        発生しない。
    """
    if pattern_index == len(patterns):
        return path_index == len(paths)
    pattern = patterns[pattern_index]
    if pattern == RECURSIVE_WILDCARD:
        if pattern_index == len(patterns) - 1:
            return path_index < len(paths)
        return any(
            matches_path_segments(patterns, paths, pattern_index + 1, next_path_index)
            for next_path_index in range(path_index, len(paths) + 1)
        )
    if path_index == len(paths):
        return False
    return matches_path_segment(pattern, paths[path_index]) and matches_path_segments(
        patterns,
        paths,
        pattern_index + 1,
        path_index + 1,
    )


def path_matches_invalidation_pattern(path: str, pattern: str) -> bool:
    """ルート相対パターンがリポジトリ相対パスに一致するか判定する。

    fnmatch は * がスラッシュを跨ぎ、** を特別扱いしないため使用しない。

    Args:
        path: 先頭スラッシュを持たないリポジトリ相対パス。
        pattern: 先頭スラッシュを持つ失効パス設定のパターン。

    Returns:
        gitignore-root-relative-v1 の意味論で一致すれば True。

    Raises:
        GuardError: パスまたはパターンが正規形ではない場合。
    """
    return matches_path_segments(pattern_segments(pattern), changed_path_segments(path))


def classify_invalidation_path(
    path: str,
    settings: InvalidationSettings,
) -> PathClassification:
    """変更パスを失効対象、allowlist、既定方針のいずれかへ分類する。

    Args:
        path: 先頭スラッシュを持たないリポジトリ相対パス。
        settings: 検証済みの失効パス設定。

    Returns:
        一致パターンと失効可否を含む分類結果。

    Raises:
        GuardError: パスがリポジトリ相対の正規形ではない場合。
    """
    invalidating_pattern = next(
        (
            pattern
            for pattern in settings.invalidating_patterns
            if path_matches_invalidation_pattern(path, pattern)
        ),
        None,
    )
    allowlist_pattern = next(
        (
            pattern
            for pattern in settings.allowlist_patterns
            if path_matches_invalidation_pattern(path, pattern)
        ),
        None,
    )
    if invalidating_pattern is not None:
        return PathClassification(
            path=path,
            classification=CLASSIFICATION_INVALIDATING,
            matched_pattern=invalidating_pattern,
            invalidating=True,
        )
    if allowlist_pattern is not None:
        return PathClassification(
            path=path,
            classification=CLASSIFICATION_ALLOWLIST,
            matched_pattern=allowlist_pattern,
            invalidating=False,
        )
    return PathClassification(
        path=path,
        classification=CLASSIFICATION_DEFAULT,
        matched_pattern=None,
        invalidating=settings.default == DEFAULT_POLICY_INVALIDATING,
    )


def is_ancestor(root: Path, tested_commit_sha: str, candidate_sha: str) -> bool:
    """tested_commit_sha が candidate_sha の祖先かを Git の三値終了コードで判定する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        tested_commit_sha: 祖先として確認するコミット OID。
        candidate_sha: 子孫として確認するコミット OID。

    Returns:
        祖先なら True、祖先でなければ False。

    Raises:
        GuardError: Git の起動、タイムアウト、またはオブジェクト解決に失敗した場合。
    """
    try:
        result = subprocess.run(
            [
                GIT_EXECUTABLE,
                GIT_MERGE_BASE_COMMAND,
                GIT_IS_ANCESTOR_OPTION,
                tested_commit_sha,
                candidate_sha,
            ],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GuardError(REASON_GIT_TIMEOUT.format(operation=OPERATION_ANCESTOR)) from error
    except OSError as error:
        raise GuardError(
            REASON_GIT_START.format(operation=OPERATION_ANCESTOR, error=error)
        ) from error
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise GuardError(
        REASON_GIT_ANCESTOR_UNRESOLVED.format(returncode=result.returncode)
    )


def changed_paths_between(
    root: Path,
    tested_commit_sha: str,
    candidate_sha: str,
) -> frozenset[str]:
    """祖先 T から候補 C までに変更されたパスの重複のない集合を得る。

    Args:
        root: Git リポジトリのルートディレクトリ。
        tested_commit_sha: 範囲の始点 T。
        candidate_sha: 範囲の終点 C。

    Returns:
        T 自身を含まず、空行を除いた変更パスの集合。

    Raises:
        GuardError: Git の起動、タイムアウト、またはコマンド実行に失敗した場合。
    """
    # -m はマージコミットを親ごとに展開し、既定時の差分取りこぼしを防ぐ。
    # --no-renames は旧パスも出力させ、失効対象から allowlist への移動を検出する。
    # git diff T C、T...C、--diff-filter は削除済みパスや必要な変更種別を落とすため使わない。
    try:
        result = subprocess.run(
            [
                GIT_EXECUTABLE,
                GIT_LOG_COMMAND,
                GIT_FORMAT_EMPTY_OPTION,
                GIT_NAME_ONLY_OPTION,
                GIT_MERGE_SEPARATE_OPTION,
                GIT_NO_RENAMES_OPTION,
                f"{tested_commit_sha}..{candidate_sha}",
            ],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GuardError(
            REASON_GIT_TIMEOUT.format(operation=OPERATION_CHANGED_PATHS)
        ) from error
    except OSError as error:
        raise GuardError(
            REASON_GIT_START.format(operation=OPERATION_CHANGED_PATHS, error=error)
        ) from error
    if result.returncode != 0:
        raise GuardError(
            REASON_GIT_FAILURE.format(
                operation=OPERATION_CHANGED_PATHS,
                returncode=result.returncode,
            )
        )
    return frozenset(path for path in result.stdout.splitlines() if path)


def evaluate_invalidation(
    root: Path,
    tested_commit_sha: str,
    candidate_sha: str,
    settings: InvalidationSettings,
) -> InvalidationResult:
    """祖先条件と変更パス集合から証跡の失効可否を判定する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        tested_commit_sha: 証跡が記録したコミット T。
        candidate_sha: 検証対象の候補コミット C。
        settings: 検証済みの失効パス設定。

    Returns:
        祖先条件と失効させたパスの照合理由を含む判定結果。

    Raises:
        GuardError: Git の実行または変更パスの照合に失敗した場合。
    """
    if not is_ancestor(root, tested_commit_sha, candidate_sha):
        return InvalidationResult(
            invalidated=True,
            ancestor=False,
            classifications=(),
        )
    classifications = tuple(
        classify_invalidation_path(path, settings)
        for path in sorted(changed_paths_between(root, tested_commit_sha, candidate_sha))
    )
    return InvalidationResult(
        invalidated=any(result.invalidating for result in classifications),
        ancestor=True,
        classifications=classifications,
    )


class EvidenceArgumentParser(argparse.ArgumentParser):
    """引数エラーを GuardError として fail-closed にする argparse パーサ。"""

    def error(self, message: str) -> NoReturn:
        """argparse の引数エラーを GuardError へ変換する。

        Args:
            message: argparse が生成した引数エラーの説明。

        Returns:
            このメソッドは戻らない。

        Raises:
            GuardError: 引数の形式または必須性が不正な場合。
        """
        raise GuardError(REASON_ARGUMENT_ERROR.format(message=message))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """NFR-021 証跡検証器のコマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時は通常のコマンドライン引数を使う。

    Returns:
        解釈済みのコマンドライン引数。

    Raises:
        GuardError: 引数の形式、ゲート種別、または release 版の組合せが不正な場合。
    """
    parser = EvidenceArgumentParser(description="NFR-021 の名指し証跡を検証する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument(
        "--gate-kind",
        choices=tuple(sorted(GATE_KINDS)),
        required=True,
        help="検証するゲート種別",
    )
    parser.add_argument(
        "--candidate-sha",
        required=True,
        help="検証対象として固定した完全な commit OID",
    )
    parser.add_argument(
        "--evidence-path",
        type=Path,
        required=True,
        help="候補 SHA のツリーにある結果証跡 1 ファイルのパス",
    )
    parser.add_argument(
        "--release-version",
        help="release ゲートで要求する vX.Y.Z 形式の版",
    )
    args = parser.parse_args(argv)
    validate_cli_gate_arguments(args.gate_kind, args.release_version)
    return args


def validate_cli_gate_arguments(
    gate_kind: str,
    release_version: str | None,
) -> None:
    """ゲート種別と release 版の判別共用体入力を検証する。

    Args:
        gate_kind: phase4 または release の要求ゲート種別。
        release_version: release で要求する版。phase4 では None でなければならない。

    Returns:
        戻り値はない。

    Raises:
        GuardError: ゲート種別または release 版の組合せが不正な場合。
    """
    if gate_kind not in GATE_KINDS:
        raise GuardError(REASON_ARGUMENT_ERROR.format(message="--gate-kind が不正"))
    if gate_kind == "phase4" and release_version is not None:
        raise GuardError(REASON_PHASE4_RELEASE_ARGUMENT)
    if gate_kind == "release" and release_version is None:
        raise GuardError(REASON_RELEASE_VERSION_REQUIRED)
    if release_version is not None and not is_release_version(release_version):
        raise GuardError(REASON_RELEASE_VERSION_ARGUMENT)


def run_git_command(
    root: Path,
    command: Sequence[str],
    operation: str,
    failure_reason: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """指定した Git コマンドを fail-closed で実行する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        command: git 実行ファイルから始まるコマンド引数列。
        operation: タイムアウト・起動失敗時に表示する操作名。
        failure_reason: 非 0 終了時に返す GuardError の理由。省略時は終了コードを含む。

    Returns:
        正常終了した Git コマンドの実行結果。

    Raises:
        GuardError: Git の起動、タイムアウト、またはコマンド実行に失敗した場合。
    """
    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GuardError(REASON_GIT_TIMEOUT.format(operation=operation)) from error
    except OSError as error:
        raise GuardError(REASON_GIT_START.format(operation=operation, error=error)) from error
    if result.returncode != 0:
        raise GuardError(
            failure_reason
            or REASON_GIT_FAILURE.format(
                operation=operation,
                returncode=result.returncode,
            )
        )
    return result


def git_object_type(root: Path, object_id: str, label: str) -> str:
    """生の Git OID が指すオブジェクト種別を取得する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        object_id: 完全な小文字 16 進 OID。
        label: エラー理由に表示する OID の役割名。

    Returns:
        git cat-file -t が返したオブジェクト種別。

    Raises:
        GuardError: OID を解決できない、または種別出力が不正な場合。
    """
    # 注釈付きタグを剥がさないため、OID をそのまま cat-file -t に渡す。
    result = run_git_command(
        root,
        [GIT_EXECUTABLE, GIT_CAT_FILE_COMMAND, GIT_OBJECT_TYPE_OPTION, object_id],
        OPERATION_OBJECT_TYPE,
        REASON_GIT_OBJECT_UNRESOLVED.format(label=label),
    )
    object_type = result.stdout.strip()
    if not object_type or "\n" in object_type:
        raise GuardError(REASON_GIT_OBJECT_TYPE_OUTPUT.format(label=label))
    return object_type


def validate_candidate_sha(root: Path, candidate_sha: str) -> None:
    """候補 SHA の字句と生の commit オブジェクト種別を検証する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        candidate_sha: 検証対象として固定した候補 SHA。

    Returns:
        戻り値はない。

    Raises:
        GuardError: SHA が完全 OID ではない、解決不能、または commit ではない場合。
    """
    if FULL_OID_RE.fullmatch(candidate_sha) is None:
        raise GuardError(REASON_CANDIDATE_SHA_LEXICAL)
    if git_object_type(root, candidate_sha, "candidate_sha") != GIT_OBJECT_COMMIT:
        raise GuardError(REASON_CANDIDATE_SHA_TYPE)


def evidence_relative_path(evidence_path: Path) -> PurePosixPath | None:
    """入力パスが受入証跡ディレクトリ直下かを判定する。

    Args:
        evidence_path: CLI で指定された証跡パス。

    Returns:
        直下のリポジトリ相対 POSIX パス。範囲外なら None。

    Raises:
        発生しない。
    """
    path = PurePosixPath(evidence_path.as_posix())
    if path.is_absolute() or path.parent != ACCEPTANCE_DIRECTORY_RELATIVE_PATH:
        return None
    if not path.name or any(part in {".", ".."} for part in path.parts):
        return None
    return path


def git_tree_has_path(root: Path, commit_sha: str, relative_path: str) -> bool:
    """指定コミットのツリーにリポジトリ相対パスが存在するかを調べる。

    Args:
        root: Git リポジトリのルートディレクトリ。
        commit_sha: 読み取るコミット OID。
        relative_path: リポジトリルートからの POSIX 相対パス。

    Returns:
        パスがコミットのツリーに収録されていれば True。

    Raises:
        GuardError: Git の起動、タイムアウト、またはツリー照会に失敗した場合。
    """
    result = run_git_command(
        root,
        [
            GIT_EXECUTABLE,
            GIT_LS_TREE_COMMAND,
            GIT_NAME_ONLY_OUTPUT_OPTION,
            commit_sha,
            GIT_PATHSPEC_SEPARATOR,
            relative_path,
        ],
        OPERATION_TREE_PATH,
    )
    return relative_path in result.stdout.splitlines()


def git_tree_object_oid(
    root: Path,
    commit_sha: str,
    relative_path: str,
) -> str | None:
    """コミットのツリーにあるパスの OID を完全形で取得する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        commit_sha: 読み取るコミット OID。
        relative_path: リポジトリルートからの POSIX 相対パス。

    Returns:
        対象パスの完全な OID。ツリーに無ければ None。

    Raises:
        GuardError: Git の起動、タイムアウト、または OID 出力の解釈に失敗した場合。
    """
    if not git_tree_has_path(root, commit_sha, relative_path):
        return None
    result = run_git_command(
        root,
        [GIT_EXECUTABLE, GIT_REV_PARSE_COMMAND, f"{commit_sha}:{relative_path}"],
        OPERATION_TREE_OBJECT,
    )
    object_id = result.stdout.strip()
    if FULL_OID_RE.fullmatch(object_id) is None:
        raise GuardError(REASON_TREE_OBJECT_OUTPUT.format(path=relative_path))
    return object_id


def git_blob_contents(root: Path, blob_sha: str) -> str:
    """生の blob OID から UTF-8 として扱う内容を Git で取得する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        blob_sha: 取得する blob の完全 OID。

    Returns:
        git show が返した blob 内容。

    Raises:
        GuardError: Git の起動、タイムアウト、または blob 内容の取得に失敗した場合。
    """
    result = run_git_command(
        root,
        [GIT_EXECUTABLE, GIT_SHOW_COMMAND, blob_sha],
        OPERATION_BLOB_CONTENT,
    )
    return result.stdout


def required_evidence_value(record: AcceptanceRecord, key: str) -> str:
    """スキーマ適合済みの結果証跡から必須文字列キーを取り出す。

    Args:
        record: スキーマ適合を確認済みの結果証跡。
        key: 取り出す frontmatter キー。

    Returns:
        空でない文字列の frontmatter 値。

    Raises:
        GuardError: スキーマ適合済みという前提に反して値を取得できない場合。
    """
    value = record.frontmatter.values.get(key)
    if not isinstance(value, str) or not value:
        raise GuardError(REASON_EVIDENCE_VALUE_UNAVAILABLE.format(key=key))
    return value


def validate_gate_conditions(
    record: AcceptanceRecord,
    requested_gate_kind: str,
    requested_release_version: str | None,
) -> tuple[str, ...]:
    """名指し結果証跡の合格条件①②⑤を検査する。

    Args:
        record: frontmatter を解析済みの結果証跡。
        requested_gate_kind: CLI で要求されたゲート種別。
        requested_release_version: release で要求された版。phase4 では None。

    Returns:
        パスを含まない不合格理由。適合していれば空のタプル。

    Raises:
        GuardError: release の要求版が不在など、CLI の判別共用体前提が崩れた場合。
    """
    values = record.frontmatter.values
    reasons: list[str] = []
    if values.get("gate_kind") != requested_gate_kind:
        reasons.append(REASON_GATE_KIND_MISMATCH)
    if values.get("result") != PASSED_RESULT:
        reasons.append(REASON_RESULT_NOT_PASSED)
    if requested_gate_kind == "release":
        if requested_release_version is None:
            raise GuardError(REASON_RELEASE_VERSION_REQUIRED)
        if values.get("release_version") != requested_release_version:
            reasons.append(REASON_RELEASE_VERSION_MISMATCH)
    elif requested_gate_kind == "phase4" and "release_version" in values:
        reasons.append(REASON_PHASE4_RELEASE_VERSION)
    return tuple(reasons)


def parse_onboarding_status(text: str) -> str | None:
    """正本の厳格な先頭 3 行 frontmatter から onboarding の status を得る。

    Args:
        text: Git blob から取得した onboarding.md の内容。

    Returns:
        許可語彙の status。3 行 frontmatter が不正なら None。

    Raises:
        発生しない。
    """
    lines = text.splitlines()
    if len(lines) < 3 or lines[0] != "---" or lines[2] != "---":
        return None
    match = ONBOARDING_STATUS_RE.fullmatch(lines[1])
    if match is None:
        return None
    status = match.group("status")
    return status if status in ONBOARDING_STATUS_VALUES else None


def validate_onboarding_blob(
    root: Path,
    tested_commit_sha: str,
    onboarding_blob_sha: str,
) -> tuple[str, ...]:
    """合格条件④の onboarding blob 一致と approved status を検査する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        tested_commit_sha: 実施時点 T の commit OID。
        onboarding_blob_sha: 結果証跡に記録された onboarding blob OID。

    Returns:
        パスを含まない不合格理由。適合していれば空のタプル。

    Raises:
        GuardError: Git の起動、タイムアウト、またはオブジェクト解決に失敗した場合。
    """
    tree_blob_sha = git_tree_object_oid(
        root,
        tested_commit_sha,
        ONBOARDING_RELATIVE_PATH,
    )
    if tree_blob_sha is None:
        return (REASON_ONBOARDING_TREE_MISSING,)
    if git_object_type(root, tree_blob_sha, "onboarding.md") != GIT_OBJECT_BLOB:
        return (REASON_ONBOARDING_TREE_TYPE,)
    reasons: list[str] = []
    if onboarding_blob_sha != tree_blob_sha:
        reasons.append(REASON_ONBOARDING_BLOB_MISMATCH)
    status = parse_onboarding_status(git_blob_contents(root, tree_blob_sha))
    if status is None:
        reasons.append(REASON_ONBOARDING_FRONTMATTER)
    elif status != APPROVED_STATUS:
        reasons.append(REASON_ONBOARDING_STATUS)
    return tuple(reasons)


def validate_evidence_object_types(
    root: Path,
    record: AcceptanceRecord,
) -> tuple[str, ...]:
    """結果証跡の tested_commit_sha と onboarding_blob_sha の生の種別を検査する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        record: スキーマ適合を確認済みの結果証跡。

    Returns:
        パスを含まない不合格理由。種別が適合していれば空のタプル。

    Raises:
        GuardError: 証跡に記録された完全 OID を解決できない場合。
    """
    tested_commit_sha = required_evidence_value(record, "tested_commit_sha")
    onboarding_blob_sha = required_evidence_value(record, "onboarding_blob_sha")
    reasons: list[str] = []
    if git_object_type(root, tested_commit_sha, "tested_commit_sha") != GIT_OBJECT_COMMIT:
        reasons.append(REASON_TESTED_OBJECT_TYPE)
    if git_object_type(root, onboarding_blob_sha, "onboarding_blob_sha") != GIT_OBJECT_BLOB:
        reasons.append(REASON_ONBOARDING_OBJECT_TYPE)
    return tuple(reasons)


def invalidation_reasons(result: InvalidationResult) -> tuple[str, ...]:
    """失効判定結果から失効対象の変更パスを説明する理由を作る。

    Args:
        result: ステップ 2 の失効判定結果。

    Returns:
        失効対象の各パスと一致元を示す理由。失効パスがなければ空のタプル。

    Raises:
        発生しない。
    """
    reasons: list[str] = []
    for classification in result.classifications:
        if not classification.invalidating:
            continue
        if classification.matched_pattern is None:
            reasons.append(
                REASON_INELIGIBLE_DEFAULT_PATH.format(path=classification.path)
            )
        else:
            reasons.append(
                REASON_INELIGIBLE_PATH.format(
                    path=classification.path,
                    source=classification.matched_pattern,
                )
            )
    return tuple(reasons)


def candidate_acceptance_tree_paths(
    root: Path,
    candidate_sha: str,
) -> tuple[PurePosixPath, ...]:
    """候補コミットの受入証跡ディレクトリにある全ツリー項目を列挙する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        candidate_sha: 読み取る候補 commit OID。

    Returns:
        リポジトリルートからの正規化済み POSIX パスを辞書順に並べた組。

    Raises:
        GuardError: Git の起動、ツリー出力、またはツリー項目のパスが不正な場合。
    """
    # -r でサブディレクトリ配下も列挙し、-z で任意のファイル名を区切る。
    result = run_git_command(
        root,
        [
            GIT_EXECUTABLE,
            GIT_LS_TREE_COMMAND,
            GIT_RECURSIVE_OPTION,
            GIT_NAME_ONLY_OUTPUT_OPTION,
            GIT_NULL_TERMINATE_OPTION,
            candidate_sha,
            GIT_PATHSPEC_SEPARATOR,
            ACCEPTANCE_DIRECTORY_RELATIVE_PATH.as_posix(),
        ],
        OPERATION_ACCEPTANCE_TREE,
    )
    paths: list[PurePosixPath] = []
    for path_text in result.stdout.split("\0"):
        if not path_text:
            continue
        path = PurePosixPath(path_text)
        try:
            relative_path = path.relative_to(ACCEPTANCE_DIRECTORY_RELATIVE_PATH)
        except ValueError as error:
            raise GuardError(
                REASON_ACCEPTANCE_TREE_PATH.format(path=path_text)
            ) from error
        if (
            path.is_absolute()
            or not relative_path.parts
            or any(part in {".", ".."} for part in relative_path.parts)
        ):
            raise GuardError(REASON_ACCEPTANCE_TREE_PATH.format(path=path_text))
        paths.append(path)
    return tuple(sorted(paths, key=PurePosixPath.as_posix))


def acceptance_relative_path(tree_path: PurePosixPath) -> PurePosixPath:
    """受入証跡ツリー項目をディレクトリからの相対パスへ変換する。

    Args:
        tree_path: リポジトリルートからの受入証跡ツリー項目の POSIX パス。

    Returns:
        docs/ops/nfr021-acceptance からの相対 POSIX パス。

    Raises:
        GuardError: 指定パスが受入証跡ディレクトリ配下の正規形でない場合。
    """
    try:
        relative_path = tree_path.relative_to(ACCEPTANCE_DIRECTORY_RELATIVE_PATH)
    except ValueError as error:
        raise GuardError(
            REASON_ACCEPTANCE_TREE_PATH.format(path=tree_path.as_posix())
        ) from error
    if not relative_path.parts or any(part in {".", ".."} for part in relative_path.parts):
        raise GuardError(REASON_ACCEPTANCE_TREE_PATH.format(path=tree_path.as_posix()))
    return relative_path


def acceptance_path_gate_key(path: AcceptancePath) -> str | None:
    """命名成分から予約・結果証跡を比較できる合成 gate_key に正規化する。

    Args:
        path: 閉じた命名文法で分類済みの受入証跡パス。

    Returns:
        reservation または evidence の合成 gate_key。その他では None。

    Raises:
        発生しない。
    """
    if path.kind == KIND_RESERVATION:
        return path.gate_key
    if path.kind == KIND_EVIDENCE:
        return derive_gate_key(path.gate_kind or "", path.release_version)
    return None


def enumerate_candidate_gate_records(
    root: Path,
    candidate_sha: str,
    gate_key: str,
) -> CandidateGateRecords:
    """候補ツリーから同一ゲートキーのレコードを列挙して適合を検査する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        candidate_sha: 読み取る候補 commit OID。
        gate_key: phase4 または release-vX.Y.Z の対象合成ゲートキー。

    Returns:
        対象ゲートキーの解析済みレコードと、ツリー・スキーマ違反の組。

    Raises:
        GuardError: Git の起動、ツリー項目の解決、または対象 gate_key が不正な場合。
    """
    if not is_gate_key(gate_key):
        raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="gate_key"))

    records: list[AcceptanceRecord] = []
    violations: list[str] = []
    for tree_path in candidate_acceptance_tree_paths(root, candidate_sha):
        relative_path = acceptance_relative_path(tree_path)
        parsed_path = parse_acceptance_path(relative_path)
        display_path = tree_path.as_posix()
        if parsed_path.kind == KIND_CANONICAL:
            continue
        if parsed_path.kind == KIND_INVALID:
            violations.append(
                format_violation(
                    display_path,
                    parsed_path.reason or REASON_INVALID_FILENAME,
                )
            )
            continue
        if parsed_path.kind not in RECORD_KINDS:
            violations.append(format_violation(display_path, REASON_RECORD_KIND))
            continue
        if acceptance_path_gate_key(parsed_path) != gate_key:
            continue

        object_id = git_tree_object_oid(root, candidate_sha, display_path)
        if object_id is None:
            raise GuardError(REASON_ACCEPTANCE_TREE_PATH.format(path=display_path))
        if git_object_type(root, object_id, display_path) != GIT_OBJECT_BLOB:
            violations.append(
                format_violation(display_path, REASON_ACCEPTANCE_TREE_ITEM_TYPE)
            )
            continue
        try:
            record = parse_acceptance_record(
                relative_path,
                git_blob_contents(root, object_id),
                display_path,
            )
        except GuardError as error:
            violations.append(format_violation(display_path, str(error)))
            continue
        records.append(record)

    # 同一ゲートキーに限りスキーマと予約・結果の一致契約を適用する。
    violations.extend(validate_records(records))
    return CandidateGateRecords(
        records=tuple(records),
        violations=tuple(dict.fromkeys(violations)),
    )


def fold_acceptance_attempts(
    records: Sequence[AcceptanceRecord],
) -> tuple[AcceptanceAttempt, ...]:
    """予約と結果証跡を attempt_id 単位の試行へ畳み込む。

    Args:
        records: スキーマ・レコード間契約に適合した同一ゲートキーのレコード。

    Returns:
        attempt_id の辞書順に並べた畳み込み済み試行。

    Raises:
        GuardError: 畳み込みに必要な attempt_id または attempt_seq を取得できない場合。
    """
    records_by_id: dict[str, list[AcceptanceRecord]] = {}
    for record in records:
        attempt_id = record_attempt_id(record)
        attempt_seq = record_attempt_sequence(record)
        if attempt_id is None:
            raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="attempt_id"))
        if attempt_seq is None:
            raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="attempt_seq"))
        records_by_id.setdefault(attempt_id, []).append(record)

    attempts: list[AcceptanceAttempt] = []
    for attempt_id in sorted(records_by_id):
        attempt_records = records_by_id[attempt_id]
        attempt_sequences = {
            record_attempt_sequence(record) for record in attempt_records
        }
        if len(attempt_sequences) != 1 or None in attempt_sequences:
            raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="attempt_seq"))
        attempt_seq = next(iter(attempt_sequences))
        if type(attempt_seq) is not int:
            raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="attempt_seq"))
        reservations = tuple(
            record
            for record in attempt_records
            if record.path.kind == KIND_RESERVATION
        )
        evidences = tuple(
            record
            for record in attempt_records
            if record.path.kind == KIND_EVIDENCE
        )
        result: str | None = None
        if len(evidences) == 1:
            evidence_result = evidences[0].frontmatter.values.get("result")
            if not isinstance(evidence_result, str):
                raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="result"))
            result = evidence_result
        attempts.append(
            AcceptanceAttempt(
                attempt_id=attempt_id,
                attempt_seq=attempt_seq,
                reservations=reservations,
                evidences=evidences,
                result=result,
            )
        )
    return tuple(attempts)


def validate_folded_attempts(
    named_record: AcceptanceRecord,
    attempts: Sequence[AcceptanceAttempt],
) -> tuple[str, ...]:
    """畳み込み済み試行集合に合格条件⑦⑧⑨を適用する。

    Args:
        named_record: evidence_path で名指しされた結果証跡。
        attempts: attempt_id で畳み込み済みの同一ゲートキー試行集合。

    Returns:
        パス付きの⑦⑧⑨違反。適合していれば空のタプル。

    Raises:
        GuardError: 名指しレコードの attempt_id を取得できない場合。
    """
    named_attempt_id = record_attempt_id(named_record)
    if named_attempt_id is None:
        raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="attempt_id"))
    named_attempt = next(
        (attempt for attempt in attempts if attempt.attempt_id == named_attempt_id),
        None,
    )
    if named_attempt is None:
        return (
            format_violation(named_record.display_path, REASON_NAMED_ATTEMPT_MISSING),
        )

    violations: list[str] = []
    maximum_attempt_seq = max(attempt.attempt_seq for attempt in attempts)
    if named_attempt.attempt_seq != maximum_attempt_seq:
        violations.append(
            format_violation(named_record.display_path, REASON_NAMED_ATTEMPT_NOT_MAXIMUM)
        )
    if sum(attempt.attempt_seq == maximum_attempt_seq for attempt in attempts) != 1:
        violations.append(
            format_violation(named_record.display_path, REASON_ATTEMPT_MAXIMUM_NOT_UNIQUE)
        )

    for attempt in attempts:
        if attempt.reservations and not attempt.evidences:
            violations.append(
                format_violation(
                    attempt.reservations[0].display_path,
                    REASON_RESERVATION_UNCLOSED.format(attempt_id=attempt.attempt_id),
                )
            )
        if len(attempt.reservations) > 1:
            for reservation in attempt.reservations:
                violations.append(
                    format_violation(
                        reservation.display_path,
                        REASON_MULTIPLE_RESERVATIONS.format(
                            attempt_id=attempt.attempt_id
                        ),
                    )
                )
        if attempt.evidences and not attempt.reservations:
            for evidence in attempt.evidences:
                violations.append(
                    format_violation(
                        evidence.display_path,
                        REASON_ORPHAN_EVIDENCE.format(attempt_id=attempt.attempt_id),
                    )
                )
        if len(attempt.evidences) > 1:
            for evidence in attempt.evidences:
                violations.append(
                    format_violation(
                        evidence.display_path,
                        REASON_MULTIPLE_EVIDENCES.format(attempt_id=attempt.attempt_id),
                    )
                )

    if len(named_attempt.reservations) != 1:
        violations.append(
            format_violation(
                named_record.display_path,
                REASON_NAMED_RESERVATION_COUNT,
            )
        )
    return tuple(dict.fromkeys(violations))


def validate_attempt_conditions(
    root: Path,
    candidate_sha: str,
    named_record: AcceptanceRecord,
) -> tuple[str, ...]:
    """候補ツリーの列挙、畳み込み、合格条件⑦⑧⑨を順に検査する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        candidate_sha: 読み取る候補 commit OID。
        named_record: evidence_path で名指しされたスキーマ適合済み結果証跡。

    Returns:
        パス付きの⑦⑧⑨違反。適合していれば空のタプル。

    Raises:
        GuardError: 対象ゲートキー、Git ツリー、または畳み込み入力を解決できない場合。
    """
    gate_key = record_gate_key(named_record)
    if gate_key is None:
        raise GuardError(REASON_ATTEMPT_VALUE_UNAVAILABLE.format(key="gate_key"))
    candidate_records = enumerate_candidate_gate_records(root, candidate_sha, gate_key)
    if candidate_records.violations:
        return candidate_records.violations
    attempts = fold_acceptance_attempts(candidate_records.records)
    return validate_folded_attempts(named_record, attempts)


def verify_named_evidence(
    root: Path,
    requested_gate_kind: str,
    candidate_sha: str,
    evidence_path: Path,
    requested_release_version: str | None,
) -> tuple[str, ...]:
    """名指しされた候補ツリー内の結果証跡について合格条件①〜⑨を検査する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        requested_gate_kind: CLI で要求された phase4 または release。
        candidate_sha: 検証対象として固定した候補 commit OID。
        evidence_path: 候補ツリーから読む結果証跡のリポジトリ相対パス。
        requested_release_version: release で要求する版。phase4 では None。

    Returns:
        display_path を先頭に持つ不合格メッセージ。適合していれば空のタプル。

    Raises:
        GuardError: 入力 SHA や Git オブジェクトを解決できず判定不能な場合。
    """
    validate_cli_gate_arguments(requested_gate_kind, requested_release_version)
    validate_candidate_sha(root, candidate_sha)
    display_path = evidence_path.as_posix()
    relative_path = evidence_relative_path(evidence_path)
    if relative_path is None:
        return (format_violation(display_path, REASON_EVIDENCE_PATH_OUTSIDE),)
    path_text = relative_path.as_posix()
    if not git_tree_has_path(root, candidate_sha, path_text):
        return (format_violation(display_path, REASON_EVIDENCE_PATH_MISSING),)
    evidence_blob_sha = git_tree_object_oid(root, candidate_sha, path_text)
    if evidence_blob_sha is None:
        return (format_violation(display_path, REASON_EVIDENCE_PATH_MISSING),)
    evidence_text = git_blob_contents(root, evidence_blob_sha)
    try:
        record = parse_acceptance_record(
            relative_path.name,
            evidence_text,
            display_path,
        )
    except GuardError as error:
        return (format_violation(display_path, str(error)),)
    if record.path.kind != KIND_EVIDENCE:
        return (format_violation(display_path, REASON_EVIDENCE_NOT_RESULT),)
    schema_violations = validate_records((record,))
    gate_violations = tuple(
        format_violation(display_path, reason)
        for reason in validate_gate_conditions(
            record,
            requested_gate_kind,
            requested_release_version,
        )
    )
    violations = tuple(dict.fromkeys((*schema_violations, *gate_violations)))
    if violations:
        return violations
    object_type_violations = tuple(
        format_violation(display_path, reason)
        for reason in validate_evidence_object_types(root, record)
    )
    if object_type_violations:
        return object_type_violations
    tested_commit_sha = required_evidence_value(record, "tested_commit_sha")
    onboarding_blob_sha = required_evidence_value(record, "onboarding_blob_sha")
    if not is_ancestor(root, tested_commit_sha, candidate_sha):
        return (format_violation(display_path, REASON_TESTED_NOT_ANCESTOR),)
    onboarding_violations = tuple(
        format_violation(display_path, reason)
        for reason in validate_onboarding_blob(
            root,
            tested_commit_sha,
            onboarding_blob_sha,
        )
    )
    invalidation = evaluate_invalidation(
        root,
        tested_commit_sha,
        candidate_sha,
        load_invalidation_settings(root / INVALIDATING_PATHS_CONFIG_PATH),
    )
    invalidation_violations = tuple(
        format_violation(display_path, reason)
        for reason in invalidation_reasons(invalidation)
    )
    prior_violations = tuple(
        dict.fromkeys((*onboarding_violations, *invalidation_violations))
    )
    if prior_violations:
        return prior_violations
    return validate_attempt_conditions(root, candidate_sha, record)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI から名指しされた NFR-021 証跡を検査する。

    Args:
        argv: テスト時に指定する引数列。省略時は通常のコマンドライン引数を使う。

    Returns:
        違反なしなら 0、不合格または判定不能なら 1。
    """
    try:
        args = parse_args(argv)
        violations = verify_named_evidence(
            args.root.resolve(),
            args.gate_kind,
            args.candidate_sha,
            args.evidence_path,
            args.release_version,
        )
    except GuardError as error:
        print(f"{SCRIPT_NAME}: {error}", file=sys.stderr)
        return 1
    for violation in violations:
        print(violation, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
