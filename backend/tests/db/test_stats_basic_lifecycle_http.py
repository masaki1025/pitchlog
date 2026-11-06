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
from .test_game_lifecycle_v3_http import _v3_script
from .test_terminal_pitch_storage import admin_connection as admin_connection
from .test_terminal_pitch_storage import (
    initial_scope_database as initial_scope_database,
)
from .test_terminal_pitch_storage import product_node_binary as product_node_binary
from .test_terminal_pitch_storage import (
    tested_role_connection as tested_role_connection,
)
from .test_terminal_pitch_storage import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


def _stats_script() -> str:
    """真正v3二球のLC実経路に成績read/CSVだけを加える。"""
    script = _v3_script()
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
    marker = "        current_lifecycle, _ = await read_full()\n"
    assert script.count(marker) == 1
    script = script.replace(marker, helper + marker, 1)
    marker = '        assert ended["status"] == "finished"\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + '        first_stats = await stats_read()\n'
        + '        assert pitch_count(first_stats) == 2\n',
        1,
    )
    marker = '        assert reopened["status"] == "in_progress"\n'
    assert script.count(marker) == 1
    script = script.replace(
        marker,
        marker
        + '        reopened_stats = await stats_read()\n'
        + '        assert reopened_stats["players"] == []\n',
        1,
    )
    marker = '        assert final["lifecycle"]["lastVersion"] == "2"\n'
    assert script.count(marker) == 1
    final_reads = '''        final_stats = await stats_read()
        assert pitch_count(final_stats) == 3
        season_response = await client.get(
            "/stats/seasons/" + str(case["year"])
            + "?category=all&limit=200", headers=headers(),
        )
        assert season_response.status_code == 200
        season_stats = season_response.json()
        assert season_stats["category"] == "all"
        assert season_stats["players"]
        csv_response = await client.get(
            "/games/" + game + "/stats.csv?mode=official", headers=headers(),
        )
        assert csv_response.status_code == 200
        assert csv_response.content.startswith(bytes.fromhex("efbbbf"))
        import csv, io
        csv_rows = list(csv.DictReader(io.StringIO(
            csv_response.content.decode("utf-8-sig")
        )))
        assert len(csv_rows) == len(final_stats["players"])
        season_csv_response = await client.get(
            "/stats/seasons/" + str(case["year"])
            + "/stats.csv?category=all", headers=headers(),
        )
        assert season_csv_response.status_code == 200
        assert season_csv_response.content.startswith(bytes.fromhex("efbbbf"))
        season_csv_rows = list(csv.DictReader(io.StringIO(
            season_csv_response.content.decode("utf-8-sig")
        )))
        assert len(season_csv_rows) == len(season_stats["players"])
'''
    script = script.replace(marker, marker + final_reads, 1)
    marker = '            "after": current["after"]["stateFields"],\n'
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
    foreign = '''            assert denied_read.status_code == 404, (
                "foreign-read", denied_read.status_code, denied_read.text
            )
'''
    assert script.count(foreign) == 1
    script = script.replace(
        foreign,
        foreign
        + '''            foreign_stats = await foreign_client.get(
                "/games/" + game + "/stats?mode=official",
                headers=foreign_headers,
            )
            assert foreign_stats.status_code == 404
''',
        1,
    )
    return script


def test_actual_end_reopen_append_reend_stats_and_csv(vertical_database):
    """偽finalizeなしの実HTTP/PGで終了版更新と二重加算なしを確認する。"""
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
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": _PASSWORD,
        "pitch_type": _PITCH_TYPE,
        "other_tenant_id": str(db.other_tenant_id),
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
    assert "exception" not in result, result.get("runtime_diagnostics", {})
    assert result["stats_pitch_counts"] == [2, 3]
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
    reference = _v3_script()
    assert script.count('await lifecycle("end",') == reference.count(
        'await lifecycle("end",'
    )
    assert script.count('await lifecycle("reopen",') == reference.count(
        'await lifecycle("reopen",'
    )
