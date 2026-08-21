"""NFR-021 受入証跡の命名とスキーマを検査する。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping, Sequence

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
