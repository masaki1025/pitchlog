"""認可資産指定と probe 既定値の互換性を検査する。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path, PurePosixPath

import pytest

from pitchlog.authz.asset_spec import PROBE_SPEC, PRODUCT_SPEC
from pitchlog.authz.ddl import (
    AuthzDDLGenerationError,
    DDLStatement,
    generate_authz_ddl,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BODY_CHECKER_PATH = _REPOSITORY_ROOT / PROBE_SPEC.body_checker_path


@pytest.fixture
def copied_repository(tmp_path: Path) -> Path:
    """Scope 変異用に Git object を共有する一時複製を作る。"""
    copied_root = tmp_path / "repository"
    result = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--shared",
            str(_REPOSITORY_ROOT),
            str(copied_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return copied_root


def _generated_sql_bytes(statements: tuple[DDLStatement, ...]) -> bytes:
    """生成された SQL 列を要素境界付きの生バイトへ変換する。"""
    payload = bytearray()
    for statement in statements:
        data = statement.sql.encode("utf-8")
        payload.extend(len(data).to_bytes(8, byteorder="big"))
        payload.extend(data)
    return bytes(payload)


def _run_body_checker(
    root: Path,
    *,
    explicit_probe: bool,
) -> subprocess.CompletedProcess[bytes]:
    """Body 検査 CLI を既定値または明示した probe 指定で実行する。"""
    arguments = [sys.executable, str(_BODY_CHECKER_PATH), "--root", str(root)]
    if explicit_probe:
        arguments.extend(("--asset-spec", "probe"))
    return subprocess.run(
        arguments,
        cwd=root,
        capture_output=True,
        check=False,
    )


def test_probe_spec_is_the_immutable_current_probe_asset() -> None:
    """PROBE_SPEC が製品値と重ならず現行probeを不変に表す。"""
    assert PROBE_SPEC.asset_root == PurePosixPath("contracts/authz")
    assert PROBE_SPEC.ddl_elements_path == PurePosixPath(
        "contracts/authz/ddl-elements.json"
    )
    assert PROBE_SPEC.body_manifest_path == PurePosixPath(
        "contracts/authz/function-bodies/manifest.json"
    )
    assert PROBE_SPEC.body_directory == PurePosixPath("contracts/authz/function-bodies")
    assert PROBE_SPEC.allowed_scope_status == "verified_probe_configuration"
    assert PROBE_SPEC.asset_kind == "probe"
    assert PROBE_SPEC.asset_root != PRODUCT_SPEC.asset_root
    assert PROBE_SPEC.ddl_elements_path != PRODUCT_SPEC.ddl_elements_path
    assert PROBE_SPEC.body_manifest_path != PRODUCT_SPEC.body_manifest_path
    assert PROBE_SPEC.body_directory != PRODUCT_SPEC.body_directory
    assert PROBE_SPEC.allowed_scope_status != PRODUCT_SPEC.allowed_scope_status
    assert PROBE_SPEC.asset_kind != PRODUCT_SPEC.asset_kind

    with pytest.raises(FrozenInstanceError):
        setattr(PROBE_SPEC, "allowed_scope_status", "product_configuration")


def test_element_section_positions_are_explicit_and_asset_specific() -> None:
    """Probeと製品が各要素セクションの生成順を明示する。"""
    assert tuple(
        (section.section_name, section.position)
        for section in PROBE_SPEC.element_sections
    ) == (
        ("roles", 0),
        ("schemas", 1),
        ("tables", 2),
        ("predicates", 3),
        ("policies", 4),
        ("functions", 5),
        ("acl_expectations", 6),
        ("column_acl_expectations", 7),
    )
    assert tuple(
        (section.section_name, section.position)
        for section in PRODUCT_SPEC.element_sections
    ) == (
        ("roles", 0),
        ("databases", 1),
        ("schemas", 2),
        ("functions", 3),
        ("tables", 4),
        ("predicates", 5),
        ("policies", 6),
        ("acl_expectations", 7),
        ("column_acl_expectations", 8),
    )


def test_default_and_explicit_probe_generator_outputs_are_byte_identical() -> None:
    """生成器の既定値と明示した PROBE_SPEC の出力が byte 一致する。"""
    default_output = generate_authz_ddl(_REPOSITORY_ROOT)
    explicit_output = generate_authz_ddl(_REPOSITORY_ROOT, PROBE_SPEC)

    assert default_output == explicit_output
    assert _generated_sql_bytes(default_output) == _generated_sql_bytes(explicit_output)


def test_default_and_explicit_probe_body_checker_outputs_are_byte_identical() -> None:
    """Body 検査 CLI の既定値と明示した probe の出力が byte 一致する。"""
    default_result = _run_body_checker(_REPOSITORY_ROOT, explicit_probe=False)
    explicit_result = _run_body_checker(_REPOSITORY_ROOT, explicit_probe=True)

    assert default_result.returncode == explicit_result.returncode == 0
    assert default_result.stdout == explicit_result.stdout
    assert default_result.stderr == explicit_result.stderr


def test_body_checker_cli_accepts_only_the_closed_asset_spec_set() -> None:
    """Body検査CLIはprobeとproductだけを受理して未知の値を拒否する。"""
    product_result = subprocess.run(
        [
            sys.executable,
            str(_BODY_CHECKER_PATH),
            "--root",
            str(_REPOSITORY_ROOT),
            "--asset-spec",
            "product",
        ],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )
    unknown_result = subprocess.run(
        [
            sys.executable,
            str(_BODY_CHECKER_PATH),
            "--root",
            str(_REPOSITORY_ROOT),
            "--asset-spec",
            "unknown",
        ],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )

    assert product_result.returncode == 0
    assert product_result.stdout == b"authz-function-bodies: OK\n"
    assert product_result.stderr == b""
    assert unknown_result.returncode == 2
    assert b"invalid choice" in unknown_result.stderr


def test_probe_spec_rejects_asset_with_non_probe_scope(
    copied_repository: Path,
) -> None:
    """資産コピーの scope だけを製品値へ変えると両読取経路が拒否する。"""
    generate_authz_ddl(copied_repository, PROBE_SPEC)
    baseline_check = _run_body_checker(copied_repository, explicit_probe=True)
    assert baseline_check.returncode == 0, baseline_check.stderr.decode("utf-8")

    ddl_path = copied_repository / PROBE_SPEC.ddl_elements_path
    text = ddl_path.read_text(encoding="utf-8")
    before = f'"{PROBE_SPEC.scope_status_field}": "{PROBE_SPEC.allowed_scope_status}"'
    after = f'"{PROBE_SPEC.scope_status_field}": "product_configuration"'
    assert text.count(before) == 1
    ddl_path.write_text(text.replace(before, after, 1), encoding="utf-8")

    with pytest.raises(AuthzDDLGenerationError, match="scope.status"):
        generate_authz_ddl(copied_repository, PROBE_SPEC)

    mutated_check = _run_body_checker(copied_repository, explicit_probe=True)
    assert mutated_check.returncode == 2
    assert b"scope.status" in mutated_check.stderr
