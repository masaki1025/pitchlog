"""候補0048を隔離owned DBへ配備して、真正P3画面を確認する。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from .sync_writer_binding_support import binding_broker
from .test_p3_candidate_compile_author import _PACKET
from .test_p3_candidate_compile_author import (
    test_owned_candidate_0048_compiles as _install_p3_candidate,
)
from .test_screen_start_e2e import _browser_environment, _run_playwright
from .test_screen_start_e2e import admin_connection as admin_connection
from .test_screen_start_e2e import initial_scope_database as initial_scope_database
from .test_screen_start_e2e import product_node_binary as product_node_binary
from .test_screen_start_e2e import tested_role_connection as tested_role_connection
from .test_screen_start_e2e import vertical_database as vertical_database

pytestmark = pytest.mark.requires_db


def _write_p3_nonplay_slot_probe(db) -> None:
    """失敗時だけ対象slotとP3同TX資格の固定比較値を保存する。"""
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        rows = admin.execute(
            """SELECT pg_catalog.jsonb_build_object(
 'old_event',e.id IS NOT NULL,'old_admission',a.source_event_id=e.id,
 'old_ledger',ol.kind='accepted' AND ol.source_fingerprint=a.event_fingerprint,
 'old_history',hi.entry=a.history_entry,
 'old_play',op.source_event_id=e.id,
 'old_xmin',e.xmin=a.xmin AND ol.xmin=a.xmin AND op.xmin=a.xmin,
 'old_projection',a.next_checkpoint_content->'projection_snapshot'=
 pg_catalog.jsonb_build_object('play_row',pg_catalog.to_jsonb(op),
 'play_runners',(SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=op.tenant_id AND rr.play_id=op.id)),
 'slot_version2',es.confirmed_version=2,
 'slot_tx',es.xmin=pa.xmin,
 'cap_head',ph.source_set_digest=pc.source_set_digest
 AND ph.stats_version_id=pc.stats_version_id,
 'cap_cp',pc.next_checkpoint_id=cp.id AND pc.watermark>=e.d1,
 'item_source',pi.state='corrected' AND pi.original_event_id=e.id
 AND pi.original_play_row_id=op.id AND pi.effective_event_id=ce.id,
 'item_original',pi.original_payload=e.payload
 AND pi.original_history_entry=hi.entry
 AND pi.original_play_row=pg_catalog.to_jsonb(op)
 AND pi.original_play_runners=(SELECT COALESCE(pg_catalog.jsonb_agg(
 pg_catalog.to_jsonb(rr) ORDER BY rr.base,rr.id),'[]'::jsonb)
 FROM public.play_runners rr WHERE rr.tenant_id=op.tenant_id AND rr.play_id=op.id),
 'item_effective',pi.play_row=pg_catalog.to_jsonb(ep),
 'admission',pa.state='consumed' AND pa.play_row_id=ep.id
 AND pa.change_event_id=ce.id AND pa.ledger_fingerprint=cl.source_fingerprint
 AND pa.expected_play_row=pg_catalog.to_jsonb(ep),
 'admission_xid',pa.xmin::text::numeric=
 pg_catalog.mod(pa.transaction_id::numeric,4294967296::numeric),
 'change_event',ce.event_kind='play_change' AND ce.ledger_kind='accepted'
 AND ce.target_generation=e.generation AND ce.target_d1=e.d1
 AND ce.expected_version=pc.expected_version AND ce.d5=pc.d5
 AND ce.replaced_at IS NULL AND ce.retired_at IS NULL AND NOT ce.is_tombstone
 AND ce.import_batch_id IS NULL AND NOT ce.migration_unverified,
 'change_ledger',cl.kind='accepted' AND cl.retired_at IS NULL
 AND cl.import_batch_id IS NULL
 AND cl.source_fingerprint=pa.ledger_fingerprint,
 'effective_play',ep.source_event_id=ce.id AND ep.hidden_at IS NULL
 AND ep.import_batch_id IS NULL AND NOT ep.migration_unverified,
 'tx_change_event',ce.xmin=pa.xmin,
 'tx_change_ledger',cl.xmin=pa.xmin,
 'tx_effective_play',ep.xmin=pa.xmin,
 'tx_capsule',pc.xmin=pa.xmin,
 'tx_item',pi.xmin=pa.xmin,
 'tx_head',ph.xmin=pa.xmin,
 'p3_tx',es.xmin=pa.xmin AND ce.xmin=pa.xmin AND cl.xmin=pa.xmin
 AND ep.xmin=pa.xmin AND pc.xmin=pa.xmin AND pi.xmin=pa.xmin
 AND ph.xmin=pa.xmin)
 FROM sync_fence.p3_projection_heads ph
 JOIN sync_fence.p3_projection_capsules pc ON
 (pc.tenant_id,pc.game_id,pc.internal_generation,pc.id)=
 (ph.tenant_id,ph.game_id,ph.internal_generation,ph.capsule_id)
 JOIN sync_fence.p3_projection_capsule_items pi ON
 (pi.tenant_id,pi.game_id,pi.internal_generation,pi.capsule_id,pi.d1)=
 (pc.tenant_id,pc.game_id,pc.internal_generation,pc.id,pc.target_d1)
 LEFT JOIN sync_fence.ordinary_pitch_checkpoints cp ON
 (cp.tenant_id,cp.game_id,cp.internal_generation)=
 (ph.tenant_id,ph.game_id,ph.internal_generation) AND cp.state='current'
 LEFT JOIN public.operation_events e ON
 (e.tenant_id,e.id)=(pi.tenant_id,pi.original_event_id)
 LEFT JOIN public.idempotency_ledger ol ON
 (ol.tenant_id,ol.d5)=(e.tenant_id,e.d5)
 LEFT JOIN sync_fence.ordinary_pitch_write_admissions a ON
 (a.tenant_id,a.source_event_id)=(e.tenant_id,e.id)
 LEFT JOIN sync_fence.ordinary_pitch_history hi ON
 (hi.tenant_id,hi.game_id,hi.internal_generation,hi.source_event_id)=
 (pi.tenant_id,pi.game_id,pi.internal_generation,pi.original_event_id)
 AND hi.history_version=cp.history_version
 LEFT JOIN public.play_rows op ON
 (op.tenant_id,op.id)=(pi.tenant_id,pi.original_play_row_id)
 LEFT JOIN public.event_slots es ON
 (es.tenant_id,es.game_id,es.generation,es.d1)=
 (e.tenant_id,e.game_id,e.generation,e.d1)
 LEFT JOIN sync_fence.p3_projection_write_admissions pa ON
 (pa.tenant_id,pa.game_id,pa.internal_generation,pa.capsule_id)=
 (pc.tenant_id,pc.game_id,pc.internal_generation,pc.id)
 LEFT JOIN public.operation_events ce ON
 (ce.tenant_id,ce.id)=(pc.tenant_id,pc.change_event_id)
 LEFT JOIN public.idempotency_ledger cl ON
 (cl.tenant_id,cl.d5)=(ce.tenant_id,ce.d5)
 LEFT JOIN public.play_rows ep ON
 (ep.tenant_id,ep.id)=(pi.tenant_id,pi.effective_play_row_id)
 WHERE ph.tenant_id=%s""",
            (db.tenant_id,),
        ).fetchall()
    safe = [{key: value is True for key, value in row[0].items()} for row in rows]
    (_PACKET / "owned-p3-nonplay-slot-proof.json").write_text(
        json.dumps({"row_count": len(safe), "checks": safe}, sort_keys=True)
    )


@pytest.mark.skipif(
    not os.environ.get("PITCHLOG_E2E_TLS_CERT_PATH")
    or not os.environ.get("PITCHLOG_E2E_TLS_KEY_PATH"),
    reason="隔離HTTPS証明書PATH未供給。P3画面縦断は未実証",
)
def test_screen_p3_https_create_three_pitches_correct_reload(vertical_database) -> None:
    """実画面の原版・原要求・再掲とT5旧新版を同じowned DBで確認する。"""
    for name in ("PITCHLOG_E2E_TLS_CERT_PATH", "PITCHLOG_E2E_TLS_KEY_PATH"):
        path = Path(os.environ[name])
        assert path.is_absolute() and path.is_file()
    db = vertical_database
    _install_p3_candidate(db)
    control_sql = (_PACKET / "p3-d1less-control-functions.candidate.sql").read_text()
    control = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "--user",
            "postgres",
            db.authority.binding_control,
            "psql",
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "binding_control_fixture",
        ],
        input=control_sql,
        capture_output=True,
        text=True,
        check=False,
    )
    assert control.returncode == 0, control.stderr[-500:]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert teams is not None
        for key, label in (
            ("batting-result.called-pitch", "見逃し"),
            ("batting-result.called-strikeout", "見逃し三振"),
        ):
            admin.execute(
                "INSERT INTO public.admin_vocabularies(key,category,display_name) "
                "VALUES (%s,'batting_result',%s) ON CONFLICT(key) DO NOTHING",
                (key, label),
            )
    config = "GameScreenPastCorrectionProduct.playwright.config.ts"
    token = uuid4()
    with db.broker_worker(token), binding_broker(db, token):
        with _browser_environment(db, config, "p3-screen", https=True) as origin:
            result = _run_playwright(
                db,
                config,
                origin,
                "p3-screen",
                {
                    "PITCHLOG_E2E_AWAY_TEAM": str(teams[0]),
                    "PITCHLOG_E2E_HOME_TEAM": str(teams[1]),
                },
            )
            if result.returncode != 0:
                (_PACKET / "owned-p3-playwright-stdout.log").write_text(result.stdout)
                (_PACKET / "owned-p3-playwright-stderr.log").write_text(result.stderr)
                stage_names = re.findall(
                    r'PITCHLOG_P3_STAGE=\{"name":"([a-z0-9-]+)"',
                    result.stdout,
                )
                (_PACKET / "owned-p3-screen-failure-stage.json").write_text(
                    json.dumps(
                        {"last_stage": stage_names[-1] if stage_names else None},
                        sort_keys=True,
                    )
                )
                _write_p3_nonplay_slot_probe(db)
            assert result.returncode == 0, (
                result.stdout[-12000:],
                result.stderr[-3000:],
            )
    found = re.findall(r"PITCHLOG_P3_SCREEN=(\{[^\n]+\})", result.stdout)
    assert len(found) == 1
    observed = json.loads(found[0])
    game_id = UUID(observed["gameId"])
    assert game_id != db.game_id
    assert (
        observed["accepted"] == 1
        and observed["replayStatus"] == 200
        and observed["suffixPitch"] == 1
        and observed["endedAfterCorrection"] is True
        and observed["reopenedAndPitchSaved"] is True
        and observed["reendedAfterCorrection"] is True
    )
    with psycopg.connect(
        db.authority.database.business_admin,
        options="-c default_transaction_read_only=on",
    ) as admin:
        key = (db.tenant_id, game_id)
        assert admin.execute(
            "SELECT count(*) FROM sync_fence.p3_projection_capsules "
            "WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (1,)
        versions = admin.execute(
            "SELECT id,is_current,source_count,completion_state,"
            "completion_receipt_id,public_pointer_receipt_id "
            "FROM sync_fence.stats_fact_versions "
            "WHERE tenant_id=%s AND game_id=%s "
            "ORDER BY created_at",
            key,
        ).fetchall()
        # 通常球はcurrent_open版のrevision/source_countを進める。
        # P3とLC end/reopenだけが新しい版IDを発行する。
        assert len(versions) == 5
        assert [(row[1], row[2], row[3]) for row in versions] == [
            (False, 3, "current_open"),
            (False, 4, "current_open"),
            (False, 4, "confirmed_ended"),
            (False, 5, "current_open"),
            (True, 5, "confirmed_ended"),
        ]
        assert versions[1][0] == UUID(observed["statsVersionId"])
        assert versions[2][4] is not None
        assert versions[2][4] == versions[2][5]
        assert versions[4][4] is not None
        assert versions[4][4] == versions[4][5]
        assert versions[4][4] != versions[2][4]
        assert admin.execute(
            "SELECT active_stats_version_id,active_receipt_id FROM "
            "sync_fence.game_lifecycle_heads WHERE tenant_id=%s AND game_id=%s",
            key,
        ).fetchone() == (versions[4][0], versions[4][4])
        slots = admin.execute(
            "SELECT d1,confirmed_version FROM public.event_slots "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY d1",
            key,
        ).fetchall()
        assert slots == [
            (1, 1),
            (2, 1),
            (3, 2),
            (4, 1),
            (5, 1),
            (6, 1),
            (7, 1),
            (8, 1),
        ]
        assert admin.execute(
            "SELECT event_kind,ledger_kind FROM public.operation_events "
            "WHERE tenant_id=%s AND game_id=%s AND d1 IN (5,6,8) ORDER BY d1",
            key,
        ).fetchall() == [
            ("game_end_declaration", "accepted"),
            ("game_reopen", "accepted"),
            ("game_end_declaration", "accepted"),
        ]
        source_slots = admin.execute(
            "SELECT d1,slot_version FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s "
            "ORDER BY d1",
            (*key, versions[4][0]),
        ).fetchall()
        assert source_slots == slots[:4] + [(7, 1)]
        old = admin.execute(
            "SELECT metric_states FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=3",
            (*key, versions[0][0]),
        ).fetchone()
        current = admin.execute(
            "SELECT metric_states FROM sync_fence.stats_primitive_sources "
            "WHERE tenant_id=%s AND game_id=%s AND fact_version_id=%s AND d1=3",
            (*key, versions[4][0]),
        ).fetchone()
        assert old is not None and current is not None
        assert old[0]["metrics"]["k"]["value"] == "1"
        assert current[0]["metrics"]["k"]["value"] == "0"
        assert old[0]["metrics"]["pitcher_k"]["value"] == "1"
        assert current[0]["metrics"]["pitcher_k"]["value"] == "0"
    (_PACKET / "owned-p3-screen-db-assertions.json").write_text(
        json.dumps(
            {
                "version_profiles": [list(row[1:4]) for row in versions],
                "slot_versions": [list(row) for row in slots],
                "current_source_slots": [list(row) for row in source_slots],
                "old_k": old[0]["metrics"]["k"]["value"],
                "current_k": current[0]["metrics"]["k"]["value"],
                "old_pitcher_k": old[0]["metrics"]["pitcher_k"]["value"],
                "current_pitcher_k": current[0]["metrics"]["pitcher_k"]["value"],
                "screen_reended": observed["reendedAfterCorrection"],
            },
            sort_keys=True,
        )
    )
