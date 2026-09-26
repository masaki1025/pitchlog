"""ランタイム認可契約の生成器と共通述語を検査する。"""

from __future__ import annotations

import ast
import copy
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from pitchlog.authz.runtime_contract_generator import (
    check_repository,
    main,
    render_repository,
)
from pitchlog.authz.runtime_contract_state import (
    GENERATED_MODULE,
    RUNTIME_CONTRACT_ASSET,
    RuntimeContractError,
    asset_digest,
    compare_staged_protected_objects,
    derive_runtime_contract_fields,
    render_runtime_contract,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ENGINE_MODULE = Path("backend/src/pitchlog/db/engine.py")
_STAGED_PRODUCT_ASSET = Path("contracts/authz/product/ddl-elements.staged.json")


def _read_asset(repository_root: Path) -> dict[str, Any]:
    """試験用リポジトリからランタイム契約を読む。"""
    value = json.loads(
        (repository_root / RUNTIME_CONTRACT_ASSET).read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _read_repository_json(relative_path: Path) -> dict[str, Any]:
    """実リポジトリの JSON object を読む。"""
    value = json.loads((_REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _application_role_row(product_asset: dict[str, Any]) -> dict[str, Any]:
    """製品資産のアプリ用ロール行を返す。"""
    roles = cast(list[dict[str, Any]], product_asset["roles"])
    matches = [row for row in roles if row.get("role_id") == "pitchlog_app"]
    assert len(matches) == 1
    return matches[0]


def _write_asset(repository_root: Path, asset: dict[str, Any]) -> None:
    """試験用リポジトリへランタイム契約を書く。"""
    (repository_root / RUNTIME_CONTRACT_ASSET).write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_repository(tmp_path: Path) -> Path:
    """生成器に必要なファイルだけを持つ worktree 形式の複製を作る。"""
    repository_root = tmp_path / "repository"
    asset_target = repository_root / RUNTIME_CONTRACT_ASSET
    module_target = repository_root / GENERATED_MODULE
    asset_target.parent.mkdir(parents=True)
    module_target.parent.mkdir(parents=True)
    shutil.copy2(_REPOSITORY_ROOT / RUNTIME_CONTRACT_ASSET, asset_target)
    shutil.copy2(_REPOSITORY_ROOT / GENERATED_MODULE, module_target)
    (repository_root / ".git").write_text("gitdir: test-worktree\n", encoding="utf-8")
    return repository_root


def _synchronize_repository(repository_root: Path, asset: dict[str, Any]) -> None:
    """変異以外の digest と生成モジュールを同期する。"""
    asset["source_digest"] = asset_digest(asset)
    _write_asset(repository_root, asset)
    (repository_root / GENERATED_MODULE).write_text(
        render_runtime_contract(asset),
        encoding="utf-8",
    )


def _assert_check_result(repository_root: Path, expected: set[str]) -> None:
    """共有 API と check モードが同じ違反を報告することを確認する。"""
    assert check_repository(repository_root) == expected
    assert main(["check"], repository_root=repository_root) == (1 if expected else 0)


def _mutate_fixture_missing(fixtures: list[dict[str, str]]) -> None:
    """危険終点 fixture を 1 件落とす。"""
    fixtures.pop()


def _mutate_fixture_duplicate(fixtures: list[dict[str, str]]) -> None:
    """危険終点 fixture を 1 件重複させる。"""
    fixtures[1] = copy.deepcopy(fixtures[0])


def _mutate_fixture_id(fixtures: list[dict[str, str]]) -> None:
    """危険終点 fixture の ID だけを変える。"""
    fixtures[0]["fixture_id"] = "DANGER_CHANGED"


def _imported_modules(path: Path) -> set[str]:
    """ソースが静的に import しているモジュール名を返す。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_staged_derivation_matches_provisional_union_exactly() -> None:
    """製品の保護対象が暫定集合と追加分6件の和集合に一致することを確認する。"""
    runtime_asset = _read_repository_json(RUNTIME_CONTRACT_ASSET)
    derived = derive_runtime_contract_fields(
        _REPOSITORY_ROOT / _STAGED_PRODUCT_ASSET,
        _REPOSITORY_ROOT / RUNTIME_CONTRACT_ASSET,
    )
    protected = derived["protected_objects"]
    comparison = compare_staged_protected_objects(
        _REPOSITORY_ROOT / _STAGED_PRODUCT_ASSET,
        runtime_asset,
    )

    assert comparison.matches is True
    assert comparison.missing.is_empty
    assert comparison.extra.is_empty
    assert len(protected["schemas"]) == 2
    assert len(protected["tables"]) == 45
    assert len(protected["functions"]) == 38

    provisional = cast(dict[str, list[Any]], runtime_asset["protected_objects"])
    added_schemas = set(protected["schemas"]) - set(provisional["schemas"])
    added_tables = {tuple(row) for row in protected["tables"]} - {
        tuple(row) for row in provisional["tables"]
    }
    added_functions = {tuple(row) for row in protected["functions"]} - {
        tuple(row) for row in provisional["functions"]
    }
    assert added_schemas == {"authz_private"}
    assert added_tables == set()
    assert added_functions == {
        ("authz_private", "tenant_has_effective_membership", "uuid, boolean"),
        ("public", "prevent_invalidation_intents_target_update", ""),
        ("public", "prevent_migrated_final_lineups_source_update", ""),
        ("public", "prevent_migration_quarantine_mutation", ""),
        ("public", "prevent_players_identity_update", ""),
    }


def test_derived_role_attributes_match_provisional_contract() -> None:
    """製品ロールから導いた7属性が暫定契約と一致することを確認する。"""
    runtime_asset = _read_repository_json(RUNTIME_CONTRACT_ASSET)
    derived = derive_runtime_contract_fields(
        _read_repository_json(_STAGED_PRODUCT_ASSET),
        runtime_asset,
    )
    application_role = cast(dict[str, Any], runtime_asset["application_role"])

    assert derived["application_role"]["attributes"] == application_role["attributes"]
    assert len(derived["application_role"]["attributes"]) == 7


@pytest.mark.parametrize(
    "mutation",
    ("unknown-key", "missing-role", "duplicate-role", "missing-attribute", "non-bool"),
)
def test_role_derivation_fails_closed_for_invalid_rows(mutation: str) -> None:
    """ロールの未知キー・一意性・7属性の形を fail-closed にする。"""
    product_asset = _read_repository_json(_STAGED_PRODUCT_ASSET)
    runtime_asset = _read_repository_json(RUNTIME_CONTRACT_ASSET)
    role = _application_role_row(product_asset)
    roles = cast(list[dict[str, Any]], product_asset["roles"])
    if mutation == "unknown-key":
        role["unexpected_attribute"] = False
    elif mutation == "missing-role":
        roles.remove(role)
    elif mutation == "duplicate-role":
        roles.append(copy.deepcopy(role))
    elif mutation == "missing-attribute":
        role.pop("superuser")
    elif mutation == "non-bool":
        role["superuser"] = "false"
    else:
        raise AssertionError(f"未知の変異: {mutation}")

    with pytest.raises(RuntimeContractError):
        derive_runtime_contract_fields(product_asset, runtime_asset)


@pytest.mark.parametrize("collection", ("schemas", "tables", "functions"))
@pytest.mark.parametrize("mutation", ("malformed", "duplicate"))
def test_protected_object_derivation_fails_closed_for_invalid_rows(
    collection: str, mutation: str
) -> None:
    """保護対象3種の不正な形と重複を fail-closed にする。"""
    product_asset = _read_repository_json(_STAGED_PRODUCT_ASSET)
    runtime_asset = _read_repository_json(RUNTIME_CONTRACT_ASSET)
    rows = cast(list[dict[str, Any]], product_asset[collection])
    if mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif collection == "schemas":
        rows[0]["schema_name"] = 1
    elif collection == "tables":
        rows[0]["table_id"] = 1
    elif collection == "functions":
        rows[0]["identity_args"] = 1
    else:
        raise AssertionError(f"未知の保護対象: {collection}")

    with pytest.raises(RuntimeContractError):
        derive_runtime_contract_fields(product_asset, runtime_asset)


def test_derivation_is_deterministic_and_sorted() -> None:
    """同じ入力の導出結果が決定的で保護対象が辞書順になることを確認する。"""
    product_asset = _read_repository_json(_STAGED_PRODUCT_ASSET)
    runtime_asset = _read_repository_json(RUNTIME_CONTRACT_ASSET)
    for key in ("schemas", "tables", "functions"):
        cast(list[object], product_asset[key]).reverse()

    first = derive_runtime_contract_fields(product_asset, runtime_asset)
    second = derive_runtime_contract_fields(product_asset, runtime_asset)
    protected = first["protected_objects"]

    assert first == second
    assert protected["schemas"] == sorted(protected["schemas"])
    assert protected["tables"] == [
        list(identifier) for identifier in sorted(map(tuple, protected["tables"]))
    ]
    assert protected["functions"] == [
        list(identifier) for identifier in sorted(map(tuple, protected["functions"]))
    ]


def test_staged_comparison_reports_one_removed_addition() -> None:
    """追加宣言を1件落とすと対応する余分1件だけを差分として返す。"""
    product_asset = _read_repository_json(_STAGED_PRODUCT_ASSET)
    runtime_asset = _read_repository_json(RUNTIME_CONTRACT_ASSET)
    additions = cast(
        list[dict[str, Any]],
        product_asset["provisional_contract_additions"],
    )
    removed = additions.pop(0)

    comparison = compare_staged_protected_objects(product_asset, runtime_asset)
    removed_identifier = (
        removed["schema_name"],
        removed["object_name"],
        removed["identity_args"],
    )

    assert comparison.matches is False
    assert comparison.missing.is_empty
    assert comparison.extra.schemas == frozenset()
    assert comparison.extra.tables == frozenset()
    assert comparison.extra.functions == frozenset({removed_identifier})


def test_rendered_source_matches_generated_module_byte_for_byte() -> None:
    """描画結果と配布する生成モジュールがバイト一致することを確認する。"""
    asset = _read_asset(_REPOSITORY_ROOT)

    assert render_runtime_contract(asset).encode() == (
        (_REPOSITORY_ROOT / GENERATED_MODULE).read_bytes()
    )


def test_check_succeeds_for_current_repository() -> None:
    """現在のリポジトリで check が成功することを確認する。"""
    _assert_check_result(_REPOSITORY_ROOT, set())


def test_d1_rejects_missing_asset_exactly(tmp_path: Path) -> None:
    """D1 が資産の欠落だけを報告することを確認する。"""
    repository_root = _copy_repository(tmp_path)
    (repository_root / RUNTIME_CONTRACT_ASSET).unlink()

    _assert_check_result(repository_root, {"PROVISIONAL_ASSET_MISSING"})


@pytest.mark.parametrize("role_name", ("pitchlog_owner", "pitchlog_shared_fn_owner"))
def test_d2_rejects_each_declared_role_name_exactly(
    tmp_path: Path, role_name: str
) -> None:
    """D2 が別の実在ロール名だけを報告することを確認する。"""
    repository_root = _copy_repository(tmp_path)
    asset = _read_asset(repository_root)
    application_role = cast(dict[str, Any], asset["application_role"])
    application_role["rolname"] = role_name
    _synchronize_repository(repository_root, asset)

    _assert_check_result(repository_root, {"DECLARED_ROLE_NAME_MISMATCH"})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", 2),
        ("asset_kind", "changed_runtime_contract"),
        ("canonicalization", "changed-canonicalization"),
    ),
)
def test_d3_rejects_each_fixed_value_exactly(
    tmp_path: Path, field: str, value: object
) -> None:
    """D3 が固定宣言値の変異だけを報告することを確認する。"""
    repository_root = _copy_repository(tmp_path)
    asset = _read_asset(repository_root)
    asset[field] = value
    _synchronize_repository(repository_root, asset)

    _assert_check_result(repository_root, {"DECLARED_VALUE_MISMATCH"})


@pytest.mark.parametrize(
    "mutate",
    (_mutate_fixture_missing, _mutate_fixture_duplicate, _mutate_fixture_id),
    ids=("missing", "duplicate", "fixture-id"),
)
def test_d4_rejects_each_dangerous_fixture_mutation_exactly(
    tmp_path: Path,
    mutate: Callable[[list[dict[str, str]]], None],
) -> None:
    """D4 が危険終点 fixture の変異だけを報告することを確認する。"""
    repository_root = _copy_repository(tmp_path)
    asset = _read_asset(repository_root)
    fixtures = cast(list[dict[str, str]], asset["dangerous_endpoint_fixtures"])
    mutate(fixtures)
    _synchronize_repository(repository_root, asset)

    _assert_check_result(repository_root, {"DANGEROUS_FIXTURES_MISMATCH"})


def test_d5_rejects_identifier_mismatch_exactly(tmp_path: Path) -> None:
    """D5 が識別値の変異だけを報告することを確認する。"""
    repository_root = _copy_repository(tmp_path)
    asset = _read_asset(repository_root)
    baseline = cast(dict[str, Any], asset["baseline_control"])
    identity = cast(dict[str, Any], baseline["identity"])
    identity["current_identifiers"] = ["runtime_contract_revision:999"]
    _synchronize_repository(repository_root, asset)

    _assert_check_result(repository_root, {"IDENTIFIER_MISMATCH"})


def test_d5_rejects_stale_source_digest_exactly(tmp_path: Path) -> None:
    """D5 が古い source digest だけを報告することを確認する。"""
    repository_root = _copy_repository(tmp_path)
    asset = _read_asset(repository_root)
    baseline = cast(dict[str, Any], asset["baseline_control"])
    identity = cast(dict[str, Any], baseline["identity"])
    identity["no_baseline_marker"] = "CHANGED_BASELINE"
    _write_asset(repository_root, asset)

    _assert_check_result(repository_root, {"SOURCE_DIGEST_STALE"})


def test_generated_module_staleness_is_reported_with_unified_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """生成モジュールの不一致を単一 ID と unified diff で報告する。"""
    repository_root = _copy_repository(tmp_path)
    module_path = repository_root / GENERATED_MODULE
    module_path.write_text(
        module_path.read_text(encoding="utf-8").replace(
            'APPLICATION_ROLE_NAME = "pitchlog_app"',
            'APPLICATION_ROLE_NAME = "changed"',
        ),
        encoding="utf-8",
    )

    _assert_check_result(repository_root, {"GENERATED_MODULE_STALE"})
    stderr = capsys.readouterr().err
    assert "GENERATED_MODULE_STALE" in stderr
    assert f"--- {GENERATED_MODULE.as_posix()}" in stderr
    assert f"+++ {GENERATED_MODULE.as_posix()} (expected)" in stderr


def test_render_is_idempotent(tmp_path: Path) -> None:
    """Render の 2 回目がファイル差分を作らないことを確認する。"""
    repository_root = _copy_repository(tmp_path)
    module_path = repository_root / GENERATED_MODULE
    module_path.write_text("# stale\n", encoding="utf-8")

    assert render_repository(repository_root) is True
    first = module_path.read_bytes()
    assert render_repository(repository_root) is False
    assert module_path.read_bytes() == first
    assert main(["render"], repository_root=repository_root) == 0
    assert module_path.read_bytes() == first


def test_repository_root_missing_returns_exit_code_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """リポジトリ外では明確なメッセージと終了コード 2 を返す。"""
    empty_directory = tmp_path / "outside"
    empty_directory.mkdir()

    assert main(["check"], repository_root=empty_directory) == 2
    assert "リポジトリルートが見つかりません" in capsys.readouterr().err


def test_rendered_source_is_already_ruff_formatted(tmp_path: Path) -> None:
    """描画結果が ruff format で変わらないことを確認する。"""
    rendered_path = tmp_path / "runtime_contract.py"
    rendered_path.write_text(
        render_runtime_contract(_read_asset(_REPOSITORY_ROOT)),
        encoding="utf-8",
    )
    ruff = Path(sys.executable).with_name("ruff")
    result = subprocess.run(
        [ruff, "format", "--check", rendered_path],
        cwd=_REPOSITORY_ROOT / "backend",
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("relative_path", (GENERATED_MODULE, _ENGINE_MODULE))
def test_runtime_modules_do_not_import_generator_or_shared_state(
    relative_path: Path,
) -> None:
    """実行時モジュールが生成器と共有状態 API を import しないことを確認する。"""
    imported = _imported_modules(_REPOSITORY_ROOT / relative_path)

    assert not any(
        module.endswith(("runtime_contract_state", "runtime_contract_generator"))
        for module in imported
    )
