"""受理交代の後続球を同TX CSV snapshotと実ZIPへ接続する。"""

from __future__ import annotations

import base64
import csv
import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from pitchlog.authz.play_export_source_read_product import candidate_read_bundle
from pitchlog.authz.play_export_writer_product import candidate_install_sql

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_play_export_v3_product_http import _read_saved_export
from .test_substitution_vertical_http import _script as substitution_script
from .test_terminal_pitch_storage import (
    admin_connection as admin_connection,
)
from .test_terminal_pitch_storage import (
    initial_scope_database as initial_scope_database,
)
from .test_terminal_pitch_storage import (
    product_node_binary as product_node_binary,
)
from .test_terminal_pitch_storage import (
    tested_role_connection as tested_role_connection,
)
from .test_terminal_pitch_storage import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db
_ROOT = Path(__file__).resolve().parents[3]


def _script() -> str:
    """既交代縦断へ前後の実ZIP取得だけを挿す。"""
    script = substitution_script()
    trace = """
from pitchlog.sync import play_export_producer as actual_csv_writer
_actual_csv_persist = actual_csv_writer.persist_accepted_play_export
def _trace_csv_persist(*args, **kwargs):
    try:
        return _actual_csv_persist(*args, **kwargs)
    except Exception as error:
        chain = []
        for _ in range(8):
            if error is None:
                break
            original = getattr(error, "orig", error)
            diag = getattr(original, "diag", None)
            frames = traceback.extract_tb(error.__traceback__)
            frame = frames[-1] if frames else None
            chain.append({
                "type": type(error).__name__,
                "sqlstate": getattr(original, "sqlstate", None),
                "function": frame.name if frame else None,
                "line": frame.lineno if frame else None,
                "db_function": getattr(diag, "source_function", None),
                "db_line": getattr(diag, "source_line", None),
            })
            error = error.__cause__ or error.__context__
        runtime_diagnostics["csv_chain"] = chain
        raise
actual_csv_writer.persist_accepted_play_export = _trace_csv_persist
"""
    if script.count("async def run():") != 1:
        raise AssertionError("交代縦断の起点が変わりました")
    script = script.replace("async def run():", trace + "\nasync def run():", 1)
    before_anchor = "        before, frames = await read_full()"
    after_anchor = '        return {\n            "game": game,'
    if script.count(before_anchor) != 1 or script.count(after_anchor) != 1:
        raise AssertionError("交代縦断の固定点が変わりました")
    script = script.replace(
        before_anchor,
        """        before_zip = await client.get(
            "/games/" + game + "/exports/plays.zip", headers=headers()
        )
        assert before_zip.status_code == 200, (
            "before-export", before_zip.status_code
        )
        import base64
        before_b64 = base64.b64encode(before_zip.content).decode("ascii")
"""
        + before_anchor,
        1,
    )
    script = script.replace(
        after_anchor,
        """        after_zip = await client.get(
            "/games/" + game + "/exports/plays.zip", headers=headers()
        )
        assert after_zip.status_code == 200, (
            "after-export", after_zip.status_code
        )
        after_b64 = base64.b64encode(after_zip.content).decode("ascii")
"""
        + after_anchor,
        1,
    )
    script = script.replace(
        '            "game": game,',
        '            "game": game, "before_b64": before_b64, "after_b64": after_b64,',
        1,
    )
    return script


def _plays(raw: bytes) -> list[list[str]]:
    """ZIPの受理済みCSVを独立標準readerで復元する。"""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        return list(
            csv.reader(io.StringIO(archive.read("plays.csv").decode("utf-8-sig")))
        )


def _events(raw: bytes) -> list[dict[str, str]]:
    """非投球の受理交代も監査sidecarの実行に残るか読む。"""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return list(
            csv.DictReader(io.StringIO(archive.read("events.csv").decode("utf-8-sig")))
        )


def test_substitution_followed_by_pitch_keeps_old_csv_and_new_pitcher(
    vertical_database,
):
    """実交代・後続球・別HTTP読取に同じ記録時選手を保存する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.called-pitch','batting_result','見逃し') "
            "ON CONFLICT(key) DO NOTHING"
        )
        home = admin.execute(
            "SELECT home_team_record_id FROM public.games WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert home is not None
        admin.execute(
            "INSERT INTO public.players(tenant_id,id,team_record_id,name,"
            "uniform_number,roster_status_key) "
            "VALUES (%s,%s,%s,'交代試験選手','11','active')",
            (db.tenant_id, UUID(int=211), home[0]),
        )
        revision = admin.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        if revision is None or revision[0] < "0047":
            ddl = (
                _ROOT
                / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
            ).read_text()
            admin.execute(sql.SQL(cast(LiteralString, ddl)))
            admin.execute(sql.SQL(cast(LiteralString, candidate_install_sql())))
            _source_query, source_install = candidate_read_bundle()
            admin.execute(sql.SQL(cast(LiteralString, source_install)))
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "other_team_name": db.other_team_name,
        "other_tenant_id": str(db.other_tenant_id),
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _script()],
            capture_output=True,
            text=True,
            timeout=500,
            check=False,
        )
    assert process.returncode == 0, process.stderr[-1000:]
    output = json.loads(process.stdout)
    if "exception_type" in output or "exception" in output:
        print(
            "CSV_SUBSTITUTION_DIAG",
            json.dumps(output.get("runtime_diagnostics", {}), ensure_ascii=False),
        )
    assert "exception_type" not in output and "exception" not in output, output
    game = UUID(output["game"])
    before = _plays(base64.b64decode(output["before_b64"]))
    after_raw = base64.b64decode(output["after_b64"])
    after = _plays(after_raw)
    assert len(before) == 3 and len(after) == 4
    assert after[:3] == before
    assert after[3][71] == "11"
    assert after[3][32] == "交代試験選手"
    event_rows = _events(after_raw)
    substitutions = [row for row in event_rows if row["event_kind"] == "substitution"]
    assert len(substitutions) == 1
    assert substitutions[0]["source_event_id"] == output["substitution_event_id"]
    business = json.loads(substitutions[0]["business_payload_json"])
    assert business["redactionFormatVersion"] == "pitchlog-event-business-redacted-v1"
    assert business["payload"]["incomingSnapshots"] == [
        {"playerId": output["pitcher"], "uniformNumber": "11"}
    ]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        saved = admin.execute(
            "SELECT plays_csv_json FROM public.play_export_snapshots "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY event_sequence",
            (db.tenant_id, game),
        ).fetchall()
    assert len(saved) == 3
    assert saved[-1][0]["投手番号"] == "11"
    reread = _read_saved_export(db, {**case, "game": str(game)})
    assert reread["status"] == 200
    encoded = reread["export_b64"]
    assert isinstance(encoded, str)
    assert _plays(base64.b64decode(encoded)) == after
