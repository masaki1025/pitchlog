"""NFR-021 受入証跡の append-only 統合時検査を行う。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import NoReturn, Sequence

# 依存の向きは append-only 検査から検証器だけであり、逆向きの import は作らない。
try:
    from core_guard import GuardError
    from verify_nfr021_evidence import (
        ACCEPTANCE_DIRECTORY_RELATIVE_PATH,
        GIT_OBJECT_BLOB,
        KIND_CANONICAL,
        KIND_EVIDENCE,
        KIND_INVALID,
        KIND_RESERVATION,
        AcceptanceRecord,
        acceptance_relative_path,
        candidate_acceptance_tree_paths,
        format_violation,
        git_blob_contents,
        git_object_type,
        git_tree_object_oid,
        parse_acceptance_path,
        parse_acceptance_record,
        record_attempt_id,
        record_attempt_sequence,
        record_gate_key,
        validate_evidence_completeness,
        validate_record_relationships,
        validate_records,
    )
except ModuleNotFoundError:  # pragma: no cover - モジュールとして読み込む場合だけ通る。
    from scripts.core_guard import GuardError
    from scripts.verify_nfr021_evidence import (
        ACCEPTANCE_DIRECTORY_RELATIVE_PATH,
        GIT_OBJECT_BLOB,
        KIND_CANONICAL,
        KIND_EVIDENCE,
        KIND_INVALID,
        KIND_RESERVATION,
        AcceptanceRecord,
        acceptance_relative_path,
        candidate_acceptance_tree_paths,
        format_violation,
        git_blob_contents,
        git_object_type,
        git_tree_object_oid,
        parse_acceptance_path,
        parse_acceptance_record,
        record_attempt_id,
        record_attempt_sequence,
        record_gate_key,
        validate_evidence_completeness,
        validate_record_relationships,
        validate_records,
    )


SCRIPT_NAME = "check_nfr021_append_only"
GIT_EXECUTABLE = "git"
GIT_DIFF_COMMAND = "diff"
GIT_NAME_STATUS_OPTION = "--name-status"
GIT_NO_RENAMES_OPTION = "--no-renames"
DIFF_TIMEOUT_SECONDS = 30
PULL_REQUEST_EVENT_NAME = "pull_request"
DEVELOP_BRANCH = "develop"
GITHUB_EVENT_NAME = "GITHUB_EVENT_NAME"
GITHUB_EVENT_PATH = "GITHUB_EVENT_PATH"
GIT_STATUS_ADDED = "A"
GIT_STATUS_TWO_PATH_KINDS = frozenset({"C", "R"})
GIT_STATUS_KINDS = frozenset({"A", "B", "C", "D", "M", "R", "T", "U", "X"})
REASON_ARGUMENT_ERROR = "コマンドライン引数が不正: {message}"
REASON_LOCAL_REVISIONS = "ローカル実行では --base と --head を両方指定する必要がある"
REASON_EVENT_NAME_MISSING = "GITHUB_EVENT_PATH があるのに GITHUB_EVENT_NAME が未設定である"
REASON_EVENT_PATH_MISSING = "pull_request イベントなのに GITHUB_EVENT_PATH が未設定である"
REASON_EVENT_READ = "GITHUB_EVENT_PATH を読み込めない: {error}"
REASON_EVENT_ENCODING = "GITHUB_EVENT_PATH が UTF-8 ではない"
REASON_EVENT_JSON = "GITHUB_EVENT_PATH の JSON が不正である"
REASON_EVENT_OBJECT = "PR イベント JSON のルートがオブジェクトではない"
REASON_PULL_REQUEST_MISSING = "PR イベントに pull_request がない"
REASON_BASE_MISSING = "PR イベントに base の ref または SHA がない"
REASON_HEAD_MISSING = "PR イベントに head SHA がない"
REASON_GIT_TIMEOUT = "git diff がタイムアウトした"
REASON_GIT_START = "git diff を起動できない: {error}"
REASON_GIT_FAILURE = "git diff に失敗した: {returncode}"
REASON_DIFF_STATUS = "git diff が未対応の変更種別を返した: {status}"
REASON_DIFF_FORMAT = "git diff の --name-status 出力が不正である"
REASON_DIFF_PATH = "git diff が不正なリポジトリ相対パスを返した: {path}"
REASON_TREE_ITEM_MISSING = "統合後ツリーに新規追加項目が収録されていない"
REASON_TREE_ITEM_TYPE = "受入証跡ツリー項目が blob オブジェクトではない"
REASON_NON_ADDED_CHANGE = "既存の受入証跡が追加以外の状態で変更されている: {status}"
REASON_EVIDENCE_RESERVATION_COUNT = (
    "統合後ツリーで結果証跡に対応する予約がちょうど 1 件ではない: {attempt_id}"
)
REASON_SECOND_EVIDENCE = "同一 attempt_id の結果証跡が 2 件目になっている: {attempt_id}"
REASON_RESERVATION_ATTEMPT_ID = (
    "統合後ツリーで同一 attempt_id の予約が一意ではない: {attempt_id}"
)
REASON_RESERVATION_GATE_SEQUENCE = (
    "統合後ツリーで同一 gate_key と attempt_seq の予約が一意ではない: {gate_key} / {attempt_seq}"
)
REASON_BASE_RESERVATION = "結果証跡に対応する予約が base ツリーにちょうど 1 件ない: {attempt_id}"
REASON_BASE_UNCLOSED_RESERVATION = (
    "base ツリーに未閉塞の予約があるため新規予約を追加できない: {attempt_id}"
)
REASON_BASE_EVIDENCE_EXISTS = "同一 attempt_id の結果証跡が base ツリーに既にある: {attempt_id}"
REASON_FIRST_SEQUENCE = "base ツリーに予約がないゲートキーの attempt_seq は 1 でなければならない"
REASON_SEQUENCE_NOT_INCREASING = (
    "新規予約の attempt_seq が base ツリーの全予約より厳密に大きくない"
)
SKIP_NON_PR_MESSAGE = "NFR-021 append-only 検査をスキップする: pull_request イベントではない"
SKIP_NON_DEVELOP_PR_MESSAGE = (
    "NFR-021 append-only 検査をスキップする: base ブランチが develop ではない"
)


@dataclass(frozen=True)
class ChangedPath:
    """Git が報告した変更種別とリポジトリ相対パス群を表す。

    Attributes:
        status: ``A``・``M``・``D``・``R`` などの変更種別。
        paths: 変更対象のリポジトリ相対 POSIX パス。改名・コピーは旧新の順に持つ。
    """

    status: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class PullRequestEvent:
    """GitHub pull_request イベントから得た比較対象を表す。

    Attributes:
        base_ref: PR の base ブランチ名。
        base_sha: PR の base commit OID。
        head_sha: PR の head commit OID。
    """

    base_ref: str
    base_sha: str
    head_sha: str


class AppendOnlyArgumentParser(argparse.ArgumentParser):
    """引数エラーを GuardError として fail-closed にする argparse パーサ。"""

    def error(self, message: str) -> NoReturn:
        """argparse の引数エラーを GuardError へ変換する。

        Args:
            message: argparse が生成した引数エラーの説明。

        Returns:
            このメソッドは戻らない。

        Raises:
            GuardError: 引数の形式が不正な場合。
        """
        raise GuardError(REASON_ARGUMENT_ERROR.format(message=message))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """append-only 検査のコマンドライン引数を解釈する。

    Args:
        argv: テスト時に指定する引数列。省略時は通常のコマンドライン引数を使う。

    Returns:
        解釈済みのコマンドライン引数。

    Raises:
        GuardError: ローカル実行用の比較 revision 指定が片方だけの場合。
    """
    parser = AppendOnlyArgumentParser(description="NFR-021 証跡の append-only 統合を検査する")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="リポジトリルート(既定: カレントディレクトリ)",
    )
    parser.add_argument("--base", help="ローカル実行・テスト専用の比較元 revision")
    parser.add_argument("--head", help="ローカル実行・テスト専用の比較先 revision")
    args = parser.parse_args(argv)
    if (args.base is None) != (args.head is None):
        raise GuardError(REASON_LOCAL_REVISIONS)
    return args


def normalize_git_path(path: str) -> str:
    """Git が返したパスをリポジトリ相対の POSIX 形式として検証する。

    Args:
        path: ``git diff --name-status`` が返したパス。

    Returns:
        検証済みのリポジトリ相対 POSIX パス。

    Raises:
        GuardError: 空、絶対、または ``.``・``..`` を含むパスの場合。
    """
    parsed_path = PurePosixPath(path)
    if (
        not path
        or parsed_path.is_absolute()
        or not parsed_path.parts
        or any(part in {".", ".."} for part in parsed_path.parts)
    ):
        raise GuardError(REASON_DIFF_PATH.format(path=path))
    return parsed_path.as_posix()


def parse_name_status(output: str) -> tuple[ChangedPath, ...]:
    """``git diff --name-status`` 出力を変更種別つきレコードへ解析する。

    Args:
        output: Git コマンドの標準出力。

    Returns:
        正規化済みの変更レコード列。

    Raises:
        GuardError: 変更種別、列数、またはパスが不正な場合。
    """
    changes: list[ChangedPath] = []
    for line in output.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        status = fields[0]
        kind = status[:1]
        if kind not in GIT_STATUS_KINDS:
            raise GuardError(REASON_DIFF_STATUS.format(status=status))
        expected_path_count = 2 if kind in GIT_STATUS_TWO_PATH_KINDS else 1
        if len(fields) != expected_path_count + 1:
            raise GuardError(REASON_DIFF_FORMAT)
        paths = tuple(normalize_git_path(path) for path in fields[1:])
        changes.append(ChangedPath(status=kind, paths=paths))
    return tuple(changes)


def changed_paths(root: Path, base: str, head: str) -> tuple[ChangedPath, ...]:
    """PR の merge-base 起点差分を変更種別つきで取得する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        base: 比較元の Git revision。
        head: 比較先の Git revision。

    Returns:
        Git が報告した変更レコード。

    Raises:
        GuardError: Git の起動、タイムアウト、実行、または出力解析に失敗した場合。
    """
    # ここは「この PR が加えた変更」を問うため merge-base 起点の三点差分を使う。
    # 失効判定は「T 以後の全変更」を問うため、作成後削除を落とさない git log の
    # 各コミット和集合を使い、三点差分を使わない。
    command = (
        GIT_EXECUTABLE,
        GIT_DIFF_COMMAND,
        GIT_NAME_STATUS_OPTION,
        GIT_NO_RENAMES_OPTION,
        f"{base}...{head}",
    )
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
        raise GuardError(REASON_GIT_TIMEOUT) from error
    except OSError as error:
        raise GuardError(REASON_GIT_START.format(error=error)) from error
    if result.returncode != 0:
        raise GuardError(REASON_GIT_FAILURE.format(returncode=result.returncode))
    return parse_name_status(result.stdout)


def is_acceptance_path(path: str) -> bool:
    """パスが受入証跡ディレクトリ配下かを判定する。

    Args:
        path: リポジトリ相対 POSIX パス。

    Returns:
        docs/ops/nfr021-acceptance 配下なら ``True``、それ以外なら ``False``。
    """
    parts = PurePosixPath(path).parts
    prefix = ACCEPTANCE_DIRECTORY_RELATIVE_PATH.parts
    return parts[: len(prefix)] == prefix


def read_pull_request_event() -> PullRequestEvent:
    """環境変数が指す pull_request イベントから base と head を取得する。

    Returns:
        検証済みの PR 比較対象。

    Raises:
        GuardError: イベントファイル、JSON、または必須キーが不正な場合。
    """
    event_path_text = os.environ.get(GITHUB_EVENT_PATH)
    if not event_path_text:
        raise GuardError(REASON_EVENT_PATH_MISSING)
    try:
        event_text = Path(event_path_text).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise GuardError(REASON_EVENT_ENCODING) from error
    except OSError as error:
        raise GuardError(REASON_EVENT_READ.format(error=error)) from error
    try:
        data = json.loads(event_text)
    except json.JSONDecodeError as error:
        raise GuardError(REASON_EVENT_JSON) from error
    if not isinstance(data, dict):
        raise GuardError(REASON_EVENT_OBJECT)
    pull_request = data.get("pull_request")
    if not isinstance(pull_request, dict):
        raise GuardError(REASON_PULL_REQUEST_MISSING)
    base = pull_request.get("base")
    head = pull_request.get("head")
    if not isinstance(base, dict):
        raise GuardError(REASON_BASE_MISSING)
    if not isinstance(head, dict):
        raise GuardError(REASON_HEAD_MISSING)
    base_ref = base.get("ref")
    base_sha = base.get("sha")
    head_sha = head.get("sha")
    if (
        not isinstance(base_ref, str)
        or not base_ref
        or not isinstance(base_sha, str)
        or not base_sha
    ):
        raise GuardError(REASON_BASE_MISSING)
    if not isinstance(head_sha, str) or not head_sha:
        raise GuardError(REASON_HEAD_MISSING)
    return PullRequestEvent(base_ref=base_ref, base_sha=base_sha, head_sha=head_sha)


def resolve_revisions(args: argparse.Namespace) -> tuple[str, str] | None:
    """イベント規則に従って append-only 検査の比較対象を決定する。

    Args:
        args: 解釈済みコマンドライン引数。

    Returns:
        検査する ``(base, head)``。スキップ時は ``None``。

    Raises:
        GuardError: PR イベントが壊れている、またはローカル比較対象がない場合。
    """
    event_name = os.environ.get(GITHUB_EVENT_NAME)
    if event_name:
        if event_name != PULL_REQUEST_EVENT_NAME:
            print(SKIP_NON_PR_MESSAGE)
            return None
        event = read_pull_request_event()
        if event.base_ref != DEVELOP_BRANCH:
            print(SKIP_NON_DEVELOP_PR_MESSAGE)
            return None
        # CI の PR 経路では CLI 値へフォールバックせず、イベントの SHA だけを使う。
        return event.base_sha, event.head_sha
    if os.environ.get(GITHUB_EVENT_PATH):
        raise GuardError(REASON_EVENT_NAME_MISSING)
    if args.base is None or args.head is None:
        raise GuardError(REASON_LOCAL_REVISIONS)
    return args.base, args.head


def tree_item_object_id(root: Path, revision: str, path: str) -> str:
    """指定ツリーの受入証跡項目が blob であることを確認して OID を得る。

    Args:
        root: Git リポジトリのルートディレクトリ。
        revision: 読み取るコミット revision。
        path: リポジトリ相対の受入証跡項目パス。

    Returns:
        取得した blob OID。

    Raises:
        GuardError: 項目がツリーにない、または blob ではない場合。
    """
    object_id = git_tree_object_oid(root, revision, path)
    if object_id is None:
        raise GuardError(REASON_TREE_ITEM_MISSING)
    if git_object_type(root, object_id, path) != GIT_OBJECT_BLOB:
        raise GuardError(REASON_TREE_ITEM_TYPE)
    return object_id


def parse_new_records(
    root: Path,
    head: str,
    paths: Sequence[str],
) -> tuple[tuple[AcceptanceRecord, ...], tuple[str, ...]]:
    """新規追加された受入証跡だけを命名・frontmatter として解析する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        head: 統合後ツリーを表す Git revision。
        paths: diff で ``A`` と報告された受入証跡パス。

    Returns:
        解析できた予約・結果証跡と、新規項目の命名・解析違反。

    Raises:
        GuardError: Git ツリーや blob を解決できない場合。
    """
    records: list[AcceptanceRecord] = []
    violations: list[str] = []
    for path in sorted(set(paths)):
        relative_path = acceptance_relative_path(PurePosixPath(path))
        parsed_path = parse_acceptance_path(relative_path)
        if parsed_path.kind == KIND_CANONICAL:
            continue
        if parsed_path.kind == KIND_INVALID:
            violations.append(
                format_violation(path, parsed_path.reason or "閉じた命名文法に一致しない")
            )
            continue
        object_id = tree_item_object_id(root, head, path)
        contents = git_blob_contents(root, object_id)
        try:
            record = parse_acceptance_record(relative_path, contents, path)
        except GuardError as error:
            violations.append(format_violation(path, str(error)))
            continue
        records.append(record)
    return tuple(records), tuple(dict.fromkeys(violations))


def tree_records(root: Path, revision: str) -> tuple[AcceptanceRecord, ...]:
    """ツリー内の解析可能な予約・結果証跡だけを関係判定用に列挙する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        revision: 列挙する Git revision。

    Returns:
        命名・frontmatter を解析できた予約・結果証跡の列。

    Raises:
        GuardError: Git ツリーや blob の取得に失敗した場合。
    """
    records: list[AcceptanceRecord] = []
    for tree_path in candidate_acceptance_tree_paths(root, revision):
        relative_path = acceptance_relative_path(tree_path)
        parsed_path = parse_acceptance_path(relative_path)
        if parsed_path.kind not in {KIND_RESERVATION, KIND_EVIDENCE}:
            continue
        path = tree_path.as_posix()
        object_id = git_tree_object_oid(root, revision, path)
        if object_id is None:
            raise GuardError(REASON_TREE_ITEM_MISSING)
        if git_object_type(root, object_id, path) != GIT_OBJECT_BLOB:
            continue
        contents = git_blob_contents(root, object_id)
        try:
            record = parse_acceptance_record(relative_path, contents, path)
        except GuardError:
            # 過去の解析不能レコードを再検査しない。新規追加分は parse_new_records が拒否する。
            continue
        records.append(record)
    return tuple(records)


def record_identity(record: AcceptanceRecord) -> tuple[str, str, int] | None:
    """関係・採番判定に必要な record の識別成分を安全に取り出す。

    Args:
        record: 予約または結果証跡レコード。

    Returns:
        ``(attempt_id, gate_key, attempt_seq)``。値が取得できなければ ``None``。
    """
    attempt_id = record_attempt_id(record)
    gate_key = record_gate_key(record)
    attempt_seq = record_attempt_sequence(record)
    if attempt_id is None or gate_key is None or attempt_seq is None:
        return None
    return attempt_id, gate_key, attempt_seq


def validate_new_record_contracts(
    new_records: Sequence[AcceptanceRecord],
    head_records: Sequence[AcceptanceRecord],
) -> tuple[str, ...]:
    """新規レコードと統合後ツリー内の対応相手との一致契約を検査する。

    Args:
        new_records: PR で追加された解析済みレコード。
        head_records: 統合後ツリーから解析できたレコード。

    Returns:
        新規レコードを含む予約・結果証跡間の一致契約違反。
    """
    violations: list[str] = []
    for new_record in new_records:
        new_attempt_id = record_attempt_id(new_record)
        if new_attempt_id is None:
            continue
        for head_record in head_records:
            if head_record.display_path == new_record.display_path:
                continue
            if record_attempt_id(head_record) != new_attempt_id:
                continue
            if head_record.path.kind == new_record.path.kind:
                continue
            violations.extend(validate_record_relationships((new_record, head_record)))
    return tuple(dict.fromkeys(violations))


def validate_integrated_relationships(
    new_records: Sequence[AcceptanceRecord],
    head_records: Sequence[AcceptanceRecord],
) -> tuple[str, ...]:
    """新規レコードに限って統合後ツリーの孤児・多重対応を検査する。

    Args:
        new_records: PR で追加された解析済みレコード。
        head_records: 統合後ツリーから解析できたレコード。

    Returns:
        新規レコードに関係する孤児・多重対応の違反。
    """
    reservations = [record for record in head_records if record.path.kind == KIND_RESERVATION]
    evidences = [record for record in head_records if record.path.kind == KIND_EVIDENCE]
    violations: list[str] = []
    for record in new_records:
        identity = record_identity(record)
        if identity is None:
            continue
        attempt_id, gate_key, attempt_seq = identity
        if record.path.kind == KIND_EVIDENCE:
            matching_reservations = [
                reservation
                for reservation in reservations
                if record_attempt_id(reservation) == attempt_id
            ]
            matching_evidences = [
                evidence for evidence in evidences if record_attempt_id(evidence) == attempt_id
            ]
            if len(matching_reservations) != 1:
                violations.append(
                    format_violation(
                        record.display_path,
                        REASON_EVIDENCE_RESERVATION_COUNT.format(attempt_id=attempt_id),
                    )
                )
            if len(matching_evidences) != 1:
                violations.append(
                    format_violation(
                        record.display_path,
                        REASON_SECOND_EVIDENCE.format(attempt_id=attempt_id),
                    )
                )
        elif record.path.kind == KIND_RESERVATION:
            matching_attempt_ids = [
                reservation
                for reservation in reservations
                if record_attempt_id(reservation) == attempt_id
            ]
            matching_gate_sequences = [
                reservation
                for reservation in reservations
                if record_gate_key(reservation) == gate_key
                and record_attempt_sequence(reservation) == attempt_seq
            ]
            if len(matching_attempt_ids) != 1:
                violations.append(
                    format_violation(
                        record.display_path,
                        REASON_RESERVATION_ATTEMPT_ID.format(attempt_id=attempt_id),
                    )
                )
            if len(matching_gate_sequences) != 1:
                violations.append(
                    format_violation(
                        record.display_path,
                        REASON_RESERVATION_GATE_SEQUENCE.format(
                            gate_key=gate_key,
                            attempt_seq=attempt_seq,
                        ),
                    )
                )
    return tuple(dict.fromkeys(violations))


def validate_reservation_protocol(
    new_records: Sequence[AcceptanceRecord],
    base_records: Sequence[AcceptanceRecord],
) -> tuple[str, ...]:
    """base ツリー基準で予約先行・閉塞・逆順・単調採番を検査する。

    Args:
        new_records: PR で追加された解析済みレコード。
        base_records: PR base ツリーから解析できたレコード。

    Returns:
        (e-1)〜(e-4) の採番・排他プロトコル違反。
    """
    base_reservations = [
        record for record in base_records if record.path.kind == KIND_RESERVATION
    ]
    base_evidences = [record for record in base_records if record.path.kind == KIND_EVIDENCE]
    violations: list[str] = []
    for record in new_records:
        identity = record_identity(record)
        if identity is None:
            continue
        attempt_id, gate_key, attempt_seq = identity
        if record.path.kind == KIND_EVIDENCE:
            matching_reservations = [
                reservation
                for reservation in base_reservations
                if record_attempt_id(reservation) == attempt_id
            ]
            if len(matching_reservations) != 1:
                violations.append(
                    format_violation(
                        record.display_path,
                        REASON_BASE_RESERVATION.format(attempt_id=attempt_id),
                    )
                )
            continue
        if record.path.kind != KIND_RESERVATION:
            continue
        gate_reservations = [
            reservation
            for reservation in base_reservations
            if record_gate_key(reservation) == gate_key
        ]
        for reservation in gate_reservations:
            reservation_attempt_id = record_attempt_id(reservation)
            reservation_identity = record_identity(reservation)
            if reservation_attempt_id is None or reservation_identity is None:
                continue
            if not any(
                record_identity(evidence) == reservation_identity
                for evidence in base_evidences
            ):
                violations.append(
                    format_violation(
                        record.display_path,
                        REASON_BASE_UNCLOSED_RESERVATION.format(
                            attempt_id=reservation_attempt_id
                        ),
                    )
                )
        if any(record_attempt_id(evidence) == attempt_id for evidence in base_evidences):
            violations.append(
                format_violation(
                    record.display_path,
                    REASON_BASE_EVIDENCE_EXISTS.format(attempt_id=attempt_id),
                )
            )
        base_sequences = [
            sequence
            for reservation in gate_reservations
            if (sequence := record_attempt_sequence(reservation)) is not None
        ]
        if not base_sequences and attempt_seq != 1:
            violations.append(format_violation(record.display_path, REASON_FIRST_SEQUENCE))
        elif base_sequences and attempt_seq <= max(base_sequences):
            violations.append(
                format_violation(record.display_path, REASON_SEQUENCE_NOT_INCREASING)
            )
    return tuple(dict.fromkeys(violations))


def check_append_only(root: Path, base: str, head: str) -> tuple[str, ...]:
    """base...head の新規 NFR-021 証跡だけに統合時受入検査を適用する。

    Args:
        root: Git リポジトリのルートディレクトリ。
        base: PR base の Git revision。
        head: PR head の Git revision。

    Returns:
        パス付きの全違反メッセージ。違反がなければ空のタプル。

    Raises:
        GuardError: Git 比較、ツリー、またはイベント入力の解決に失敗した場合。
    """
    changes = changed_paths(root, base, head)
    violations: list[str] = []
    new_paths: list[str] = []
    for change in changes:
        for path in change.paths:
            if not is_acceptance_path(path):
                continue
            if change.status != GIT_STATUS_ADDED:
                violations.append(
                    format_violation(
                        path,
                        REASON_NON_ADDED_CHANGE.format(status=change.status),
                    )
                )
            else:
                new_paths.append(path)
    if not new_paths:
        return tuple(dict.fromkeys(violations))

    new_records, parse_violations = parse_new_records(root, head, new_paths)
    violations.extend(parse_violations)
    # (b)(c) は PR で追加された予約・結果証跡だけへ適用する。
    violations.extend(validate_records(new_records))
    # (a) は結果証跡だけへ適用する。予約には 11 欄・合格項目表がない。
    for record in new_records:
        if record.path.kind == KIND_EVIDENCE:
            violations.extend(
                format_violation(record.display_path, reason)
                for reason in validate_evidence_completeness(record)
            )

    head_records = tree_records(root, head)
    base_records = tree_records(root, base)
    violations.extend(validate_new_record_contracts(new_records, head_records))
    violations.extend(validate_integrated_relationships(new_records, head_records))
    violations.extend(validate_reservation_protocol(new_records, base_records))
    return tuple(dict.fromkeys(violations))


def main(argv: Sequence[str] | None = None) -> int:
    """イベントまたは明示された比較対象に append-only 検査を実行する。

    Args:
        argv: テスト時に指定する引数列。省略時は通常のコマンドライン引数を使う。

    Returns:
        スキップまたは違反なしなら 0、違反・判定不能なら 1。
    """
    try:
        args = parse_args(argv)
        revisions = resolve_revisions(args)
        if revisions is None:
            return 0
        violations = check_append_only(args.root.resolve(), *revisions)
    except GuardError as error:
        print(f"{SCRIPT_NAME}: {error}", file=sys.stderr)
        return 1
    for violation in violations:
        print(violation, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
