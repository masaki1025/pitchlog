"""取消publisherの権限境界を検査する。実PGの証拠は別に必要。"""

import copy
import json

import pytest

from pitchlog.authz import nonplay_product as publisher
from pitchlog.authz.first_ball_product import _function_argument_names
from pitchlog.authz.nonplay_prefix_sql import candidate_function_bodies
from pitchlog.db.writer_binding.nonplay_models import NonplayWriteAdmission


def test_exact_six_bodies_and_catalog_signatures():
    """単一renderer全本文と既installerの引数解析を保ち、別SQLを作らない。"""
    declarations, bodies = publisher.candidate_declarations()
    original = candidate_function_bodies()
    assert len(declarations["functions"]) == 6
    assert {r["function_name"] for r in declarations["functions"]} == set(original)
    for row in declarations["functions"]:
        sql = bodies["function|" + row["function_id"]]
        source = original[row["function_name"]].replace(
            "CREATE OR REPLACE FUNCTION", "CREATE FUNCTION", 1
        )
        assert sql.startswith(source)
        names, table_result = _function_argument_names(sql)
        assert table_result is True
        assert len(names) == len(row["identity_args"].split(",")) + len(
            row["returns"].split(",")
        )
        assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["search_path"] == ["pg_catalog", "pg_temp"]
        assert row["acl_expectations"] == [
            {
                "grantee": "pitchlog_app",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ]
        assert "FROM PUBLIC,pitchlog_app;" in sql


def test_private_table_and_update_columns_are_minimal():
    """appの表直接DML・物理削除・所有権変更を付与しない。"""
    declarations, bodies = publisher.candidate_declarations()
    assert declarations["tables"] == [
        {
            "table_id": "nonplay_write_admissions",
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    ]
    assert declarations["acl_expectations"][0]["privilege_ids"] == ["SELECT"]
    assert len(declarations["acl_expectations"]) == 1
    rows = declarations["column_acl_expectations"]
    assert len(rows) == 44
    table_rows = [r for r in rows if r["object_id"] == "nonplay_write_admissions"]
    assert {r["column_id"] for r in table_rows} == set(
        NonplayWriteAdmission.__table__.c.keys()
    )
    mutable = NonplayWriteAdmission.immutability.conditional_update_columns
    assert {
        r["column_id"] for r in table_rows if "UPDATE" in r["privilege_ids"]
    } == mutable
    assert {r["column_id"] for r in table_rows if "INSERT" in r["privilege_ids"]} == (
        set(NonplayWriteAdmission.__table__.c.keys()) - mutable | {"state"}
    )
    public = [r for r in rows if r["object_schema"] == "public"]
    assert [(r["object_id"], r["column_id"], r["privilege_ids"]) for r in public] == [
        ("play_rows", "hidden_at", ["UPDATE"])
    ]
    for row in rows:
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["grant_option"] is False
        assert set(row["privilege_ids"]) <= {"SELECT", "INSERT", "UPDATE"}
    for sql in bodies.values():
        assert "GRANT DELETE" not in sql
        assert "GRANT TRUNCATE" not in sql
        assert "WITH GRANT OPTION" not in sql


def test_policies_require_same_tenant_and_real_app_session():
    """GUCだけや別session userで私有表を書けるpolicyを作らない。"""
    declarations, _ = publisher.candidate_declarations()
    assert len(declarations["policies"]) == 4
    for row in declarations["policies"]:
        assert row["role_ids"] == ["pitchlog_sync_right_fn_owner"]
        assert row["command"] in {"SELECT", "INSERT", "UPDATE"}
        for expression in (row["using_expression"], row["with_check_expression"]):
            if expression is not None:
                assert "tenant_id = NULLIF" in expression
                assert "session_user = 'pitchlog_app'" in expression


@pytest.mark.parametrize("mutation", ["extra", "missing", "signature", "definer"])
def test_unknown_sql_family_or_changed_signature_is_rejected(monkeypatch, mutation):
    """既SQL集合のドリフトをdescriptorの追随だけで受け入れない。"""
    source = candidate_function_bodies()
    if mutation == "extra":
        source["unknown"] = source["bind_nonplay_device"]
    elif mutation == "missing":
        del source["prepare_nonplay_undo"]
    elif mutation == "signature":
        source["bind_nonplay_device"] = source["bind_nonplay_device"].replace(
            "p_credential_digest bytea", "p_credential_digest text", 1
        )
    else:
        source["bind_nonplay_device"] = source["bind_nonplay_device"].replace(
            "SECURITY DEFINER", "SECURITY INVOKER", 1
        )
    monkeypatch.setattr(publisher, "candidate_function_bodies", lambda: source)
    with pytest.raises(ValueError):
        publisher.candidate_declarations()


def test_mutable_column_expansion_is_rejected(monkeypatch):
    """別の列を更新対象へ足す変更は再受理なしには描画しない。"""
    monkeypatch.setattr(publisher, "_MUTABLE", publisher._MUTABLE | {"tenant_id"})
    with pytest.raises(ValueError):
        publisher.candidate_declarations()


def test_fresh_json_values_do_not_mutate_later_declarations():
    """候補値の編集で次回の正式入力へ別権限を混入させない。"""
    expected = publisher.candidate_declarations()
    actual = copy.deepcopy(expected)
    actual[0]["functions"][0]["acl_expectations"].clear()
    assert publisher.candidate_declarations() == expected
    assert json.loads(json.dumps(expected[0])) == expected[0]
