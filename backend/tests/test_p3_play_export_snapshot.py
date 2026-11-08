"""P3 CSVの同版値境界。DB資格/producer成功を模倣しない。"""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from operator import setitem
from typing import cast
from uuid import UUID

import pytest

from pitchlog.exports.p3_snapshot import (
    P3SnapshotIdentity,
    require_p3_snapshot,
    require_p3_snapshot_page,
)
from pitchlog.exports.play_rows import CSV_HEADERS, PlayExportSupplyError
from pitchlog.repositories.play_export_source_codec import SourceIdentity, SourceVersion


def _fixture(d1=1):
    key = P3SnapshotIdentity(
        UUID(int=1),
        UUID(int=2),
        1,
        UUID(int=3),
        d1,
        UUID(int=10 + d1),
        UUID(int=20 + d1),
        UUID(int=30 + d1),
        1,
        "a" * 64,
        "b" * 64,
        UUID(int=4),
    )
    source = SourceIdentity(
        1,
        d1,
        d1 * 1000,
        key.effective_event_id,
        key.effective_play_row_id,
        1,
        1,
        UUID(int=40 + d1),
        "c" * 64,
    )
    row = {
        **asdict(key),
        "plays_csv_json": {column: None for column in CSV_HEADERS["plays.csv"]},
        "full_innings_json": [],
        "runner_rows_json": [],
        "reference_json": None,
        "captured_at": datetime(2026, 11, 8, tzinfo=timezone.utc),
    }
    version = SourceVersion(UUID(int=5), 2, "d" * 64, 2, "current_open", "123:124:")
    return key, source, row, version


def test_same_capsule_source_and_completed_values_are_preserved():
    """原本の全値を保持し、不正値を完成へ補完しない。"""
    key, source, row, version = _fixture()
    row["plays_csv_json"][CSV_HEADERS["plays.csv"][14]] = "2"
    result = require_p3_snapshot(row, key, source)
    assert result.identity is key
    assert dict(result.values) == row["plays_csv_json"]
    assert result.values[CSV_HEADERS["plays.csv"][14]] == "2"
    with pytest.raises(TypeError):
        setitem(cast(dict[str, str], result.values), "other", "0")
    assert require_p3_snapshot_page(
        (row,), (source,), (key,), version=version, expected_version=version
    ) == (result,)


@pytest.mark.parametrize(
    "field",
    [
        "tenant_id",
        "game_id",
        "capsule_id",
        "original_play_row_id",
        "effective_event_id",
        "effective_play_row_id",
        "capsule_stats_version_id",
    ],
)
def test_cross_scope_or_old_capsule_is_not_a_current_snapshot(field):
    """原本の全値を保持し、不正値を完成へ補完しない。"""
    key, source, row, _ = _fixture()
    row[field] = UUID(int=999)
    with pytest.raises(PlayExportSupplyError):
        require_p3_snapshot(row, key, source)


@pytest.mark.parametrize(
    "field",
    [
        "internal_generation",
        "d1",
        "play_row_version",
        "item_digest",
        "capsule_source_set_digest",
    ],
)
def test_original_identity_and_item_digest_are_fully_compared(field):
    """原本の全値を保持し、不正値を完成へ補完しない。"""
    key, source, row, _ = _fixture()
    row[field] = 2 if type(row[field]) is int else "f" * 64
    with pytest.raises(PlayExportSupplyError):
        require_p3_snapshot(row, key, source)


@pytest.mark.parametrize(
    "mutation", ["extra", "missing", "bool", "partial", "nan", "extra-column"]
)
def test_unknown_shape_or_partial_88_columns_are_not_filled(mutation):
    """原本の全値を保持し、不正値を完成へ補完しない。"""
    key, source, row, _ = _fixture()
    if mutation == "extra":
        row["success"] = True
    elif mutation == "missing":
        del row["item_digest"]
    elif mutation == "bool":
        row["play_row_version"] = True
    elif mutation == "partial":
        row["plays_csv_json"].pop(next(iter(row["plays_csv_json"])))
    elif mutation == "nan":
        row["plays_csv_json"][CSV_HEADERS["plays.csv"][0]] = float("nan")
    else:
        row["plays_csv_json"]["unknown"] = "0"
    with pytest.raises(PlayExportSupplyError):
        require_p3_snapshot(row, key, source)


@pytest.mark.parametrize(
    "mutation",
    [
        "old-version",
        "partial-page",
        "extra-row",
        "duplicate",
        "source-foreign",
        "capsule-replaced",
        "old-transaction",
    ],
)
def test_page_requires_same_rr_source_set_and_one_to_one_supply(mutation):
    """原本の全値を保持し、不正値を完成へ補完しない。"""
    key, source, row, version = _fixture()
    rows = (row,)
    sources = (source,)
    keys = (key,)
    expected = version
    if mutation == "old-version":
        expected = replace(version, revision=1)
    elif mutation == "old-transaction":
        expected = replace(version, transaction_id="123:125:")
    elif mutation == "partial-page":
        rows = ()
    elif mutation == "extra-row":
        rows = (row, row)
    elif mutation == "duplicate":
        rows = (row, row)
        sources = (source, source)
        keys = (key, key)
    elif mutation == "source-foreign":
        sources = (replace(source, source_event_id=UUID(int=999)),)
    else:
        keys = (replace(key, capsule_id=UUID(int=999)),)
    with pytest.raises(PlayExportSupplyError):
        require_p3_snapshot_page(
            rows, sources, keys, version=version, expected_version=expected
        )


def test_second_correction_does_not_accept_the_first_capsule_overlay():
    """原本の全値を保持し、不正値を完成へ補完しない。"""
    key, source, row, version = _fixture()
    second = replace(key, capsule_id=UUID(int=99), item_digest="e" * 64)
    with pytest.raises(PlayExportSupplyError):
        require_p3_snapshot_page(
            (row,), (source,), (second,), version=version, expected_version=version
        )


def test_all_page_values_keep_source_order_without_cross_game_collection():
    """原本の全値を保持し、不正値を完成へ補完しない。"""
    a, sa, ra, v = _fixture(1)
    b, sb, rb, _ = _fixture(2)
    result = require_p3_snapshot_page(
        (ra, rb), (sa, sb), (a, b), version=v, expected_version=v
    )
    assert [x.identity.d1 for x in result] == [1, 2]
    with pytest.raises(PlayExportSupplyError):
        require_p3_snapshot_page(
            (rb, ra), (sb, sa), (b, a), version=v, expected_version=v
        )


def test_shared_source_codec_snapshot_and_wire_prefix_are_preserved():
    """SourceVersionの値はxidではなく実pg_snapshot形式である。"""
    key, source, row, version = _fixture()
    source = replace(source, source_fingerprint="wire-v1:" + "c" * 64, d2=-1000)
    assert (
        len(
            require_p3_snapshot_page(
                (row,), (source,), (key,), version=version, expected_version=version
            )
        )
        == 1
    )
