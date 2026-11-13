"""P3関数のsource統一と既baseline/権限の閉じた追随を照合する。"""

import copy
import json
import re

import pytest

from pitchlog.authz import p3_function_product as product
from pitchlog.authz import p3_storage_guard
from pitchlog.authz.first_ball_product import (
    _P3_BASELINE_BODIES as BODIES,
)
from pitchlog.authz.first_ball_product import (
    _P3_BASELINE_FUNCTIONS as FUNCTIONS,
)
from pitchlog.repositories.operation_registry import PRODUCT_FUNCTION_OPERATIONS


def test_all_p3_operations_have_real_function_sources_and_closed_owners():
    """内部binding読取をapp公開せず、有限9操作とguardを実factoryへ結ぶ。"""
    declarations, bodies = product.candidate_declarations(FUNCTIONS, BODIES)
    rows = declarations["functions"]
    assert len(rows) == len(bodies) == 22
    names = {row["schema_name"] + "." + row["function_name"] for row in rows}
    operations = [
        entry
        for entry in PRODUCT_FUNCTION_OPERATIONS
        if entry.operation_id.startswith("SYNC_P3:")
    ]
    assert len(operations) == 9
    assert all(entry.function_id in names for entry in operations)
    binding = next(
        row for row in rows if row["function_name"] == "read_p3_writer_binding"
    )
    assert binding["owner_role_id"] == "pitchlog_sync_binding_fn_owner"
    assert binding["acl_expectations"] == [
        {
            "grantee": "pitchlog_sync_right_fn_owner",
            "privilege": "EXECUTE",
            "grantable": False,
        }
    ]
    guard = next(
        row
        for row in rows
        if row["function_name"] == "p3_reject_unfinished_page_progress"
    )
    assert guard["owner_role_id"] == "pitchlog_owner"
    assert guard["acl_expectations"] == []
    assert bodies["function|" + guard["function_id"]] == "\n".join(
        p3_storage_guard.candidate_statements()[:3]
    )


def test_replaced_function_attributes_and_footer_remain_exact():
    """既source署名/全属性/owner・ACL・既triggerを部分比較へ緩めない。"""
    declarations, bodies = product.candidate_declarations(FUNCTIONS, BODIES)
    old_rows = {row["function_id"]: row for row in FUNCTIONS}
    replaced = [
        row
        for row in declarations["functions"]
        if row["function_id"] in product._OLD_PINS
    ]
    assert len(replaced) == 11
    for row in replaced:
        identity = row["function_id"]
        assert row == old_rows[identity]
        before = product._parts(BODIES["function|" + identity].split("\n\n", 1)[1])
        after = product._parts(bodies["function|" + identity])
        assert len(before) == len(after) == 1
        assert before[0]["suffix"] == after[0]["suffix"]
    for row in declarations["functions"]:
        if row["function_name"] in {
            "save_primitive_source",
            "open_primitive_snapshot",
            "read_primitive_totals",
            "read_play_export_primitives",
            "read_writer_play_export_aggregate",
            "read_play_export_source_page",
        }:
            assert (
                "sync_fence.p3_projection_capsule_items"
                in bodies["function|" + row["function_id"]]
            )


@pytest.mark.parametrize("mutation", ["body", "owner", "acl", "missing", "duplicate"])
def test_unknown_baseline_is_not_replaced(mutation):
    """出所不明の旧版/全属性差/欠落を『更新済み』へ補修しない。"""
    rows = copy.deepcopy(FUNCTIONS)
    bodies = dict(BODIES)
    identity = next(iter(product._OLD_PINS))
    row = next(row for row in rows if row["function_id"] == identity)
    if mutation == "body":
        bodies["function|" + identity] += "\n"
    elif mutation == "owner":
        row["owner_role_id"] = "pitchlog_app"
    elif mutation == "acl":
        row["acl_expectations"].append(
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        )
    elif mutation == "missing":
        rows.remove(row)
    else:
        rows.append(copy.deepcopy(row))
    with pytest.raises(ValueError):
        product.candidate_declarations(rows, bodies)


@pytest.mark.parametrize("mutation", ["version", "table", "extra"])
def test_unaccepted_selection_profile_cannot_supply_functions(
    tmp_path, monkeypatch, mutation
):
    """版/表/余剰fieldを既v2 validatorより手前で補修しない。"""
    profile = json.loads((product._ROOT / product._PROFILE).read_bytes())
    if mutation == "version":
        profile["version"] = True
    elif mutation == "table":
        profile["p3"]["items"] = "public.operation_events"
    else:
        profile["unreviewed"] = True
    target = tmp_path / product._PROFILE
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(profile))
    monkeypatch.setattr(product, "_ROOT", tmp_path)
    with pytest.raises(ValueError):
        product.candidate_declarations(FUNCTIONS, BODIES)


def test_normal_profile_contains_the_same_full_p3_publishers():
    """隔離手動SQLと別sourceにせず、通常宣言へ全163本文を登録する。"""
    from pitchlog.authz.first_ball_product import ADDITIONS
    from pitchlog.authz.first_ball_product import BODIES as active_bodies
    from pitchlog.authz.p3_storage_product import candidate_declarations

    functions, function_bodies = product.candidate_declarations(FUNCTIONS, BODIES)
    storage, storage_bodies = candidate_declarations()
    kinds = {
        "functions": "function",
        "tables": "table",
        "policies": "policy",
        "column_acl_expectations": "column_acl_expectation",
    }
    identifiers = {
        "functions": "function_id",
        "tables": "table_id",
        "policies": "policy_id",
        "column_acl_expectations": "expectation_id",
    }
    for declarations, bodies in [
        (functions, function_bodies),
        (storage, storage_bodies),
    ]:
        for section, rows in declarations.items():
            for row in rows:
                identifier = row[identifiers[section]]
                assert [
                    r
                    for r in ADDITIONS[section]
                    if r[identifiers[section]] == identifier
                ] == [row]
                kind = kinds[section]
                key = kind + "|" + identifier
                assert (
                    active_bodies[key]
                    == f"-- ELEMENT-TYPE: {kind}\n-- ELEMENT-ID: {identifier}\n\n"
                    + re.sub(
                        r"^CREATE(?: OR REPLACE)?\s+FUNCTION\s+",
                        "CREATE FUNCTION ",
                        bodies[key],
                        count=1,
                    )
                )


def test_normal_current_uses_all_private_tables_and_p3_provider():
    """CURRENTだけ先行せず全原本と保存provider型を同じsourceへ含める。"""
    from sqlalchemy import CheckConstraint

    from pitchlog.db.current_product_startup import CURRENT_REVISION, _tables
    from pitchlog.db.game_state.stats import StatsPrimitiveSource
    from pitchlog.db.past_correction.models import P3_STORAGE_MODELS

    assert CURRENT_REVISION == "0051_tiebreak_start_receipt"
    names = {table.name for table in _tables()}
    assert len(names) == 22
    assert {model.__table__.name for model in P3_STORAGE_MODELS} <= names
    provider = next(
        c
        for c in StatsPrimitiveSource.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_stats_source_provider"
    )
    assert (
        str(provider.sqltext)
        == "provider_kind IN ('first_ball','ordinary','past_correction')"
    )


def test_all_p3_functions_use_the_strict_normal_reapply_guard():
    """OR REPLACEで既関数や作成競合を補修せず全22件を適用器へ渡す。"""
    from pitchlog.authz.first_ball_product import ADDITIONS, application_function_sql
    from pitchlog.authz.first_ball_product import BODIES as active_bodies

    rows = [
        r
        for r in ADDITIONS["functions"]
        if (r["schema_name"], r["function_name"]) in product._SIGNATURES
    ]
    assert len(rows) == 22
    for row in rows:
        key = row["function_id"]
        body = active_bodies["function|" + key]
        assert "CREATE OR REPLACE FUNCTION" not in body
        wrapped = application_function_sql(key, body)
        assert wrapped is not None
        assert "IF existing IS NULL THEN" in wrapped
        assert "first ball function definition collision" in wrapped
        assert "first ball function privilege collision" in wrapped


def test_every_declared_xmin_grant_is_visible_to_the_real_catalog_query():
    """宣言を追加したのに検査queryが未取得のままになる往復を防ぐ。"""
    from pitchlog.authz.first_ball_product import ADDITIONS
    from pitchlog.authz.product_catalog import _COLUMN_ACL_QUERY
    from pitchlog.db.past_correction.models import P3_STORAGE_MODELS

    expected = {
        (row["object_schema"], row["object_id"])
        for row in ADDITIONS["column_acl_expectations"]
        if row["column_id"] == "xmin"
    }
    collected = set(
        re.findall(r"\('([a-z_][a-z_0-9]*)', '([a-z_][a-z_0-9]*)'\)", _COLUMN_ACL_QUERY)
    )
    assert expected <= collected
    assert len({table for _, table in expected if table.startswith("p3_")}) == 4
    assert {
        (model.__table__.schema, model.__table__.name) for model in P3_STORAGE_MODELS
    } <= collected
