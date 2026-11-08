"""妨害prepare候補だけの厳格親・宣言・本文差分を検査する。"""

import copy
import hashlib
from pathlib import Path

import pytest

from pitchlog.authz import first_ball_product as product
from pitchlog.authz.interference_evidence_sql import (
    FUNCTION_ID,
    PARENT_SHA256,
    overlay_prepared_parent,
)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "contracts/authz/product/function-bodies/functions"


def _parent_and_declaration():
    """現行正式本文を固定親として読み、同じ宣言1件を取得する。"""
    parent = (CANONICAL / f"{FUNCTION_ID}.sql").read_text()
    rows = [
        row for row in product.ADDITIONS["functions"]
        if row["function_id"] == FUNCTION_ID
    ]
    assert len(rows) == 1
    assert hashlib.sha256(parent.encode()).hexdigest() == PARENT_SHA256
    return parent, rows[0]


def test_only_prepare_body_changes_and_retains_the_other_selected_bodies():
    """唯一prepare以外の全78関数本文を正式原本とbyte比較する。"""
    parent, declaration = _parent_and_declaration()
    body = overlay_prepared_parent(parent, declaration)
    assert product.BODIES["function|" + FUNCTION_ID] == body
    assert body != parent
    assert body.count("interference physical source rejected") == 1
    assert body.count("'妨害裁定アウト'") == 3
    assert body.count("'secondary-result.offensive-interference'") > 0
    seen = 0
    for key, current in product.BODIES.items():
        if not key.startswith("function|") or key == "function|" + FUNCTION_ID:
            continue
        official = CANONICAL / f"{key.removeprefix('function|')}.sql"
        if official.exists():
            assert current == official.read_text(), key
            seen += 1
    assert seen == 78


@pytest.mark.parametrize("fault", ["body", "id", "declaration"])
def test_parent_or_declaration_change_is_rejected(fault):
    """SQL片側改変や宣言差替えを新許可へ取り込まない。"""
    parent, declaration = _parent_and_declaration()
    declaration = copy.deepcopy(declaration)
    if fault == "body":
        parent += " "
    elif fault == "id":
        declaration["function_id"] += "x"
    else:
        declaration["search_path"] = ["public"]
    with pytest.raises(ValueError):
        overlay_prepared_parent(parent, declaration)
