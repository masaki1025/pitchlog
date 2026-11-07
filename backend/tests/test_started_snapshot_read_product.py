"""RR専用readerの有限宣言と親の未知変更拒否を検査する。"""

from copy import deepcopy

import pytest

from pitchlog.authz import first_ball_product
from pitchlog.authz import started_snapshot_read_product as product
from pitchlog.authz import started_snapshot_read_sql as source


def test_only_three_closed_rr_functions_are_added_without_writer_changes():
    """親の全metadataを保ち、PUBLIC既定権限を新identityへ持ち込まない。"""
    before = deepcopy(first_ball_product.ADDITIONS["functions"])
    rows, bodies = product.candidate_declarations(before)
    assert before == first_ball_product.ADDITIONS["functions"]
    assert len(rows) == len(bodies) == 3
    for row in rows:
        assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
        assert row["acl_expectations"] == [
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
        ]
        assert row["revoked_acl_expectations"] == [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        ]
        body = bodies["function|" + row["function_id"]]
        assert body.count(source._RR_RO_GUARD) == 1
        assert "FOR UPDATE" not in body and "FOR SHARE" not in body
        assert " OWNER TO pitchlog_sync_right_fn_owner;" in body
        assert " FROM PUBLIC,pitchlog_app;" in body
        assert " TO pitchlog_app;" in body


@pytest.mark.parametrize("fault", ["missing", "duplicate", "owner", "public-execute"])
def test_unknown_parent_metadata_cannot_be_promoted_to_readonly_profile(fault):
    """署名/所有/ACLの違う元関数を暗黙採用して読み替えない。"""
    rows = deepcopy(first_ball_product.ADDITIONS["functions"])
    row = next(r for r in rows if r["function_name"] == "read_ordinary_history_page")
    if fault == "missing":
        rows.remove(row)
    elif fault == "duplicate":
        rows.append(deepcopy(row))
    elif fault == "owner":
        row["owner_role_id"] = "pitchlog_app"
    else:
        row["acl_expectations"].append(
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        )
    with pytest.raises(ValueError, match="固定値"):
        product.candidate_declarations(rows)


def test_changed_source_body_cannot_drop_a_condition_during_lock_removal(monkeypatch):
    """元SQLを未知版へ変更してからの再導出を拒否する。"""
    original = source.ordinary

    def changed():
        bodies = original()
        bodies["read_ordinary_history_page"] += "\n-- unknown change\n"
        return bodies

    monkeypatch.setattr(
        source, "_SOURCE", (("read_ordinary_history_page", changed, 1),)
    )
    with pytest.raises(ValueError, match="固定構造"):
        source.candidate_started_read_function_bodies()
