"""cases 展開器の実行時ファイル依存を検証する。"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPANDER_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_expander_dependencies.py"
DERIVER_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_deriver_dependencies.py"
DESCRIPTOR_CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_input_axes_descriptor.py"
FREEZE_CHECKER_PATH = REPOSITORY_ROOT / "scripts/state_transition_freeze.py"
POLICY_PATH = (
    REPOSITORY_ROOT
    / "contracts/state-transition/expander_dependency_policy_v1.json"
)
DESIGN_PATH = REPOSITORY_ROOT / "docs/features/appendix-e-golden-vectors/design.md"
DISALLOWED_PATH = REPOSITORY_ROOT / "pyproject.toml"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象を sys.path の変更なしで読み込む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_module("state_transition_freeze", FREEZE_CHECKER_PATH)
_load_module("check_input_axes_descriptor", DESCRIPTOR_CHECKER_PATH)
_load_module("check_deriver_dependencies", DERIVER_CHECKER_PATH)
checker = _load_module("check_expander_dependencies", EXPANDER_CHECKER_PATH)


def _policy() -> Any:
    """リポジトリの展開器依存宣言を返す。"""
    return checker.validate_repository_policy(REPOSITORY_ROOT)


def _first_rule(policy: Any) -> Any:
    """宣言順で最初の展開器規則を返す。"""
    return next(iter(policy.expanders.values()))


def _assert_disallowed_read_fails(operation: Callable[[], object]) -> None:
    """allowlist 外の読み取りが監査違反になることを確認する。"""
    policy = _policy()
    rule = _first_rule(policy)
    with pytest.raises(checker.ExpanderDependencyError, match="allowlist外"):
        checker.trace_expander_file_reads(
            REPOSITORY_ROOT,
            policy,
            rule.expander_id,
            operation,
        )


def test_repository_expander_dependency_policy_is_valid() -> None:
    policy = _policy()
    assert POLICY_PATH.is_file()
    assert policy.expanders
    for rule in policy.expanders.values():
        assert rule.allowed_read_paths
        assert any((REPOSITORY_ROOT / path).is_file() for path in rule.allowed_read_paths)


def test_claim_boundary_limits_the_claim_to_executable_expanders() -> None:
    policy = _policy()
    boundary = policy.claim_boundary
    assert boundary["subject"] == "executable-expanders-only"
    assert boundary["deriverCoverage"] == "not-covered-step-41-policy"
    assert boundary["fixtureIndependenceClaim"] == (
        "manual-fixtures-independent-from-expander-only"
    )
    assert boundary["clauseBranchRegisterIndependence"] == "not-claimed"
    assert "independence-from-clause-branch-register" in boundary["notGuaranteed"]
    design = DESIGN_PATH.read_text(encoding="utf-8")
    assert "実行可能な展開器の追跡対象呼出区間で観測したファイル読み取りだけ" in design
    assert "`clauseBranchRegister` からの独立を主張しない" in design


def test_declared_read_is_traced_and_allowed() -> None:
    policy = _policy()
    rule = _first_rule(policy)
    allowed_relative = next(
        path
        for path in rule.allowed_read_paths
        if (REPOSITORY_ROOT / path).is_file()
    )
    allowed_path = REPOSITORY_ROOT / allowed_relative

    value, trace = checker.trace_expander_file_reads(
        REPOSITORY_ROOT,
        policy,
        rule.expander_id,
        lambda: allowed_path.read_bytes(),
    )

    assert value
    assert trace.observed_read_paths == (allowed_relative,)


def test_builtin_open_outside_allowlist_fails() -> None:
    def read_with_builtin() -> str:
        with open(DISALLOWED_PATH, encoding="utf-8") as stream:
            return stream.read()

    _assert_disallowed_read_fails(read_with_builtin)


def test_pathlib_read_outside_allowlist_fails() -> None:
    _assert_disallowed_read_fails(
        lambda: DISALLOWED_PATH.read_text(encoding="utf-8")
    )


def test_os_open_outside_allowlist_fails() -> None:
    def read_with_os_open() -> int:
        descriptor = os.open(DISALLOWED_PATH, os.O_RDONLY)
        os.close(descriptor)
        return descriptor

    _assert_disallowed_read_fails(read_with_os_open)


def test_swallowed_audit_exception_still_fails() -> None:
    def swallow_violation() -> None:
        try:
            DISALLOWED_PATH.read_bytes()
        except checker.ExpanderDependencyError:
            pass
        except ValueError:
            pass

    _assert_disallowed_read_fails(swallow_violation)


def test_untraced_subprocess_is_fail_closed() -> None:
    policy = _policy()
    rule = _first_rule(policy)

    def spawn_child() -> None:
        subprocess.run([sys.executable, "-c", "pass"], check=True)

    with pytest.raises(checker.ExpanderDependencyError, match="未追跡の子プロセス"):
        checker.trace_expander_file_reads(
            REPOSITORY_ROOT,
            policy,
            rule.expander_id,
            spawn_child,
        )
