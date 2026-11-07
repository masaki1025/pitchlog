"""P3関数のsource統一と既baseline/権限の閉じた追随を照合する。"""

import copy
import json

import pytest

from pitchlog.authz import p3_function_product as product
from pitchlog.authz import p3_storage_guard
from pitchlog.authz.first_ball_product import ADDITIONS, BODIES
from pitchlog.repositories.operation_registry import PRODUCT_FUNCTION_OPERATIONS


def test_all_p3_operations_have_real_function_sources_and_closed_owners():
    """内部binding読取をapp公開せず、有限9操作とguardを実factoryへ結ぶ。"""
    declarations, bodies = product.candidate_declarations(
        ADDITIONS["functions"], BODIES
    )
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
    declarations, bodies = product.candidate_declarations(
        ADDITIONS["functions"], BODIES
    )
    old_rows = {row["function_id"]: row for row in ADDITIONS["functions"]}
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
    rows = copy.deepcopy(ADDITIONS["functions"])
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
        product.candidate_declarations(ADDITIONS["functions"], BODIES)
