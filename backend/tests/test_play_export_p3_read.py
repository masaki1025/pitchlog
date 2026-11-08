"""P3 CSV readerの値/ABI正負。真正DB資格の成功は模倣しない。"""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from test_p3_play_export_projection import _inputs

from pitchlog.authz.play_export_p3_read_product import candidate_read_body
from pitchlog.exports.p3_projection import project_p3_direct
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories import play_export_p3_read as read
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.play_export_source_codec import SourceVersion
from pitchlog.sync.idempotency import source_fingerprint


def _page():
    values, item, identity, reference = _inputs()
    aggregate = {
        CSV_HEADERS["plays.csv"][n]: values[CSV_HEADERS["plays.csv"][n]]
        for n in (34, 86, 87)
    }
    values = {
        **project_p3_direct(values, item, identity, target_d1=1, reference=reference),
        **aggregate,
    }
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    db_item = {k: v for k, v in item.items() if k != "digest"}
    db_item.update(
        tenant_id=str(identity.tenant_id),
        game_id=str(identity.game_id),
        internal_generation=identity.internal_generation,
        capsule_id=str(identity.capsule_id),
        item_digest=item["digest"],
    )
    row = {
        **asdict(identity),
        "plays_csv_json": values,
        "full_innings_json": [],
        "runner_rows_json": item["play_runners"],
        "captured_at": now,
        "capsule_watermark": 2,
        "capsule_target_d1": 1,
        "current_head": True,
        "item_json": db_item,
        "reference_json": {
            "formatVersion": "p3-csv-references-v1",
            "priorCapsuleId": None,
            "priorNativeVersionId": str(UUID(int=99)),
            "priorCheckpoint": {
                "id": str(UUID(int=98)),
                "revision": 1,
                "digest": "a" * 64,
            },
            "replacementResult": {
                "id": str(reference.reference_id),
                "key": reference.key,
                "displayName": reference.display_name,
                "capturedAt": now.isoformat(),
                "capsuleId": str(identity.capsule_id),
                "effectiveEventId": str(identity.effective_event_id),
            },
        },
    }
    version = SourceVersion(UUID(int=100), 1, "a" * 64, 2, "current_open", "10:11:")
    return row, version


def _wire(row, version, count=2):
    return (
        *asdict(version).values(),
        count,
        *(row[name] for name, _ in read._ROW_OUTPUTS),
    )


def test_exact_values_and_database_item_are_preserved():
    """Data fixtureでDB成功を主張せず、同版rowだけを全値保持する。"""
    row, version = _page()
    before = deepcopy(row)
    count, values = read.decode_page(
        (_wire(row, version),), read.ReadP3ExportPage(row["game_id"]), version
    )
    assert count == 2 and values == (row,)
    assert row == before
    assert (
        source_fingerprint(
            {
                k: v
                for k, v in row["item_json"].items()
                if k
                not in {
                    "tenant_id",
                    "game_id",
                    "internal_generation",
                    "capsule_id",
                    "item_digest",
                }
            }
        )
        == row["item_digest"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "tenant",
        "game",
        "capsule",
        "item",
        "snapshot-extra",
        "snapshot-missing",
        "bool-watermark",
        "unknown-item-key",
        "reference-key",
        "reference-time",
        "reference-capsule",
        "naive-time",
    ],
)
def test_corrupted_snapshot_item_or_reference_is_not_supply(mutation):
    """余剰/欠落/同時metadata差替え/非正準参照を成功に変えない。"""
    row, version = _page()
    game = row["game_id"]
    if mutation in {"tenant", "game", "capsule"}:
        key = {"tenant": "tenant_id", "game": "game_id", "capsule": "capsule_id"}[
            mutation
        ]
        row[key] = UUID(int=99999)
    elif mutation == "item":
        row["item_json"]["payload"] = {}
    elif mutation == "snapshot-extra":
        row["plays_csv_json"]["extra"] = "0"
    elif mutation == "snapshot-missing":
        del row["plays_csv_json"][next(iter(row["plays_csv_json"]))]
    elif mutation == "bool-watermark":
        row["capsule_watermark"] = True
    elif mutation == "unknown-item-key":
        row["item_json"]["extra"] = 1
    elif mutation == "reference-key":
        row["reference_json"]["replacementResult"]["key"] = "unknown"
    elif mutation == "reference-time":
        row["reference_json"]["replacementResult"]["capturedAt"] = "2026-11-09"
    elif mutation == "reference-capsule":
        row["reference_json"]["replacementResult"]["capsuleId"] = str(UUID(int=888))
    else:
        row["captured_at"] = datetime(2026, 11, 9)
    with pytest.raises(PlayExportSupplyError):
        read.decode_page((_wire(row, version),), read.ReadP3ExportPage(game), version)


def test_old_header_extra_column_duplicate_and_reverse_cursor_reject():
    """版差替え/余剰列/同一位置再送/逆行を区別なく閉拒否する。"""
    row, version = _page()
    token = read.ReadP3ExportPage(row["game_id"])
    wire = _wire(row, version)
    with pytest.raises(PlayExportSupplyError):
        read.decode_page(
            (wire,), token, replace(version, fact_version_id=UUID(int=200))
        )
    for rows in ((wire + (None,),), (wire, wire)):
        with pytest.raises(PlayExportSupplyError):
            read.decode_page(rows, token, version)
    cursor = read.ReadP3ExportPage(
        row["game_id"], row["internal_generation"], row["capsule_id"], row["d1"]
    )
    with pytest.raises(PlayExportSupplyError):
        read.decode_page((wire,), cursor, version)


def test_same_rr_sentinel_has_no_fake_overlay_and_respects_header():
    """0件/頁終端はheaderだけにし偽snapshotを生成しない。"""
    row, version = _page()
    sentinel = (*asdict(version).values(), 0, *(None for _ in read._ROW_OUTPUTS))
    assert read.decode_page(
        (sentinel,), read.ReadP3ExportPage(row["game_id"]), version
    ) == (0, ())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page_size": 501},
        {"page_size": True},
        {"after_d1": 1},
        {"after_generation": 1, "after_capsule_id": UUID(int=1)},
    ],
)
def test_partial_cursor_and_overlimit_token_are_rejected(kwargs):
    """game長を制限せず単頁だけ500に制限する。"""
    with pytest.raises(PlayExportSupplyError):
        read.ReadP3ExportPage(UUID(int=1), **kwargs)


def test_reader_cannot_use_fake_scope_and_generic_decoder_is_closed():
    """任意Session/runner/fake handleでread資格を作らない。"""
    with pytest.raises(TenantBindingError):
        read.ReadP3ExportSnapshots(object(), UUID(int=1), _page()[1])
    with pytest.raises(read.FunctionOperationError):
        read._deny_generic_decode(object())


def test_generated_sql_binds_exact_catalog_item_and_sole_s_in_read_only_rr():
    """通常read ABIを変更せず、同RR/500keyset/全17列をSQLへ固定する。"""
    sql = candidate_read_body()
    assert "'repeatable read'" in sql and "IS DISTINCT FROM 'on'" in sql
    assert "p_page_size>500" in sql
    assert "SUM(c.watermark)" in sql
    assert "(c.tenant_id,c.game_id)=(tenant,p_game_id)" in sql
    assert "x.capsule_source_set_digest,x.capsule_stats_version_id" in sql
    assert (
        "i.item_digest,i.original_play_row_id,i.effective_event_id,i.effective_play_row_id"
        in sql
    )
    assert "ORDER BY x.internal_generation,x.capsule_id,x.d1 LIMIT p_page_size" in sql
    assert "UPDATE " not in sql and "DELETE " not in sql
    assert read.registration_shape()["max_rows"] == 500
