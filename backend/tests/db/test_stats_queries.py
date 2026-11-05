"""生成canonical S/COUNT/SUM/windowを実native保存後の所有PGで比較する。"""

from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.psycopg import dialect

from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

from .test_play_export_primitives import (
    _run_native_reader,
)
from .test_play_export_primitives import admin_connection as admin_connection
from .test_play_export_primitives import (
    initial_scope_database as initial_scope_database,
)
from .test_play_export_primitives import product_node_binary as product_node_binary
from .test_play_export_primitives import (
    tested_role_connection as tested_role_connection,
)
from .test_play_export_primitives import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


def _queries():
    """唯一生成artifactの固定sectionだけを取り出す。期待値は読まない。"""
    path = (
        Path(__file__).resolve().parents[2]
        / "src/pitchlog/exports/generated/play_primitives.sql"
    )
    raw = path.read_text()
    sections = {}
    for part in raw.split("-- pitchlog-query: ")[1:]:
        name, body = part.split("\n", 1)
        assert name not in sections
        sections[name] = body
    assert set(sections) == {
        "window",
        "count",
        "current_totals",
        "canonical_members",
        "canonical_health",
    }
    return sections


def _execute(conn, sql, parameters):
    """SQLAlchemyの固定bind構文をpsycopg named bindへ下げる。"""
    compiled = text(sql).compile(dialect=dialect(paramstyle="pyformat"))
    return conn.execute(str(compiled), parameters).fetchall()


def test_real_generated_sql_has_same_native_membership_count_and_window(
    vertical_database,
):
    """実保存経路を先に通し、同Sの実SQL結果を独立3球期待と比較する。"""
    db = vertical_database
    # 事前投入のaccepted源や任意receiptを供給せず、実HTTP/保存/唯一readerを通す。
    _run_native_reader(db)
    queries = _queries()
    with psycopg.connect(db.authority.database.business_admin) as conn:
        row = conn.execute(
            "SELECT v.game_id,v.id,v.revision,v.source_set_sha256,f.player_id "
            "FROM sync_fence.stats_fact_versions v "
            "JOIN sync_fence.stats_primitive_facts f "
            "ON f.tenant_id=v.tenant_id AND f.game_id=v.game_id "
            "AND f.fact_version_id=v.id "
            "WHERE v.tenant_id=%s AND v.is_current AND f.metric_id='pitch_count' "
            "GROUP BY v.game_id,v.id,v.revision,v.source_set_sha256,f.player_id",
            (db.tenant_id,),
        ).fetchall()
        assert len(row) == 1, "実native T5保存が未接合か、複数current版である"
        game, version, revision, digest, player = row[0]
        params = {
            "tenant_id": db.tenant_id,
            "game_id": game,
            "player_id": player,
            "model_sha256": SOURCE_MODEL_HASH,
            "fact_version_id": version,
            "revision": revision,
            "source_set_sha256": digest,
            "after_d2": None,
            "after_source_event_id": None,
            "after_metric_id": None,
            "page_size": 500,
            "canonical_after_generation": None,
            "canonical_after_d1": None,
            "canonical_page_size": 500,
        }
        health = _execute(conn, queries["canonical_health"], params)
        assert health == [(1, 3, 0, digest)]
        count = _execute(conn, queries["count"], params)
        assert len(count) == 1 and count[0][4:6] == (3, 78)
        assert count[0][8:] == (3, 3, 0, digest)
        totals = {
            r[0]: r[1:] for r in _execute(conn, queries["current_totals"], params)
        }
        assert totals["pitch_count"] == ("available", 3)
        assert type(totals["pitch_count"][1]) is Decimal
        assert totals["pitching_outs"] == ("available", 0)
        assert totals["runs"] == ("source_unavailable", None)
        first = _execute(conn, queries["window"], {**params, "page_size": 2})
        assert len(first) == 2
        last = first[-1]
        next_page = _execute(
            conn,
            queries["window"],
            {
                **params,
                "page_size": 2,
                "after_d2": last[3],
                "after_source_event_id": last[4],
                "after_metric_id": last[0],
            },
        )
        assert len(next_page) == 2
        assert set((r[3], r[4], r[0]) for r in first).isdisjoint(
            (r[3], r[4], r[0]) for r in next_page
        )
        # 異model/S/版を同Sとして0件成功へ変換しない。
        invalid = _execute(
            conn, queries["current_totals"], {**params, "source_set_sha256": "f" * 64}
        )
        assert all(r[1] == "source_unavailable" and r[2] is None for r in invalid)
        foreign = _execute(
            conn,
            queries["canonical_health"],
            {**params, "tenant_id": UUID("00000000-0000-0000-0000-000000000099")},
        )
        assert foreign[0][:3] == (0, 0, 0)


def test_real_pending_game_is_not_published_as_completed_ops(vertical_database):
    """同版native接合後の所有PGでのみ実行し、未終了試合を集計しない。"""
    from datetime import datetime

    db = vertical_database
    _run_native_reader(db)
    raw = (
        Path(__file__).resolve().parents[2]
        / "src/pitchlog/stats/generated/stats_rates.sql"
    ).read_text()
    sections = dict(
        part.split("\n", 1) for part in raw.split("-- pitchlog-rate-query: ")[1:]
    )
    assert set(sections) == {"season.ops", "game.ops"}
    with psycopg.connect(db.authority.database.business_admin) as conn:
        rows = conn.execute(
            "SELECT v.game_id,f.player_id FROM sync_fence.stats_fact_versions v JOIN sync_fence.stats_primitive_facts f ON f.tenant_id=v.tenant_id AND f.game_id=v.game_id AND f.fact_version_id=v.id WHERE v.tenant_id=%s AND v.is_current AND f.metric_id='pitch_count'",  # noqa: E501 — 生成target/固定SQLのliteral
            (db.tenant_id,),
        ).fetchall()
        assert rows
        game, player = rows[0]
        params = {
            "tenant_id": db.tenant_id,
            "game_id": game,
            "player_id": player,
            "model_sha256": SOURCE_MODEL_HASH,
            "year_start_jst": datetime.fromisoformat("2026-01-01T00:00:00+09:00"),
            "year_end_jst": datetime.fromisoformat("2027-01-01T00:00:00+09:00"),
            "named_category": "all",
            "raw_game_type_keys": [
                "game_official",
                "game_semi_official",
                "game_open",
                "game_intrasquad",
                "game_other",
            ],
        }
        for sql in sections.values():
            result = _execute(conn, sql, params)
            assert len(result) == 1 and tuple(result[0][:5]) == (
                "ops",
                "available",
                "undefined_zero_denominator",
                None,
                None,
            )
            assert tuple(result[0][5:]) == (0, 0, 0, 0)
