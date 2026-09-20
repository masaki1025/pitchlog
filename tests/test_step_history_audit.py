"""実装ステップの履歴時点の成果物とコマンド実行契約を監査する。

実リポジトリでは第一親履歴とステップ定義の突合までを行う。全コマンドの
再実行は行わず、cwd と exit 契約を同じ型で表した短い合成コマンドを実際に
起動して、実行結果を自己申告ではなく subprocess の戻り値から判定する。
"""

from __future__ import annotations

import ast
import importlib
import json
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
    if command == "uv sync --locked" or command == "uv run pytest tests/test_packaging.py":
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


def _implementation_commits(
    root: Path, total: int, base_ref: str = "origin/develop"
) -> tuple[StepCommit, ...]:
    """第一親履歴から通常の実装ステップコミットだけを抽出する。"""
    history = _git(
        root,
        "log",
        "--first-parent",
        "--reverse",
        "--format=%H%x1f%s",
        f"{base_ref}..HEAD",
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
    if observed != list(range(1, max(observed) + 1)):
        raise AuditViolation(f"実装ステップコミットが連続していない: {observed}")
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
    program = (
        "from pathlib import Path; "
        f"Path({marker!r}).write_text('executed', encoding='utf-8')"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(program)}"


def test_real_repository_artifacts_exist_at_each_completed_step_commit(
    steps_data: dict[str, Any],
) -> None:
    total = int(steps_data["expected_total"])
    commits = _implementation_commits(ROOT, total)

    assert len(commits) == len({record.step_id for record in commits})
    _assert_artifacts_at_commits(ROOT, steps_data, commits)


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
