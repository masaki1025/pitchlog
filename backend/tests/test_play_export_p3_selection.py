"""毎球CSVと成績が同じ正規S・訂正済みpayloadを用いる境界を照合する。"""

import copy
import json
import re
from pathlib import Path

import pytest

from pitchlog.authz.play_export_product import connection_declarations
from pitchlog.authz.play_export_source_read_product import candidate_read_bundle
from pitchlog.authz.play_export_writer_product import (
    candidate_function_body,
)
from pitchlog.authz.stats_primitive_sql import _verified_candidate_inputs
from pitchlog.domaingen.play_export_score import (
    _canonical_parts,
    generate_play_export_score_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE = json.loads(
    (ROOT / "backend/tests/fixtures/play_export_p3_selector_v2.json").read_bytes()
)


def test_default_generated_sql_and_writer_bodies_remain_byte_identical():
    """旧SQL/正式bodyを自己期待へ再描画せず、保存済み全byteと照合する。"""
    generated, _ = generate_play_export_score_bundle()
    assert (
        generated
        == (
            ROOT / "backend/src/pitchlog/exports/generated/play_export_score.sql"
        ).read_text()
    )
    bodies = ROOT / "contracts/authz/product/function-bodies/functions"
    _, full_bodies = connection_declarations()
    functions = {
        key: value for key, value in full_bodies.items() if key.startswith("function|")
    }
    assert len(functions) == 4
    # P3現行の共有読取2関数はcapsule item優先の凍結application bodyを正本とする。
    from pitchlog.authz.first_ball_product import BODIES as active_bodies

    p3_bodies = {
        identity: active_bodies["function|" + identity].split("\n\n", 1)[1]
        for identity in (
            "FUNCTION:stats_api:read_writer_play_export_aggregate("
            "uuid, uuid, uuid, uuid, text, bigint, bytea)",
            "FUNCTION:stats_api:read_play_export_source_page("
            "uuid, bigint, bigint, integer)",
        )
    }
    for key, actual in functions.items():
        identity = key.removeprefix("function|")
        canonical = (bodies / f"{identity}.sql").read_text()
        assert canonical.split("\n\n", 1)[1] == p3_bodies.get(identity, actual)


def test_p3_consumers_share_the_official_selector_and_effective_payload():
    """Sを選び直さず所属済みidentityへだけcapsule payloadを結ぶ。"""
    _, sections, _, _ = _verified_candidate_inputs(ROOT, p3_selector_profile=PROFILE)
    prefix, _ = _canonical_parts(sections)
    score, manifest = generate_play_export_score_bundle(p3_selector_profile=PROFILE)
    read_query, read_body = candidate_read_bundle(p3_selector_profile=PROFILE)
    writer = candidate_function_body(p3_selector_profile=PROFILE)
    assert prefix in score and prefix in read_query
    binds = {
        "tenant_id": "tenant",
        "game_id": "p_game_id",
        "model_sha256": "model_hash",
        "after_generation": "p_after_generation",
        "after_d1": "p_after_d1",
        "page_size": "p_page_size",
    }
    bound_prefix = re.sub(
        r"'(?:''|[^'])*'|(?<!:):([a-z][a-z0-9_]*)",
        lambda match: binds[match[1]] if match[1] is not None else match[0],
        prefix,
    )
    assert bound_prefix in read_body
    assert "sync_fence.p3_projection_heads" in score
    assert "THEN export_item.payload ELSE e.payload END AS payload" in score
    assert "s.source_event_id,s.play_row_id)" in score
    assert "s.d1<=export_p3.watermark" in score
    assert "play export writer boundary rejected" in writer
    assert "e.event_kind='play_input'" in writer
    assert "e.xmin::text::numeric" in writer
    assert manifest["candidateNativeSelection"]["profile"] == PROFILE
    assert PROFILE["version"] == 2


@pytest.mark.parametrize("mutation", ["version", "table", "extra", "identity"])
def test_all_csv_consumers_reject_unregistered_selection(mutation):
    """版・表・束縛の改変は生成前に拒否し、任意SQLへ広げない。"""
    changed = copy.deepcopy(PROFILE)
    if mutation == "version":
        changed["version"] = True
    elif mutation == "table":
        changed["p3"]["items"] = "public.operation_events"
    elif mutation == "extra":
        changed["unreviewed"] = True
    else:
        changed["bindingIdentity"].remove("transaction_id")
    for build in (
        generate_play_export_score_bundle,
        candidate_read_bundle,
        candidate_function_body,
    ):
        with pytest.raises(ValueError):
            build(p3_selector_profile=changed)
