"""既成績Sと保存T1の生成SQLを新規3球のowned PGで照合する。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.play_export_writer_product import candidate_install_sql
from pitchlog.exports.play_rows import CSV_HEADERS
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

from . import test_ordinary_pitch_vertical_http as ordinary
from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import _PASSWORD, _PITCH_TYPE
from .test_ordinary_pitch_vertical_http import (
    admin_connection as admin_connection,
)
from .test_ordinary_pitch_vertical_http import (
    initial_scope_database as initial_scope_database,
)
from .test_ordinary_pitch_vertical_http import (
    product_node_binary as product_node_binary,
)
from .test_ordinary_pitch_vertical_http import (
    tested_role_connection as tested_role_connection,
)
from .test_ordinary_pitch_vertical_http import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db
_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_WITH_CHAIN = ordinary._SCRIPT.replace(
    "runtime_diagnostics = {}",
    "def safe_chain(error):\n"
    "    chain=[]\n"
    "    for _ in range(8):\n"
    "        if error is None: break\n"
    "        frames=traceback.extract_tb(error.__traceback__)\n"
    "        chain.append({'type':type(error).__name__,"
    "'site':(frames[-1].name,frames[-1].lineno) if frames else None})\n"
    "        error=error.__cause__ or error.__context__\n"
    "    return chain\n"
    "runtime_diagnostics = {}",
    1,
).replace(
    "exception_type=type(error).__name__,",
    "exception_type=type(error).__name__,exception_chain=safe_chain(error),",
    1,
)


def test_new_three_play_saved_t1_score_and_pitch_count(vertical_database):
    """fixture行を捏造せず実HTTP3球後の生成SQLを同版原本へ照合する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        admin.execute(
            sql.SQL(
                cast(
                    LiteralString,
                    (
                        _ROOT
                        / "docs/features/ud2-csv-export/candidates/"
                        "play_export_snapshots.sql"
                    ).read_text(),
                )
            )
        )
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
    output = json.loads(process.stdout)
    assert "exception" not in output, json.dumps(output.get("runtime_diagnostics"))
    assert output["prefix"] == "3"
    game = UUID(output["game"])
    query = (
        _ROOT / "backend/src/pitchlog/exports/generated/play_export_score.sql"
    ).read_text()
    for name in (
        "tenant_id",
        "game_id",
        "fact_version_id",
        "source_set_sha256",
        "revision",
        "model_sha256",
        "source_event_id",
    ):
        query = query.replace(f":{name}", f"%({name})s")
    with psycopg.connect(db.authority.database.business_admin) as admin:
        rows = admin.execute(
            "SELECT s.source_event_id,v.id,v.revision,v.source_set_sha256 "
            "FROM sync_fence.stats_primitive_sources s "
            "JOIN sync_fence.stats_fact_versions v "
            "ON (s.tenant_id,s.game_id,s.fact_version_id)=(v.tenant_id,v.game_id,v.id) "
            "WHERE s.tenant_id=%s AND s.game_id=%s AND v.is_current "
            "ORDER BY s.d2",
            (db.tenant_id, game),
        ).fetchall()
        assert len(rows) == 3
        snapshots = admin.execute(
            "SELECT source_event_id,plays_csv_json,full_innings_json "
            "FROM public.play_export_snapshots "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY event_sequence",
            (db.tenant_id, game),
        ).fetchall()
        assert len(snapshots) == 3
        for position, (event_id, values, innings) in enumerate(snapshots, 1):
            assert event_id == rows[position - 1][0]
            assert set(values) == set(CSV_HEADERS["plays.csv"])
            assert values["球数"] == str(position)
            assert len(json.loads(values["top_score"])) == 16
            assert len(json.loads(values["bottom_score"])) == 16
            assert innings == [
                {"inning": 1, "half": "top", "state": "in-progress", "runs": 0},
                {"inning": 1, "half": "bottom", "state": "unplayed", "runs": None},
            ]
        for position, (source, version, revision, source_set) in enumerate(rows, 1):
            result = admin.execute(
                sql.SQL(cast(LiteralString, query)),
                {
                    "tenant_id": db.tenant_id,
                    "game_id": game,
                    "fact_version_id": version,
                    "source_set_sha256": source_set,
                    "revision": revision,
                    "model_sha256": SOURCE_MODEL_HASH,
                    "source_event_id": source,
                },
            ).fetchall()
            if len(result) != 1:
                diagnostic_query = query.split(
                    "\nSELECT p.value AS pitcher_pitch_count,", 1
                )[0] + (
                    "\nSELECT (SELECT COUNT(*) FROM version_scope),"
                    "(SELECT COUNT(*) FROM source_members),"
                    "(SELECT COUNT(*) FROM target),"
                    "(SELECT actual_count=source_count FROM member_health),"
                    "(SELECT valid FROM score_health),"
                    "(SELECT valid FROM pitcher_total),"
                    "(SELECT value FROM pitcher_total),"
                    "(SELECT COUNT(*) FROM score_rows),"
                    "(SELECT value IS NOT NULL FROM all_innings);"
                )
                diagnostic = admin.execute(
                    sql.SQL(cast(LiteralString, diagnostic_query)),
                    {
                        "tenant_id": db.tenant_id,
                        "game_id": game,
                        "fact_version_id": version,
                        "source_set_sha256": source_set,
                        "revision": revision,
                        "model_sha256": SOURCE_MODEL_HASH,
                        "source_event_id": source,
                    },
                ).fetchone()
                assert len(result) == 1, diagnostic
            count, top, bottom, innings = result[0]
            assert count == position
            assert len(top) == len(bottom) == 16
            assert top[0] == ""
            assert top[12:] == [0, 0, 0, 0]
            assert bottom[12:] == [0, 0, 0, 0]
            assert innings == [
                {"inning": 1, "half": "top", "state": "in-progress", "runs": 0},
                {"inning": 1, "half": "bottom", "state": "unplayed", "runs": None},
            ]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            admin.execute(
                "SELECT * FROM stats_api.read_writer_play_export_aggregate("
                " %s,%s,%s,%s,%s,%s,%s)",
                (uuid4(), uuid4(), rows[-1][0], rows[-1][1], rows[-1][3], 3, b"x" * 32),
            ).fetchall()
