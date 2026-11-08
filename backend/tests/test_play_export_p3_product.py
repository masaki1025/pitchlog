"""P3 CSV候補の唯一生成源・有限SQL ABI・保存前後境界を検査する。"""

from uuid import UUID

import pytest
from sqlalchemy import text

from pitchlog.authz import play_export_p3_product as product
from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.sync.play_export_p3_producer import (
    P3CsvPriorReceipt,
    _consume_prior,
    prepare_p3_play_export_anchor,
)
from pitchlog.sync.play_export_producer import PlayExportWriterUnavailable


def test_storage_is_append_only_and_has_no_app_or_actor_dml():
    """17列/有限FK/列ACLを固定し、UPDATE/DELETEで履歴を上書きしない。"""
    declaration = product.storage_declaration()
    assert len(declaration["columns"]) == 17
    assert len({v["name"] for v in declaration["columns"]}) == 17
    assert declaration["owner"] == "pitchlog_owner"
    assert declaration["enableRls"] and declaration["forceRls"]
    assert declaration["appendOnly"]
    assert declaration["primaryKey"] == [
        "tenant_id",
        "game_id",
        "internal_generation",
        "capsule_id",
        "d1",
    ]
    assert len(declaration["foreignKeys"]) == 5
    assert declaration["tablePrivileges"] == {}
    assert set(declaration["columnPrivileges"]) == {"pitchlog_sync_right_fn_owner"}
    privileges = declaration["columnPrivileges"]["pitchlog_sync_right_fn_owner"]
    assert set(privileges) == {"SELECT", "INSERT"}
    assert len(privileges["SELECT"]) == 17
    assert privileges["INSERT"] == privileges["SELECT"][:-1]
    assert declaration["noDirectAppDml"] and declaration["noDirectActorDml"]


def test_generated_abi_is_closed_and_keyset_has_no_game_length_limit():
    """writer固有bindを全消費し、25件頁をゲーム長上限に転用しない。"""
    query = product.writer_source_query()
    assert set(text(query)._bindparams) == {
        "tenant_id",
        "game_id",
        "model_sha256",
        "after_generation",
        "after_d1",
        "page_size",
        "transaction_id",
        "capsule_id",
        "change_event_id",
        "prior_capsule_id",
        "recording_generation",
    }
    body = product.candidate_writer_read_body()
    assert not text(body)._bindparams
    assert "p_page_size>25" in body
    assert "p_after_d1>=watermark_bound" in body
    assert "watermark_bound>500" not in body
    assert "prior_item.payload=i.original_payload" in body
    assert "prior_item.history_entry=i.original_history_entry" in body
    assert "prior_item.play_row=i.original_play_row" in body
    assert "prior_item.play_runners=i.original_play_runners" in body
    assert "prior_csv.item_digest" in body
    assert "prior_cap.stats_version_id=p_prior_native_version_id" not in body
    assert "NOT old.is_current AND old.invalidated_at IS NOT NULL" in body
    assert "a.transaction_id=own_xid AND a.state='consumed'" in body
    assert "MAX(" not in body and "ORDER BY captured_at" not in body


def test_before_anchor_reads_real_cp_and_source_not_latest_guess():
    """保存前にのみ現在S/CP/headを固定し、後から旧headを推定しない。"""
    body = product.candidate_prior_read_body()
    assert "P3 CSV prior source already published" in body
    assert "FROM sync_fence.stats_fact_versions v" in body
    assert "v.source_count=p_watermark" in body
    assert "JOIN sync_fence.ordinary_pitch_checkpoints cp" in body
    assert "sync_fence.stats_primitive_sources s" in body
    assert "is_current" not in body
    assert "count(*) FROM sync_fence.stats_primitive_sources s" in body
    assert "p_checkpoint_id,p_checkpoint_revision,p_checkpoint_digest" in body
    assert "h.capsule_id,v.id,cp.id,cp.revision,cp.content_digest" in body
    assert "b.transaction_id=own_xid" in body
    assert "LIMIT 500" not in body
    assert "MAX(" not in body and "ORDER BY captured_at" not in body


def test_carry_uses_original_full_values_suffix_only_uses_sole_score_query():
    """先行はDB carry、suffixだけ既唯一生成SQL、訂正時語彙を実lookupする。"""
    body = product.candidate_save_body()
    assert product.writer_score_query() in body
    assert "IF p_direct_json IS NULL THEN" in body
    assert "expected_count:=LEAST(25,target-p_d1)::integer" in body
    assert "FROM valid x ORDER BY x.d1" in body
    assert "inserted_count IS DISTINCT FROM expected_count" in body
    assert "IF ctx.d1<ctx.target_d1 THEN" in body
    assert "IF p_direct_json IS NOT NULL" in body
    assert "finished_json:=ctx.original_csv_json;" in body
    assert "ctx.original_history_entry IS DISTINCT FROM ctx.history_entry" in body
    assert "ctx.original_play_runners IS DISTINCT FROM ctx.play_runners" in body
    assert "INSERT INTO sync_fence.play_export_p3_snapshots" in body
    assert "UPDATE sync_fence.play_export_p3_snapshots" not in body
    assert "DELETE FROM" not in body
    assert "'p3-csv-references-v1'" in body
    assert "'capturedAt',ctx.reference_captured_at" in body
    assert "'priorCapsuleId',p_prior_capsule_id" in body
    query = product.writer_source_query()
    assert "v.category='batting_result' AND NOT v.disabled" in query
    assert "v.display_name AS replacement_label" in query
    assert "v.hidden_at" not in query
    # 元列88と直接列85の閉集合がSQLに全列出力される。
    for name in CSV_HEADERS["plays.csv"]:
        assert "'" + name + "'" in body


@pytest.mark.parametrize("name", ["unknown", "prior_capsule_ids"])
def test_unknown_writer_query_bind_is_not_interpolated(monkeypatch, name):
    """query差替え・未知bindを黙って実行可能SQLへ補修しない。"""
    original = product.writer_source_query()
    monkeypatch.setattr(
        product, "writer_source_query", lambda root: original + f":{name}"
    )
    with pytest.raises(ValueError):
        product.candidate_writer_read_body()


def test_receipt_cannot_be_minted_or_consumed_from_free_values():
    """資格を自由stubで肯定せず、不発行/偽frameの拒否を検査する。"""
    with pytest.raises(PlayExportWriterUnavailable):
        P3CsvPriorReceipt()
    forged = object.__new__(P3CsvPriorReceipt)
    with pytest.raises(PlayExportWriterUnavailable):
        _consume_prior(object(), object(), object(), forged, object())
    with pytest.raises(PlayExportWriterUnavailable):
        prepare_p3_play_export_anchor(object(), UUID(int=1), object())
