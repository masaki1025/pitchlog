"""実HTTPの新規3球と唯一S identity読取の候補境界を実PGで確認する。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.play_export_source_read_product import candidate_read_bundle
from pitchlog.authz.play_export_writer_product import candidate_install_sql
from pitchlog.repositories.play_export_source_codec import (
    ReadExportSourcePageToken,
    decode_source_page,
)
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

from . import test_ordinary_pitch_vertical_http as ordinary
from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import _PASSWORD, _PITCH_TYPE
from .test_play_export_score_vertical import (
    _SCRIPT_WITH_CHAIN,
)
from .test_play_export_score_vertical import (
    admin_connection as admin_connection,
)
from .test_play_export_score_vertical import (
    initial_scope_database as initial_scope_database,
)
from .test_play_export_score_vertical import (
    product_node_binary as product_node_binary,
)
from .test_play_export_score_vertical import (
    tested_role_connection as tested_role_connection,
)
from .test_play_export_score_vertical import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db
_ROOT = Path(__file__).resolve().parents[3]
_CALL = "SELECT * FROM stats_api.read_play_export_source_page(%s,%s,%s,%s)"


def test_actual_http_sources_match_closed_identity_pages(vertical_database):
    """真正3球保存後に同RRの全sourceと越境/別scope拒否を確認する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        ddl = (
            _ROOT / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
        ).read_text()
        admin.execute(sql.SQL(cast(LiteralString, ddl)))
        admin.execute(sql.SQL(cast(LiteralString, candidate_install_sql())))
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        ordinary._prepare_app_configuration(db)
        process = subprocess.run(
            [
                "docker",
                *ordinary._app_arguments(db, case),
                "-u",
                "-c",
                _SCRIPT_WITH_CHAIN,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    assert process.returncode == 0, (process.stdout[-500:], process.stderr[-500:])
    result = json.loads(process.stdout)
    assert "exception" not in result, result.get("runtime_diagnostics")
    assert result["prefix"] == "3"
    game = UUID(result["game"])
    assert game != db.game_id
    _, install = candidate_read_bundle()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(sql.SQL(cast(LiteralString, install)))
        expected = admin.execute(
            "SELECT s.recording_generation,s.d1,s.d2,s.source_event_id,s.play_row_id,"
            "s.slot_version,s.play_row_version,s.source_fingerprint "
            "FROM sync_fence.stats_primitive_sources s "
            "JOIN sync_fence.stats_fact_versions v ON "
            "(v.tenant_id,v.game_id,v.id)=(s.tenant_id,s.game_id,s.fact_version_id) "
            "WHERE v.tenant_id=%s AND v.game_id=%s AND v.is_current "
            "AND v.invalidated_at IS NULL AND v.model_sha256=%s "
            "ORDER BY s.recording_generation,s.d1",
            (db.tenant_id, game, SOURCE_MODEL_HASH),
        ).fetchall()
        assert len(expected) == 3
    with psycopg.connect(db.authority.database.business_admin, autocommit=True) as app:
        app.execute("SET SESSION AUTHORIZATION pitchlog_app")
        assert app.execute("SELECT session_user,current_user").fetchone() == (
            "pitchlog_app",
            "pitchlog_app",
        )
        with app.transaction():
            app.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            app.execute(
                "SELECT set_config('app.tenant_id',%s,true)", (str(db.tenant_id),)
            )
            header = None
            cursor = None
            identities = []
            for _ in range(4):
                request = ReadExportSourcePageToken(
                    game, *(cursor or (None, None)), page_size=1
                )
                raw = tuple(
                    app.execute(
                        _CALL, (game, request.after_generation, request.after_d1, 1)
                    ).fetchall()
                )
                page = decode_source_page(raw, request, header)
                header = page.version
                if not page.rows:
                    break
                identities.extend(page.rows)
                cursor = page.rows[-1].ordering_key
            else:
                pytest.fail("3sourceの終端がない")
            assert header is not None and header.source_count == 3
            assert header.completion_state == "current_open"
            assert [
                (
                    s.recording_generation,
                    s.d1,
                    s.d2,
                    s.source_event_id,
                    s.play_row_id,
                    s.slot_version,
                    s.play_row_version,
                    s.source_fingerprint,
                )
                for s in identities
            ] == expected
        for tenant, isolation, readonly, params, code in (
            (None, "REPEATABLE READ", True, (game, None, None, 1), "42501"),
            (uuid4(), "REPEATABLE READ", True, (game, None, None, 1), "22023"),
            (db.tenant_id, "READ COMMITTED", True, (game, None, None, 1), "42501"),
            (db.tenant_id, "REPEATABLE READ", False, (game, None, None, 1), "42501"),
            (db.tenant_id, "REPEATABLE READ", True, (game, None, None, 501), "42501"),
            (db.tenant_id, "REPEATABLE READ", True, (game, 1, None, 1), "42501"),
        ):
            with pytest.raises(psycopg.Error) as refused:
                with app.transaction():
                    app.execute(
                        sql.SQL(
                            "SET TRANSACTION ISOLATION LEVEL "
                            + isolation
                            + (" READ ONLY" if readonly else " READ WRITE")
                        )
                    )
                    if tenant is not None:
                        app.execute(
                            "SELECT set_config('app.tenant_id',%s,true)", (str(tenant),)
                        )
                    app.execute(_CALL, params).fetchall()
            assert refused.value.sqlstate == code
