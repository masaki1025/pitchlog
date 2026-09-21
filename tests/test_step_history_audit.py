"""実装ステップの履歴時点の成果物とコマンド実行契約を監査する。

実リポジトリでは第一親履歴とステップ定義の突合までを行う。全コマンドの
再実行は行わず、cwd と exit 契約を同じ型で表した短い合成コマンドを実際に
起動して、実行結果を自己申告ではなく subprocess の戻り値から判定する。
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Iterable

import pytest

ROOT = Path(__file__).resolve().parents[1]
STEPS_PATH = ROOT / "docs/features/domain-calc-dsl/steps.json"
BACKEND_SRC = ROOT / "backend/src"
THIS_FILE = Path(__file__).resolve()
STEPS_HISTORY_PATH = "docs/features/domain-calc-dsl/steps.json"

ROOT_CWD = "."
BACKEND_CWD = "backend"
FRONTEND_CWD = "frontend"
COMMAND_CWD_ALLOWLIST = frozenset({ROOT_CWD, BACKEND_CWD, FRONTEND_CWD})
EXPECTED_COMMAND_EXIT = 0
SELF_RECURSIVE_COMMAND = "uv run pytest tests/test_step_history_audit.py"
COMMAND_EXECUTION_EXCLUSIONS = frozenset({SELF_RECURSIVE_COMMAND})

# 走査件数の証跡。`exit 0` は「異常終了しなかった」でしかなく、対象を 1 件も見ずに
# 終わったコマンドと区別できない(ステップ 45 で `depcruise --validate` が対象省略のまま
# usage を表示して `exit 0` になった実例)。そこで各コマンドへ「何件を見たか」が出力に
# 現れることを要求し、件数 0 を不合格にする。
SCOPE_EVIDENCE_PATTERN = re.compile(r"(\d+)\s+(?:passed|modules)")
# 走査件数を出力しないコマンドは、代わりに「観測できる副作用」で非空虚を示す。
SIDE_EFFECT_EVIDENCE: dict[str, str] = {
    "uv sync --locked": "Resolved",
    "uv run python scripts/check_docs_status.py": "",
}

CODE_SPAN_PATTERN = re.compile(r"`([^`]+)`")
IMPLEMENTATION_TOKEN_PATTERN = re.compile(
    r"(?:\(|（)ステップ\s+([1-9]\d*)(?:/([1-9]\d*))?(?:\)|）)"
)


class AuditViolation(AssertionError):
    """履歴またはコマンド実行契約への違反を表す。"""


@dataclass(frozen=True)
class StepCommit:
    """実装ステップと、その完了コミットの対応を表す。"""

    step_id: int
    commit_oid: str
    subject: str


@dataclass(frozen=True)
class CommandAudit:
    """1 コマンドの実行ディレクトリと期待 exit を表す。"""

    step_id: int
    command: str
    cwd: str
    expected_exit: int


@dataclass(frozen=True)
class HistoryOrderException:
    """段階実装の順序を意図的に入れ替えた宣言を表す。"""

    step_id: int
    after_step_id: int
    reason: str


def _load_backend_module(name: str) -> ModuleType:
    """backend の既存モジュールを動的に読み込む。"""
    if str(BACKEND_SRC) not in sys.path:
        sys.path.insert(0, str(BACKEND_SRC))
    return importlib.import_module(name)


SEAL_MODULE = _load_backend_module("pitchlog.domaincheck.seal")


@pytest.fixture(scope="module")
def steps_data() -> dict[str, Any]:
    """ステップ単一定義を読み込む。"""
    value = json.loads(STEPS_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """既存の封印機構を通して Git を実行し、非 0 を監査不能として拒否する。"""
    result = SEAL_MODULE._run_git(root, *arguments)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise AuditViolation(f"Git 履歴を監査できない: {detail}")
    return result


def _code_spans(value: str, label: str) -> tuple[str, ...]:
    """Markdown セルから空でない code span を取り出す。"""
    spans = tuple(CODE_SPAN_PATTERN.findall(value))
    if not spans or any(not span.strip() for span in spans):
        raise AuditViolation(f"{label} に監査対象の code span が無い")
    return spans


def _artifact_paths(step: dict[str, Any]) -> tuple[str, ...]:
    """ステップの artifact セルからリポジトリ相対パスを返す。"""
    paths = _code_spans(str(step["artifact"]), "artifact")
    for raw_path in paths:
        path = PurePosixPath(raw_path.removesuffix("/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise AuditViolation(f"artifact がリポジトリ相対パスでない: {raw_path}")
    return paths


def _command_cwd(command: str) -> str:
    """閉じた規則でコマンドの cwd を決める。"""
    if command.startswith("pnpm "):
        return FRONTEND_CWD
    # `uv sync --locked` は backend のロックを対象にするので backend で実行する。
    # 一方 `tests/` 配下のテストはすべてリポジトリルートにあり、backend で走らせると
    # 収集 0 件のまま pytest が usage エラー(exit 4)になる。実走して初めて判明した。
    if command == "uv sync --locked":
        return BACKEND_CWD
    if command.startswith("uv run "):
        return ROOT_CWD
    raise AuditViolation(f"cwd を決定できない未登録コマンド: {command}")


def _command_audit_asset(data: dict[str, Any]) -> tuple[CommandAudit, ...]:
    """全コマンドへ cwd と期待 exit を付けた監査資産を構築する。"""
    records: list[CommandAudit] = []
    for step in data["steps"]:
        for command in _code_spans(str(step["command"]), "command"):
            records.append(
                CommandAudit(
                    step_id=int(step["id"]),
                    command=command,
                    cwd=_command_cwd(command),
                    expected_exit=EXPECTED_COMMAND_EXIT,
                )
            )
    return tuple(records)


def _history_order_exceptions(
    data: dict[str, Any],
) -> tuple[HistoryOrderException, ...]:
    """単一定義から履歴順序の例外を厳密な形で読む。

    Args:
        data: ``steps.json`` の内容。

    Returns:
        宣言された順序例外。

    Raises:
        AuditViolation: キー、型、値域、理由が不正な場合。
    """
    raw_exceptions = data.get("history_order_exceptions")
    if not isinstance(raw_exceptions, list):
        raise AuditViolation("history_order_exceptions が配列でない")
    total = int(data["expected_total"])
    exceptions: list[HistoryOrderException] = []
    for index, raw in enumerate(raw_exceptions):
        if not isinstance(raw, dict) or set(raw) != {
            "stepId",
            "afterStepId",
            "reason",
        }:
            raise AuditViolation(f"順序例外 {index} のキー集合が不正")
        step_id = raw["stepId"]
        after_step_id = raw["afterStepId"]
        reason = raw["reason"]
        if not isinstance(step_id, int) or not isinstance(after_step_id, int):
            raise AuditViolation(f"順序例外 {index} のステップ ID が整数でない")
        if not 1 <= step_id < after_step_id <= total:
            raise AuditViolation(f"順序例外 {index} のステップ ID が値域外")
        if not isinstance(reason, str) or not reason.strip():
            raise AuditViolation(f"順序例外 {index} に理由がない")
        exceptions.append(
            HistoryOrderException(
                step_id=step_id,
                after_step_id=after_step_id,
                reason=reason,
            )
        )
    counts = Counter(exception.step_id for exception in exceptions)
    duplicates = sorted(step_id for step_id, count in counts.items() if count != 1)
    if duplicates:
        raise AuditViolation(f"順序例外の対象ステップが重複している: {duplicates}")
    return tuple(exceptions)


def _assert_declared_step_order(
    records: Iterable[StepCommit],
    exceptions: Iterable[HistoryOrderException],
) -> None:
    """実履歴が昇順、または宣言から一意に導いた順序か検査する。"""
    observed = [record.step_id for record in records]
    declared = tuple(exceptions)
    expected = sorted(observed)
    for exception in declared:
        if exception.step_id not in expected or exception.after_step_id not in expected:
            raise AuditViolation(
                "宣言した順序例外のステップが実履歴にない: "
                f"step={exception.step_id} after={exception.after_step_id}"
            )
        expected.remove(exception.step_id)
        insertion = expected.index(exception.after_step_id) + 1
        expected.insert(insertion, exception.step_id)
    if observed == expected:
        return
    if not declared:
        raise AuditViolation(f"実装ステップコミットが昇順でない: {observed}")
    raise AuditViolation(
        f"宣言した順序例外と実履歴が一致しない: actual={observed} expected={expected}"
    )


def _history_head_revision() -> str:
    """履歴監査を始める PR head またはローカル HEAD を返す。

    PR の checkout は合成 merge commit になるため、その `HEAD` は使わずイベントが
    指す head SHA を使う。PR 外ではローカルと push の双方で従来の `HEAD` を使う。

    Returns:
        Git log の起点にする revision。

    Raises:
        AuditViolation: PR イベントから head SHA を取得できない場合。
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return "HEAD"
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise AuditViolation("PR 履歴監査に GITHUB_EVENT_PATH が無い")
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuditViolation("PR イベントを読み取れない") from error
    pull_request = event.get("pull_request") if isinstance(event, dict) else None
    head = pull_request.get("head") if isinstance(pull_request, dict) else None
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(head_sha, str) or not head_sha:
        raise AuditViolation("PR イベントに head SHA が無い")
    return head_sha


def _implementation_commits(
    root: Path,
    total: int,
    base_ref: str = "origin/develop",
    head_ref: str | None = None,
    order_exceptions: Iterable[HistoryOrderException] = (),
) -> tuple[StepCommit, ...]:
    """PR head またはローカル HEAD の第一親履歴から実装コミットを抽出する。

    Args:
        root: Git リポジトリのルート。
        total: 計画にあるステップ総数。
        base_ref: 履歴範囲から除く base revision。
        head_ref: 明示する head revision。省略時は実行環境から決める。
        order_exceptions: 単一定義が宣言する順序例外。

    Returns:
        ステップ番号と完了コミットの対応。
    """
    selected_head = head_ref or _history_head_revision()
    history = _git(
        root,
        "log",
        "--first-parent",
        "--reverse",
        "--format=%H%x1f%s",
        f"{base_ref}..{selected_head}",
    )
    records: list[StepCommit] = []
    for line in history.stdout.splitlines():
        commit_oid, separator, subject = line.partition("\x1f")
        if not separator:
            raise AuditViolation("Git log の commit OID と件名を分離できない")
        tokens = IMPLEMENTATION_TOKEN_PATTERN.findall(subject)
        if not tokens:
            continue
        if len(tokens) != 1:
            raise AuditViolation(f"実装ステップトークンが複数ある: {subject}")
        raw_step_id, raw_total = tokens[0]
        if raw_total and int(raw_total) != total:
            raise AuditViolation(f"実装ステップ総数が単一定義と違う: {subject}")
        records.append(
            StepCommit(
                step_id=int(raw_step_id),
                commit_oid=commit_oid,
                subject=subject,
            )
        )
    if not records:
        raise AuditViolation("実装ステップコミットを第一親履歴から取得できない")
    counts = Counter(record.step_id for record in records)
    duplicates = sorted(step_id for step_id, count in counts.items() if count != 1)
    if duplicates:
        raise AuditViolation(f"実装ステップコミットが重複している: {duplicates}")
    observed = [record.step_id for record in records]
    _assert_declared_step_order(records, order_exceptions)
    if max(observed) > total:
        raise AuditViolation("計画の総数を超える実装ステップコミットがある")
    return tuple(records)


def _steps_snapshot(root: Path, commit_oid: str) -> dict[str, Any]:
    """指定コミット時点のステップ単一定義を読む。"""
    snapshot = _git(root, "show", f"{commit_oid}:{STEPS_HISTORY_PATH}")
    try:
        value = json.loads(snapshot.stdout)
    except json.JSONDecodeError as error:
        raise AuditViolation("履歴時点の steps.json が JSON でない") from error
    if not isinstance(value, dict):
        raise AuditViolation("履歴時点の steps.json が object でない")
    return value


def _historical_step(snapshot: dict[str, Any], step_id: int) -> dict[str, Any]:
    """履歴時点の単一定義から対象ステップを一意に返す。"""
    matches = [step for step in snapshot["steps"] if step.get("id") == step_id]
    if len(matches) != 1:
        raise AuditViolation(f"履歴時点のステップ {step_id} が一意でない")
    return matches[0]


def _assert_artifacts_at_commits(
    root: Path,
    current_steps: dict[str, Any],
    commits: Iterable[StepCommit],
) -> None:
    """各ステップ完了コミットの tree に宣言済み artifact があることを検査する。"""
    current_by_id = {int(step["id"]): step for step in current_steps["steps"]}
    for record in commits:
        current = current_by_id.get(record.step_id)
        if current is None:
            raise AuditViolation(f"現行定義にステップ {record.step_id} が無い")
        historical = _historical_step(
            _steps_snapshot(root, record.commit_oid), record.step_id
        )
        for key in ("artifact", "command"):
            if historical[key] != current[key]:
                raise AuditViolation(
                    f"ステップ {record.step_id} の {key} が完了後に再束縛された"
                )
        for raw_path in _artifact_paths(historical):
            path = raw_path.removesuffix("/")
            result = SEAL_MODULE._run_git(root, "show", f"{record.commit_oid}:{path}")
            if result.returncode != 0:
                raise AuditViolation(
                    f"ステップ {record.step_id} の完了時点に artifact が無い: {raw_path}"
                )


def _commands_for_execution(records: Iterable[CommandAudit]) -> tuple[CommandAudit, ...]:
    """自己再帰するコマンドを実行対象から構造的に除外する。"""
    return tuple(
        record
        for record in records
        if record.command not in COMMAND_EXECUTION_EXCLUSIONS
    )


def _assert_no_self_recursive_command(records: Iterable[CommandAudit]) -> None:
    """実行対象に本テスト自身のコマンドが残っていないことを検査する。"""
    recursive = [
        record.command
        for record in records
        if record.command == SELF_RECURSIVE_COMMAND
    ]
    if recursive:
        raise AuditViolation("本ステップ自身の command が実行対象に含まれている")


def _resolve_command_cwd(root: Path, cwd: str) -> Path:
    """allowlist 済み cwd を実ディレクトリへ解決する。"""
    if cwd not in COMMAND_CWD_ALLOWLIST:
        raise AuditViolation(f"command cwd が allowlist 外である: {cwd}")
    resolved_root = root.resolve()
    resolved = (root / cwd).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise AuditViolation("command cwd がリポジトリ外を指している") from error
    if not resolved.is_dir():
        raise AuditViolation(f"command cwd が実在しない: {cwd}")
    return resolved


def _execute_commands(root: Path, records: Iterable[CommandAudit]) -> None:
    """コマンドを実プロセスで起動し、観測 exit を契約と照合する。"""
    selected = tuple(records)
    _assert_no_self_recursive_command(selected)
    for record in selected:
        result = subprocess.run(
            shlex.split(record.command),
            cwd=_resolve_command_cwd(root, record.cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != record.expected_exit:
            raise AuditViolation(
                f"command の exit が不一致: step={record.step_id} "
                f"expected={record.expected_exit} actual={result.returncode}"
            )
        _assert_scope_evidence(record, result.stdout + result.stderr)


def _assert_scope_evidence(record: CommandAudit, output: str) -> None:
    """コマンドが実際に 1 件以上を走査したことを出力から要求する。

    `exit 0` だけでは、対象を 1 件も見ずに終わったコマンドと区別できない。

    Args:
        record: 実行したコマンドの監査レコード。
        output: 標準出力と標準エラーを連結したもの。

    Raises:
        AuditViolation: 走査件数が出力に現れないか 0 件の場合。
    """
    if record.command in SIDE_EFFECT_EVIDENCE:
        marker = SIDE_EFFECT_EVIDENCE[record.command]
        if marker and marker not in output:
            raise AuditViolation(
                f"command の副作用証跡が出力に無い: step={record.step_id} "
                f"command={record.command}"
            )
        return
    counts = [int(value) for value in SCOPE_EVIDENCE_PATTERN.findall(output)]
    if not counts:
        raise AuditViolation(
            f"command の走査件数が出力に現れない: step={record.step_id} "
            f"command={record.command}"
        )
    if max(counts) <= 0:
        raise AuditViolation(
            f"command が 1 件も走査していない: step={record.step_id} "
            f"command={record.command}"
        )


def _git_commit(root: Path, subject: str) -> str:
    """一時リポジトリの全変更をコミットし完全 OID を返す。"""
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", subject)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _history_repository(tmp_path: Path) -> Path:
    """成果物の履歴時点検査に使う最小 Git リポジトリを作る。"""
    repository = tmp_path / "history-repository"
    repository.mkdir()
    _git(repository, "init", "--quiet", "--initial-branch", "develop")
    _git(repository, "config", "user.email", "history-test@example.invalid")
    _git(repository, "config", "user.name", "History Test")
    return repository


def _synthetic_steps(artifact: str, command: str) -> dict[str, Any]:
    """履歴負例に必要な最小ステップ定義を返す。"""
    return {
        "expected_total": 1,
        "steps": [
            {
                "id": 1,
                "artifact": f"`{artifact}`",
                "command": f"`{command}`",
            }
        ],
    }


def _write_synthetic_steps(root: Path, data: dict[str, Any]) -> None:
    """合成 steps.json を履歴監査と同じ位置へ書く。"""
    path = root / STEPS_HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _python_marker_command(marker: str) -> str:
    """実行された cwd に印を残す短い Python コマンドを返す。"""
    # 走査件数の証跡も併せて出す。実コマンドへ課す要求を合成コマンドだけ免除すると、
    # 証跡検査そのものが合成側で一度も働かなくなる。
    program = (
        "from pathlib import Path; "
        f"Path({marker!r}).write_text('executed', encoding='utf-8'); "
        "print('1 passed')"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}"


def test_real_repository_commands_actually_run_and_report_nonempty_scope(
    steps_data: dict[str, Any],
) -> None:
    """実リポジトリの全 command を実プロセスで起動し、非空虚であることを要求する。

    合成コマンドだけを起動していた旧版は、`exit 0` で何も走査しない実コマンドを
    再導入しても検知できなかった(敵対レビュー 2026-09-21 の指摘)。実測では
    本ステップ自身を除く全 command が 2 分程度で完走するため、実走を避ける理由が無い。
    """
    records = _command_audit_asset(steps_data)
    executable = tuple(
        record
        for record in records
        if record.command not in COMMAND_EXECUTION_EXCLUSIONS
    )
    assert executable, "実行対象のコマンドが 1 件も無い"
    assert len(executable) < len(records), "自己再帰するコマンドが除外されていない"
    _execute_commands(ROOT, executable)


def test_command_reporting_no_scope_count_is_rejected() -> None:
    """走査件数を出力しないコマンドが不合格になることを示す。"""
    silent = CommandAudit(
        step_id=1,
        command=f"{shlex.quote(sys.executable)} -c {shlex.quote('pass')}",
        cwd=ROOT_CWD,
        expected_exit=0,
    )
    with pytest.raises(AuditViolation):
        _execute_commands(ROOT, (silent,))


def test_command_reporting_zero_scope_count_is_rejected() -> None:
    """走査件数 0 を報告するコマンドが不合格になることを示す。"""
    program = "print('0 passed')"
    empty = CommandAudit(
        step_id=1,
        command=f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}",
        cwd=ROOT_CWD,
        expected_exit=0,
    )
    with pytest.raises(AuditViolation):
        _execute_commands(ROOT, (empty,))


def test_real_repository_artifacts_exist_at_each_completed_step_commit(
    steps_data: dict[str, Any],
) -> None:
    total = int(steps_data["expected_total"])
    exceptions = _history_order_exceptions(steps_data)
    commits = _implementation_commits(ROOT, total, order_exceptions=exceptions)

    assert len(commits) == len({record.step_id for record in commits})
    _assert_artifacts_at_commits(ROOT, steps_data, commits)


def test_undeclared_step_order_violation_is_rejected(tmp_path: Path) -> None:
    """宣言の無い逆順コミットは従来どおり拒否する。"""
    repository = _history_repository(tmp_path)
    (repository / "base.txt").write_text("base\n", encoding="utf-8")
    base_commit = _git_commit(repository, "base")
    for step_id in (2, 1):
        (repository / f"step-{step_id}.txt").write_text("step\n", encoding="utf-8")
        _git_commit(repository, f"feat: step (ステップ {step_id}/2)")

    with pytest.raises(AuditViolation, match="昇順でない"):
        _implementation_commits(repository, 2, base_ref=base_commit)


def test_declared_order_that_disagrees_with_history_is_rejected(
    tmp_path: Path,
) -> None:
    """宣言があっても実履歴が宣言どおりでなければ拒否する。"""
    repository = _history_repository(tmp_path)
    (repository / "base.txt").write_text("base\n", encoding="utf-8")
    base_commit = _git_commit(repository, "base")
    for step_id in (1, 2):
        (repository / f"step-{step_id}.txt").write_text("step\n", encoding="utf-8")
        _git_commit(repository, f"feat: step (ステップ {step_id}/2)")
    declaration = HistoryOrderException(
        step_id=1,
        after_step_id=2,
        reason="後段の実行証跡が必要なため。",
    )

    with pytest.raises(AuditViolation, match="宣言した順序例外と実履歴が一致しない"):
        _implementation_commits(
            repository,
            2,
            base_ref=base_commit,
            order_exceptions=(declaration,),
        )


def test_pull_request_merge_checkout_audits_event_head_first_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR の合成 merge commit でなくイベントの head 履歴を実際に監査する。"""
    repository = _history_repository(tmp_path)
    (repository / "README.md").write_text("base\n", encoding="utf-8")
    base_commit = _git_commit(repository, "base")
    _git(repository, "switch", "--quiet", "-c", "feature")
    (repository / "step-1.txt").write_text("one\n", encoding="utf-8")
    _git_commit(repository, "feat: one (ステップ 1/2)")
    (repository / "step-2.txt").write_text("two\n", encoding="utf-8")
    feature_head = _git_commit(repository, "feat: two (ステップ 2/2)")
    _git(repository, "switch", "--quiet", "develop")
    (repository / "develop.txt").write_text("unrelated\n", encoding="utf-8")
    develop_tip = _git_commit(repository, "chore: unrelated develop change")
    _git(repository, "merge", "--quiet", "--no-ff", "feature", "-m", "PR merge")
    merge_commit = _git(repository, "rev-parse", "HEAD").stdout.strip()
    first_parent = _git(repository, "rev-parse", "HEAD^1").stdout.strip()
    event_path = tmp_path / "pull-request.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": develop_tip},
                    "head": {"sha": feature_head},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    records = _implementation_commits(repository, 2, base_ref=base_commit)

    assert merge_commit != feature_head
    assert first_parent == develop_tip
    assert [record.step_id for record in records] == [1, 2]
    assert records[-1].commit_oid == feature_head


def test_local_history_audit_uses_checked_out_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR イベント外ではローカルの HEAD を同じ履歴起点として使う。"""
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    assert _history_head_revision() == "HEAD"


def test_command_audit_asset_has_closed_cwds_and_expected_exit_zero(
    steps_data: dict[str, Any],
) -> None:
    records = _command_audit_asset(steps_data)
    total = int(steps_data["expected_total"])

    assert {record.step_id for record in records} == set(range(1, total + 1))
    assert {record.cwd for record in records} == COMMAND_CWD_ALLOWLIST
    assert {record.expected_exit for record in records} == {EXPECTED_COMMAND_EXIT}


def test_declared_commands_and_artifacts_are_unique_with_mother_set_measurement(
    steps_data: dict[str, Any],
) -> None:
    total = int(steps_data["expected_total"])
    commands = [str(step["command"]) for step in steps_data["steps"]]
    artifact_cells = [str(step["artifact"]) for step in steps_data["steps"]]
    artifact_paths = [
        path for step in steps_data["steps"] for path in _artifact_paths(step)
    ]

    assert len(commands) == total
    assert len(set(commands)) == total
    assert len(artifact_cells) == total
    assert len(set(artifact_cells)) == total
    assert len(artifact_paths) == len(set(artifact_paths))


def test_self_recursive_command_is_excluded_from_execution_asset(
    steps_data: dict[str, Any],
) -> None:
    records = _command_audit_asset(steps_data)
    selected = _commands_for_execution(records)

    assert any(record.command == SELF_RECURSIVE_COMMAND for record in records)
    assert len(selected) == len(records) - len(COMMAND_EXECUTION_EXCLUSIONS)
    _assert_no_self_recursive_command(selected)


def test_self_recursion_exclusion_exists_in_executable_ast() -> None:
    source = THIS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_commands_for_execution"
    )
    exclusions = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Compare)
        and any(isinstance(operator, ast.NotIn) for operator in node.ops)
        and any(
            isinstance(comparator, ast.Name)
            and comparator.id == "COMMAND_EXECUTION_EXCLUSIONS"
            for comparator in node.comparators
        )
    ]

    assert len(exclusions) == 1


def test_artifact_added_after_step_commit_does_not_satisfy_history(
    tmp_path: Path,
) -> None:
    repository = _history_repository(tmp_path)
    artifact = "generated/result.txt"
    command = "uv run synthetic-check"
    data = _synthetic_steps(artifact, command)
    _write_synthetic_steps(repository, data)
    step_commit = _git_commit(repository, "step without artifact")
    artifact_path = repository / artifact
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("late\n", encoding="utf-8")
    _git_commit(repository, "artifact added later")
    record = StepCommit(step_id=1, commit_oid=step_commit, subject="synthetic")

    assert artifact_path.exists(), "現在木だけを見る検査なら誤って通る fixture でなければならない"
    with pytest.raises(AuditViolation, match="完了時点に artifact が無い"):
        _assert_artifacts_at_commits(repository, data, (record,))


def test_artifact_present_in_step_commit_passes_history_audit(tmp_path: Path) -> None:
    repository = _history_repository(tmp_path)
    artifact = "generated/result.txt"
    command = "uv run synthetic-check"
    data = _synthetic_steps(artifact, command)
    _write_synthetic_steps(repository, data)
    artifact_path = repository / artifact
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("present\n", encoding="utf-8")
    step_commit = _git_commit(repository, "step with artifact")
    record = StepCommit(step_id=1, commit_oid=step_commit, subject="synthetic")

    _assert_artifacts_at_commits(repository, data, (record,))


def test_nonzero_command_exit_is_rejected(tmp_path: Path) -> None:
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote('raise SystemExit(9)')}"
    record = CommandAudit(
        step_id=1,
        command=command,
        cwd=ROOT_CWD,
        expected_exit=EXPECTED_COMMAND_EXIT,
    )

    with pytest.raises(AuditViolation, match="exit が不一致"):
        _execute_commands(tmp_path, (record,))


def test_allowing_self_recursive_command_is_rejected(
    steps_data: dict[str, Any],
) -> None:
    records = _command_audit_asset(steps_data)

    with pytest.raises(AuditViolation, match="本ステップ自身"):
        _assert_no_self_recursive_command(records)


def test_all_synthetic_commands_actually_exit_zero_in_declared_cwds(
    tmp_path: Path,
) -> None:
    for cwd in COMMAND_CWD_ALLOWLIST:
        (tmp_path / cwd).mkdir(parents=True, exist_ok=True)
    records = tuple(
        CommandAudit(
            step_id=index,
            command=_python_marker_command(f"executed-{cwd.replace('.', 'root')}.txt"),
            cwd=cwd,
            expected_exit=EXPECTED_COMMAND_EXIT,
        )
        for index, cwd in enumerate(sorted(COMMAND_CWD_ALLOWLIST), start=1)
    )

    _execute_commands(tmp_path, records)

    for record in records:
        marker = f"executed-{record.cwd.replace('.', 'root')}.txt"
        assert (tmp_path / record.cwd / marker).read_text(encoding="utf-8") == "executed"
