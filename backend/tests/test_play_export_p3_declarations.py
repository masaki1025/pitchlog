"""root向けP3 CSV宣言のowner/ACL/RLS/監査guardを有限に照合する。"""

import json
from pathlib import Path

import pytest

from pitchlog.authz import play_export_p3_product as product


def test_five_exact_functions_keep_raw_source_owner_and_finite_execute():
    """通常4関数app EXECUTEと監査1関数非公開を混同しない。"""
    sections, bodies = product.candidate_declarations()
    assert {key: len(value) for key, value in sections.items()} == {
        "tables": 1,
        "functions": 5,
        "policies": 3,
        "acl_expectations": 0,
        "column_acl_expectations": 27,
    }
    assert len(bodies) == 36
    sources = {name: sql for name, sql, _, _ in product._function_candidates()}
    assert set(sources) == {
        "read_writer_p3_play_export_prior",
        "read_writer_p3_play_export_page",
        "save_writer_p3_play_export_snapshot",
        "read_play_export_p3_snapshots",
        "protect_play_export_p3_snapshots",
    }
    for row in sections["functions"]:
        body = bodies["function|" + row["function_id"]]
        assert body.startswith(sources[row["function_name"]])
        assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["security_mode"] == "definer" and row["language"] == "plpgsql"
        assert row["search_path"] == ["pg_catalog", "pg_temp"]
        guard = row["function_name"] == "protect_play_export_p3_snapshots"
        assert row["acl_expectations"] == (
            []
            if guard
            else [
                {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
            ]
        )
        assert all(
            x["grantee"] in product._FUNCTION_ROLES
            and x["privilege"] == "EXECUTE"
            and not x["grantable"]
            for x in row["revoked_acl_expectations"]
        )
        assert any(x["grantee"] == "PUBLIC" for x in row["revoked_acl_expectations"])
        assert body.count("GRANT EXECUTE ON FUNCTION") == (0 if guard else 1)
        assert "OWNER TO pitchlog_sync_right_fn_owner;" in body
        assert "FROM PUBLIC,pitchlog_app,pitchlog_initial_actor," in body
        assert "GRANT EXECUTE" not in body or body.rstrip().endswith("TO pitchlog_app;")


def test_snapshot_and_existing_dependencies_grant_columns_only():
    """17新列・旧INSERT9保持・表示名1だけを追加し、xmin/table DMLを足さない。"""
    sections, bodies = product.candidate_declarations()
    assert sections["acl_expectations"] == []
    indexed = {
        (r["object_id"], r["column_id"]): r for r in sections["column_acl_expectations"]
    }
    columns = [name for name, _ in product._COLUMNS]
    for name in columns:
        row = indexed["play_export_p3_snapshots", name]
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["privilege_ids"] == (
            ["SELECT"] if name == "captured_at" else ["SELECT", "INSERT"]
        )
        assert not row["grant_option"]
    normal = [r for r in indexed.values() if r["object_id"] == "play_export_snapshots"]
    assert len(normal) == 9
    assert all(r["privilege_ids"] == ["SELECT", "INSERT"] for r in normal)
    assert indexed["admin_vocabularies", "display_name"]["privilege_ids"] == ["SELECT"]
    assert all(r["column_id"] != "xmin" for r in indexed.values())
    assert "ENABLE ROW LEVEL SECURITY" in bodies["table|play_export_p3_snapshots"]
    assert "FORCE ROW LEVEL SECURITY" in bodies["table|play_export_p3_snapshots"]
    assert "REVOKE ALL ON TABLE" in bodies["table|play_export_p3_snapshots"]
    assert "GRANT " not in bodies["table|play_export_p3_snapshots"]
    # 既key/category/disabledの原典SELECTは再描画/削除しない。
    asset = json.loads(
        (
            Path(__file__).parents[2] / "contracts/authz/product/ddl-elements.json"
        ).read_bytes()
    )
    for name in ("key", "category", "disabled"):
        identity = (
            f"COLUMN-ACL:public:admin_vocabularies:{name}:pitchlog_sync_right_fn_owner"
        )
        row = next(
            r
            for r in asset["column_acl_expectations"]
            if r["expectation_id"] == identity
        )
        assert row["privilege_ids"] == ["SELECT"] and not row["grant_option"]
        assert "column_acl_expectation|" + identity not in bodies


def test_new_and_old_snapshot_policies_are_only_tenant_owner_read_insert():
    """旧app SELECT/owner INSERTを消さず、owner SELECTを別policyで追加する。"""
    sections, _ = product.candidate_declarations()
    assert {
        (r["table_id"], r["policy_name"], r["command"]) for r in sections["policies"]
    } == {
        ("play_export_p3_snapshots", "play_export_p3_snapshots_select", "SELECT"),
        ("play_export_p3_snapshots", "play_export_p3_snapshots_insert", "INSERT"),
        ("play_export_snapshots", "play_export_snapshots_p3_select", "SELECT"),
    }
    for row in sections["policies"]:
        assert row["role_ids"] == ["pitchlog_sync_right_fn_owner"]
        assert row["policy_mode"] == "permissive"
        if row["command"] == "SELECT":
            assert row["using_expression"] == product._PREDICATE
            assert row["with_check_expression"] is None
        else:
            assert row["with_check_expression"] == product._PREDICATE
            assert row["using_expression"] is None


def test_guard_is_unconditional_and_all_update_delete_truncate_are_protected():
    """列限定UPDATE/条件付きguard/無権限に頼るだけの監査保護にしない。"""
    sql = product.candidate_guard_body()
    assert "RAISE EXCEPTION" in sql and "ERRCODE='42501'" in sql
    assert "IF " not in sql and "RETURN " not in sql
    trigger = product.guard_trigger_sql()
    assert trigger.count("CREATE TRIGGER ") == 2
    assert "BEFORE UPDATE OR DELETE" in trigger and "FOR EACH ROW" in trigger
    assert "BEFORE TRUNCATE" in trigger and "FOR EACH STATEMENT" in trigger
    assert "UPDATE OF" not in trigger and "WHEN " not in trigger
    assert trigger.count("stats_api.protect_play_export_p3_snapshots()") == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "column",
        "nullable-int",
        "app-guard",
        "extra-function",
        "bad-returns",
        "outside-sql",
    ],
)
def test_unknown_storage_or_function_metadata_is_not_self_expected(
    monkeypatch, mutation
):
    """固定pinで未知構造/署名/guard公開化を拒否し、正式値へ自動採取しない。"""
    if mutation in {"column", "nullable-int"}:
        declaration = product.storage_declaration()
        if mutation == "column":
            declaration["columns"][0]["name"] = "other"
        else:
            declaration["columns"][0]["nullable"] = 0
        monkeypatch.setattr(product, "storage_declaration", lambda: declaration)
    else:
        original = product._function_candidates()
        values = list(original)
        if mutation == "app-guard":
            name, sql, v, _ = values[-1]
            values[-1] = (name, sql, v, True)
        elif mutation == "extra-function":
            values.append(values[-1])
        elif mutation == "bad-returns":
            name, sql, v, app = values[-1]
            values[-1] = (
                name,
                sql.replace("RETURNS trigger", "RETURNS TABLE(extra uuid)"),
                v,
                app,
            )
        else:
            name, sql, v, app = values[-1]
            values[-1] = (name, sql + "GRANT EXECUTE TO PUBLIC;\n", v, app)
        monkeypatch.setattr(product, "_function_candidates", lambda: tuple(values))
    with pytest.raises(ValueError):
        product.candidate_declarations()


@pytest.mark.parametrize("mutation", ["missing-public", "unknown-role", "predicate"])
def test_role_or_tenant_boundary_cannot_silently_change(monkeypatch, mutation):
    """actor/PUBLIC拒否とtenant式を構造pinから切り離さない。"""
    if mutation == "missing-public":
        monkeypatch.setattr(product, "_FUNCTION_ROLES", product._FUNCTION_ROLES[1:])
    elif mutation == "unknown-role":
        monkeypatch.setattr(
            product, "_FUNCTION_ROLES", (*product._FUNCTION_ROLES, "unknown")
        )
    else:
        monkeypatch.setattr(product, "_PREDICATE", "true")
    with pytest.raises(ValueError):
        product.candidate_declarations()
