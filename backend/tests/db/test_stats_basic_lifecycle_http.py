"""真正LC終了版から基本成績を読む実HTTP縦断。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_first_ball_vertical_http import (
    _PASSWORD,
    _PITCH_TYPE,
    _app_arguments,
    _prepare_app_configuration,
)
from .test_game_lifecycle_http import _SCRIPT as _LIFECYCLE_SCRIPT
from .test_game_lifecycle_http import admin_connection as admin_connection
from .test_game_lifecycle_http import (
    initial_scope_database as initial_scope_database,
)
from .test_game_lifecycle_http import product_node_binary as product_node_binary
from .test_game_lifecycle_http import (
    tested_role_connection as tested_role_connection,
)
from .test_game_lifecycle_http import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


def _stats_script() -> str:
    """既LC実経路の同一workerへ成績の真正readだけを追加する。"""
    helper = '''        async def stats_read():
            response = await client.get(
                "/games/" + game + "/stats?mode=official&limit=200",
                headers=headers(),
            )
            assert response.status_code == 200, ("stats-read", response.status_code)
            packet = response.json()
            assert packet["mode"] == "official"
            for player in packet["players"]:
                assert len(player["batting"]) == 16
                assert len(player["pitching"]) == 11
            return packet

        def pitch_count(packet):
            return sum(
                item["value"]
                for player in packet["players"]
                for item in player["pitching"]
                if item["metric_id"] == "pitch_count"
                and item["state"] == "available"
            )

'''
    marker = "        current, _ = await read_full()\n"
    assert _LIFECYCLE_SCRIPT.count(marker) == 1
    script = _LIFECYCLE_SCRIPT.replace(marker, helper + marker, 1)
    marker = '        reopened, reopen_d5 = await lifecycle("reopen", ended)\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        '        first_stats = await stats_read()\n'
        '        assert pitch_count(first_stats) == 1\n' + marker,
        1,
    )
    marker = '        assert reopened["lifecycle"]["lastVersion"] == "1"\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + '        reopened_stats = await stats_read()\n'
        + '        assert reopened_stats["players"] == []\n',
        1,
    )
    marker = '        reload, _ = await read_full()\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        '        final_stats = await stats_read()\n'
        '        assert pitch_count(final_stats) == 3\n'
        '        season_response = await client.get(\n'
        '            "/stats/seasons/" + str(case["year"]) '
        '+ "?category=all&limit=200",\n'
        '            headers=headers(),\n'
        '        )\n'
        '        assert season_response.status_code == 200\n'
        '        season_stats = season_response.json()\n'
        '        assert season_stats["category"] == "all"\n'
        '        assert season_stats["players"]\n'
        '        csv_response = await client.get(\n'
        '            "/games/" + game + "/stats.csv?mode=official",\n'
        '            headers=headers(),\n'
        '        )\n'
        '        assert csv_response.status_code == 200\n'
        '        assert csv_response.content.startswith(bytes.fromhex("efbbbf"))\n'
        '        import csv, io\n'
        '        csv_rows = list(csv.DictReader(io.StringIO(\n'
        '            csv_response.content.decode("utf-8-sig")\n'
        '        )))\n'
        '        assert len(csv_rows) == len(final_stats["players"])\n'
        '        season_csv_response = await client.get(\n'
        '            "/stats/seasons/" + str(case["year"])\n'
        '            + "/stats.csv?category=all", headers=headers(),\n'
        '        )\n'
        '        assert season_csv_response.status_code == 200\n'
        '        assert season_csv_response.content.startswith('
        'bytes.fromhex("efbbbf"))\n'
        '        season_csv_rows = list(csv.DictReader(io.StringIO(\n'
        '            season_csv_response.content.decode("utf-8-sig")\n'
        '        )))\n'
        '        assert len(season_csv_rows) == len(season_stats["players"])\n'
        + marker,
        1,
    )
    marker = '            "controls": [end_d5, reopen_d5, reend_d5],\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + '            "stats_pitch_counts": [pitch_count(first_stats), '
        'pitch_count(final_stats)],\n'
        + '            "stats_csv_rows": len(csv_rows),\n'
        + '            "season_csv_rows": len(season_csv_rows),\n',
        1,
    )
    marker = (
        '            assert invisible.status_code == 404, '
        '("foreign", invisible.status_code)\n'
    )
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + '            foreign_stats = await foreign.get(\n'
        '                "/games/" + game + "/stats?mode=official",\n'
        '                headers=foreign_headers,\n'
        '            )\n'
        '            assert foreign_stats.status_code == 404\n',
        1,
    )
    return script


def test_actual_end_reopen_append_reend_stats_and_csv(vertical_database):
    """偽finalizeなしの実HTTP/PGで終了版更新と二重加算なしを確認する。"""
    db = vertical_database
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "other_tenant": str(db.other_tenant_id),
        "other_team_name": db.other_team_name,
        "year": datetime.now(timezone(timedelta(hours=9))).year,
    }
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        _prepare_app_configuration(db)
        process = subprocess.run(
            ["docker", *_app_arguments(db, case), "-u", "-c", _stats_script()],
            capture_output=True,
            text=True,
            timeout=400,
        )
    assert process.returncode == 0, "基本成績実app workerが異常終了"
    result = json.loads(process.stdout)
    assert "exception_type" not in result, result.get("runtime_diagnostics", {})
    assert result["stats_pitch_counts"] == [1, 3]
    game_id = UUID(result["game"])
    with psycopg.connect(db.authority.database.business_admin) as connection:
        versions = connection.execute(
            "SELECT v.source_count,v.completion_state,"
            "v.completion_receipt_id=h.active_receipt_id,"
            "v.public_pointer_receipt_id=h.active_receipt_id "
            "FROM sync_fence.stats_fact_versions v "
            "JOIN sync_fence.game_lifecycle_heads h ON "
            "h.tenant_id=v.tenant_id AND h.game_id=v.game_id "
            "AND h.active_stats_version_id=v.id "
            "WHERE v.tenant_id=%s AND v.game_id=%s AND v.is_current "
            "AND v.invalidated_at IS NULL",
            (db.tenant_id, game_id),
        ).fetchall()
    assert versions == [(3, "confirmed_ended", True, True)]


def test_stats_script_only_adds_reads_to_existing_lifecycle_flow():
    """元のLC送信/故障注入を変更せず、追加readの構文を閉じる。"""
    script = _stats_script()
    compile(script, "<basic-stats-lifecycle>", "exec")
    assert script.count('await lifecycle("end",') == _LIFECYCLE_SCRIPT.count(
        'await lifecycle("end",'
    )
    assert script.count('await lifecycle("reopen",') == _LIFECYCLE_SCRIPT.count(
        'await lifecycle("reopen",'
    )
