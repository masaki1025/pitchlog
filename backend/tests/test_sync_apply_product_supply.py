"""初球製品供給のexact差分・旧投影・DDL非実行を確認する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pitchlog.authz import product_catalog as cat
from pitchlog.authz import product_provisioning as prov
from pitchlog.authz.asset_spec import PRODUCT_SPEC, load_product_application_steps
from pitchlog.authz.first_ball_product import ADDITIONS, IDS, legacy_asset, validate

ROOT = Path(__file__).resolve().parents[2]


def asset():
    """検証用の実資産を読み、予期しない処理を閉じる。"""
    return json.loads((ROOT / "contracts/authz/product/ddl-elements.json").read_bytes())


ROWS = [(s, i) for s, rows in ADDITIONS.items() for i in range(len(rows))]


@pytest.mark.parametrize("section,index", ROWS)
@pytest.mark.parametrize("fault", ["missing", "mutated", "duplicate"])
def test_extension_rejects_every_missing_mutated_or_duplicate_row(
    section, index, fault
):
    """実認可資産の閉集合と失敗条件を検査する。"""
    value = asset()
    target = ADDITIONS[section][index]
    key = IDS[section]
    at = next(i for i, r in enumerate(value[section]) if r[key] == target[key])
    if fault == "missing":
        value[section].pop(at)
    elif fault == "duplicate":
        value[section].append(copy.deepcopy(value[section][at]))
    else:
        value[section][at]["unexpected"] = True
    with pytest.raises(ValueError):
        validate(value)


def test_legacy_projection_preserves_semantics_and_input():
    """実認可資産の閉集合と失敗条件を検査する。"""
    value = asset()
    assert validate(value)
    legacy = legacy_asset(value)
    assert not validate(legacy)
    assert legacy_asset(legacy) == legacy
    assert not any(r.get("schema_name") == "sync_fence" for r in legacy["tables"])
    assert value == asset()


@pytest.mark.parametrize(
    "fault", ["connect", "usage", "namespace", "invoker", "unknown-invoker", "bool-int"]
)
def test_profile_rejects_partial_privileges_namespace_and_mode(fault):
    """実認可資産の閉集合と失敗条件を検査する。"""
    value = asset()
    if fault == "connect":
        value["databases"][0]["acl_expectations"] = [
            r
            for r in value["databases"][0]["acl_expectations"]
            if r["grantee"] != "pitchlog_sync_binding_actor"
        ]
    elif fault == "usage":
        next(r for r in value["schemas"] if r["schema_id"] == "public")[
            "acl_expectations"
        ].pop()
    elif fault == "namespace":
        value["tables"][-1]["schema_name"] = "public"
    elif fault == "bool-int":
        value["roles"][-1]["bypass_rls"] = 0
    else:
        r = next(r for r in value["functions"] if r["function_kind"] == "invoker")
        if fault == "invoker":
            r["security_mode"] = "definer"
        else:
            r["function_id"] = "FUNCTION:sync_fence_api:unknown(uuid)"
    with pytest.raises(ValueError):
        validate(value)


def test_catalog_keeps_added_objects_and_actual_bodies():
    """実認可資産の閉集合と失敗条件を検査する。"""
    e = cat._load_product_expectations()
    assert {("sync_fence", "writer_bindings"), ("sync_fence", "writer_admissions")} <= {
        r[:2] for r in e.tables
    }
    rows = [
        r
        for r in cat._expected_lifecycle_function_details()
        if r[0] in {"sync_fence_api", "sync_right_api"}
    ]
    assert len(rows) == 12
    assert sum(r[4] is False for r in rows) == 2
    assert all(r[9] and r[8] == ("search_path=pg_catalog, pg_temp",) for r in rows)


def test_invoker_has_exact_helper_step_position():
    """実認可資産の閉集合と失敗条件を検査する。"""
    s = load_product_application_steps(ROOT, PRODUCT_SPEC)
    assert s.application_steps[2].element_groups == (
        "functions:rls_helper",
        "functions:definer",
        "functions:invoker",
    )


def test_full_apply_has_nine_definitions_and_four_guards_without_execution():
    """実認可資産の閉集合と失敗条件を検査する。"""
    _, s = prov._build_operation_statements(prov.ProductOperation.APPLY)
    sql = "\n".join(r.sql for r in s)
    assert sql.count("CREATE FUNCTION sync_fence_api.") == 7
    assert sql.count("CREATE FUNCTION sync_right_api.") == 5
    assert sql.count("CREATE TRIGGER sync_writer_") == 4
    assert sql.count("CREATE TRIGGER trg_first_ball_") == 2


def test_pre_rule_defers_unavailable_dependencies():
    """実認可資産の閉集合と失敗条件を検査する。"""
    _, s = prov._build_operation_statements(prov.ProductOperation.APPLY_PRE_RULE)
    sql = "\n".join(r.sql for r in s)
    assert "CREATE FUNCTION sync_fence_api." not in sql
    assert "CREATE FUNCTION sync_right_api." not in sql
    assert "ALTER TABLE sync_fence." not in sql
    assert "CREATE ROLE pitchlog_sync_binding_actor" in sql


def test_unapply_rejects_before_generation_or_execution(monkeypatch):
    """実認可資産の閉集合と失敗条件を検査する。"""

    def forbidden(*a, **kw):
        """検証用の実資産を読み、予期しない処理を閉じる。"""
        raise AssertionError("DDL生成へ進めない")

    monkeypatch.setattr(prov, "generate_authz_ddl", forbidden)
    with pytest.raises(prov.ProductProvisioningError, match="退役は未提供"):
        prov._build_operation_statements(prov.ProductOperation.UNAPPLY)


def test_reapply_is_closed_to_exact_nine_and_preserves_frozen_first_apply():
    """新9は未存在分岐だけで元全文を実行し既存時は検査だけを行う。"""
    from pitchlog.authz.first_ball_product import application_function_sql, body

    for row in ADDITIONS["functions"]:
        original = body("function", row["function_id"])
        assert original is not None
        wrapped = application_function_sql(row["function_id"], original)
        assert wrapped is not None
        assert wrapped.startswith("DO $first_ball_reapply$")
        assert wrapped.count("EXECUTE ") == original.count("EXECUTE ") + 1
        literal = "'" + original.replace("'", "''") + "'"
        assert (
            f"IF existing IS NULL THEN\n        EXECUTE {literal};\n        RETURN;"
            in wrapped
        )
        existing_branch = wrapped.split("        RETURN;\n    END IF;", 1)[1]
        assert "CREATE FUNCTION " not in existing_branch
        assert "CREATE TRIGGER " not in existing_branch
        assert "ALTER FUNCTION " not in existing_branch
        assert "GRANT " not in existing_branch
        assert "REVOKE " not in existing_branch
        assert "DROP " not in existing_branch
        for required in (
            "p.prokind='f'",
            "p.provolatile='v'",
            "p.proparallel='u'",
            "NOT p.proisstrict",
            "NOT p.proleakproof",
            "p.provariadic=0",
            "p.pronargdefaults=0",
            "p.proargmodes IS NOT DISTINCT FROM",
            "p.procost=100",
            "p.prorows=",
            "p.prosupport=0",
            "p.probin IS NULL",
            "p.prosqlbody IS NULL",
            "p.protrftypes IS NULL",
            "p.proargnames IS NOT DISTINCT FROM",
            "p.prosecdef=",
            "p.proretset=",
            "pg_get_function_result(p.oid)",
            "p.proconfig=ARRAY['search_path=pg_catalog, pg_temp']::pg_catalog.text[]",
            "pg_catalog.btrim(p.prosrc, E' \\t\\r\\n')=",
            "p.proowner",
            "a.privilege_type,a.is_grantable",
            "a.grantee<>p.proowner",
            "first ball function definition collision",
            "first ball function privilege collision",
        ):
            assert required in existing_branch
        assert f"o.rolname='{row['owner_role_id']}'" in existing_branch
        with pytest.raises(ValueError, match="凍結値"):
            application_function_sql(row["function_id"], original + "-- changed")
    assert (
        application_function_sql("FUNCTION:other:unknown()", "CREATE FUNCTION x")
        is None
    )


def test_reapply_guard_retains_exact_four_triggers_and_refuses_collisions():
    """guardの対象/事象/行単位/関数/有効状態/余剰を検査し修復しない。"""
    from pitchlog.authz.first_ball_product import application_function_sql, body

    key = "FUNCTION:sync_fence_api:guard_writer_records()"
    original = body("function", key)
    assert original is not None
    wrapped = application_function_sql(key, original)
    assert wrapped is not None
    check = wrapped.split("        RETURN;\n    END IF;", 1)[1]
    for name, table, tgtype in (
        ("sync_writer_binding_immutable", "writer_bindings", 27),
        ("sync_writer_binding_no_truncate", "writer_bindings", 34),
        ("sync_writer_admission_immutable", "writer_admissions", 27),
        ("sync_writer_admission_no_truncate", "writer_admissions", 34),
    ):
        assert (
            f"t.tgname='{name}' AND t.tgrelid='sync_fence.{table}'"
            f"::pg_catalog.regclass AND t.tgtype={tgtype}"
        ) in check
    for required in (
        "<> 4",
        "NOT t.tgisinternal",
        "t.tgfoid=existing",
        "t.tgenabled='O'",
        "NOT t.tgdeferrable",
        "NOT t.tginitdeferred",
        "t.tgconstraint=0",
        "t.tgnargs=0",
        "t.tgattr::text=''",
        "t.tgqual IS NULL",
        "t.tgargs=''::pg_catalog.bytea",
        "t.tgoldtable IS NULL",
        "t.tgnewtable IS NULL",
        "first ball trigger definition collision",
    ):
        assert required in check


def test_reapply_keeps_all_other_generated_statements_exact():
    """正式520文のうち関数12以外508文を全byteへ束縛する。"""
    import hashlib

    _, rows = prov._build_operation_statements(prov.ProductOperation.APPLY)
    wrappers = [r for r in rows if r.sql.startswith("DO $first_ball_reapply$")]
    keep = [
        {"sequence": r.sequence, "sql": r.sql}
        for r in rows
        if not r.sql.startswith("DO $first_ball_reapply$")
    ]
    assert len(rows) == 520 and len(wrappers) == 12 and len(keep) == 508
    digest = hashlib.sha256(
        json.dumps(keep, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == "4fd030d3ac2118c8a11624860dc83dcefdf23a2123ebfe7903180b49b505e527"


def test_reapply_is_per_function_and_normalizes_only_new_table_spacing():
    """部分既配置でも一関数ずつ照合し未知の名前/型を補わない。"""
    from pitchlog.authz.first_ball_product import (
        _function_argument_names,
        _pg_result_type,
        application_function_sql,
        body,
        function_details,
    )

    assert _pg_result_type("TABLE (x boolean)") == "TABLE(x boolean)"
    assert _pg_result_type("void") == "void"
    for row in function_details():
        assert isinstance(row[6], str)
        assert row[6] == "void" or row[6] == "trigger" or row[6].startswith("TABLE(")
    key = "FUNCTION:sync_fence_api:read_writer_identity(uuid)"
    original = body("function", key)
    assert original is not None
    wrapped = application_function_sql(key, original)
    assert wrapped is not None
    assert "guard_writer_records()" not in wrapped
    assert "assert_writer_binding(" not in wrapped
    names, table = _function_argument_names(original)
    assert table is True
    assert names == (
        "p_tenant_id",
        "system_identifier",
        "database_oid",
        "postmaster_started_at",
        "backend_pid",
        "backend_start",
        "transaction_id",
    )
    with pytest.raises(ValueError):
        _function_argument_names("CREATE PROCEDURE x.y() LANGUAGE sql")


def test_device_state_formal_declaration_uses_shared_pipeline():
    """新read1だけを固定owner/ACLと既canonical描画へ追加する。"""
    from pitchlog.authz.first_ball_product import body, declaration
    from pitchlog.authz.sync_right_sql import render_device_state_read_create_sql

    key = "FUNCTION:sync_right_api:read_device_state(uuid, uuid)"
    row = declaration("functions", key)
    assert row is not None
    assert row == {
        "function_id": key,
        "schema_name": "sync_right_api",
        "function_name": "read_device_state",
        "identity_args": "uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_sync_right_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(device_active boolean)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        ],
    }
    original = body("function", key)
    assert original is not None
    assert (
        render_device_state_read_create_sql().replace(
            "CREATE OR REPLACE FUNCTION", "CREATE FUNCTION", 1
        )
        in original
    )
    assert "OWNER TO pitchlog_sync_right_fn_owner" in original
    assert "FROM PUBLIC" in original and "TO pitchlog_app" in original


def test_device_state_overload_guard_only_extends_new_wrapper():
    """同名別署名だけを拒否し、真の欠落は既CREATE分岐へ進める。"""
    from pitchlog.authz.first_ball_product import application_function_sql, body

    for row in ADDITIONS["functions"]:
        canonical = body("function", row["function_id"])
        assert canonical is not None
        wrapped = application_function_sql(row["function_id"], canonical)
        assert wrapped is not None
        has_guard = "other.oid IS DISTINCT FROM existing" in wrapped
        assert has_guard is (row["function_name"] == "read_device_state")
        if has_guard:
            assert wrapped.index("other.oid IS DISTINCT FROM existing") < wrapped.index(
                "IF existing IS NULL THEN"
            )
            assert "AND other.proname='read_device_state'" in wrapped
