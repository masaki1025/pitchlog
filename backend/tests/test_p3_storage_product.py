"""P3の保存権限が実actorへ漏れず、未知の型元を閉じることを検査する。"""

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, DefaultClause, MetaData, Text, text

from pitchlog.authz import p3_storage_product as product


def test_p3_storage_grants_only_closed_writer_columns():
    """app直接DML/DELETE/TRUNCATE/tenant identity更新を与えない。"""
    declarations, bodies = product.candidate_declarations()
    assert len(declarations["tables"]) == 6
    assert len(bodies) == 141
    updates = set()
    for row in declarations["column_acl_expectations"]:
        assert row["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["grant_option"] is False
        assert set(row["privilege_ids"]) <= {"SELECT", "INSERT", "UPDATE"}
        if row["column_id"] == "xmin":
            assert row["privilege_ids"] == ["SELECT"]
        if "UPDATE" in row["privilege_ids"]:
            updates.add((row["object_id"], row["column_id"]))
    assert updates == {
        ("p3_projection_heads", field)
        for field in (
            "capsule_id",
            "revision",
            "source_set_digest",
            "stats_version_id",
            "updated_at",
        )
    } | {("p3_projection_write_admissions", "state")} | {
        ("p3_projection_page_progress", field)
        for field in (
            "state",
            "item_count",
            "last_d1",
            "last_d2",
            "page_count",
            "source_page_seal",
            "evaluation_page_seal",
            "finalized_at",
        )
    }
    for row in declarations["policies"]:
        if row["role_ids"] == ["pitchlog_owner"]:
            assert row["using_expression"] == "true"
        else:
            assert row["role_ids"] == ["pitchlog_sync_right_fn_owner"]
            predicate = row["using_expression"] or row["with_check_expression"]
            assert "app.tenant_id" in predicate
            assert "session_user = 'pitchlog_app'" in predicate


@pytest.mark.parametrize("mutation", ["extra", "type", "nullable", "default", "owner"])
def test_p3_model_drift_cannot_silently_expand_grants(monkeypatch, mutation):
    """型元の新列/別型/nullable/default/ownerを受理なしでGRANTしない。"""
    models: list[object] = list(product.P3_STORAGE_MODELS)
    table = product.P3_STORAGE_MODELS[0].__table__.to_metadata(MetaData())
    if mutation == "extra":
        table.append_column(Column("unreviewed", Text))
    elif mutation == "type":
        table.c.tenant_id.type = Text()
    elif mutation == "nullable":
        table.c.tenant_id.nullable = True
    elif mutation == "default":
        table.c.digest_format.server_default = DefaultClause(text("'unreviewed'"))
    else:
        table.info["storage_owner"] = "pitchlog_app"
    models[0] = SimpleNamespace(__table__=table)
    monkeypatch.setattr(product, "P3_STORAGE_MODELS", tuple(models))
    with pytest.raises(ValueError, match="固定集合"):
        product.candidate_declarations()


def test_p3_storage_duplicate_table_is_rejected(monkeypatch):
    """重複をdictの後勝ちで補修しない。"""
    monkeypatch.setattr(
        product,
        "P3_STORAGE_MODELS",
        (*product.P3_STORAGE_MODELS, product.P3_STORAGE_MODELS[0]),
    )
    with pytest.raises(ValueError, match="固定集合"):
        product.candidate_declarations()
