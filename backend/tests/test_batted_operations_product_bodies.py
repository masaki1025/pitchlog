"""DBを作る前に、適用SQLと固定canonical生成の全関数を照合する。"""

import pytest

from pitchlog.authz import first_ball_product as canonical
from pitchlog.authz import product_provisioning as provisioning

FID = "FUNCTION:initial_right_api:persist_start_pitcher_entry(uuid, uuid, bigint)"
OLD = "71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff"
NEW = "b565641886c758b81787baff95bdacceb3dea648781515cac39f868583c156ad"


def test_every_selected_first_ball_function_matches_canonical_before_owned_pg():
    """ピン追随漏れを36秒のDB配置に進まず検出し、関数の欠落も拒否する。"""
    _, entries = provisioning._selected_product_ddl(provisioning.ProductOperation.APPLY)
    expected = {r["function_id"] for r in canonical.ADDITIONS["functions"]}
    found = []
    for row in entries:
        if row.element_type == "function" and row.element_id in expected:
            assert row.sql == canonical.body("function", row.element_id), row.element_id
            found.append(row.element_id)
    assert len(found) == len(set(found))
    assert set(found) == expected


def test_old_start_participation_pin_is_not_accepted_as_same_frozen_body():
    """生成漏れの旧3pinを再導入すると、元の固定本文ゲートで拒否される。"""
    sql = canonical.body("function", FID)
    assert type(sql) is str and sql.count(NEW) == 3 and OLD not in sql
    with pytest.raises(ValueError, match="適用本文が凍結値と不一致"):
        canonical.application_function_sql(FID, sql.replace(NEW, OLD))
