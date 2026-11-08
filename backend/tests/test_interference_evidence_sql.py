"""妨害prepare候補だけの厳格親・宣言・本文差分を検査する。"""

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from pitchlog.authz import batted_operations_evidence_sql as batted_operations
from pitchlog.authz import batted_out_evidence_sql as batted_out
from pitchlog.authz import first_ball_product as product
from pitchlog.authz import runner_physical_evidence_sql as runner
from pitchlog.authz.interference_evidence_sql import (
    _BATTED_RULING,
    FUNCTION_ID,
    PARENT_SHA256,
    overlay_prepared_parent,
)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "contracts/authz/product/function-bodies/functions"


def _parent_and_declaration():
    """過去の全生成層からc275固定親を再導出する。"""
    rows = [
        row
        for row in product.ADDITIONS["functions"]
        if row["function_id"] == FUNCTION_ID
    ]
    assert len(rows) == 1
    raw = product._D03_BASELINE_BODIES["function|" + FUNCTION_ID]
    parent = batted_operations.overlay_prepared_parent(
        batted_out.overlay_prepared_parent(
            runner.overlay_prepared_parent(raw, rows[0]), rows[0]
        ),
        rows[0],
    )
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


@pytest.mark.parametrize(
    "fault",
    [
        "old-no-interference",
        "valid-adopted-play",
        "missing-observation",
        "missing-request",
        "both-missing",
        "missing-kind",
        "missing-adopted",
    ],
)
def test_three_valued_missing_ruling_is_not_accepted(fault):
    """各欠落のSQL NULL伝播をJSON1で純比較し、実PGは後続へ分離する。"""
    assert "IS NOT TRUE)" in _BATTED_RULING
    old = {"kind": "not-required"}
    adopted = {
        "kind": "batting-interference",
        "adopted": {"kind": "play-result", "resultId": "batting-result.single"},
    }
    observation, request = adopted, adopted
    if fault == "old-no-interference":
        observation, request = old, "not-required"
    elif fault == "missing-observation":
        observation = None
    elif fault == "missing-request":
        request = None
    elif fault == "both-missing":
        observation, request = None, None
    elif fault == "missing-kind":
        observation = request = {"adopted": adopted["adopted"]}
    elif fault == "missing-adopted":
        observation = request = {"kind": "batting-interference"}
    obs = json.dumps(observation, sort_keys=True) if observation is not None else None
    req = json.dumps(request, sort_keys=True) if request is not None else None
    with sqlite3.connect(":memory:") as connection:
        actual = connection.execute(
            """SELECT
            (json(?) IS DISTINCT FROM json('{"kind":"not-required"}')
             OR json_extract(?, '$') IS DISTINCT FROM 'not-required')
            AND (json(?) IS NOT DISTINCT FROM json(?)
             AND json_extract(?, '$.kind') = 'batting-interference'
             AND json_extract(?, '$.adopted') =
              json_object('kind','play-result','resultId','batting-result.single'))
             IS NOT TRUE""",
            (obs, req, obs, req, obs, obs),
        ).fetchone()[0]
    assert bool(actual) is (fault not in {"old-no-interference", "valid-adopted-play"})
