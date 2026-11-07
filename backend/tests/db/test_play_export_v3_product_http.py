"""現行v3新規作成・開始・2球から同TX88列と実ZIPを照合する。"""

from __future__ import annotations

import base64
import csv
import hashlib
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

from pitchlog.authz.play_export_writer_product import candidate_install_sql
from pitchlog.exports.play_rows import CSV_HEADERS

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_terminal_pitch_storage import _lineup_script
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
from .test_terminal_pitch_storage import (
    vertical_database as vertical_database,
)

pytestmark = pytest.mark.requires_db
_ROOT = Path(__file__).resolve().parents[3]


def _v3_export_script() -> str:
    """既現行v3 HTTPの真の2球後に認可付きZIP GETを追加する。"""
    script = _lineup_script()
    old = '''        results = [
            "batting-result.called-pitch",
            "batting-result.called-pitch",
            "batting-result.called-strikeout",
        ] * 3 + ["batting-result.ball"]'''
    new = '''        results = [
            "batting-result.called-pitch",
            "batting-result.called-pitch",
        ]'''
    if script.count(old) != 1 or script.count("if index in (1, 9):") != 1:
        raise AssertionError("現行v3脚本の固定点が変化しました")
    script = script.replace(old, new, 1).replace(
        "if index in (1, 9):", "if index in ():", 1
    )
    diagnostic_anchor = "        runtime_diagnostics.update("
    if script.count(diagnostic_anchor) != 1:
        raise AssertionError("v3の閉診断固定点が変化しました")
    script = script.replace(
        diagnostic_anchor,
        '''        chain = []
        current_error = error
        for _ in range(8):
            if current_error is None:
                break
            frames = traceback.extract_tb(current_error.__traceback__)
            last = frames[-1] if frames else None
            database_error = getattr(current_error, "orig", None)
            chain.append({
                "stage": "sync_apply",
                "type": type(current_error).__name__,
                "sqlstate": getattr(database_error, "sqlstate", None),
                "function": last.name if last else None,
                "line": last.lineno if last else None,
            })
            current_error = current_error.__cause__ or current_error.__context__
        runtime_diagnostics.update(exception_chain=chain,
''',
        1,
    )
    marker = '        return {\n            "game": game,'
    if script.count(marker) != 1:
        raise AssertionError("現行v3の実GET固定点が変化しました")
    injected = '''        import base64
        exported = await client.get(
            "/games/" + game + "/exports/plays.zip", headers=headers()
        )
        assert exported.status_code == 200, (
            "export", exported.status_code, exported.text[:200]
        )
        export_headers = {
            "content_type": exported.headers.get("content-type"),
            "content_length": exported.headers.get("content-length"),
            "sha256": exported.headers.get("x-pitchlog-archive-sha256"),
        }
        absent_export = await client.get(
            "/games/" + str(uuid4()) + "/exports/plays.zip", headers=headers()
        )
        assert absent_export.status_code == 404
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as guest:
            anonymous_export = await guest.get(
                "/games/" + game + "/exports/plays.zip", headers=headers()
            )
            assert anonymous_export.status_code == 401
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://test"
        ) as foreign_client:
            foreign_login = await login(foreign_client, case["other_team_name"])
            assert foreign_login.status_code == 200
            foreign_headers = headers()
            foreign_headers["X-Pitchlog-Expected-Tenant"] = case["other_tenant_id"]
            foreign_export = await foreign_client.get(
                "/games/" + game + "/exports/plays.zip", headers=foreign_headers
            )
            assert foreign_export.status_code == 404
        export_b64 = base64.b64encode(exported.content).decode("ascii")
'''
    script = script.replace(marker, injected + marker, 1)
    script = script.replace(
        '            "game": game,',
        '            "game": game, "export_b64": export_b64, '
        '"export_headers": export_headers,',
        1,
    )
    return script


def _read_saved_export_script() -> str:
    """保存原本を別HTTP要求で読み、200または409を検証する。"""
    setup = _lineup_script().split("async def run():", 1)[0]
    return setup + '''
async def run():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        logged = await login(client, team)
        assert logged.status_code == 200
        result = await client.get(
            "/games/" + case["game"] + "/exports/plays.zip", headers=headers()
        )
        import base64
        return {
            "status": result.status_code,
            "code": (
                result.json().get("error", {}).get("code")
                if result.status_code != 200 else None
            ),
            "export_b64": (
                base64.b64encode(result.content).decode("ascii")
                if result.status_code == 200 else None
            ),
        }
print(json.dumps(asyncio.run(run()), ensure_ascii=False))
'''


def _read_saved_export(db, case: dict[str, str]) -> dict[str, object]:
    """同一owned PGの別App/HTTPで現保存版を読む。"""
    process = subprocess.run(
        ["docker", *_app_arguments(db, case), "-u", "-c", _read_saved_export_script()],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert process.returncode == 0, (process.stdout[-500:], process.stderr[-500:])
    return json.loads(process.stdout)


def test_actual_v3_two_play_snapshot_and_zip_from_new_game(vertical_database):
    """事前投入play/88列を使わず製品writer→ZIPを同版で検証する。"""
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        for key, name in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.ball", "ボール"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, name),
            )
        ddl = (
            _ROOT
            / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
        ).read_text()
        admin.execute(sql.SQL(cast(LiteralString, ddl)))
        admin.execute(sql.SQL(cast(LiteralString, candidate_install_sql())))
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
            ["docker", *_app_arguments(db, case), "-u", "-c", _v3_export_script()],
            capture_output=True,
            text=True,
            timeout=400,
            check=False,
        )
    assert process.returncode == 0, (process.stdout[-500:], process.stderr[-500:])
    output = json.loads(process.stdout)
    assert "exception" not in output, output.get("runtime_diagnostics")
    assert output["prefix"] == "2" and output["history"] == 2
    game = UUID(output["game"])
    with psycopg.connect(db.authority.database.business_admin) as admin:
        snapshots = admin.execute(
            "SELECT source_event_id,plays_csv_json,full_innings_json "
            "FROM public.play_export_snapshots WHERE tenant_id=%s AND game_id=%s "
            "ORDER BY event_sequence",
            (db.tenant_id, game),
        ).fetchall()
        assert len(snapshots) == 2
        for index, (_source, values, innings) in enumerate(snapshots, 1):
            assert set(values) == set(CSV_HEADERS["plays.csv"])
            assert values["球数"] == str(index)
            assert innings[0]["state"] == "in-progress"
    data = base64.b64decode(output["export_b64"], validate=True)
    assert output["export_headers"]["content_type"] == "application/zip"
    assert len(data) == int(output["export_headers"]["content_length"])
    assert hashlib.sha256(data).hexdigest() == output["export_headers"]["sha256"]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert set(archive.namelist()) == set(CSV_HEADERS) | {"manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format_version"] == "pitchlog-play-export-v2-candidate"
        assert manifest["game_id"] == str(game)
        assert {item["name"] for item in manifest["files"]} == set(CSV_HEADERS)
        for item in manifest["files"]:
            raw = archive.read(item["name"])
            assert item["byte_length"] == len(raw)
            assert item["sha256"] == hashlib.sha256(raw).hexdigest()
            rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
            assert item["data_row_count"] == len(rows) - 1
            assert rows[0] == list(CSV_HEADERS[item["name"]])
        plays = list(
            csv.reader(
                io.StringIO(archive.read("plays.csv").decode("utf-8-sig"), newline="")
            )
        )
        assert tuple(plays[0]) == CSV_HEADERS["plays.csv"]
        assert len(plays) == 3
        assert [row[34] for row in plays[1:]] == ["1", "2"]
        innings = list(
            csv.reader(
                io.StringIO(
                    archive.read("inning_scores.csv").decode("utf-8-sig"), newline=""
                )
            )
        )
        assert tuple(innings[0]) == CSV_HEADERS["inning_scores.csv"]
        assert [(row[5], row[6], row[7], row[8]) for row in innings[1:]] == [
            ("1", "top", "in-progress", "0"),
            ("1", "bottom", "unplayed", ""),
        ]
        assert {row[3] for row in innings[1:]} == {str(snapshots[-1][0])}

    # owned disposable DBだけの数式セル注入。製品writerの成功証拠とは別である。
    case["game"] = str(game)
    with psycopg.connect(db.authority.database.business_admin) as admin:
        changed = admin.execute(
            "UPDATE public.play_export_snapshots SET plays_csv_json="
            "pg_catalog.jsonb_set(plays_csv_json, '{打者登録名}', "
            "'\"=1+1\"'::jsonb, false) "
            "WHERE tenant_id=%s AND game_id=%s AND source_event_id=%s "
            "RETURNING play_row_id",
            (db.tenant_id, game, snapshots[-1][0]),
        ).fetchall()
        assert len(changed) == 1
    formula = _read_saved_export(db, case)
    assert formula["status"] == 200
    assert type(formula["export_b64"]) is str
    formula_zip = base64.b64decode(formula["export_b64"], validate=True)
    with zipfile.ZipFile(io.BytesIO(formula_zip)) as archive:
        formula_rows = list(
            csv.reader(
                io.StringIO(archive.read("plays.csv").decode("utf-8-sig"), newline="")
            )
        )
        assert formula_rows[-1][63] == "'=1+1"

    # 同じ使い捨てDBの一原本を破損し、実repository/routeが409へ閉じる。
    with psycopg.connect(db.authority.database.business_admin) as admin:
        changed = admin.execute(
            "UPDATE public.play_export_snapshots SET plays_csv_json='{}'::jsonb "
            "WHERE tenant_id=%s AND game_id=%s AND source_event_id=%s "
            "RETURNING play_row_id",
            (db.tenant_id, game, snapshots[-1][0]),
        ).fetchall()
        assert len(changed) == 1
    unavailable = _read_saved_export(db, case)
    assert unavailable == {
        "status": 409,
        "code": "EXPORT_SOURCE_UNAVAILABLE",
        "export_b64": None,
    }

    # 行内容の破損と別に、対象試合のsnapshot行が一件ない条件を実HTTPへ残す。
    with psycopg.connect(db.authority.database.business_admin) as admin:
        restored = admin.execute(
            "UPDATE public.play_export_snapshots SET plays_csv_json=%s::jsonb "
            "WHERE tenant_id=%s AND game_id=%s AND source_event_id=%s "
            "RETURNING play_row_id",
            (
                json.dumps(snapshots[-1][1], ensure_ascii=False),
                db.tenant_id,
                game,
                snapshots[-1][0],
            ),
        ).fetchall()
        assert len(restored) == 1
        moved = admin.execute(
            "UPDATE public.play_export_snapshots SET game_id=%s "
            "WHERE tenant_id=%s AND game_id=%s AND source_event_id=%s "
            "RETURNING play_row_id",
            (db.game_id, db.tenant_id, game, snapshots[0][0]),
        ).fetchall()
        assert len(moved) == 1
    missing_row = _read_saved_export(db, case)
    assert missing_row == {
        "status": 409,
        "code": "EXPORT_SOURCE_UNAVAILABLE",
        "export_b64": None,
    }
