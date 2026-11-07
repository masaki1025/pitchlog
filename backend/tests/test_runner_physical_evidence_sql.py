"""走者原観測の限定SQL overlayと旧本文不変性の純検査。"""

import copy
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.authz import first_ball_product
from pitchlog.authz.runner_physical_evidence_sql import (
    FUNCTION_ID,
    PARENT_SHA256,
    overlay_prepared_parent,
)
from pitchlog.domainrt.lineup_play_prefix_continuation import (
    decode_lineup_prefix_request,
    decode_lineup_prefix_response,
)
from pitchlog.sync.runner_physical_labels import (
    ADVANCE_STATUS_BY_BASE_DESTINATION,
    OUT_STATUS_BY_OBSERVED_KIND,
)
from pitchlog.sync.terminal_pitch_projection import runner_physical_rows

_ROOT = Path(__file__).resolve().parents[2]


def _parent() -> tuple[str, dict[str, object]]:
    """現行正式候補の元本文と唯一宣言をそのまま読む。"""
    rows = [
        row
        for row in first_ball_product.ADDITIONS["functions"]
        if row["function_id"] == FUNCTION_ID
    ]
    assert len(rows) == 1
    return first_ball_product._D03_BASELINE_BODIES["function|" + FUNCTION_ID], rows[0]


def test_runner_overlay_accepts_only_pinned_parent_and_keeps_other_functions():
    """P3/旧writer/readerを無変更とし、未知の親body/宣言を拒否する。"""
    parent, declaration = _parent()
    assert hashlib.sha256(parent.encode()).hexdigest() == PARENT_SHA256
    before = dict(first_ball_product.BODIES)
    result = overlay_prepared_parent(parent, declaration)
    assert result != parent
    assert len(result) > len(parent)
    assert result.count("runner physical evidence rejected") == 16
    assert "runnerObservation' THEN false ELSE" in result
    assert "runnerDefaultAdvance'->'" in result
    assert (
        result.count("CREATE FUNCTION sync_right_api.prepare_play_prefix_projection(")
        == 1
    )
    assert first_ball_product.BODIES == before
    for name in (
        "guard_play_prefix_runner_insert()",
        "finish_play_prefix_projection()",
        "read_play_prefix_history_page(uuid, uuid, bigint, bigint, uuid, "
        "bigint, bigint, bigint, bigint, bigint, uuid, integer)",
    ):
        assert any(name in key for key in before)
    with pytest.raises(ValueError, match="親本文"):
        overlay_prepared_parent(
            parent.replace("FOR UPDATE OF s", "FOR SHARE OF s"), declaration
        )
    wrong = copy.deepcopy(declaration)
    wrong["owner_role_id"] = "pitchlog_app"
    with pytest.raises(ValueError, match="宣言"):
        overlay_prepared_parent(parent, wrong)


def test_only_v3_runner_check_is_wrapped_and_preserved():
    """旧判定本文を削除せず、v3 RunnerEvent時だけ新照合へ分ける。"""
    parent, declaration = _parent()
    result = overlay_prepared_parent(parent, declaration)
    marker = (
        " THEN RAISE EXCEPTION 'lineup physical source rejected' "
        "USING ERRCODE='42501'; END IF;"
    )
    assert parent.count(marker) == result.count(marker) == 1
    parent_start = parent.rfind(
        " IF pg_catalog.jsonb_array_length", 0, parent.index(marker)
    )
    result_start = result.rfind(
        " IF pg_catalog.jsonb_array_length", 0, result.index(marker)
    )
    assert result[:result_start] == parent[:parent_start]
    assert (
        "runnerAdvanceOverrides'->'overrides'"
        in result[result_start : result.index(marker)]
    )
    assert (
        result[result.index(" -- 新安打だけの閉分岐。") :]
        == parent[parent.index(" -- 新安打だけの閉分岐。") :]
    )
    assert "rp_per->'runnerEventPayload'->'by_runner'" in result
    assert "rp_per->'runnerAdvanceOverridesByRunner'->'by_runner'" in result
    assert "rp_t1->'runnerObservation' IS DISTINCT FROM" in result
    assert "'batting-result.called-pitch'" in result
    assert "rp_t1->'runnerObservation'->>'primaryResultId'" in result
    assert "rp_target_count<>1" in result


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, [("投手牽制死", "manual")]),
        (1, [("投手牽制死", "manual")]),
        (2, [("盗塁死", "manual")]),
        (3, [("二進", "manual"), ("三進", "manual"), ("本進", "manual")]),
        (4, [("二進", "manual"), ("三進", "manual"), ("本進", "manual")]),
        (5, [("二進", "manual"), ("三進", "manual"), ("本進", "manual")]),
        (6, [("二進", "manual")]),
    ],
)
def test_existing_host_output_uses_one_physical_label_set(index, expected):
    """既採用候補の観測/唯一T1から作る10列とSQLラベル宣言を束縛する。"""
    cases = json.loads(
        (
            _ROOT
            / "docs/features/mvp-runner-operations-connection/candidate-cases.json"
        ).read_text()
    )["cases"]
    case = cases[index]
    request = decode_lineup_prefix_request(json.dumps(case["request"]))
    response = decode_lineup_prefix_response(json.dumps(case["expected"]))
    assert response.ok is True
    rows = runner_physical_rows(
        request.source.runners,
        t1=response.value.t1,
        t1_input=request.t1,
        tenant_id=UUID(request.prefix_ref.tenant_id),
        play_id=UUID(request.play_identity.play_id),
    )
    assert [(row["status"], row["status_source"]) for row in rows] == expected
    assert all(
        row["status"]
        in {"継続", *OUT_STATUS_BY_OBSERVED_KIND.values()}
        | {
            status
            for destinations in ADVANCE_STATUS_BY_BASE_DESTINATION.values()
            for status in destinations.values()
        }
        for row in rows
    )
