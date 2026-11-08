"""P3の有限37列/保護4列と既stampを緩めない正負対向。"""

from copy import deepcopy

import pytest
from sqlalchemy import Column, MetaData, Table, Text

from pitchlog.authz import p3_play_row_insert_product as product
from pitchlog.authz.first_ball_product import (
    _P3_PLAY_INSERT_BASELINE_ADDITIONS as ADDITIONS,
)
from pitchlog.authz.first_ball_product import (
    _P3_PLAY_INSERT_BASELINE_BODIES as BODIES,
)
from pitchlog.authz.p3_projection_paged_sql import _APPEND_SQL
from pitchlog.authz.p3_projection_sql import _SQL


def test_exact_37_acl_and_one_policy_preserve_all_other_declarations():
    """保護列と既権利は不変更、37行とINSERT policy1だけを導出する。"""
    before, old_bodies = deepcopy(ADDITIONS), deepcopy(BODIES)
    rows, bodies = product.extend_p3_play_insert(ADDITIONS, BODIES)
    assert ADDITIONS == before and BODIES == old_bodies
    changed = [
        row
        for row, old in zip(
            rows["column_acl_expectations"],
            before["column_acl_expectations"],
            strict=True,
        )
        if row != old
    ]
    assert len(changed) == 37
    assert {row["column_id"] for row in changed} == set(product.insert_columns())
    assert all(
        row["privilege_ids"] == ["SELECT", "INSERT"] and not row["grant_option"]
        for row in changed
    )
    for section in rows:
        if section not in {"column_acl_expectations", "policies"}:
            assert rows[section] == before[section]
    assert rows["policies"][:-1] == before["policies"]
    policy = rows["policies"][-1]
    assert policy["command"] == "INSERT"
    assert policy["role_ids"] == ["pitchlog_sync_right_fn_owner"]
    assert "session_user = 'pitchlog_app'" in policy["with_check_expression"]
    assert "ready" not in policy["with_check_expression"]
    assert len([key for key in bodies if bodies[key] != old_bodies.get(key)]) == 38


@pytest.mark.parametrize("kind,sql", [("single", _SQL), ("page", _APPEND_SQL)])
def test_both_inserts_use_same_columns_and_protected_strict_values(kind, sql):
    """入力4値を厳格に拒否し、既nonce/xid/admission消費部分を保存する。"""
    rendered = product.rewrite_p3_play_insert(sql, kind)
    assert product._OLD_INSERT not in rendered
    assert (
        "INSERT INTO public.play_rows (" + ",".join(product.insert_columns()) + ")"
        in rendered
    )
    for name in product._PROTECTED - {"migration_unverified"}:
        assert f"item->'play_row'->'{name}' IS DISTINCT FROM 'null'::jsonb" in rendered
    assert "'migration_unverified' IS DISTINCT FROM 'false'::jsonb" in rendered
    start = rendered.index(" IF item->'play_row'->'hidden_at'")
    end = rendered.index(" NULL::public.play_rows,item->'play_row') r;", start)
    end += len(" NULL::public.play_rows,item->'play_row') r;")
    assert rendered[:start] + product._OLD_INSERT + rendered[end:] == sql


@pytest.mark.parametrize("damage", ["privilege", "option", "body", "policy"])
def test_unknown_acl_or_extra_policy_is_not_silently_accepted(damage):
    """既宣言不一致/未知権限/描画改変を追随として受理しない。"""
    rows, bodies = deepcopy(ADDITIONS), deepcopy(BODIES)
    selected = next(
        row
        for row in rows["column_acl_expectations"]
        if row["expectation_id"]
        == "COLUMN-ACL:public:play_rows:id:pitchlog_sync_right_fn_owner"
    )
    if damage == "privilege":
        selected["privilege_ids"].append("INSERT")
    elif damage == "option":
        selected["grant_option"] = True
    elif damage == "body":
        key = "column_acl_expectation|" + selected["expectation_id"]
        bodies[key] += (
            "GRANT INSERT ON public.play_rows TO pitchlog_sync_right_fn_owner;"
        )
    else:
        rows["policies"].append(
            {
                "table_id": "play_rows",
                "role_ids": ["pitchlog_sync_right_fn_owner"],
                "command": "INSERT",
            }
        )
    with pytest.raises(ValueError):
        product.extend_p3_play_insert(rows, bodies)


def test_unknown_column_is_not_an_automatic_insert_grant(monkeypatch):
    """ORM追加を列許可拡張として暗黙受理しない。"""
    original = product._TABLE
    assert isinstance(original, Table)
    table = original.to_metadata(MetaData())
    table.append_column(Column("unexpected", Text, nullable=True))
    monkeypatch.setattr(product, "_TABLE", table)
    with pytest.raises(ValueError):
        product.insert_columns()
