"""認証の故障系試験を実装変異で red → green と確認する。"""

import ast
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = _BACKEND_ROOT.parent
_SOURCE_ROOT = _BACKEND_ROOT / "src" / "pitchlog"


@dataclass(frozen=True)
class _Mutation:
    """守りを外す実装変更と既存試験の対応を保持する。"""

    name: str
    source: str
    original: str
    changed: str
    occurrences: int
    tests: tuple[str, ...]
    failed: int


_MUTATIONS = (
    _Mutation(
        name="signature_and_rotated_key",
        source="authz/token_presentation.py",
        original="if not _hmac.compare_digest(expected, bytes.fromhex(signature_hex)):",
        changed="if False:",
        occurrences=1,
        tests=(
            "tests/test_authz_verified_tenant.py::"
            "test_logout_rejects_unsigned_values_without_db[tampered_signature]",
            "tests/test_authz_token_presentation.py::"
            "test_signature_from_another_key_is_rejected_without_leaking_input",
        ),
        failed=2,
    ),
    _Mutation(
        name="malformed_presentation",
        source="authz/token_presentation.py",
        original="_PRESENTATION_PATTERN.fullmatch(value)",
        changed="_PRESENTATION_PATTERN.match(value)",
        occurrences=1,
        tests=(
            "tests/test_authz_failure_mutations.py::"
            "test_valid_signed_value_with_suffix_is_rejected",
        ),
        failed=1,
    ),
    _Mutation(
        name="missing_and_short_key",
        source="authz/signing_key_config.py",
        original="    if not value:\n",
        changed="    return bytes(32)\n    if not value:\n",
        occurrences=1,
        tests=(
            "tests/test_authz_signing_key_config.py::"
            "test_missing_signing_key_prevents_app_creation",
            "tests/test_authz_signing_key_config.py::"
            "test_short_decoded_signing_key_prevents_app_creation",
        ),
        failed=3,
    ),
    _Mutation(
        name="unverified_transport",
        source="authz/database_transport.py",
        original="    try:\n        url = make_url(normalized_url)\n",
        changed="    return\n    try:\n        url = make_url(normalized_url)\n",
        occurrences=1,
        tests=(
            "tests/test_authz_database_transport.py::"
            "test_engine_rejects_unverified_or_ambiguous_transport",
        ),
        failed=12,
    ),
    _Mutation(
        name="unsigned_authn_calls",
        source="authz/verified_tenant.py",
        original="verified_id = presentation.decode(value)",
        changed="verified_id = _UUID(str(value).split('.')[0])",
        occurrences=2,
        tests=(
            "tests/test_authz_verified_tenant.py::"
            "test_unsigned_id_and_tampered_value_never_open_db",
            "tests/test_authz_verified_tenant.py::"
            "test_logout_rejects_unsigned_values_without_db[raw_uuid]",
        ),
        failed=2,
    ),
)

# 計画書の条件文を起点に、既存試験と追加した形式試験を対応付ける。
_ACCEPTANCE_COVERAGE = {
    "署名の改ざん": (
        "tests/test_authz_verified_tenant.py::"
        "test_logout_rejects_unsigned_values_without_db[tampered_signature]",
    ),
    "鍵の入れ替え後のトークン": (
        "tests/test_authz_token_presentation.py::"
        "test_signature_from_another_key_is_rejected_without_leaking_input",
    ),
    "不正な形式の提示値": (
        "tests/test_authz_token_presentation.py::"
        "test_malformed_presentation_is_rejected",
        "tests/test_authz_failure_mutations.py::"
        "test_valid_signed_value_with_suffix_is_rejected",
    ),
    "鍵の欠落・短い鍵で起動拒否": (
        "tests/test_authz_signing_key_config.py::"
        "test_missing_signing_key_prevents_app_creation",
        "tests/test_authz_signing_key_config.py::"
        "test_short_decoded_signing_key_prevents_app_creation",
    ),
    "TLS でない設定を拒否": (
        "tests/test_authz_database_transport.py::"
        "test_engine_rejects_unverified_or_ambiguous_transport",
    ),
    "正しく署名された失効済み・無効テナントの ID": (
        "tests/db/test_authz_verified_tenant.py::"
        "test_signed_invalid_token_returns_no_tenant[logged_out]",
        "tests/db/test_authz_verified_tenant.py::"
        "test_signed_invalid_token_returns_no_tenant[stale_credential]",
        "tests/db/test_authz_verified_tenant.py::"
        "test_signed_invalid_token_returns_no_tenant[disabled]",
        "tests/db/test_authz_verified_tenant.py::"
        "test_signed_invalid_token_returns_no_tenant[wrong_tenant]",
        "tests/db/test_authz_verified_tenant.py::"
        "test_signed_invalid_token_returns_no_tenant[expired]",
    ),
    "署名を照合していない ID": (
        "tests/test_authz_verified_tenant.py::"
        "test_unsigned_id_and_tampered_value_never_open_db",
        "tests/test_authz_verified_tenant.py::"
        "test_logout_rejects_unsigned_values_without_db[raw_uuid]",
        "tests/test_authz_app_layer_surface.py::"
        "test_db_reach_is_exact_set_and_absences_are_explicit",
    ),
}


def _run_tests(
    source_root: Path, tests: tuple[str, ...]
) -> subprocess.CompletedProcess[str]:
    """一時的な製品ソースを優先して既存試験を別プロセスで実行する。

    Args:
        source_root: 置換した製品パッケージの親ディレクトリ。
        tests: 実行する既存試験の node ID。

    Returns:
        pytest の終了状態と標準出力。
    """
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(source_root), environment.get("PYTHONPATH", ""))
    )
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no", *tests],
        cwd=_BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _imported_source(source_root: Path, relative_path: str, fragment: str) -> bool:
    """子プロセスが変異したモジュールと文を実際に読み込むか確認する。

    Args:
        source_root: 一時的な製品パッケージの親ディレクトリ。
        relative_path: 製品パッケージ内の対象ファイル。
        fragment: 実装へ入れた文。

    Returns:
        読み込まれたパスとソースの両方が変異先なら True。
    """
    module = "pitchlog." + relative_path.removesuffix(".py").replace("/", ".")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(source_root), environment.get("PYTHONPATH", ""))
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib, inspect, sys; "
            "m = importlib.import_module(sys.argv[1]); "
            "print(m.__file__); print(sys.argv[2] in inspect.getsource(m))",
            module,
            fragment,
        ],
        cwd=_BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    lines = probe.stdout.splitlines()
    expected = source_root / "pitchlog" / relative_path
    return (
        probe.returncode == 0
        and len(lines) == 2
        and Path(lines[0]).resolve() == expected.resolve()
        and lines[1] == "True"
    )


def _summary_count(output: str, kind: str) -> int:
    """Pytest の結果行から合格または失敗件数を返す。"""
    match = re.search(rf"(\d+) {kind}\b", output)
    return int(match.group(1)) if match else 0


def test_valid_signed_value_with_suffix_is_rejected() -> None:
    """署名自体が正しくても余分な末尾文字を許さない。"""
    from pitchlog.authz.token_presentation import TokenPresentation

    presentation = TokenPresentation(secrets.token_bytes(32))
    value = presentation.encode(UUID(int=1))

    with pytest.raises(ValueError, match="提示値の形式または署名が不正です"):
        presentation.decode(value + "x")


def test_step6_acceptance_clauses_have_real_tests() -> None:
    """計画書の条件文から試験への対応と参照先の実在を確認する。"""
    plan = (_REPOSITORY_ROOT / "docs/features/ua1-auth-app-layer/plan.md").read_text(
        encoding="utf-8"
    )
    step = next(line for line in plan.splitlines() if line.startswith("| 6 |"))
    assert len(_ACCEPTANCE_COVERAGE) == 7
    for clause, tests in _ACCEPTANCE_COVERAGE.items():
        assert clause in step
        assert tests
        for node_id in tests:
            relative, function = node_id.split("::", 1)
            path = _BACKEND_ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"))
            functions = {
                node.name: node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            name, _, case = function.partition("[")
            assert name in functions
            if case:
                values = {
                    node.value
                    for node in ast.walk(functions[name])
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                assert case.removesuffix("]") in values


@pytest.mark.parametrize("mutation", _MUTATIONS, ids=lambda item: item.name)
def test_guard_mutation_is_red_then_green(mutation: _Mutation, tmp_path: Path) -> None:
    """実装変異を読み込ませた試験を red にし、復元後に green を確認する。"""
    source_root = tmp_path / "src"
    shutil.copytree(_SOURCE_ROOT, source_root / "pitchlog")
    original_file = _SOURCE_ROOT / mutation.source
    changed_file = source_root / "pitchlog" / mutation.source
    original_bytes = original_file.read_bytes()
    original = original_bytes.decode("utf-8")
    assert original.count(mutation.original) == mutation.occurrences
    changed = original.replace(mutation.original, mutation.changed)
    assert ast.dump(ast.parse(changed)) != ast.dump(ast.parse(original))
    changed_file.write_text(changed, encoding="utf-8")

    try:
        # red の判定に先立って、一時実装の AST と子プロセスの import 先を確かめる。
        assert changed_file.read_text(encoding="utf-8").count(mutation.changed) == (
            mutation.occurrences
        )
        assert _imported_source(source_root, mutation.source, mutation.changed)
        red = _run_tests(source_root, mutation.tests)
    finally:
        changed_file.write_bytes(original_bytes)

    assert changed_file.read_bytes() == original_file.read_bytes()
    assert _imported_source(source_root, mutation.source, mutation.original)
    green = _run_tests(source_root, mutation.tests)

    red_failed = _summary_count(red.stdout, "failed")
    green_passed = _summary_count(green.stdout, "passed")
    print(
        f"{mutation.name}: 変異到達確認済み、red={red_failed} failed、"
        f"復元差分=0、green={green_passed} passed"
    )
    assert red.returncode == 1
    assert red_failed == mutation.failed
    assert green.returncode == 0
    assert green_passed == mutation.failed
