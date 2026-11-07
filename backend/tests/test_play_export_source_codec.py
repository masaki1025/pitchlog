"""唯一Sのsource identity値境界と非補完を検証する。"""

from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from pitchlog.authz.play_export_source_read_product import candidate_read_bundle
from pitchlog.repositories.play_export_source_codec import (
    PlayExportSourceError,
    ReadExportSourcePageToken,
    build_source_read_call,
    decode_source_page,
)

GAME = UUID(int=1)
HEADER = (UUID(int=2), 3, "a" * 64, 1, "current_open", "1:3:")
ITEM = (1, 1, -1000, UUID(int=3), UUID(int=4), 2, 1, UUID(int=5), "wire-v1:" + "b" * 64)


def test_current_source_identity_keeps_slot2_signed_order_and_original_ids():
    """P3の論理位置とeffective物理原本を別値のまま保持する。"""
    page = decode_source_page((HEADER + ITEM,), ReadExportSourcePageToken(GAME))
    assert page.version.fact_version_id == UUID(int=2)
    assert page.rows[0].slot_version == 2
    assert page.rows[0].d2 == -1000
    assert page.rows[0].source_event_id != page.rows[0].base_event_id
    call = build_source_read_call(ReadExportSourcePageToken(GAME))
    sql = str(call.statement.compile(dialect=postgresql.dialect()))
    assert "stats_api.read_play_export_source_page" in sql
    assert tuple(call.parameters) == (
        "game_id",
        "after_generation",
        "after_d1",
        "page_size",
    )


@pytest.mark.parametrize("count", [0, 1, 500, 501])
def test_exact_page_boundary_and_empty_header_sentinel(count):
    """500以外を切捨てず、空集合も実header付きで扱う。"""
    token = ReadExportSourcePageToken(GAME)
    if count == 0:
        page = decode_source_page(
            ((HEADER[:3] + (0,) + HEADER[4:]) + (None,) * 9,), token
        )
        assert page.rows == () and page.version.source_count == 0
    else:
        header = HEADER[:3] + (count,) + HEADER[4:]
        rows = tuple(header + (1, n, *ITEM[2:]) for n in range(1, count + 1))
        if count > 500:
            with pytest.raises(PlayExportSourceError):
                decode_source_page(rows, token)
        else:
            assert len(decode_source_page(rows, token).rows) == count


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "partial-null",
        "bool-int",
        "wrong-completion",
        "bad-hash",
        "not-uuid",
        "duplicate",
        "backwards",
        "stale-version",
        "other-snapshot",
        "empty-with-count",
    ],
)
def test_malformed_or_unbound_source_is_rejected(mutation):
    """余剰・旧版・別snapshot・欠測・逆行を補完せず拒否する。"""
    token = ReadExportSourcePageToken(GAME)
    row: list[Any] = list(HEADER + ITEM)
    expected = None
    if mutation == "missing":
        row.pop()
    elif mutation == "extra":
        row.append(None)
    elif mutation == "partial-null":
        row[10] = None
    elif mutation == "bool-int":
        row[11] = True
    elif mutation == "wrong-completion":
        row[4] = "finished"
    elif mutation == "bad-hash":
        row[2] = "A" * 64
    elif mutation == "not-uuid":
        row[9] = str(row[9])
    elif mutation == "backwards":
        token = ReadExportSourcePageToken(GAME, 1, 1)
    elif mutation == "stale-version":
        expected = replace(decode_source_page((tuple(row),), token).version, revision=4)
    elif mutation == "other-snapshot":
        expected = replace(
            decode_source_page((tuple(row),), token).version, transaction_id="3:4:"
        )
    elif mutation == "empty-with-count":
        row[6:] = [None] * 9
    rows = (tuple(row),) * (2 if mutation == "duplicate" else 1)
    with pytest.raises(PlayExportSourceError):
        decode_source_page(rows, token, expected)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"game_id": str(GAME)},
        {"after_generation": 1},
        {"after_d1": 1},
        {"after_generation": True, "after_d1": 1},
        {"page_size": 0},
        {"page_size": 501},
    ],
)
def test_forged_token_values_do_not_become_sql(kwargs: dict[str, Any]):
    """型やcursor片側だけのtokenをSQLへ渡さない。"""
    with pytest.raises(PlayExportSourceError):
        values: dict[str, Any] = {"game_id": GAME, **kwargs}
        ReadExportSourcePageToken(**values)


def test_generated_source_identity_reuses_the_verified_selector():
    """S条件は既generatorだけから取り、raw PlayRow独自選択をしない。"""
    query, install = candidate_read_bundle()
    assert "canonical_s AS (" in query and "c.source_state='included'" in query
    assert "h.actual_count=h.source_count" in query
    assert "ORDER BY s.recording_generation,s.d1 LIMIT :page_size" in query
    assert "p_page_size>500" in install
    assert "IS DISTINCT FROM 'repeatable read'" in install
    assert "transaction_read_only') IS DISTINCT FROM 'on'" in install
    assert "GRANT SELECT" not in install
