"""ランタイム認可契約の生成器と共通述語を検査する。"""

from __future__ import annotations

import ast
import base64
import copy
import importlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from test_authz_runtime_contract_repository import (
    copy_product_repository,
    provisional_reference_revision,
)

from pitchlog.authz import runtime_contract_generator as generator
from pitchlog.authz.runtime_contract_generator import (
    check_repository,
    main,
    rederive_repository,
    render_repository,
)
from pitchlog.authz.runtime_contract_state import (
    GENERATED_MODULE,
    PRODUCT_ASSET,
    RUNTIME_CONTRACT_ASSET,
    STAGED_PRODUCT_ASSET,
    RuntimeContractError,
    RuntimeContractState,
    asset_digest,
    compare_staged_protected_objects,
    derive_runtime_contract_fields,
    evaluate_repository,
    render_runtime_contract,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ENGINE_MODULE = Path("backend/src/pitchlog/db/engine.py")
_STAGED_PRODUCT_ASSET = STAGED_PRODUCT_ASSET


def _provisional_asset_at_base(relative_path: Path) -> dict[str, Any]:
    """製品化後も比較元の暫定資産を変異試験へ供給する。"""
    if (_REPOSITORY_ROOT / STAGED_PRODUCT_ASSET).is_file():
        return _read_repository_json(relative_path)
    result = subprocess.run(
        [
            "git",
            "show",
            f"{provisional_reference_revision(_REPOSITORY_ROOT)}:{relative_path.as_posix()}",
        ],
        cwd=_REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _write_provisional_inputs(repository_root: Path) -> None:
    """暫定の変異試験に必要な資産と生成モジュールを複製へ置く。"""
    asset = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
    _write_asset(repository_root, asset)
    _write_module_source(repository_root, render_runtime_contract(asset))


def _read_asset(repository_root: Path) -> dict[str, Any]:
    """試験用リポジトリからランタイム契約を読む。"""
    value = json.loads(
        (repository_root / RUNTIME_CONTRACT_ASSET).read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _read_copied_json(repository_root: Path, relative_path: Path) -> dict[str, Any]:
    """試験用リポジトリの JSON object を読む。"""
    value = json.loads((repository_root / relative_path).read_text(encoding="utf-8"))
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
    state, violations = evaluate_repository(_REPOSITORY_ROOT)
    assert not violations
    if state is RuntimeContractState.PRODUCT:
        product_target = repository_root / PRODUCT_ASSET
        product_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPOSITORY_ROOT / PRODUCT_ASSET, product_target)
    (repository_root / ".git").write_text("gitdir: test-worktree\n", encoding="utf-8")
    return repository_root


def _copy_pending_repository(tmp_path: Path) -> Path:
    """現在の未発効状態に必要な資産を複製する。"""
    repository_root = _copy_repository(tmp_path)
    product_target = repository_root / PRODUCT_ASSET
    if product_target.exists():
        product_target.unlink()
    _write_provisional_inputs(repository_root)
    staged_target = repository_root / STAGED_PRODUCT_ASSET
    staged_target.parent.mkdir(parents=True, exist_ok=True)
    _write_repository_json(
        repository_root,
        STAGED_PRODUCT_ASSET,
        _provisional_asset_at_base(STAGED_PRODUCT_ASSET),
    )
    return repository_root


def _write_repository_json(
    repository_root: Path,
    relative_path: Path,
    value: dict[str, Any],
) -> None:
    """試験用リポジトリの指定パスへ JSON object を書く。"""
    target = repository_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _replace_module_constant(source: str, name: str, value_source: str) -> str:
    """生成モジュールの単純代入定数を1件だけ置き換える。"""
    lines = source.splitlines(keepends=True)
    matching = [
        index for index, line in enumerate(lines) if line.startswith(f"{name} = ")
    ]
    assert len(matching) == 1
    index = matching[0]
    newline = "\n" if lines[index].endswith("\n") else ""
    lines[index] = f"{name} = {value_source}{newline}"
    return "".join(lines)


def _write_module_source(repository_root: Path, source: str) -> None:
    """試験用リポジトリの生成モジュールを書く。"""
    (repository_root / GENERATED_MODULE).write_text(source, encoding="utf-8")


def _synchronize_with_lifecycle_overrides(
    repository_root: Path,
    asset: dict[str, Any],
    overrides: dict[str, str],
) -> None:
    """資産と生成物を同期し、指定したライフサイクル定数だけ差し替える。"""
    asset["source_digest"] = asset_digest(asset)
    _write_asset(repository_root, asset)
    source = render_runtime_contract(asset)
    for name, value_source in overrides.items():
        source = _replace_module_constant(source, name, value_source)
    _write_module_source(repository_root, source)


def _copy_product_repository(tmp_path: Path) -> Path:
    """Switch を使わず、試験用の正しい製品状態を組み立てる。"""
    return copy_product_repository(_REPOSITORY_ROOT, tmp_path / "repository")


def _git_repository_for_rederive(tmp_path: Path, *, full_history: bool = False) -> Path:
    """製品契約の比較元コミットを持つ使い捨てリポジトリを作る。"""
    root = tmp_path / "repository"
    for relative in (RUNTIME_CONTRACT_ASSET, GENERATED_MODULE, PRODUCT_ASSET):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPOSITORY_ROOT / relative, target)
    if full_history:
        shutil.copytree(
            _REPOSITORY_ROOT / "contracts/tenant_boundary",
            root / "contracts/tenant_boundary",
            dirs_exist_ok=True,
        )
        external_paths = {
            Path(path)
            for asset_path in (root / "contracts/tenant_boundary").glob("*.json")
            for path in json.loads(asset_path.read_text(encoding="utf-8"))[
                "baseline_control"
            ]["identity"]["frozen_projection"]["external_files"]
        }
        for relative in sorted(external_paths):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_REPOSITORY_ROOT / relative, target)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        check=True,
    )
    return root


def _add_test_function(root: Path) -> None:
    """製品 DDL 宣言に重複しない関数を 1 件加える。"""
    product = _read_copied_json(root, PRODUCT_ASSET)
    function = copy.deepcopy(cast(list[dict[str, Any]], product["functions"])[0])
    function["function_id"] = "FUNCTION:public:test_rederive_step_five()"
    function["function_name"] = "test_rederive_step_five"
    cast(list[dict[str, Any]], product["functions"]).append(function)
    _write_repository_json(root, PRODUCT_ASSET, product)


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


def _assert_evaluation(
    repository_root: Path,
    expected_state: RuntimeContractState,
    expected_violations: set[str],
) -> None:
    """共有入口の状態と違反 ID を exact に確認する。"""
    state, violations = evaluate_repository(repository_root)
    assert state is expected_state
    assert violations == expected_violations


def _mutate_fixture_missing(fixtures: list[dict[str, str]]) -> None:
    """危険終点 fixture を 1 件落とす。"""
    fixtures.pop()


def _mutate_fixture_duplicate(fixtures: list[dict[str, str]]) -> None:
    """危険終点 fixture を 1 件重複させる。"""
    fixtures[1] = copy.deepcopy(fixtures[0])


def _mutate_fixture_id(fixtures: list[dict[str, str]]) -> None:
    """危険終点 fixture の ID だけを変える。"""
    fixtures[0]["fixture_id"] = "DANGER_CHANGED"


def _apply_provisional_mutation(repository_root: Path, mutation: str) -> None:
    """暫定・未発効述語の独立変異を適用する。"""
    asset = _read_asset(repository_root)
    module_path = repository_root / GENERATED_MODULE
    source = module_path.read_text(encoding="utf-8")
    if mutation == "t1-provisional-false":
        asset["provisional"] = False
        _synchronize_with_lifecycle_overrides(
            repository_root,
            asset,
            {"PROVISIONAL": "True"},
        )
    elif mutation == "t2-superseded-missing":
        asset.pop("superseded_by")
        _synchronize_with_lifecycle_overrides(
            repository_root,
            asset,
            {"SUPERSEDED_BY": json.dumps(PRODUCT_ASSET.as_posix())},
        )
    elif mutation == "t2-superseded-other":
        asset["superseded_by"] = "contracts/authz/product/other.json"
        _synchronize_with_lifecycle_overrides(
            repository_root,
            asset,
            {"SUPERSEDED_BY": json.dumps(PRODUCT_ASSET.as_posix())},
        )
    elif mutation == "t3-derived-added":
        asset["derived_from"] = PRODUCT_ASSET.as_posix()
        _synchronize_with_lifecycle_overrides(
            repository_root,
            asset,
            {"DERIVED_FROM": "None"},
        )
    elif mutation == "t4-module-provisional-false":
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "PROVISIONAL", "False"),
        )
    elif mutation == "t5-module-source-other":
        _write_module_source(
            repository_root,
            _replace_module_constant(
                source,
                "SOURCE_ASSET",
                json.dumps("contracts/tenant_boundary/other.json"),
            ),
        )
    elif mutation == "t6-module-superseded-none":
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "SUPERSEDED_BY", "None"),
        )
    elif mutation == "t7-module-derived-final":
        _write_module_source(
            repository_root,
            _replace_module_constant(
                source,
                "DERIVED_FROM",
                json.dumps(PRODUCT_ASSET.as_posix()),
            ),
        )
    elif mutation == "t8-module-protected-table":
        _write_module_source(
            repository_root,
            source.replace(
                '("public", "tenants"),',
                '("public", "changed_tenants"),',
                1,
            ),
        )
    elif mutation == "t8-module-revision":
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "RUNTIME_CONTRACT_REVISION", "999"),
        )
    elif mutation == "t8-module-digest":
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "SOURCE_DIGEST", json.dumps("stale")),
        )
    else:
        raise AssertionError(f"未知の暫定変異: {mutation}")


def _apply_product_mutation(repository_root: Path, mutation: str) -> None:
    """製品述語の独立変異を適用する。"""
    asset = _read_asset(repository_root)
    product_asset = _read_copied_json(repository_root, PRODUCT_ASSET)
    source = (repository_root / GENERATED_MODULE).read_text(encoding="utf-8")
    if mutation == "p1-provisional-true":
        asset["provisional"] = True
        _synchronize_with_lifecycle_overrides(
            repository_root,
            asset,
            {"PROVISIONAL": "False"},
        )
    elif mutation == "p2-superseded-null":
        asset["superseded_by"] = None
        _synchronize_repository(repository_root, asset)
    elif mutation == "p2-superseded-old":
        asset["superseded_by"] = PRODUCT_ASSET.as_posix()
        _synchronize_with_lifecycle_overrides(
            repository_root,
            asset,
            {"SUPERSEDED_BY": "None"},
        )
    elif mutation in {"p3-derived-staged", "p3-derived-other", "p3-derived-missing"}:
        if mutation == "p3-derived-staged":
            asset["derived_from"] = STAGED_PRODUCT_ASSET.as_posix()
        elif mutation == "p3-derived-other":
            asset["derived_from"] = "contracts/authz/product/other.json"
        else:
            asset.pop("derived_from")
        _synchronize_with_lifecycle_overrides(
            repository_root,
            asset,
            {"DERIVED_FROM": json.dumps(PRODUCT_ASSET.as_posix())},
        )
    elif mutation.startswith("p4-"):
        application_role = cast(dict[str, Any], asset["application_role"])
        attributes = cast(dict[str, bool], application_role["attributes"])
        protected = cast(dict[str, list[Any]], asset["protected_objects"])
        if mutation == "p4-function-missing":
            protected["functions"].pop()
        elif mutation == "p4-function-added":
            protected["functions"].append(["public", "unexpected_function", ""])
        elif mutation == "p4-provisional-functions":
            provisional = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
            provisional_protected = cast(
                dict[str, list[Any]], provisional["protected_objects"]
            )
            protected["functions"] = copy.deepcopy(provisional_protected["functions"])
        elif mutation == "p4-attribute":
            attributes["rolcanlogin"] = not attributes["rolcanlogin"]
        elif mutation == "p4-public-schema-only":
            protected["schemas"] = ["public"]
        else:
            raise AssertionError(f"未知の P4 変異: {mutation}")
        _synchronize_repository(repository_root, asset)
    elif mutation == "p5-pending-switch":
        product_asset["pending_switch"] = "TSK-443"
        _write_repository_json(repository_root, PRODUCT_ASSET, product_asset)
    elif mutation == "p6-provisional-additions":
        staged = _provisional_asset_at_base(STAGED_PRODUCT_ASSET)
        product_asset["provisional_contract_additions"] = staged[
            "provisional_contract_additions"
        ]
        _write_repository_json(repository_root, PRODUCT_ASSET, product_asset)
    elif mutation == "p7-module-provisional-true":
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "PROVISIONAL", "True"),
        )
    elif mutation == "p8-module-superseded-old":
        _write_module_source(
            repository_root,
            _replace_module_constant(
                source,
                "SUPERSEDED_BY",
                json.dumps(PRODUCT_ASSET.as_posix()),
            ),
        )
    elif mutation in {"p9-module-source-final", "p9-module-source-staged"}:
        path = PRODUCT_ASSET if mutation.endswith("final") else STAGED_PRODUCT_ASSET
        _write_module_source(
            repository_root,
            _replace_module_constant(
                source,
                "SOURCE_ASSET",
                json.dumps(path.as_posix()),
            ),
        )
    elif mutation in {"p10-module-derived-staged", "p10-module-derived-none"}:
        value_source = (
            json.dumps(STAGED_PRODUCT_ASSET.as_posix())
            if mutation.endswith("staged")
            else "None"
        )
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "DERIVED_FROM", value_source),
        )
    elif mutation == "p11-module-protected-old":
        provisional = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
        module_asset = copy.deepcopy(asset)
        module_asset["protected_objects"] = copy.deepcopy(
            provisional["protected_objects"]
        )
        _write_module_source(
            repository_root,
            render_runtime_contract(module_asset),
        )
    elif mutation == "p11-module-revision":
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "RUNTIME_CONTRACT_REVISION", "999"),
        )
    elif mutation == "p11-module-digest":
        _write_module_source(
            repository_root,
            _replace_module_constant(source, "SOURCE_DIGEST", json.dumps("stale")),
        )
    else:
        raise AssertionError(f"未知の製品変異: {mutation}")


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
    runtime_asset = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
    staged = _provisional_asset_at_base(_STAGED_PRODUCT_ASSET)
    derived = derive_runtime_contract_fields(
        staged,
        runtime_asset,
    )
    protected = derived["protected_objects"]
    comparison = compare_staged_protected_objects(
        staged,
        runtime_asset,
    )

    assert comparison.matches is True
    assert comparison.missing.is_empty
    assert comparison.extra.is_empty
    assert len(protected["schemas"]) == 2
    assert len(protected["tables"]) == 45
    assert len(protected["functions"]) == len(staged["functions"])

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
    runtime_asset = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
    derived = derive_runtime_contract_fields(
        _provisional_asset_at_base(_STAGED_PRODUCT_ASSET),
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
    product_asset = _provisional_asset_at_base(_STAGED_PRODUCT_ASSET)
    runtime_asset = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
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
    product_asset = _provisional_asset_at_base(_STAGED_PRODUCT_ASSET)
    runtime_asset = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
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
    product_asset = _provisional_asset_at_base(_STAGED_PRODUCT_ASSET)
    runtime_asset = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
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
    product_asset = _provisional_asset_at_base(_STAGED_PRODUCT_ASSET)
    runtime_asset = _provisional_asset_at_base(RUNTIME_CONTRACT_ASSET)
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
    expected_state = evaluate_repository(_REPOSITORY_ROOT)[0]
    _assert_evaluation(_REPOSITORY_ROOT, expected_state, set())
    _assert_check_result(_REPOSITORY_ROOT, set())


def test_provisional_state_is_green(tmp_path: Path) -> None:
    """Staged と最終資産が無い正しい暫定状態が green になることを確認する。"""
    repository_root = _copy_pending_repository(tmp_path)
    (repository_root / STAGED_PRODUCT_ASSET).unlink()

    _assert_evaluation(repository_root, RuntimeContractState.PROVISIONAL, set())


def test_product_state_is_green(tmp_path: Path) -> None:
    """試験 helper で組み立てた正しい製品状態が green になることを確認する。"""
    repository_root = _copy_product_repository(tmp_path)

    _assert_evaluation(repository_root, RuntimeContractState.PRODUCT, set())
    _assert_check_result(repository_root, set())


def test_both_product_assets_are_invalid(tmp_path: Path) -> None:
    """Staged と最終資産の併存を単一の違反 ID で拒否する。"""
    repository_root = _copy_pending_repository(tmp_path)
    shutil.copy2(
        repository_root / STAGED_PRODUCT_ASSET,
        repository_root / PRODUCT_ASSET,
    )

    _assert_evaluation(
        repository_root,
        RuntimeContractState.INVALID,
        {"BOTH_STAGED_AND_FINAL"},
    )


@pytest.mark.parametrize(
    "mutation",
    ("missing", "renamed"),
    ids=("d1-asset-missing", "d1-asset-renamed"),
)
def test_d1_rejects_each_missing_asset_mutation_exactly(
    tmp_path: Path,
    mutation: str,
) -> None:
    """D1 が資産の欠落と改名を同じ ID だけで報告する。"""
    repository_root = _copy_repository(tmp_path)
    copied_state = evaluate_repository(repository_root)[0]
    asset_path = repository_root / RUNTIME_CONTRACT_ASSET
    if mutation == "missing":
        asset_path.unlink()
    else:
        asset_path.rename(asset_path.with_suffix(".renamed.json"))

    _assert_evaluation(
        repository_root,
        copied_state,
        {"PROVISIONAL_ASSET_MISSING"},
    )


@pytest.mark.parametrize(
    "role_name",
    ("pitchlog_owner", "pitchlog_shared_fn_owner"),
    ids=("d2-pitchlog-owner", "d2-shared-fn-owner"),
)
def test_d2_rejects_each_declared_role_name_exactly(
    tmp_path: Path, role_name: str
) -> None:
    """D2 が別の実在ロール名だけを報告することを確認する。"""
    repository_root = _copy_pending_repository(tmp_path)
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
    ids=("d3-schema-version", "d3-asset-kind", "d3-canonicalization"),
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
    ids=("d4-missing", "d4-duplicate", "d4-fixture-id"),
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


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("identifier", {"IDENTIFIER_MISMATCH"}),
        ("digest", {"SOURCE_DIGEST_STALE"}),
    ),
    ids=("d5-identifier", "d5-source-digest"),
)
def test_d5_rejects_each_identity_mutation_exactly(
    tmp_path: Path,
    mutation: str,
    expected: set[str],
) -> None:
    """D5 が識別値と digest の変異を対応する ID だけで報告する。"""
    repository_root = _copy_repository(tmp_path)
    asset = _read_asset(repository_root)
    baseline = cast(dict[str, Any], asset["baseline_control"])
    identity = cast(dict[str, Any], baseline["identity"])
    if mutation == "identifier":
        identity["current_identifiers"] = ["runtime_contract_revision:999"]
        _synchronize_repository(repository_root, asset)
    else:
        identity["no_baseline_marker"] = "CHANGED_BASELINE"
        _write_asset(repository_root, asset)

    _assert_check_result(repository_root, expected)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("t1-provisional-false", {"PROVISIONAL_FLAG_MISSING"}),
        ("t2-superseded-missing", {"SUPERSEDED_BY_MISMATCH"}),
        ("t2-superseded-other", {"SUPERSEDED_BY_MISMATCH"}),
        ("t3-derived-added", {"DERIVED_FROM_BEFORE_SWITCH"}),
        ("t4-module-provisional-false", {"GENERATED_MODULE_IS_NOT_PROVISIONAL"}),
        ("t5-module-source-other", {"GENERATED_MODULE_SOURCE_MISMATCH"}),
        (
            "t6-module-superseded-none",
            {"GENERATED_MODULE_SUPERSEDED_BY_MISMATCH"},
        ),
        (
            "t7-module-derived-final",
            {"GENERATED_MODULE_DERIVED_FROM_MISMATCH"},
        ),
        ("t8-module-protected-table", {"GENERATED_MODULE_STALE"}),
        ("t8-module-revision", {"GENERATED_MODULE_STALE"}),
        ("t8-module-digest", {"GENERATED_MODULE_STALE"}),
    ),
    ids=(
        "t1-provisional-false",
        "t2-superseded-missing",
        "t2-superseded-other",
        "t3-derived-added",
        "t4-module-provisional-false",
        "t5-module-source-other",
        "t6-module-superseded-none",
        "t7-module-derived-final",
        "t8-module-protected-table",
        "t8-module-revision",
        "t8-module-digest",
    ),
)
def test_each_provisional_predicate_mutation_is_exact(
    tmp_path: Path,
    mutation: str,
    expected: set[str],
) -> None:
    """T1〜T8 の各変異が対応する違反 ID だけを返すことを確認する。"""
    repository_root = _copy_pending_repository(tmp_path)
    _apply_provisional_mutation(repository_root, mutation)

    _assert_evaluation(repository_root, RuntimeContractState.PENDING, expected)


@pytest.mark.parametrize(
    "removed_index",
    (-1,),
    ids=("u1-addition-missing",),
)
def test_u1_rejects_one_missing_provisional_addition_exactly(
    tmp_path: Path,
    removed_index: int,
) -> None:
    """U1 が追加宣言1件の欠落だけを報告することを確認する。"""
    repository_root = _copy_pending_repository(tmp_path)
    staged = _provisional_asset_at_base(STAGED_PRODUCT_ASSET)
    additions = cast(list[dict[str, Any]], staged["provisional_contract_additions"])
    additions.pop(removed_index)
    _write_repository_json(repository_root, STAGED_PRODUCT_ASSET, staged)

    _assert_evaluation(
        repository_root,
        RuntimeContractState.PENDING,
        {"STAGED_PROTECTED_SET_MISMATCH"},
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("p1-provisional-true", {"PROVISIONAL_REMAINS"}),
        ("p2-superseded-null", {"SUPERSEDED_BY_REMAINS"}),
        ("p2-superseded-old", {"SUPERSEDED_BY_REMAINS"}),
        ("p3-derived-staged", {"DERIVED_FROM_MISMATCH"}),
        ("p3-derived-other", {"DERIVED_FROM_MISMATCH"}),
        ("p3-derived-missing", {"DERIVED_FROM_MISMATCH"}),
        ("p4-function-missing", {"DERIVED_FIELDS_STALE"}),
        ("p4-function-added", {"DERIVED_FIELDS_STALE"}),
        ("p4-provisional-functions", {"DERIVED_FIELDS_STALE"}),
        ("p4-attribute", {"DERIVED_FIELDS_STALE"}),
        ("p4-public-schema-only", {"DERIVED_FIELDS_STALE"}),
        ("p5-pending-switch", {"PENDING_SWITCH_REMAINS"}),
        ("p6-provisional-additions", {"PROVISIONAL_ADDITIONS_REMAIN"}),
        ("p7-module-provisional-true", {"GENERATED_MODULE_IS_PROVISIONAL"}),
        ("p8-module-superseded-old", {"GENERATED_MODULE_HAS_SUPERSEDED_BY"}),
        ("p9-module-source-final", {"GENERATED_MODULE_SOURCE_MISMATCH"}),
        ("p9-module-source-staged", {"GENERATED_MODULE_SOURCE_MISMATCH"}),
        (
            "p10-module-derived-staged",
            {"GENERATED_MODULE_DERIVED_FROM_MISMATCH"},
        ),
        (
            "p10-module-derived-none",
            {"GENERATED_MODULE_DERIVED_FROM_MISMATCH"},
        ),
        ("p11-module-protected-old", {"GENERATED_MODULE_STALE"}),
        ("p11-module-revision", {"GENERATED_MODULE_STALE"}),
        ("p11-module-digest", {"GENERATED_MODULE_STALE"}),
    ),
    ids=(
        "p1-provisional-true",
        "p2-superseded-null",
        "p2-superseded-old",
        "p3-derived-staged",
        "p3-derived-other",
        "p3-derived-missing",
        "p4-function-missing",
        "p4-function-added",
        "p4-provisional-functions",
        "p4-attribute",
        "p4-public-schema-only",
        "p5-pending-switch",
        "p6-provisional-additions",
        "p7-module-provisional-true",
        "p8-module-superseded-old",
        "p9-module-source-final",
        "p9-module-source-staged",
        "p10-module-derived-staged",
        "p10-module-derived-none",
        "p11-module-protected-old",
        "p11-module-revision",
        "p11-module-digest",
    ),
)
def test_each_product_predicate_mutation_is_exact(
    tmp_path: Path,
    mutation: str,
    expected: set[str],
) -> None:
    """P1〜P11 の各変異が対応する違反 ID だけを返すことを確認する。"""
    repository_root = _copy_product_repository(tmp_path)
    _apply_product_mutation(repository_root, mutation)

    _assert_evaluation(repository_root, RuntimeContractState.PRODUCT, expected)


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


def test_rederive_no_change_and_one_revision_from_base(tmp_path: Path) -> None:
    """再導出を繰り返しても比較元 +1 に止まり P4 が解消する。"""
    root = _git_repository_for_rederive(tmp_path)
    asset_before = (root / RUNTIME_CONTRACT_ASSET).read_bytes()
    module_before = (root / GENERATED_MODULE).read_bytes()
    assert main(["rederive", "--base", "HEAD"], repository_root=root) == 0
    assert (root / RUNTIME_CONTRACT_ASSET).read_bytes() == asset_before
    assert (root / GENERATED_MODULE).read_bytes() == module_before

    _add_test_function(root)
    assert check_repository(root) == {"DERIVED_FIELDS_STALE"}
    base_revision = _read_asset(root)["runtime_contract_revision"]
    assert main(["rederive", "--base", "HEAD"], repository_root=root) == 3
    updated = _read_asset(root)
    assert updated["runtime_contract_revision"] == base_revision + 1
    assert updated["baseline_control"]["identity"]["current_identifiers"] == [
        f"runtime_contract_revision:{base_revision + 1}"
    ]
    assert updated["source_digest"] == asset_digest(updated)
    assert updated["protected_objects"] != json.loads(asset_before)["protected_objects"]
    assert (root / GENERATED_MODULE).read_text(
        encoding="utf-8"
    ) == render_runtime_contract(updated)
    assert check_repository(root) == set()
    assert main(["rederive", "--base", "HEAD"], repository_root=root) == 0
    assert _read_asset(root)["runtime_contract_revision"] == base_revision + 1
    _write_repository_json(root, PRODUCT_ASSET, _read_repository_json(PRODUCT_ASSET))
    assert main(["rederive", "--base", "HEAD"], repository_root=root) == 3
    restored = _read_asset(root)
    assert restored["runtime_contract_revision"] == base_revision
    assert restored["baseline_control"]["identity"]["current_identifiers"] == [
        f"runtime_contract_revision:{base_revision}"
    ]


def test_rederive_rejects_revision_plus_two_and_nonancestor(tmp_path: Path) -> None:
    """改訂の飛び越しと HEAD の祖先でない比較元を拒否する。"""
    root = _git_repository_for_rederive(tmp_path)
    asset = _read_asset(root)
    asset["runtime_contract_revision"] += 2
    _write_asset(root, asset)
    assert main(["rederive", "--base", "HEAD"], repository_root=root) == 1
    _write_asset(root, _read_repository_json(RUNTIME_CONTRACT_ASSET))
    original_branch = subprocess.check_output(
        ["git", "-C", str(root), "branch", "--show-current"], text=True
    ).strip()
    subprocess.run(["git", "-C", str(root), "checkout", "-qb", "other"], check=True)
    (root / "marker.txt").write_text("other\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "marker.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "other",
        ],
        check=True,
    )
    other = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "-C", str(root), "checkout", "-q", original_branch], check=True
    )
    assert main(["rederive", "--base", other], repository_root=root) == 1


def test_rederive_rejects_provisional_base(tmp_path: Path) -> None:
    """比較元が製品状態でなければ再導出しない。"""
    root = _git_repository_for_rederive(tmp_path)
    asset = _read_asset(root)
    asset["provisional"] = True
    _write_asset(root, asset)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "provisional",
        ],
        check=True,
    )
    provisional_base = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    _write_asset(root, _read_repository_json(RUNTIME_CONTRACT_ASSET))
    assert main(["rederive", "--base", provisional_base], repository_root=root) == 1


def test_rederive_restores_both_files_on_postwrite_revision_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """書き込み後の改訂拘束が破れたら二つのファイルを戻す。"""
    root = _git_repository_for_rederive(tmp_path)
    _add_test_function(root)
    asset_path = root / RUNTIME_CONTRACT_ASSET
    module_path = root / GENERATED_MODULE
    original_asset = asset_path.read_bytes()
    original_module = module_path.read_bytes()
    atomic_write = generator._atomic_write
    calls = 0

    def corrupt_once(target: Path, content: str) -> None:
        nonlocal calls
        if target == asset_path and calls == 0:
            calls += 1
            value = json.loads(content)
            value["runtime_contract_revision"] += 1
            atomic_write(target, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            return
        atomic_write(target, content)

    monkeypatch.setattr(generator, "_atomic_write", corrupt_once)
    with pytest.raises(ValueError, match="書き込み後の revision"):
        rederive_repository(root, "HEAD")
    assert asset_path.read_bytes() == original_asset
    assert module_path.read_bytes() == original_module


def test_acceptance_template_passes_frozen_history_in_committed_copy(
    tmp_path: Path,
) -> None:
    """雛形を複製へ追記し、v2 と識別値移動の検査を通す。"""
    scripts_path = str(_REPOSITORY_ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    frozen_history = importlib.import_module("frozen_history")
    root = _git_repository_for_rederive(tmp_path, full_history=True)
    base_sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    base_snapshot_root = tmp_path / "base-snapshots"
    shutil.copytree(
        root / "contracts/tenant_boundary/history-snapshots", base_snapshot_root
    )
    _add_test_function(root)
    assert rederive_repository(root, base_sha)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "head",
        ],
        check=True,
    )
    head_sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    output = tmp_path / "acceptance.json"
    cli = [
        sys.executable,
        "-m",
        "pitchlog.authz.runtime_contract_acceptance",
        "--repository",
        str(root),
        "--base",
        base_sha,
        "--acceptance-id",
        "example/pitchlog#123",
        "--approved-by",
        "試験者",
        "--approved-on",
        "2026-10-05",
        "--reason",
        "製品資産の変更を受理するため。",
        "--movement-fact",
        "保護関数を一件追加した。",
        "--output",
        str(output),
    ]
    subprocess.run(cli, check=True)
    bundle = json.loads(output.read_text(encoding="utf-8"))
    record = bundle["record"]
    assert record["change"]["aspect"] == ["asset_snapshots", "declaration"]
    stdout_result = subprocess.run(cli[:-2], capture_output=True, text=True, check=True)
    assert json.loads(stdout_result.stdout) == bundle
    inside_output = [*cli]
    inside_output[-1] = str(root / "acceptance.json")
    inside_result = subprocess.run(
        inside_output, capture_output=True, text=True, check=False
    )
    assert inside_result.returncode == 1
    assert not (root / "acceptance.json").exists()
    rejected = [*cli]
    rejected[rejected.index("製品資産の変更を受理するため。")] = "PENDING"
    result = subprocess.run(rejected, capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "予約 marker" in result.stderr
    authority_path = root / bundle["authority_asset"]
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["baseline_control"]["history"].append(record)
    authority_path.write_text(
        json.dumps(authority, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    snapshot_root = root / "contracts/tenant_boundary/history-snapshots"
    for digest, content in bundle["snapshots_base64"].items():
        (snapshot_root / digest).write_bytes(base64.b64decode(content))
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "record",
        ],
        check=True,
    )
    asset_paths = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "contracts/tenant_boundary").glob("*.json")
    )
    base_assets = {
        path: json.loads(
            subprocess.check_output(
                ["git", "-C", str(root), "show", f"{base_sha}:{path}"]
            )
        )
        for path in asset_paths
    }
    head_assets = {
        path: json.loads((root / path).read_text(encoding="utf-8"))
        for path in asset_paths
    }
    base_implementations = {}
    head_implementations = {}
    for asset in base_assets.values():
        for path in asset["baseline_control"]["identity"]["frozen_projection"][
            "external_files"
        ]:
            base_implementations[path] = subprocess.check_output(
                ["git", "-C", str(root), "show", f"{base_sha}:{path}"]
            )
            head_implementations[path] = (root / path).read_bytes()
    context = frozen_history.EvaluationContext(
        frozen_history.EvaluationMode.PR_ACCEPTANCE,
        frozen_history.PullRequestEvent(
            "example/pitchlog", 123, "develop", base_sha, head_sha
        ),
    )
    frozen_history.validate_repository_histories(
        base_assets,
        head_assets,
        base_implementations=base_implementations,
        head_implementations=head_implementations,
        base_snapshot_root=base_snapshot_root,
        head_snapshot_root=snapshot_root,
        head_parents=(base_sha, head_sha),
        evaluation_context=context,
    )


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
