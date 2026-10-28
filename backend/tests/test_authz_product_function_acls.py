"""製品DDLのmigrationトリガ関数ACLを検査する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_authz_runtime_contract_repository import product_spec_for_repository

from pitchlog.authz.ddl import generate_authz_ddl
from pitchlog.authz.product_function_acl import (
    build_product_function_acl_declaration,
    generate_product_function_acl_sql,
    product_function_id,
)
from pitchlog.authz.runtime_contract import PROTECTED_FUNCTIONS
from pitchlog.authz.runtime_contract_state import (
    RuntimeContractState,
    evaluate_repository,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_SPEC = product_spec_for_repository(_REPOSITORY_ROOT)
_CATALOG_CHECKER = _REPOSITORY_ROOT / "scripts/check_authz_catalog.py"
_MIGRATION_VERSIONS = Path("backend/migrations/versions")


def test_product_function_argument_shapes_come_from_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新しい引数形は複製した製品資産の宣言で許可する。"""
    from pitchlog.authz import product_function_acl

    asset = json.loads(
        (_REPOSITORY_ROOT / "contracts/authz/product/ddl-elements.json").read_text(
            encoding="utf-8"
        )
    )
    asset["functions"].append({"identity_args": "text"})
    path = tmp_path / "contracts/authz/product/ddl-elements.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(asset), encoding="utf-8")
    monkeypatch.setattr(product_function_acl, "_REPOSITORY_ROOT", tmp_path)

    assert (
        product_function_id("public", "sample", "text")
        == "FUNCTION:public:sample(text)"
    )
    with pytest.raises(ValueError, match="資産宣言"):
        product_function_id("public", "sample", "integer")


_EXPECTED_GAPS = {
    (
        "public",
        "prevent_invalidation_intents_target_update",
        "",
    ): "0015_invalidation_intents",
    (
        "public",
        "prevent_migration_quarantine_mutation",
        "",
    ): "0016_migration_quarantine",
    (
        "public",
        "prevent_migrated_final_lineups_source_update",
        "",
    ): "0017_migrated_final_lineups",
    (
        "public",
        "prevent_players_identity_update",
        "",
    ): "0024_players_identity_trigger",
}
_RUNTIME_CONTRACT_STATE, _RUNTIME_CONTRACT_VIOLATIONS = evaluate_repository(
    _REPOSITORY_ROOT
)


def _load_catalog_checker() -> Any:
    """静的検査を独立したモジュール名で読み込む。"""
    module_spec = importlib.util.spec_from_file_location(
        "check_authz_catalog_product_function_acls_under_test",
        _CATALOG_CHECKER,
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


_catalog_checker = _load_catalog_checker()


def _read_json_object(path: Path) -> dict[str, Any]:
    """JSON objectを読み、試験入力の形を確定する。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _product_asset() -> dict[str, Any]:
    """製品DDL資産を読む。"""
    return _read_json_object(_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path)


def _validate_product_asset(
    asset: dict[str, Any],
    root: Path = _REPOSITORY_ROOT,
) -> dict[str, object]:
    """製品DDL資産を静的検査へ渡す。"""
    return _catalog_checker.validate_ddl_elements(asset, root, PRODUCT_SPEC)


def _copy_static_inputs(root: Path) -> None:
    """関数ACL検査に必要な資産とmigrationを一時領域へ複製する。"""
    paths = (
        Path("contracts/db/schema-manifest.json"),
        Path("contracts/authz/product/table-classification.json"),
        Path("contracts/authz/product/exposure-facts.json"),
        PRODUCT_SPEC.ddl_elements_path,
        PRODUCT_SPEC.body_manifest_path,
        Path("contracts/tenant_boundary/runtime-authz-contract.json"),
        Path("backend/src/pitchlog/authz/runtime_contract.py"),
        Path("backend/src/pitchlog/recording_rights/rg1_lifecycle.sql"),
        Path("backend/src/pitchlog/durable_rights_ledger/business_identity.sql"),
    )
    for relative_path in paths:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPOSITORY_ROOT / relative_path, destination)
    shutil.copytree(
        _REPOSITORY_ROOT / PRODUCT_SPEC.body_directory,
        root / PRODUCT_SPEC.body_directory,
        dirs_exist_ok=True,
    )
    shutil.copytree(
        _REPOSITORY_ROOT / _MIGRATION_VERSIONS,
        root / _MIGRATION_VERSIONS,
    )


def _function_rows(asset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """関数宣言を関数IDで引ける形へ変換する。"""
    rows = asset["functions"]
    assert isinstance(rows, list)
    result = {str(row["function_id"]): row for row in rows}
    assert len(result) == len(rows)
    return result


def _mutate_add_unknown_function(asset: dict[str, Any]) -> None:
    """Migration母集合にない関数を宣言へ足す。"""
    asset["functions"].append(
        build_product_function_acl_declaration(
            "public",
            "not_created_by_migration",
            "",
        )
    )


def _mutate_remove_function(asset: dict[str, Any]) -> None:
    """Migration関数の宣言を1件消す。"""
    index = next(
        index
        for index, row in enumerate(asset["functions"])
        if row["function_kind"] == "migration_trigger"
    )
    asset["functions"].pop(index)


def test_unlisted_migration_regular_function_is_red(tmp_path: Path) -> None:
    """複製した migration に通常関数を足すと種別込みの照合が失敗する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)
    migration = next((root / _MIGRATION_VERSIONS).glob("*.py"))
    migration.write_text(
        migration.read_text(encoding="utf-8")
        + "\n_STEP4_ORDINARY = '''\n"
        + "CREATE FUNCTION public.step4_unlisted_ordinary()\n"
        + "RETURNS text\nLANGUAGE sql\nAS $$ SELECT 'x'::text $$;\n"
        + "'''\n",
        encoding="utf-8",
    )
    kinds: dict[tuple[str, str, str], str] = {}
    _catalog_checker._product_migration_functions(root, kinds=kinds)
    assert kinds[("public", "step4_unlisted_ordinary", "")] == "migration_function"
    with pytest.raises(
        _catalog_checker.CatalogError, match="種別込みでexact-set不一致"
    ):
        _validate_product_asset(asset, root)


def test_migration_regular_function_declares_revoked_execute() -> None:
    """通常関数もトリガ関数と同じ関数 ACL の閉じた形を持つ。"""
    declaration = build_product_function_acl_declaration(
        "public", "step4_ordinary", "", function_kind="migration_function"
    )
    assert declaration["function_kind"] == "migration_function"
    assert declaration["owner_role_id"] == "pitchlog_owner"
    assert declaration["acl_expectations"] == []
    assert declaration["revoked_acl_expectations"] == [
        {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
        {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
    ]


def _mutate_remove_gap(asset: dict[str, Any]) -> None:
    """暫定契約の宣言済み追加分を1件消す。"""
    index = next(
        index
        for index, row in enumerate(asset["provisional_contract_additions"])
        if row["reason"] == "provisional_contract_gap"
    )
    asset["provisional_contract_additions"].pop(index)


def _mutate_add_reasonless_gap(asset: dict[str, Any]) -> None:
    """理由を持たない関数を暫定契約の追加分へ足す。"""
    schema_name, function_name, identity_args = PROTECTED_FUNCTIONS[0]
    asset["provisional_contract_additions"].append(
        {
            "addition_id": product_function_id(
                schema_name,
                function_name,
                identity_args,
            ),
            "object_kind": "function",
            "schema_name": schema_name,
            "object_name": function_name,
            "identity_args": identity_args,
            "detail": "理由コードがない不正な追加分",
            "migration_revision": "0000_unknown",
        }
    )


def _mutate_restore_provisional_additions(asset: dict[str, Any]) -> None:
    """製品状態へ廃止済みの暫定追加欄を戻す。"""
    asset["provisional_contract_additions"] = []


_DECLARATION_MUTATIONS = (
    pytest.param(_mutate_add_unknown_function, id="unknown-function"),
    pytest.param(_mutate_remove_function, id="function-removed"),
    *(
        (
            pytest.param(_mutate_remove_gap, id="gap-removed"),
            pytest.param(_mutate_add_reasonless_gap, id="reasonless-gap"),
        )
        if _RUNTIME_CONTRACT_STATE is RuntimeContractState.PENDING
        else (
            pytest.param(
                _mutate_restore_provisional_additions,
                id="provisional-additions-restored",
            ),
        )
    ),
)


def test_migration_function_acls_and_runtime_contract_match_exactly() -> None:
    """Migration 由来の関数と状態別ランタイム契約を完全照合する。"""
    asset = _product_asset()
    _validate_product_asset(asset)

    migration_kinds: dict[tuple[str, str, str], str] = {}
    migration_origins = _catalog_checker._product_migration_functions(
        _REPOSITORY_ROOT, kinds=migration_kinds
    )
    migration_functions = set(migration_origins)
    protected_functions = {
        (str(schema), str(name), str(identity_args))
        for schema, name, identity_args in PROTECTED_FUNCTIONS
    }
    declared_functions = {
        (
            str(row["schema_name"]),
            str(row["function_name"]),
            str(row["identity_args"]),
        )
        for row in asset["functions"]
    }
    assert _RUNTIME_CONTRACT_VIOLATIONS == set()
    declared_migration_functions = {
        (str(row["schema_name"]), str(row["function_name"]), str(row["identity_args"]))
        for row in asset["functions"]
        if row["function_kind"] in {"migration_trigger", "migration_function"}
    }
    assert migration_functions == declared_migration_functions
    if _RUNTIME_CONTRACT_STATE is RuntimeContractState.PENDING:
        assert len(protected_functions) == len(migration_functions) - len(
            _EXPECTED_GAPS
        )
        assert migration_functions - protected_functions == set(_EXPECTED_GAPS)
        assert protected_functions <= migration_functions
        for physical_id, revision in _EXPECTED_GAPS.items():
            assert revision in migration_origins[physical_id]
    else:
        assert _RUNTIME_CONTRACT_STATE is RuntimeContractState.PRODUCT
        assert len(protected_functions) == len(declared_functions)
        assert protected_functions == declared_functions
        assert migration_functions < protected_functions
        assert "provisional_contract_additions" not in asset

    functions = {
        function_id: row
        for function_id, row in _function_rows(asset).items()
        if row["function_kind"] == "migration_trigger"
    }
    expected_ids = {
        product_function_id(schema_name, function_name, identity_args)
        for schema_name, function_name, identity_args in migration_functions
        if migration_kinds[(schema_name, function_name, identity_args)]
        == "migration_trigger"
    }
    assert set(functions) == expected_ids
    for function_id, row in functions.items():
        assert row["owner_role_id"] == "pitchlog_owner"
        assert row["acl_expectations"] == []
        # 初期権の内部triggerだけはactor/ownerの直接EXECUTEも明示剥奪する。
        revoked_grantees = ("PUBLIC", "pitchlog_app")
        if function_id == "FUNCTION:public:protect_initial_right_storage()":
            revoked_grantees += ("pitchlog_initial_actor", "pitchlog_initial_fn_owner")
        assert row["revoked_acl_expectations"] == [
            {"grantee": grantee, "privilege": "EXECUTE", "grantable": False}
            for grantee in revoked_grantees
        ]
        assert function_id == product_function_id(
            str(row["schema_name"]),
            str(row["function_name"]),
            str(row["identity_args"]),
        )

    if _RUNTIME_CONTRACT_STATE is RuntimeContractState.PENDING:
        additions = [
            row
            for row in asset["provisional_contract_additions"]
            if row["reason"] == "provisional_contract_gap"
        ]
        assert isinstance(additions, list) and len(additions) == 4
        assert {
            (
                str(row["schema_name"]),
                str(row["object_name"]),
                str(row["identity_args"]),
            ): str(row["migration_revision"])
            for row in additions
        } == _EXPECTED_GAPS
        assert all(row["reason"] == "provisional_contract_gap" for row in additions)

    statements = generate_authz_ddl(_REPOSITORY_ROOT, PRODUCT_SPEC)
    function_sql = {
        statement.element_id: statement.sql
        for statement in statements
        if statement.element_type == "function" and statement.element_id in expected_ids
    }
    assert set(function_sql) == expected_ids
    for row in functions.values():
        function_id = str(row["function_id"])
        assert function_sql[function_id] == generate_product_function_acl_sql(
            str(row["schema_name"]),
            str(row["function_name"]),
            str(row["identity_args"]),
        )


@pytest.mark.parametrize(
    "mutate",
    _DECLARATION_MUTATIONS,
)
def test_function_acl_declaration_mutations_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """正常資産を確認後、関数または追加分の宣言変異を拒否する。"""
    asset = _product_asset()
    _validate_product_asset(asset)
    mutated = copy.deepcopy(asset)
    mutate(mutated)

    with pytest.raises(_catalog_checker.CatalogError):
        _validate_product_asset(mutated)


def test_removing_one_public_execute_revocation_is_rejected(tmp_path: Path) -> None:
    """正常bodyを確認後、PUBLIC EXECUTE剥奪の欠落を拒否する。"""
    root = tmp_path / "repository"
    _copy_static_inputs(root)
    asset = _product_asset()
    _validate_product_asset(asset, root)

    physical_id = sorted(_catalog_checker._product_migration_functions(root))[0]
    schema_name, function_name, identity_args = physical_id
    function_id = product_function_id(schema_name, function_name, identity_args)
    body_path = root / PRODUCT_SPEC.body_directory / "functions" / f"{function_id}.sql"
    text = body_path.read_text(encoding="utf-8")
    target = (
        f"REVOKE EXECUTE ON FUNCTION {schema_name}.{function_name}({identity_args}) "
        "FROM PUBLIC;\n"
    )
    assert text.count(target) == 1
    body_path.write_text(text.replace(target, "", 1), encoding="utf-8")

    with pytest.raises(_catalog_checker.CatalogError, match="剥奪が生成結果と不一致"):
        _validate_product_asset(asset, root)


@pytest.mark.parametrize(
    "grantee",
    (
        "pitchlog_rg1_control_owner",
        "pitchlog_ledger_identity_owner",
    ),
)
def test_builtin_additional_execute_has_exact_signature_and_preserves_public(
    grantee: str,
) -> None:
    """追加grantは引数空builtin1件だけ、PUBLICの既権限を変更しない。"""
    from pitchlog.authz.product_function_acl import (
        build_builtin_execute_declaration,
        generate_builtin_execute_sql,
    )

    declaration = build_builtin_execute_declaration(grantee)
    assert declaration == {
        "acl_id": f"ACL:pg_catalog:pg_control_system():{grantee}",
        "object_kind": "builtin_function",
        "object_schema": "pg_catalog",
        "object_id": "pg_control_system",
        "profile": "additional_builtin_execute",
        "grantee_role_id": grantee,
        "privilege_ids": ["EXECUTE"],
        "grant_option": False,
    }
    sql = generate_builtin_execute_sql(declaration)
    assert (
        f"GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {grantee};" in sql
    )
    assert "REVOKE" not in sql and "PUBLIC" not in sql and "OWNER" not in sql


@pytest.mark.parametrize(
    "field,value",
    (
        ("object_schema", "public"),
        ("object_id", "pg_control_system(uuid)"),
        ("object_id", "pg_control_checkpoint"),
        ("grantee_role_id", "pitchlog_app"),
        ("grantee_role_id", "pitchlog_ledger_identity_probe"),
        ("grantee_role_id", "PUBLIC"),
        ("privilege_ids", ["EXECUTE", "SELECT"]),
        ("grant_option", True),
        ("grant_option", 0),
        ("profile", "general_function"),
    ),
)
def test_builtin_execute_rejects_every_unapproved_signature_and_privilege(
    field: str,
    value: object,
) -> None:
    """未知署名/主体/権限/真偽値の代用を有限分岐で拒否する。"""
    from pitchlog.authz.product_function_acl import (
        build_builtin_execute_declaration,
        generate_builtin_execute_sql,
    )

    declaration = build_builtin_execute_declaration("pitchlog_rg1_control_owner")
    declaration[field] = value
    with pytest.raises(ValueError):
        generate_builtin_execute_sql(declaration)


def test_builtin_unapply_only_revokes_its_explicit_grant() -> None:
    """Builtin DROP/OWNER変更/PUBLIC撤去を伴わない逆操作を照合する。"""
    from pathlib import PurePosixPath

    from pitchlog.authz import product_provisioning
    from pitchlog.authz.ddl import DDLStatement
    from pitchlog.authz.product_function_acl import build_builtin_execute_declaration

    declaration = build_builtin_execute_declaration("pitchlog_ledger_identity_owner")
    statement = DDLStatement(
        "acl_expectation",
        str(declaration["acl_id"]),
        PurePosixPath("unused.sql"),
        "unused",
    )
    element = product_provisioning._ProductElement(
        "acl_expectation",
        str(declaration["acl_id"]),
        declaration,
    )
    sql = product_provisioning._unapplication_sql(statement, element, (), ())
    assert sql == (
        "REVOKE EXECUTE ON FUNCTION pg_catalog.pg_control_system() "
        'FROM "pitchlog_ledger_identity_owner";'
    )


def test_lifecycle_eight_functions_keep_source_body_and_exact_subjects() -> None:
    """rg1_control8/observer1の属性・実SQL本文をコピー計算なしに照合する。"""
    from pitchlog.authz.product_function_acl import (
        build_lifecycle_function_declarations,
        generate_lifecycle_function_sql,
    )

    expected = {
        "try_controller_lease": ("boolean", ("pitchlog_rg1_control_actor",)),
        "release_controller_lease": ("boolean", ("pitchlog_rg1_control_actor",)),
        "close_gate": ("boolean", ("pitchlog_rg1_control_actor",)),
        "open_fresh_gate": ("boolean", ("pitchlog_rg1_control_actor",)),
        "controller_lease_alive": (
            "boolean",
            (
                "pitchlog_rg1_control_actor",
                "pitchlog_rg1_fn_owner",
            ),
        ),
        "read_closed_gate": ("jsonb", ("pitchlog_rg1_control_actor",)),
        "scope_binding": ("text", ("pitchlog_app", "pitchlog_initial_actor")),
        "bind_initial_fresh_epoch": ("boolean", ("pitchlog_rg1_control_actor",)),
        "identity": ("jsonb", ("pitchlog_ledger_identity_probe",)),
    }
    rows = build_lifecycle_function_declarations()
    assert len(rows) == 9
    for function_id, row in rows.items():
        name = str(row["function_name"])
        returns, grantees = expected[name]
        assert row["returns"] == returns
        assert row["acl_expectations"] == [
            {"grantee": role, "privilege": "EXECUTE", "grantable": False}
            for role in grantees
        ]
        assert row["search_path"] == ["pg_catalog", "pg_temp"]
        assert row["security_mode"] == "definer"
        body = generate_lifecycle_function_sql(function_id, _REPOSITORY_ROOT)
        assert f"-- ELEMENT-ID: {function_id}" in body
        source_path = (
            "backend/src/pitchlog/durable_rights_ledger/business_identity.sql"
            if name == "identity"
            else "backend/src/pitchlog/recording_rights/rg1_lifecycle.sql"
        )
        source = (_REPOSITORY_ROOT / source_path).read_text()
        start = body.index("CREATE ")
        delimiter = "$$;" if name == "identity" else "$function$;"
        end = body.index(delimiter, start) + len(delimiter)
        definition = body[start:end]
        if name in {"identity", "bind_initial_fresh_epoch"}:
            # 再適用header2だけの正規化を許し、引数/戻り値/AS本文は全byte照合する。
            assert definition.startswith("CREATE OR REPLACE FUNCTION ")
            original_definition = definition.replace(
                "CREATE OR REPLACE FUNCTION ", "CREATE FUNCTION ", 1
            )
            assert original_definition in source
        else:
            assert definition in source


def test_device_state_read_has_exact_formal_owner_and_acl():
    """read追加を既ACL producerへ通し、他主体へのEXECUTEを許さない。"""
    from pitchlog.authz.first_ball_product import ADDITIONS

    rows = [
        r for r in ADDITIONS["functions"] if r["function_name"] == "read_device_state"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
    assert row["acl_expectations"] == [
        {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
    ]
    assert row["revoked_acl_expectations"] == [
        {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
    ]
    value = json.loads(
        (_REPOSITORY_ROOT / "contracts/authz/product/ddl-elements.json").read_text()
    )
    assert [
        r for r in value["functions"] if r["function_id"] == row["function_id"]
    ] == [row]
    mutated = copy.deepcopy(value)
    target = next(
        r for r in mutated["functions"] if r["function_id"] == row["function_id"]
    )
    target["acl_expectations"].append(
        {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
    )
    from pitchlog.authz.first_ball_product import validate

    with pytest.raises(ValueError):
        validate(mutated)
