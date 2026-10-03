"""BOOT-STALL と BOOT-REAPPROVAL の履歴遅移を検査する。"""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
STALL_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/boot/stall.py"

sys.path.insert(0, str(BACKEND_SRC))
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")


@dataclass(frozen=True)
class _Repository:
    """再承認の前後関係を持つ合成 Git 履歴。"""

    root: Path
    activation: str
    preapproval: str
    expiry: str
    valid: str
    mixed: str
    non_po: str


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """合成リポジトリで Git を実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def _write_files(root: Path, files: dict[str, str]) -> None:
    """合成変更のファイルを書き込む。"""
    for relative, contents in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


def _merge_change(
    root: Path,
    branch: str,
    files: dict[str, str],
) -> str:
    """専用ブランチを develop へマージし、統合 OID を返す。"""
    _git(root, "switch", "--quiet", "-c", branch)
    _write_files(root, files)
    _git(root, "add", "--all")
    _git(root, "commit", "--quiet", "-m", f"{branch} の変更")
    _git(root, "switch", "--quiet", "develop")
    _git(
        root,
        "merge",
        "--quiet",
        "--no-ff",
        branch,
        "-m",
        f"Merge pull request for {branch}",
    )
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _approval(approval_id: str, approver: str = "山田正輝") -> str:
    """厳密キー集合の再承認記録 JSON を返す。"""
    value = {
        "schemaVersion": 1,
        "approvalId": approval_id,
        "approver": approver,
    }
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> _Repository:
    """失効前後の承認記録を持つ第一親履歴を作る。"""
    root = tmp_path_factory.mktemp("stall-repository")
    _git(root, "init", "--quiet", "--initial-branch=develop")
    _git(root, "config", "user.email", "stall-test@example.invalid")
    _git(root, "config", "user.name", "Stall Test")
    _write_files(root, {"README.md": "base\n"})
    _git(root, "add", "README.md")
    _git(root, "commit", "--quiet", "-m", "base")

    activation = _merge_change(
        root,
        "activation",
        {"activation.txt": "BOOT-ACTIVATION\n"},
    )
    preapproval = _merge_change(
        root,
        "approval-before-expiry",
        {"approvals/pre.json": _approval("approval-pre")},
    )
    expiry = _merge_change(
        root,
        "fiftieth-without-progress",
        {"progress.txt": "unchanged\n"},
    )
    valid = _merge_change(
        root,
        "valid-reapproval",
        {"approvals/valid.json": _approval("approval-valid")},
    )
    mixed = _merge_change(
        root,
        "mixed-reapproval",
        {
            "approvals/mixed.json": _approval("approval-mixed"),
            "unrelated.txt": "再承認以外の変更\n",
        },
    )
    non_po = _merge_change(
        root,
        "non-po-reapproval",
        {"approvals/non-po.json": _approval("approval-non-po", "PO 以外")},
    )
    return _Repository(
        root=root,
        activation=activation,
        preapproval=preapproval,
        expiry=expiry,
        valid=valid,
        mixed=mixed,
        non_po=non_po,
    )


def _expired_state(repository: _Repository) -> object:
    """50 件目の PR 統合で失効した状態を返す。"""
    state = STALL.activate(STALL.defined_state(10), repository.activation)
    for index in range(STALL.STALL_MERGE_LIMIT - 1):
        state = STALL.observe_pr_integration(state, f"synthetic-{index}", 10)
    state = STALL.observe_pr_integration(state, repository.expiry, 10)
    assert state.grant == STALL.GrantStatus.EXPIRED
    return state


def _assert_violation(call: Callable[[], object], message: str) -> None:
    """CheckerViolation と指定文言を検査する。"""
    with pytest.raises(STALL.CheckerViolation, match=message):
        call()


def test_stall_contract_uses_three_epoch_starts_and_fifty_merges() -> None:
    defined = STALL.defined_state(10)
    assert defined.effective is False
    assert defined.epoch is None
    assert STALL.STALL_MERGE_LIMIT == 50

    activated = STALL.activate(defined, "activation")
    assert activated.epoch.reason == STALL.EpochStartReason.ACTIVATION

    before_boundary = activated
    for index in range(STALL.STALL_MERGE_LIMIT - 1):
        before_boundary = STALL.observe_pr_integration(
            before_boundary,
            f"merge-{index}",
            10,
        )
    assert before_boundary.grant == STALL.GrantStatus.ACTIVE
    expired = STALL.observe_pr_integration(before_boundary, "merge-50", 10)
    assert expired.grant == STALL.GrantStatus.EXPIRED

    decreased = STALL.observe_pr_integration(before_boundary, "merge-50", 9)
    assert decreased.grant == STALL.GrantStatus.ACTIVE
    assert decreased.epoch.reason == STALL.EpochStartReason.DECREASE
    assert decreased.epoch.merge_count == 0

    promoted = STALL.observe_pr_integration(before_boundary, "merge-50", 0)
    assert promoted.program == STALL.ProgramStatus.PROMOTED
    assert promoted.grant == STALL.GrantStatus.ENDED


def test_first_parent_collector_counts_only_develop_pr_integrations(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "--quiet", "--initial-branch=develop")
    _git(root, "config", "user.email", "stall-test@example.invalid")
    _git(root, "config", "user.name", "Stall Test")
    _write_files(root, {"base.txt": "base\n"})
    _git(root, "add", "base.txt")
    _git(root, "commit", "--quiet", "-m", "base")
    base = _git(root, "rev-parse", "HEAD").stdout.strip()

    _git(root, "switch", "--quiet", "-c", "long-lived-feature")
    _write_files(root, {"feature.txt": "feature\n"})
    _git(root, "add", "feature.txt")
    _git(root, "commit", "--quiet", "-m", "feature work")
    _git(root, "switch", "--quiet", "develop")
    integration_one = _merge_change(root, "other-feature", {"other.txt": "other\n"})
    _git(root, "switch", "--quiet", "long-lived-feature")
    _git(root, "merge", "--quiet", "--no-ff", "develop", "-m", "develop 取り込み")
    feature_merge = _git(root, "rev-parse", "HEAD").stdout.strip()
    _git(root, "switch", "--quiet", "develop")
    _git(
        root,
        "merge",
        "--quiet",
        "--no-ff",
        "long-lived-feature",
        "-m",
        "Merge pull request for long-lived-feature",
    )
    integration_two = _git(root, "rev-parse", "HEAD").stdout.strip()

    history = STALL.collect_first_parent_history(root)

    assert history.pr_integrations == (integration_one, integration_two)
    assert feature_merge not in history.commits
    assert STALL.pr_integrations_after(history, base) == (
        integration_one,
        integration_two,
    )


def test_pre_expiry_approval_cannot_start_reapproval_epoch(
    repository: _Repository,
) -> None:
    state = _expired_state(repository)

    _assert_violation(
        lambda: STALL.reapprove_from_git(
            repository.root,
            state,
            "approvals/pre.json",
            repository.preapproval,
        ),
        "失効前",
    )


def test_same_approval_record_cannot_start_two_epochs(
    repository: _Repository,
) -> None:
    state = _expired_state(repository)
    started = STALL.reapprove_from_git(
        repository.root,
        state,
        "approvals/valid.json",
        repository.valid,
    )
    expired_again = replace(
        started,
        grant=STALL.GrantStatus.EXPIRED,
        expired_at_commit=repository.expiry,
    )

    _assert_violation(
        lambda: STALL.reapprove_from_git(
            repository.root,
            expired_again,
            "approvals/valid.json",
            repository.valid,
        ),
        "再利用",
    )


def test_reapproval_pr_with_other_changes_is_rejected(
    repository: _Repository,
) -> None:
    state = _expired_state(repository)

    _assert_violation(
        lambda: STALL.reapprove_from_git(
            repository.root,
            state,
            "approvals/mixed.json",
            repository.mixed,
        ),
        "専用の変更",
    )


def test_reapproval_after_promotion_is_rejected(repository: _Repository) -> None:
    state = STALL.activate(STALL.defined_state(1), repository.activation)
    promoted = STALL.observe_pr_integration(state, repository.expiry, 0)

    _assert_violation(
        lambda: STALL.reapprove_from_git(
            repository.root,
            promoted,
            "approvals/valid.json",
            repository.valid,
        ),
        "昇格後",
    )


def test_reapproval_by_non_po_is_rejected(repository: _Repository) -> None:
    state = _expired_state(repository)

    _assert_violation(
        lambda: STALL.reapprove_from_git(
            repository.root,
            state,
            "approvals/non-po.json",
            repository.non_po,
        ),
        "PO でない",
    )


def test_no_time_based_expiry_exists_in_implementation() -> None:
    source = STALL_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {"datetime", "time"}
    temporal_tokens = {
        "day",
        "datetime",
        "deadline",
        "duration",
        "hour",
        "minute",
        "second",
        "time",
        "timedelta",
        "ttl",
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    identifiers = {
        node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert imported.isdisjoint(forbidden_imports)
    assert not any(
        token in identifier
        for identifier in identifiers
        for token in temporal_tokens
    )


def test_git_history_calls_reuse_seal_runner_and_allowed_subcommands() -> None:
    tree = ast.parse(STALL_SOURCE.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    git_subcommands = {
        node.args[1].value
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "_run_git"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }
    subprocess_calls = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]

    assert git_subcommands == {"log", "show"}
    assert git_subcommands <= {"rev-parse", "log", "show"}
    assert subprocess_calls == []


def test_valid_reapproval_starts_stall_epoch(repository: _Repository) -> None:
    state = _expired_state(repository)

    started = STALL.reapprove_from_git(
        repository.root,
        state,
        "approvals/valid.json",
        repository.valid,
    )

    assert started.grant == STALL.GrantStatus.ACTIVE
    assert started.epoch.reason == STALL.EpochStartReason.REAPPROVAL
    assert started.epoch.start_commit == repository.valid
    assert started.epoch.merge_count == 0
    assert started.epoch.reapproval_id == "approval-valid"
    assert started.used_reapproval_ids == frozenset({"approval-valid"})


def test_stall_module_is_loaded_from_backend_source() -> None:
    assert isinstance(STALL, ModuleType)
    module_file = STALL.__file__
    assert module_file is not None
    assert Path(module_file).resolve() == STALL_SOURCE.resolve()
