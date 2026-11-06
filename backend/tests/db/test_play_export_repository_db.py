"""実記録済み試合を同一snapshot readerで読み、欠測列を実DBで固定する。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from . import test_first_ball_vertical_http as vertical

pytestmark = pytest.mark.requires_db

_MARKER = (
    "        h=headers();after=await client.get('/games/'+game+'/started',headers=h)"
)
_READ = r"""
        from pitchlog.repositories.play_export import (
            PlayExportNotVisible,project_play_cells,read_play_export_source)
        from pitchlog.repositories.tenant_context_issuance import (
            issue_tenant_context_from_presented_token)
        from pitchlog.repositories.transaction import tenant_export_read_scope
        issued=issue_tenant_context_from_presented_token(
            cookie,app.state.token_presentation)
        assert issued is not None
        context,_=issued
        with tenant_export_read_scope(context) as scope:
            source=read_play_export_source(scope,UUID(game))
            plays=list(source.iter_plays())
            assert len(plays)==1, len(plays)
            runners=tuple(source.iter_runners_for((plays[0]['id'],)))
            cells,missing=project_play_cells(source,plays[0],runners)
            out['export']={
                'play_count':len(plays),
                'snapshot_hex':len(source.snapshot.snapshot_id),
                'source_versions_hex':len(source.snapshot.source_versions),
                'missing':sorted(item.header for item in missing),
                'inning':cells.get('回'),
                'half':cells.get('表.裏'),
                'strikes':cells.get('S'),
                'balls':cells.get('B'),
                'outs':cells.get('アウト'),
                'pitch_type':cells.get('球種'),
                'play_number':cells.get('プレイの番号'),
            }
        try:
            with tenant_export_read_scope(context) as scope:
                read_play_export_source(scope,UUID(int=1))
        except PlayExportNotVisible:
            out['missing_game']='not_visible'
        else:
            raise AssertionError('不存在試合を可視として読んだ')
"""  # noqa: E501 — 実app容器へ渡す読取script


def test_recorded_game_reads_same_snapshot_and_reports_exact_gaps(
    vertical_database: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実記録1試合を同じreaderで読み、既知の未接続列だけを欠測にする。"""
    script = vertical._APP_SCRIPT.replace(_MARKER, _READ + _MARKER, 1)
    assert script != vertical._APP_SCRIPT
    monkeypatch.setattr(vertical, "_APP_SCRIPT", script)

    db = vertical_database
    token = uuid4()
    case = {
        "phase": "record",
        "tenant": str(db.tenant_id),
        "game": str(db.game_id),
        "team_name": db.team_name,
        "password": vertical._PASSWORD,
        "start_request_id": str(db.start_request_id),
        "pitch_type": vertical._PITCH_TYPE,
        "course": list(vertical._COURSE),
    }
    with db.broker_worker(token), vertical.binding_broker(db, token):
        vertical._prepare_app_configuration(db)
        value = vertical._run_case(db, case)

    assert value["stages"][-1] == ["started_after", 200], value
    export = value["export"]
    assert export["play_count"] == 1
    assert export["snapshot_hex"] == 64
    assert export["source_versions_hex"] == 64
    assert export["missing"] == [
        "Result_col",
        "bottom_score",
        "top_score",
        "コースX",
        "コースY",
        "先攻打順",
        "後攻打順",
        "打席結果",
        "打球位置X",
        "打球位置Y",
        "球数",
        "球速",
    ]
    assert export["inning"] == "1"
    assert export["half"] == "表"
    assert export["strikes"] == "0"
    assert export["balls"] == "1"
    assert export["outs"] == "0"
    assert export["pitch_type"] == "直球"
    assert export["play_number"] == 1
    assert value["missing_game"] == "not_visible"
