"""実HTTPS画面の2球2取消次球。作者collectのみ、root所有環境で実行する。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    and not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="実HTTPS証明書PATH未供給。画面縦断は未実証",
)
def test_screen_create_two_pitches_two_undo_next_pitch_reload(vertical_database):
    """事前game投入を実証にせず、新UIが作ったgameの原本を実DBで照合する。"""
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
    assert teams is not None
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(
            db, "GameScreenUndoProduct.playwright.config.ts", "undo-product", https=True
        ) as origin:
            result = _run_playwright(
                db,
                "GameScreenUndoProduct.playwright.config.ts",
                origin,
                "undo-product",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            if result.returncode != 0:
                attempted = re.findall(
                    r"PITCHLOG_UNDO_ATTEMPT_GAME=([a-f0-9-]{36})", result.stdout
                )
                if len(attempted) == 1:
                    with psycopg.connect(
                        db.authority.database.business_admin,
                        options="-c default_transaction_read_only=on",
                    ) as diagnostic:
                        events = diagnostic.execute(
                            "SELECT d1,event_kind FROM public.operation_events "
                            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1 LIMIT 10",
                            (db.tenant_id, UUID(attempted[0])),
                        ).fetchall()
                        ledger = diagnostic.execute(
                            "SELECT kind,reason,count(*) "
                            "FROM public.idempotency_ledger WHERE tenant_id=%s "
                            "GROUP BY kind,reason ORDER BY kind,reason",
                            (db.tenant_id,),
                        ).fetchall()
                        integrity = diagnostic.execute(
                            "SELECT jsonb_build_object("
                            "'state',a.state='consumed',"
                            "'saved_at',a.consumed_at=c.saved_at,"
                            "'checkpoint_id',a.checkpoint_id=c.id,"
                            "'revision',a.checkpoint_revision+1=c.revision,"
                            "'content',a.next_checkpoint_content=c.content,"
                            "'roster',a.roster_snapshot=c.roster,"
                            "'tx_cp',a.xmin=c.xmin,"
                            "'tx_event',e.xmin=a.xmin,"
                            "'tx_ledger',l.xmin=a.xmin,"
                            "'tx_slot',es.xmin=a.xmin,"
                            "'top_xid',a.xmin::text::numeric=mod(a.transaction_id::numeric,4294967296),"
                            "'source_d2',e.d2=a.source_d2,"
                            "'source_d5',e.d5=a.d5,"
                            "'ledger_fingerprint',l.source_fingerprint=a.event_fingerprint,"
                            "'head_id',c.content->'last_source'->>'id'=e.id::text,"
                            "'head_d5',c.content->'last_source'->>'d5'=e.d5::text,"
                            "'head_fingerprint',c.content->'last_source'->>'source_fingerprint'=l.source_fingerprint,"
                            "'wire_d4',c.content->>'wire_d4'=a.wire_d4,"
                            "'confirmed_version',es.confirmed_version=1) "
                            "FROM sync_fence.ordinary_pitch_checkpoints c "
                            "JOIN sync_fence.ordinary_pitch_write_admissions a "
                            "ON a.tenant_id=c.tenant_id AND a.game_id=c.game_id "
                            "AND a.internal_generation=c.internal_generation "
                            "AND a.source_d1=c.confirmed_watermark "
                            "JOIN public.operation_events e ON e.tenant_id=a.tenant_id "
                            "AND e.game_id=a.game_id AND e.id=a.source_event_id "
                            "JOIN public.idempotency_ledger l ON l.tenant_id=e.tenant_id AND l.d5=e.d5 "
                            "JOIN public.event_slots es ON (es.tenant_id,es.game_id,es.generation,es.d1)="
                            "(e.tenant_id,e.game_id,e.generation,e.d1) "
                            "WHERE c.tenant_id=%s AND c.game_id=%s AND c.state='current' LIMIT 2",
                            (db.tenant_id, UUID(attempted[0])),
                        ).fetchall()
                    print("PITCHLOG_UNDO_FAILURE_INTEGRITY=" + json.dumps(integrity))
                    print(
                        "PITCHLOG_UNDO_FAILURE_DB="
                        + json.dumps(
                            {"events": events, "ledger_kind_reason_counts": ledger},
                            ensure_ascii=False,
                        )
                    )
            assert result.returncode == 0, (
                result.stdout[-8000:],
                result.stderr[-3000:],
            )
    matches = re.findall(r"PITCHLOG_UNDO_PRODUCT_GAME=([a-f0-9-]{36})", result.stdout)
    assert len(matches) == 1
    created = UUID(matches[0])
    assert created != db.game_id
    with psycopg.connect(db.authority.database.business_admin) as admin:
        events = admin.execute(
            "SELECT d1,event_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s AND ledger_kind='accepted' "
            "ORDER BY d1",
            (db.tenant_id, created),
        ).fetchall()
        assert events == [
            (1, "play_input"),
            (2, "play_input"),
            (3, "undo"),
            (4, "undo"),
            (5, "play_input"),
        ]
        plays = admin.execute(
            "SELECT play_number,hidden_at IS NOT NULL FROM public.play_rows "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY play_number",
            (db.tenant_id, created),
        ).fetchall()
        assert plays == [(1, True), (2, True), (3, False)]
