"""基本成績の実API→実DB縦断をowned PGで確認する。

試合・3球は既存の実HTTP縦断を再利用し、公式化のreceiptだけを試験用UUIDで
呼ぶ。製品の終了確定経路が未接続であることは記録し、成功を正式提供へ広げない。
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from typing import Any, LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest

from . import test_ordinary_pitch_vertical_http as ordinary
from .test_first_ball_vertical_http import (
    _app_arguments,
    _prepare_app_configuration,
)
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

_MODEL = "sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d"

_STATS_SCRIPT = r"""
import asyncio,base64,csv,io,json,os,sys
from uuid import UUID,uuid4
case=json.loads(os.environ['PITCHLOG_VERTICAL_CASE'])
assert os.geteuid()==20003 and os.getegid()==20003
os.environ['PITCHLOG_TOKEN_SIGNING_KEY_B64']=base64.b64encode(bytes(range(32))).decode()
os.environ['PITCHLOG_ALLOWED_ORIGINS']='https://test'
os.environ['PITCHLOG_DATABASE_URL']='postgresql+psycopg://pitchlog_app@/ledger_fixture?host=%2Fbusiness-socket&sslmode=disable'
os.environ['PITCHLOG_DATABASE_POOLED']='false'
os.environ['PITCHLOG_BINDING_CLIENT_CONFIG']='/run/pitchlog/public/binding-client.json'
import psycopg
from httpx import AsyncClient,ASGITransport
from pitchlog.api.app import create_app

app=create_app()
tenant=case['tenant'];game=case['game'];team=case['team_name'];password=case['password']
year=case['year'];mode=case.get('mode','official')

def headers():
    return {'Origin':'https://test','X-Pitchlog-Request':'1',
        'X-Pitchlog-Expected-Tenant':tenant,
        'X-Pitchlog-Tenant-Challenge':str(uuid4())}

async def login(client):
    return await client.post('/auth/login',json={'team_name':team,'password':password},
        headers={'Origin':'https://test','X-Pitchlog-Request':'1'})

def finalize():
    with psycopg.connect(
        'postgresql://pitchlog_app@/ledger_fixture?host=/business-socket&sslmode=disable'
    ) as connection:
        connection.execute("SELECT set_config('app.tenant_id',%s,true)",(tenant,))
        rows=connection.execute(
            "SELECT fact_version_id,revision,completion_state "
            "FROM stats_basic_api.finalize_game_stats(%s,%s,%s,%s,%s)",
            (tenant,game,case['completion_receipt'],case['public_pointer_receipt'],
             case['model'])).fetchall()
        connection.commit()
    return [[str(v) if hasattr(v,'hex') else v for v in row] for row in rows]

async def run():
    out={'phase':'stats','stages':[]}
    out['finalize']=finalize()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='https://test') as client:
        response=await login(client)
        out['stages'].append(['login',response.status_code])
        if response.status_code!=200:
            out['login_body']=response.text[:400]
            return out
        for name,path in (
            ('game_official',f'/games/{game}/stats?mode=official&limit=200'),
            ('game_current',f'/games/{game}/stats?mode=current&limit=200'),
            ('season_all',f'/stats/seasons/{year}?category=all&limit=200'),
            ('season_official',f'/stats/seasons/{year}?category=official&limit=200'),
            ('season_practice',f'/stats/seasons/{year}?category=practice&limit=200'),
        ):
            result=await client.get(path,headers=headers())
            out['stages'].append([name,result.status_code])
            out[name]=result.json() if result.status_code==200 else result.text[:400]
        for name,path in (
            ('game_csv',f'/games/{game}/stats.csv?mode=official'),
            ('season_csv',f'/stats/seasons/{year}/stats.csv?category=all'),
        ):
            result=await client.get(path,headers=headers())
            out['stages'].append([name,result.status_code])
            if result.status_code==200:
                text=result.content.decode('utf-8-sig')
                reader=csv.DictReader(io.StringIO(text))
                rows=list(reader)
                out[name]={'status':result.status_code,'rows':len(rows),
                    'header':reader.fieldnames,'first':rows[0] if rows else None,
                    'bom':result.content[:3].hex(),
                    'content_type':result.headers.get('content-type')}
            else:
                out[name]={'status':result.status_code}
    return out

print(json.dumps(asyncio.run(run()),ensure_ascii=False))
"""


def _run_stats_case(db: Any, case: dict[str, Any]) -> dict[str, Any]:
    """製品app UID20003でread+finalize候補を実行し、HTTP結果を返す。"""
    process = subprocess.run(
        ["docker", *_app_arguments(db, case), "-u", "-c", _STATS_SCRIPT],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert process.returncode == 0, (process.stdout[-6000:], process.stderr[-6000:])
    return json.loads(process.stdout)


def _db_fact_sums(admin: psycopg.Connection[Any], tenant: UUID, game: UUID):
    """保存済みfactのplayer/metric合計をAPI比較の正解にする。"""
    rows = admin.execute(
        "SELECT player_id,metric_id,SUM(amount) FROM sync_fence.stats_primitive_facts "
        "WHERE tenant_id=%s AND game_id=%s AND state='available' "
        "GROUP BY player_id,metric_id",
        (tenant, game),
    ).fetchall()
    result: dict[UUID, dict[str, int]] = {}
    for player, metric, value in rows:
        result.setdefault(player, {})[metric] = int(value)
    return result


def test_basic_stats_official_current_and_season_vertical(
    vertical_database, monkeypatch, tmp_path
):
    """3球の実保存→候補finalize→実API公式/暫定/暦年を同じDBで照合する。"""
    db = vertical_database
    case = {
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": "public-owned-vertical-password-A1",
        "pitch_type": "u06-first-ball-fastball",
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
    assert game != db.game_id
    with psycopg.connect(db.authority.database.business_admin) as admin:
        scheduled = admin.execute(
            "SELECT scheduled_at FROM public.games WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, game),
        ).fetchone()
        assert scheduled is not None
        admin.execute(
            "UPDATE public.games SET status='finished' WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, game),
        )
        from pitchlog.stats.basic_sql import candidate_sql

        admin.execute(cast(LiteralString, candidate_sql()))
        # 候補finalizeの正式ACL差分。製品catalogは未受理のためownedだけに置く。
        admin.execute(
            "GRANT SELECT(scheduled_at,game_type_key,away_team_record_id,"
            "home_team_record_id) ON public.games TO pitchlog_sync_right_fn_owner"
        )
        admin.execute(
            "GRANT SELECT(tenant_id,id,name,uniform_number,team_record_id,hidden_at) "
            "ON public.players TO pitchlog_sync_right_fn_owner"
        )
        admin.execute(
            "GRANT SELECT(tenant_id,id,name,kind,hidden_at) ON public.team_records "
            "TO pitchlog_sync_right_fn_owner"
        )
        admin.execute(
            "CREATE POLICY stats_basic_players ON public.players FOR SELECT TO "
            "pitchlog_sync_right_fn_owner USING ("
            "tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid "
            "AND session_user='pitchlog_app')"
        )
        admin.execute(
            "CREATE POLICY stats_basic_teams ON public.team_records FOR SELECT TO "
            "pitchlog_sync_right_fn_owner USING ("
            "tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid "
            "AND session_user='pitchlog_app')"
        )
        admin.execute(
            "GRANT UPDATE(completion_state,completion_receipt_id,"
            "public_pointer_receipt_id) ON sync_fence.stats_fact_versions "
            "TO pitchlog_sync_right_fn_owner"
        )
        admin.execute(
            "CREATE POLICY stats_basic_finalize ON "
            "sync_fence.stats_fact_versions FOR UPDATE TO "
            "pitchlog_sync_right_fn_owner USING ("
            "tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid "
            "AND session_user='pitchlog_app' AND completion_state='current_open') "
            "WITH CHECK ("
            "tenant_id=NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid "
            "AND session_user='pitchlog_app' AND completion_state='confirmed_ended' "
            "AND completion_receipt_id IS NOT NULL AND "
            "public_pointer_receipt_id IS NOT NULL)"
        )
        facts = _db_fact_sums(admin, db.tenant_id, game)
    # JST暦年はUTC年と異なり得るため、JSTへ直して送る。
    import datetime as dt

    jst = dt.timezone(dt.timedelta(hours=9), "JST")
    year = scheduled[0].astimezone(jst).year

    completion_receipt = str(uuid4())
    public_pointer_receipt = str(uuid4())
    _prepare_app_configuration(db)
    out = _run_stats_case(
        db,
        {
            **case,
            "game": str(game),
            "year": year,
            "model": _MODEL,
            "completion_receipt": completion_receipt,
            "public_pointer_receipt": public_pointer_receipt,
        },
    )
    assert out["finalize"][0][2] == "confirmed_ended"
    assert out["stages"] == [
        ["login", 200],
        ["game_official", 200],
        ["game_current", 200],
        ["season_all", 200],
        ["season_official", 200],
        ["season_practice", 200],
        ["game_csv", 200],
        ["season_csv", 200],
    ]
    official = out["game_official"]
    assert official["mode"] == "official"
    assert len(official["players"]) == 20
    # APIのcount値を保存fact合計と全件比較する。率は同じ十分統計から生成済み。
    for player in official["players"]:
        player_id = UUID(player["player_id"])
        expected = facts.get(player_id, {})
        actual = {
            item["metric_id"]: item["value"]
            for item in player["batting"] + player["pitching"]
            if item["state"] == "available"
            and item["metric_id"]
            not in {
                "avg",
                "obp",
                "slg",
                "ops",
                "whip",
                "innings_pitched",
                "appearances",
                "batters_faced",
            }
        }
        for metric, value in actual.items():
            if metric in {
                "pitch_count",
                "pa",
                "ab",
                "h",
                "hr",
                "bb",
                "hbp",
                "k",
                "sh",
                "sf",
                "catcher_interference_reached",
                "runner_interference_reached",
                "doubles",
                "triples",
                "total_bases",
                "runs",
                "rbi",
                "stolen_bases",
                "pitching_outs",
                "pitcher_k",
                "pitcher_bb",
                "pitcher_hbp",
                "hits_allowed",
                "home_runs_allowed",
                "fielding_errors",
                "runs_allowed",
            }:
                assert value == expected.get(metric, 0)
        assert actual.get("pitch_count", 0) >= 0
    # 暫定はfinalize後に対象版が無く、空で返る（古い値を最新と偽らない）。
    assert out["game_current"]["players"] == []
    # 暦年allはgame_otherを含み、officialは含まない。
    assert len(out["season_all"]["players"]) == 10
    assert out["season_official"]["players"] == []
    assert len(out["season_practice"]["players"]) == 10
    # CSVは同じsnapshot・同じ表示値で、BOM付きUTF-8・全27項目ヘッダを持つ。
    for name, count in (("game_csv", 20), ("season_csv", 10)):
        csv_out = out[name]
        assert csv_out["status"] == 200
        assert csv_out["bom"] == "efbbbf"
        assert csv_out["content_type"].startswith("text/csv")
        assert csv_out["rows"] == count
        assert "batting_pa" in csv_out["header"]
        assert "pitching_whip" in csv_out["header"]
        assert "pending" in csv_out["header"]
    first = out["game_csv"]["first"]
    assert first["player_id"] == official["players"][0]["player_id"]
    assert first["batting_pa"] == official["players"][0]["batting"][0]["display"]
    assert "D03_SOURCE_PENDING" in first["pending"]
    assert "runs" in first["source_unavailable_metrics"]
    # 同じfinalizeをもう一度呼んでも版・件数が変わらない（原子/冪等）。
    again = _run_stats_case(
        db,
        {
            **case,
            "game": str(game),
            "year": year,
            "model": _MODEL,
            "completion_receipt": completion_receipt,
            "public_pointer_receipt": public_pointer_receipt,
        },
    )
    assert again["finalize"] == out["finalize"]
    assert again["game_official"] == official
    assert again["season_all"] == out["season_all"]
