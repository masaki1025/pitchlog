"""打球群の生成が固定親以外を受けず、既資格/原子性の本文を保持する。"""

import copy
import hashlib

import pytest

from pitchlog.authz import batted_operations_evidence_sql as candidate
from pitchlog.authz import batted_out_evidence_sql as batted_out
from pitchlog.authz import first_ball_product
from pitchlog.authz import interference_evidence_sql as interference
from pitchlog.authz import runner_physical_evidence_sql as runner


def _parent():
    """過去の生成層から固定済み親を再現し、稼働bodyを上書きしない。"""
    declaration = next(
        row
        for row in first_ball_product.ADDITIONS["functions"]
        if row["function_id"] == candidate.FUNCTION_ID
    )
    raw = first_ball_product._D03_BASELINE_BODIES["function|" + candidate.FUNCTION_ID]
    parent = batted_out.overlay_prepared_parent(
        runner.overlay_prepared_parent(raw, declaration), declaration
    )
    assert hashlib.sha256(parent.encode()).hexdigest() == candidate.PARENT_SHA256
    return parent, declaration


def test_batted_group_generation_keeps_qualification_and_every_other_function():
    """親/宣言を破壊せず、観測節の外と全関数登録をそのまま保持する。"""
    parent, declaration = _parent()
    before_declaration = copy.deepcopy(declaration)
    before_bodies = dict(first_ball_product.BODIES)
    result = candidate.overlay_prepared_parent(parent, declaration)
    start = parent.index(" -- 新安打だけの閉分岐。")
    end = "  THEN RAISE EXCEPTION 'batted hit physical source rejected'"
    restored = result
    for old, new in reversed(candidate._physical_replacements()):
        assert restored.count(new) == 3
        restored = restored.replace(new, old)
    assert restored[:start] == parent[:start]
    assert restored[restored.index(end) :] == parent[parent.index(end) :]
    assert declaration == before_declaration
    assert first_ball_product.BODIES == before_bodies
    assert hashlib.sha256(result.encode()).hexdigest() == interference.PARENT_SHA256
    assert (
        interference.overlay_prepared_parent(result, declaration)
        == first_ball_product.BODIES["function|" + candidate.FUNCTION_ID]
    )
    assert candidate.overlay_prepared_parent(parent, declaration) == result
    # 途中再適用で親を偽装せず、未知版は改めてレビューを要する。
    with pytest.raises(ValueError, match="親本文"):
        candidate.overlay_prepared_parent(result, declaration)


@pytest.mark.parametrize("mutation", ["body", "owner", "function", "extra"])
def test_batted_group_refuses_unreviewed_body_or_declaration(mutation):
    """余分な空白/権限/別関数/宣言追加も固定版に読み替えない。"""
    parent, declaration = _parent()
    wrong = copy.deepcopy(declaration)
    if mutation == "body":
        parent += "\n"
    elif mutation == "owner":
        wrong["owner_role_id"] = "pitchlog_app"
    elif mutation == "function":
        wrong["function_id"] = "FUNCTION:public.unreviewed()"
    else:
        wrong["unreviewed_grant"] = True
    with pytest.raises(ValueError, match="親本文または宣言"):
        candidate.overlay_prepared_parent(parent, wrong)
