# ruff: noqa: E501
"""毎球CSVの実HTTP/ZIPをowned隔離PGで確認する（88列projectionは試験fixture）。"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, LiteralString, cast
from uuid import UUID

import psycopg
import pytest

from pitchlog.exports.play_rows import CSV_HEADERS

from . import test_ordinary_pitch_vertical_http as ordinary
from .owned_pg_network_lock import owned_pg_browser_network_lock
from .test_first_ball_vertical_http import _app_arguments, _prepare_app_configuration
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


@pytest.fixture(autouse=True)
def _owned_pg_network_lock():
    """隔離PGの作成から後始末までを共通ロックで囲む。"""
    with owned_pg_browser_network_lock():
        yield


def _script(body: str) -> str:
    header = ordinary._APP_SCRIPT.split("async def run():")[0]
    return (
        header
        + "\nasync def run():\n"
        + "    from pitchlog.api.routers import game_exports\n"
        + "    app.include_router(game_exports.router)\n"
        + body
        + "\nprint(json.dumps(asyncio.run(run()),ensure_ascii=False))\n"
    )


_READ_SCRIPT = _script(
    r"""
    out={'phase':'play-export'}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='https://test') as client:
        logged=await login(client,team)
        out['login']=logged.status_code
        if logged.status_code!=200:
            out['login_body']=logged.text[:400]
            return out
        absent=await client.get('/games/'+str(uuid4())+'/exports/plays.zip',headers=headers())
        out['missing_game']=absent.status_code
        async with AsyncClient(transport=ASGITransport(app=app),base_url='https://test') as guest:
            anonymous=await guest.get('/games/'+game+'/exports/plays.zip',headers=headers())
            out['anonymous']=anonymous.status_code
        async with AsyncClient(transport=ASGITransport(app=app),base_url='https://test') as foreign_client:
            foreign=await login(foreign_client,case['other_team_name'])
            out['foreign_login']=foreign.status_code
            if foreign.status_code==200:
                foreign_headers=headers()
                foreign_headers['X-Pitchlog-Expected-Tenant']=case['other_tenant']
                foreign_result=await foreign_client.get('/games/'+game+'/exports/plays.zip',headers=foreign_headers)
                out['foreign_game']=foreign_result.status_code
        result=await client.get('/games/'+game+'/exports/plays.zip',headers=headers())
        out['status']=result.status_code
        out['content_type']=result.headers.get('content-type')
        out['content_length']=result.headers.get('content-length')
        out['archive_sha']=result.headers.get('x-pitchlog-archive-sha256')
        out['body']=result.text[:2000] if result.status_code!=200 else None
        if result.status_code==200:
            import io,zipfile
            bundle=zipfile.ZipFile(io.BytesIO(result.content))
            names=sorted(bundle.namelist())
            manifest=json.loads(bundle.read('manifest.json'))
            out['archive_b64']=base64.b64encode(result.content).decode()
            import csv
            plays_text=bundle.read('plays.csv').decode('utf-8-sig')
            parsed_rows=list(csv.reader(io.StringIO(plays_text)))
            out['plays_first_row']=[parsed_rows[1][63]] if len(parsed_rows)>1 else []
            out['files']={name:{
                'size':len(bundle.read(name)),
                'header':bundle.read(name).decode('utf-8-sig').splitlines()[0]
                if name.endswith('.csv') else None,
                'rows':len(bundle.read(name).decode('utf-8-sig').splitlines())-1
                if name.endswith('.csv') else None,
            } for name in names if name.endswith('.csv')}
            out['manifest']=manifest
    return out
"""
)


def _run(db: Any, case: dict[str, Any], script: str) -> dict[str, Any]:
    process = subprocess.run(
        ["docker", *_app_arguments(db, case), "-u", "-c", script],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert process.returncode == 0, (process.stdout[-2000:], process.stderr[-2000:])
    return json.loads(process.stdout)


def _install_snapshot_table(admin: psycopg.Connection[Any]) -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
    )
    admin.execute(cast(LiteralString, path.read_text()))


def _insert_complete_snapshots(
    admin: psycopg.Connection[Any], tenant: UUID, game: UUID
):
    """88列projectionの試験fixture。実記録producerの成功を意味しない。"""
    headers = CSV_HEADERS["plays.csv"]
    values = {header: "" for header in headers}
    values["打者登録名"] = "=1+1"
    rows = admin.execute(
        "SELECT p.id, e.generation, e.d2, p.source_event_id, p.version FROM public.play_rows p "
        "JOIN public.operation_events e "
        "ON e.tenant_id=p.tenant_id AND e.id=p.source_event_id "
        "WHERE p.tenant_id=%s AND p.game_id=%s ORDER BY p.play_number, p.id",
        (tenant, game),
    ).fetchall()
    for play_id, generation, d2, source_event_id, version in rows:
        admin.execute(
            "INSERT INTO public.play_export_snapshots"
            "(tenant_id,game_id,play_row_id,plays_csv_json,"
            "recording_generation,event_sequence,source_event_id,play_version) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                tenant,
                game,
                play_id,
                json.dumps(values),
                generation,
                d2,
                source_event_id,
                version,
            ),
        )
    return len(rows)


def test_play_export_404_409_then_complete_snapshot_200(
    vertical_database, monkeypatch, tmp_path
):
    """未供給は409、snapshot fixture後は実HTTPで10CSV ZIPを返す。"""
    db = vertical_database
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": "public-owned-vertical-password-A1",
        "pitch_type": "u06-first-ball-fastball",
        "other_team_name": db.other_team_name,
        "other_tenant": str(db.other_tenant_id),
    }
    with monkeypatch.context() as patch:
        patch.setattr(
            ordinary,
            "tempfile",
            SimpleNamespace(gettempdir=lambda: str(tmp_path)),
        )
        ordinary.test_actual_http_create_start_three_pitches_replay_and_prefix_reload(
            db
        )
    result = json.loads(
        (
            tmp_path
            / "pitchlog/ordinary37-runtime-source-candidate-20261030"
            / "newAPI-last-result.json"
        ).read_text()
    )
    game = UUID(result["game"])
    case["game"] = str(game)

    _prepare_app_configuration(db)
    missing = _run(db, case, _READ_SCRIPT)
    assert missing["login"] == 200
    assert missing["status"] == 409
    assert missing["body"] is not None
    assert "EXPORT_SOURCE_UNAVAILABLE" in missing["body"]

    with psycopg.connect(db.authority.database.business_admin) as admin:
        _install_snapshot_table(admin)
        count = _insert_complete_snapshots(admin, db.tenant_id, game)
        play_count_row = admin.execute(
            "SELECT count(*) FROM public.play_rows WHERE tenant_id=%s AND game_id=%s",
            (db.tenant_id, game),
        ).fetchone()
        assert play_count_row is not None
        play_count = play_count_row[0]
    assert count == play_count == 3

    complete = _run(db, case, _READ_SCRIPT)
    assert complete["login"] == 200
    assert complete["status"] == 200, complete
    assert complete["content_type"] == "application/zip"
    assert int(complete["content_length"]) > 0
    assert complete["archive_b64"]
    assert complete["manifest"]["game_id"] == str(game)
    assert set(complete["files"]) == set(CSV_HEADERS) - {"manifest.json"}
    assert complete["files"]["plays.csv"]["rows"] == 3
    assert complete["files"]["events.csv"]["rows"] >= 3
    assert "試合日時" in complete["files"]["plays.csv"]["header"]
    assert "play_row_id" in complete["files"]["play_links.csv"]["header"]
    assert complete["missing_game"] == 404
    assert complete["anonymous"] == 401
    assert complete["foreign_login"] == 200
    assert complete["foreign_game"] == 404
    import hashlib

    payload = base64.b64decode(complete["archive_b64"])
    assert len(payload) == int(complete["content_length"])
    assert hashlib.sha256(payload).hexdigest() == complete["archive_sha"]
    assert "'=1+1" in complete["plays_first_row"][0]
