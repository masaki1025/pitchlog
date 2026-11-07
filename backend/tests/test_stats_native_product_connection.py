"""成績canonical接合の旧全値保持と有限追加を検証する。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import frozen_history

from pitchlog.authz import first_ball_product as product
from pitchlog.authz import stats_primitive_product as stats
from pitchlog.authz import stats_primitive_write_state as writer
from pitchlog.authz.function_result_type import pg_result_type
from pitchlog.authz.product_catalog import _LIFECYCLE_FUNCTION_DETAILS_QUERY


def _hash(value: object) -> str:
    """接合前に独立保存した旧集合の全byte相当を比較する。"""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def test_all_old_declarations_bodies_details_and_guards_remain_exact():
    """接合前ee632系統の全宣言・323本文・29関数guardを保持する。"""
    declarations, bodies = stats.connection_declarations()
    old = {
        section: [
            row
            for row in rows
            if row[product.IDS[section]]
            not in {r[product.IDS[section]] for r in declarations.get(section, [])}
        ]
        for section, rows in product.ADDITIONS.items()
    }
    assert _hash(old) == frozen_history.read_original_pr197_pin(
        "stats_native_old_product_additions_sha256"
    )
    old_bodies = {
        key: value for key, value in product.BODIES.items() if key not in bodies
    }
    assert len(old_bodies) == 323
    assert _hash(old_bodies) == frozen_history.read_original_pr197_pin(
        "stats_native_old_product_bodies_sha256"
    )
    details = [row for row in product.function_details() if row[0] != "stats_api"]
    assert len(details) == 29
    assert _hash(details) == frozen_history.read_original_pr197_pin(
        "stats_native_old_product_details_sha256"
    )
    guards = {}
    for row in product.ADDITIONS["functions"]:
        if row["schema_name"] == "stats_api":
            continue
        sql = product.body("function", row["function_id"])
        assert sql is not None
        guards[row["function_id"]] = product.application_function_sql(
            row["function_id"], sql
        )
    assert _hash(guards) == frozen_history.read_original_pr197_pin(
        "stats_native_old_product_guards_sha256"
    )


def test_new_five_functions_three_private_tables_and_schema_are_exact():
    """SQL/ACL/RLSを同じcanonical producerから既installerへ供給する。"""
    declarations, bodies = stats.connection_declarations()
    assert {section: len(rows) for section, rows in declarations.items()} == {
        "functions": 5,
        "policies": 10,
        "column_acl_expectations": 70,
        "schemas": 1,
        "tables": 3,
    }
    assert len(bodies) == 89
    for section, rows in declarations.items():
        for row in rows:
            key = row[product.IDS[section]]
            assert product.declaration(section, key) == row
            assert key in product.pre_rule_deferred_ids()
    assert set(stats.candidate_function_bodies()) == {
        "save_primitive_source",
        "open_primitive_snapshot",
        "read_play_export_primitives",
        "read_primitive_totals",
    }
    assert writer.FUNCTION_ID in {
        row["function_id"] for row in declarations["functions"]
    }
    for key, sql in bodies.items():
        kind, identifier = key.split("|", 1)
        canonical = product.body(kind, identifier)
        assert (
            canonical
            == f"-- ELEMENT-TYPE: {kind}\n-- ELEMENT-ID: {identifier}\n\n" + sql
        )
        if kind == "function":
            guard = product.application_function_sql(identifier, canonical)
            assert guard is not None
            for condition in (
                "function definition collision",
                "function privilege collision",
                "p.proargnames IS NOT DISTINCT FROM",
                "p.proargmodes IS NOT DISTINCT FROM",
                "p.prosecdef=TRUE",
                "p.proconfig=ARRAY",
                "pg_catalog.btrim(p.prosrc",
            ):
                assert condition in guard
            with pytest.raises(ValueError):
                product.application_function_sql(identifier, canonical + "\n")
    for row in declarations["tables"]:
        assert row["table_id"] in product.TABLES
        assert row["schema_name"] == "sync_fence"
        assert row["enable_row_level_security"] is True
        assert row["force_row_level_security"] is True
    schema = stats.candidate_schema()
    assert schema["owner"] == "pitchlog_owner"
    assert schema["schema_name"] in product.SCHEMAS
    assert schema["acl_expectations"] == [
        {"grantee": stats.APP, "privilege": "USAGE", "grantable": False},
        {"grantee": stats.OWNER, "privilege": "USAGE", "grantable": False},
    ]
    assert all(not row["grantable"] for row in schema["revoked_acl_expectations"])
    assert "'stats_api'" in _LIFECYCLE_FUNCTION_DETAILS_QUERY


@pytest.mark.parametrize(
    "mutation",
    ["role", "privilege", "grant", "unknown_column", "unknown_table", "unknown_schema"],
)
def test_changed_or_unknown_new_declaration_is_rejected(mutation):
    """xminも固定4列だけで、未知列/owner/権限へ一般化しない。"""
    declarations, _ = stats.connection_declarations()
    row = copy.deepcopy(
        next(
            r
            for r in declarations["column_acl_expectations"]
            if r["column_id"] == "xmin"
        )
    )
    if mutation == "role":
        row["grantee_role_id"] = "pitchlog_app"
    elif mutation == "privilege":
        row["privilege_ids"] = ["SELECT", "UPDATE"]
    elif mutation == "grant":
        row["grant_option"] = True
    elif mutation == "unknown_column":
        row["column_id"] = "unknown"
    elif mutation == "unknown_table":
        row["object_id"] = "unknown"
    else:
        row["object_schema"] = "unknown"
    with pytest.raises(ValueError):
        product.require_row("column_acl_expectations", row)


def test_duplicate_same_column_keeps_old_body_and_conflicts_fail(monkeypatch):
    """同値重複で再描画せず、異値/余剰本文は拒否する。"""
    existing = copy.deepcopy(product.ADDITIONS)
    old_bodies = copy.deepcopy(product.BODIES)
    monkeypatch.setattr(product, "ADDITIONS", existing)
    monkeypatch.setattr(product, "BODIES", old_bodies)
    before_rows = copy.deepcopy(existing)
    before_bodies = copy.deepcopy(old_bodies)
    product._activate_stats_profile()
    assert product.ADDITIONS == before_rows
    assert product.BODIES == before_bodies
    original = stats.connection_declarations
    rows, bodies = original()
    row = rows["column_acl_expectations"][0]
    row["grant_option"] = True
    monkeypatch.setattr(stats, "connection_declarations", lambda: (rows, bodies))
    with pytest.raises(ValueError, match="既宣言と衝突"):
        product._activate_stats_profile()
    rows, bodies = original()
    bodies["function|unknown"] = "SELECT true"
    monkeypatch.setattr(stats, "connection_declarations", lambda: (rows, bodies))
    with pytest.raises(ValueError, match="本文集合"):
        product._activate_stats_profile()


@pytest.mark.parametrize("first", ["first_ball_product", "stats_primitive_product"])
def test_real_import_both_orders_without_cycle(first):
    """独立processの実import順2通りと旧名互換を確認する。"""
    other = (
        "stats_primitive_product"
        if first == "first_ball_product"
        else "first_ball_product"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from pitchlog.authz import {first}; from pitchlog.authz import {other}",
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for value in ("TABLE (a uuid)", "TABLE(a bigint)", "void", "trigger"):
        assert product._pg_result_type(value) == pg_result_type(value)


@pytest.mark.parametrize("mutation", ["none", "missing", "extra", "owner", "bool_int"])
def test_prospective_profile_requires_exact_closed_new_set(mutation):
    """正式資産供給前でも閉集合の欠落/未知/権限改変を拒否する。"""
    asset = copy.deepcopy(product.ADDITIONS)
    asset["databases"] = [
        {
            "acl_expectations": [copy.deepcopy(product.DB_GRANT)],
            "revoked_acl_expectations": copy.deepcopy(product.DB_REVOKES),
        }
    ]
    asset["schemas"].append(
        {
            "schema_name": "public",
            "acl_expectations": copy.deepcopy(product.PUBLIC_GRANTS),
            "revoked_acl_expectations": [],
        }
    )
    row = next(r for r in asset["functions"] if r["schema_name"] == "stats_api")
    if mutation == "missing":
        asset["functions"].remove(row)
    elif mutation == "extra":
        extra = copy.deepcopy(row)
        extra["function_id"] += "_unknown"
        asset["functions"].append(extra)
    elif mutation == "owner":
        row["owner_role_id"] = "pitchlog_app"
    elif mutation == "bool_int":
        row["acl_expectations"][0]["grantable"] = 0
    if mutation == "none":
        assert product.validate(asset) is True
    else:
        with pytest.raises(ValueError):
            product.validate(asset)


@pytest.mark.parametrize(
    "change", ["owner", "public_create", "app_create", "function_owner_create"]
)
def test_schema_owner_and_create_grant_changes_are_rejected(change):
    """新schemaの既ownerや最小USAGE以外を宣言へ混ぜられない。"""
    declarations = copy.deepcopy(product.ADDITIONS)
    declarations["databases"] = [
        {
            "acl_expectations": [copy.deepcopy(product.DB_GRANT)],
            "revoked_acl_expectations": copy.deepcopy(product.DB_REVOKES),
        }
    ]
    declarations["schemas"].append(
        {
            "schema_name": "public",
            "acl_expectations": copy.deepcopy(product.PUBLIC_GRANTS),
            "revoked_acl_expectations": [],
        }
    )
    schema = next(r for r in declarations["schemas"] if r["schema_name"] == "stats_api")
    if change == "owner":
        schema["owner"] = "pitchlog_app"
    else:
        grantee = {
            "public_create": "PUBLIC",
            "app_create": stats.APP,
            "function_owner_create": stats.OWNER,
        }[change]
        schema["acl_expectations"].append(
            {"grantee": grantee, "privilege": "CREATE", "grantable": False}
        )
    with pytest.raises(ValueError):
        product.validate(declarations)


def test_schema_create_owner_collision_guard_and_minimal_acl_body():
    """既規約と同型で異ownerを修復せず拒否し、CREATE権限を残さない。"""
    sql = stats.candidate_schema_body()
    canonical = product.body("schema", "stats_api")
    assert canonical == "-- ELEMENT-TYPE: schema\n-- ELEMENT-ID: stats_api\n\n" + sql
    assert sql.count("CREATE SCHEMA stats_api AUTHORIZATION pitchlog_owner;") == 1
    assert "n.nspname='stats_api' AND r.rolname='pitchlog_owner'" in sql
    assert "RAISE EXCEPTION 'stats schema owner collision';" in sql
    assert "ALTER SCHEMA" not in sql
    assert "REVOKE ALL ON SCHEMA stats_api FROM PUBLIC;" in sql
    assert (
        "REVOKE CREATE ON SCHEMA stats_api FROM "
        "pitchlog_app,pitchlog_sync_right_fn_owner;" in sql
    )
    assert (
        "GRANT USAGE ON SCHEMA stats_api TO pitchlog_app,pitchlog_sync_right_fn_owner;"
        in sql
    )
    assert "GRANT CREATE" not in sql


def test_canonical_declarations_remain_exact_after_real_json_roundtrip():
    """ORM quoted_nameをJSONへ保存して戻しても厳密型・全fieldを維持する。"""
    declarations, _ = stats.connection_declarations()
    restored = json.loads(json.dumps(declarations, ensure_ascii=False))
    assert product._exact(restored, declarations)


def test_current_v2_sink_does_not_execute_historical_model_or_artifact():
    """履歴profileの来歴を現在5関数の自由な代替版へ変えない。"""
    from pitchlog.repositories.stats_function_codec import _native_profiles
    from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

    profiles = _native_profiles()
    functions = stats.candidate_function_bodies()
    assert len(functions) == 4
    for text in functions.values():
        assert SOURCE_MODEL_HASH in text
        assert profiles["v1"]["model_sha256"] not in text
    save = functions["save_primitive_source"]
    assert "p_evaluation_json->'decisions' IS DISTINCT FROM" in save
    assert "p_evaluation_json->'pending'" not in save
    assert profiles["v1"]["artifact_binding"]["model_sha256"] not in save
    writer_sql = writer.candidate_sql()
    assert f"OR p_model_sha256 IS DISTINCT FROM '{SOURCE_MODEL_HASH}'" in writer_sql
    assert profiles["v1"]["model_sha256"] not in writer_sql
