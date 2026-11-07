"""出場helperの有限権限と未知の保存本文を補修しない境界を検査する。"""

from __future__ import annotations

import copy
import hashlib

import pytest

from pitchlog.authz import first_ball_product as baseline
from pitchlog.authz import pitcher_appearance_product as product
from pitchlog.authz.product_function_acl import _INITIAL_API_SQL


def test_only_owner_helpers_and_select_insert_columns_are_declared():
    """公開actorへ実行や書込権限を追加せず、原本の更新削除も許可しない。"""
    rows, bodies = product.candidate_declarations()
    assert {f["function_name"] for f in rows["functions"]} == {
        "persist_start_pitcher_entry",
        "persist_writer_pitcher_entry",
        "protect_pitcher_entry_sources",
        "read_pitcher_appearance_context",
        "read_pitcher_appearance_source",
    }
    assert len(bodies) == 44
    for function in rows["functions"]:
        assert function["acl_expectations"] == []
        assert function["owner_role_id"] in {
            product.INITIAL_OWNER,
            product.WRITER_OWNER,
        }
        assert function["security_mode"] == "definer"
        assert function["search_path"] == ["pg_catalog", "pg_temp"]
    entry_columns = [
        row
        for row in rows["column_acl_expectations"]
        if row["object_id"] == product.TABLE
    ]
    assert len(entry_columns) == 34
    assert len({row["column_id"] for row in entry_columns}) == 17
    for row in entry_columns:
        assert row["grantee_role_id"] in {product.INITIAL_OWNER, product.WRITER_OWNER}
        assert row["privilege_ids"] == ["SELECT", "INSERT"]
        assert row["grant_option"] is False
    native_xmin = [
        row
        for row in rows["column_acl_expectations"]
        if row["object_id"] != product.TABLE
    ]
    assert {(row["object_id"], row["column_id"]) for row in native_xmin} == {
        ("stats_primitive_sources", "xmin"),
        ("stats_fact_versions", "xmin"),
    }
    assert all(row["privilege_ids"] == ["SELECT"] for row in native_xmin)
    assert {policy["command"] for policy in rows["policies"]} == {"SELECT", "INSERT"}
    for policy in rows["policies"]:
        assert policy["role_ids"] == [product.INITIAL_OWNER, product.WRITER_OWNER]
        assert (policy["using_expression"] or policy["with_check_expression"]) == (
            "tenant_id = NULLIF(pg_catalog.current_setting("
            "'app.tenant_id',true),'')::uuid"
        )


def test_unknown_table_owner_is_rejected_before_any_column_grant(monkeypatch):
    """同じ列名でもowner改変を既モデルとして許可しない。"""
    monkeypatch.setitem(
        product.PitcherEntrySource.__table__.info, "storage_owner", "PUBLIC"
    )
    with pytest.raises(ValueError, match="固定列集合"):
        product.candidate_declarations()


def test_unknown_private_function_owner_is_not_promoted_to_a_declaration(monkeypatch):
    """供給側の未知ownerを正式publisherの許可値へ暗黙採用しない。"""
    rows, bodies = product.candidate_private_entry_declarations()
    rows["functions"][1]["owner_role_id"] = "PUBLIC"
    monkeypatch.setattr(
        product, "candidate_private_entry_declarations", lambda: (rows, bodies)
    )
    with pytest.raises(ValueError, match="既private helper集合"):
        product.candidate_declarations()


def test_normal_save_overlay_matches_reviewed_candidate_and_preserves_baseline():
    """正規P3適用後だけへ挿入し、入口/監査/親最終再確認を落とさない。"""
    active = copy.deepcopy(baseline.BODIES)
    saved = copy.deepcopy(baseline._D03_BASELINE_BODIES)
    changed = {}
    for key, sql in saved.items():
        if key.startswith("function|"):
            result = product.overlay_saved_function(key.removeprefix("function|"), sql)
            if result != sql:
                changed[key] = result
    assert baseline.BODIES == active
    assert len(changed) == 2
    save = next(v for k, v in changed.items() if ":save_primitive_source(" in k)
    assert hashlib.sha256(save.encode()).hexdigest() == (
        "e93e2b55f1f6ddeb1cd7833a7282ec3cc30db059ce3643a2ca79b036c48a21d4"
    )
    assert save.count("PERFORM stats_api.persist_writer_pitcher_entry(") == 2
    assert (
        save.count(
            "IF event_row.event_kind='play_input' "
            "AND provider IN ('first_ball','ordinary') THEN"
        )
        == 2
    )
    # 元入口のbinding検査も残り、追加hook後にも同じ末尾検査を実施する。
    assert save.count("PERFORM sync_fence_api.assert_writer_binding(tenant,") == 3


@pytest.mark.parametrize(
    "name", ["save_primitive_source", "consume_nonplay_substitution"]
)
def test_changed_parent_body_cannot_be_overlaid(name):
    """未知の元版や既適用版を文字列置換で補修しない。"""
    key = next(
        k
        for k in baseline._D03_BASELINE_BODIES
        if k.startswith("function|FUNCTION:") and f":{name}(" in k
    )
    function_id = key.removeprefix("function|")
    sql = baseline._D03_BASELINE_BODIES[key]
    with pytest.raises(ValueError, match="保存元本文"):
        product.overlay_saved_function(function_id, sql + " ")
    with pytest.raises(ValueError, match="保存元本文"):
        product.overlay_saved_function(
            function_id, product.overlay_saved_function(function_id, sql)
        )


def test_initial_overlay_keeps_original_and_rejects_changed_parent():
    """真正開始へ1回だけ結び、元関数や無関係IDを変更しない。"""
    source = _INITIAL_API_SQL[product.INITIAL_FUNCTION]
    result = product.overlay_initial_function(product.INITIAL_FUNCTION, source)
    assert result.count("PERFORM initial_right_api.persist_start_pitcher_entry(") == 1
    assert _INITIAL_API_SQL[product.INITIAL_FUNCTION] == source
    assert product.overlay_initial_function("unrelated", source) == source
    with pytest.raises(ValueError, match="初期付与元本文"):
        product.overlay_initial_function(product.INITIAL_FUNCTION, source + " ")
    with pytest.raises(ValueError, match="初期付与元本文"):
        product.overlay_initial_function(product.INITIAL_FUNCTION, result)
