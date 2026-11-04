"""実画面の三振3打席と反対側球をroot所有の実HTTPS/PGで通す。"""

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
    reason="明示TLS証明書/鍵PATH未供給のため三振画面縦断は未実証",
)
def test_screen_lineup_https_create_strikeouts_reload(vertical_database) -> None:
    """事前game/play投入なしの実画面10球とACK喪失・元要求を照合する。"""
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
        for key, label in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, label),
            )
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db,
            "GameScreenLineupPrefix.playwright.config.ts",
            "lineup-https",
            https=True,
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenLineupPrefix.playwright.config.ts",
                origin,
                "lineup-https",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )
            match = re.search(r"PITCHLOG_LINEUP_GAME_ID=([0-9a-f-]{36})", result.stdout)
            assert match is not None
            created = match.group(1)
            assert created != str(db.game_id)
            with psycopg.connect(db.authority.database.business_admin) as admin:
                for table in ("play_rows", "operation_events", "event_slots"):
                    count = admin.execute(
                        sql.SQL(
                            "SELECT count(*) FROM public.{} "
                            "WHERE tenant_id=%s AND game_id=%s"
                        ).format(sql.Identifier(table)),
                        (db.tenant_id, created),
                    ).fetchone()
                    assert count == (10,), table
                ledger = admin.execute(
                    "SELECT count(*) FROM public.idempotency_ledger AS ledger "
                    "JOIN public.operation_events AS op "
                    "ON ledger.tenant_id=op.tenant_id AND ledger.d5=op.d5 "
                    "WHERE op.tenant_id=%s AND op.game_id=%s",
                    (db.tenant_id, created),
                ).fetchone()
                assert ledger == (10,)
