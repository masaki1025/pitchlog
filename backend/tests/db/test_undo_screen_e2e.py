"""実画面の通常1球→取消→再取得→reloadを、owned HTTPS/PG/実appで通す。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import (
    _browser_environment,
    _run_playwright,
)
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="明示TLS証明書/鍵PATH未供給のため取消画面縦断は未実証",
)
def test_screen_undo_https_save_undo_reload(vertical_database) -> None:
    """事前play投入なしの実画面1球保存と取消後のサーバー状態を照合する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = os.environ.get(name)
        assert path and Path(path).is_absolute() and Path(path).is_file()
    db = vertical_database
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        admin.execute(
            "INSERT INTO public.admin_vocabularies(key,category,display_name) "
            "VALUES ('batting-result.ball','batting_result','ボール') "
            "ON CONFLICT(key) DO NOTHING"
        )
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            "GameScreenUndoSpike.playwright.config.ts",
            "undo-spike-https",
            https=True,
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenUndoSpike.playwright.config.ts",
                origin,
                "undo-spike-https",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )
            match = re.search(
                r"PITCHLOG_UNDO_SPIKE_GAME_ID=([0-9a-f-]{36})", result.stdout
            )
            assert match is not None
            created = match.group(1)
            assert created != str(db.game_id)
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for table, expected in (("play_rows", 1), ("operation_events", 2)):
                    count = admin.execute(
                        sql.SQL(
                            "SELECT count(*) FROM public.{} "
                            "WHERE tenant_id=%s AND game_id=%s"
                        ).format(sql.Identifier(table)),
                        (db.tenant_id, created),
                    ).fetchone()
                    assert count == (expected,), (table, count)
                undo = admin.execute(
                    "SELECT d1, target_d1, event_kind FROM public.operation_events "
                    "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
                    (db.tenant_id, created),
                ).fetchall()
                assert undo == [(1, None, "play_input"), (2, 1, "undo")], undo
                ledger = admin.execute(
                    "SELECT count(*) FROM public.idempotency_ledger AS ledger "
                    "JOIN public.operation_events AS op "
                    "ON ledger.tenant_id=op.tenant_id AND ledger.d5=op.d5 "
                    "WHERE op.tenant_id=%s AND op.game_id=%s",
                    (db.tenant_id, created),
                ).fetchone()
                assert ledger == (2,)
