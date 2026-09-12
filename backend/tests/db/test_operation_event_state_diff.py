"""操作イベント種別と V8 の種別条件を実 PostgreSQL で検査する。"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from psycopg.types.json import Jsonb

from pitchlog.db.sync_protocol.event_kinds import (
    CHANGE_EVENT_KIND_LITERALS,
    EVENT_KIND_BY_CANONICAL_NAME,
    PLAY_INPUT_EVENT_KIND,
)

from .conftest import DisposablePostgres
from .test_alembic_migrations import (
    _alembic_config,
    _insert_recording_generation,
    _insert_test_vocabularies,
    _sqlalchemy_url,
)

pytestmark = pytest.mark.requires_db

_EVENT_KIND_CONSTRAINT = "ck_operation_events_event_kind"
_D2_CONSTRAINT = "ck_operation_events_d2_by_kind"
_EXPECTED_VERSION_CONSTRAINT = "ck_operation_events_expected_version_by_kind"
_STATE_DIFF_CONSTRAINT = "ck_operation_events_state_diff_by_kind"
_TARGET_CONSTRAINT = "ck_operation_events_target_by_kind"
_TOMBSTONE_CONSTRAINT = "ck_operation_events_tombstone"
_TARGET_PAIR_CONSTRAINT = "ck_operation_events_target_pair"


def _insert_game_context(cursor: psycopg.Cursor[Any]) -> tuple[UUID, UUID]:
    """操作イベントの参照先とテスト用イベントスロットを作る。"""
    tenant_id = uuid4()
    game_id = uuid4()
    self_team_id = uuid4()
    opponent_team_id = uuid4()
    cursor.execute(
        "INSERT INTO tenants (id, name) VALUES (%s, %s)",
        (tenant_id, "操作イベント種別テストテナント"),
    )
    _insert_test_vocabularies(cursor, tenant_id)
    cursor.executemany(
        """
        INSERT INTO team_records (tenant_id, id, kind, name)
        VALUES (%s, %s, %s, %s)
        """,
        [
            (tenant_id, self_team_id, "self", "自チーム"),
            (tenant_id, opponent_team_id, "opponent", "対戦相手"),
        ],
    )
    cursor.execute(
        """
        INSERT INTO games (
            tenant_id,
            id,
            scheduled_at,
            game_type_key,
            tournament_key,
            away_team_record_id,
            home_team_record_id,
            applied_rules
        ) VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
        """,
        (
            tenant_id,
            game_id,
            "official",
            "autumn",
            opponent_team_id,
            self_team_id,
            Jsonb({}),
        ),
    )
    _insert_recording_generation(cursor, tenant_id, game_id)
    cursor.executemany(
        """
        INSERT INTO event_slots (tenant_id, game_id, generation, d1)
        VALUES (%s, %s, 1, %s)
        """,
        [(tenant_id, game_id, d1) for d1 in range(1, 6)],
    )
    return tenant_id, game_id


def _insert_operation_event(
    cursor: psycopg.Cursor[Any],
    tenant_id: UUID,
    game_id: UUID,
    *,
    event_kind: str,
    state_diff: Jsonb | None,
    d1: int | None,
    d2: int | None,
    payload: dict[str, object] | None = None,
    is_tombstone: bool = False,
    target_pair: tuple[int | None, int | None] | None = None,
) -> UUID:
    """台帳を先に作り、指定した種別と V8 で操作イベントを挿入する。"""
    event_id = uuid4()
    d5 = uuid4()
    cursor.execute(
        """
        INSERT INTO idempotency_ledger (
            tenant_id, d5, kind, source_fingerprint, result
        ) VALUES (%s, %s, 'accepted', %s, %s)
        """,
        (tenant_id, d5, f"event-kind:{event_id}", Jsonb({})),
    )
    is_change = event_kind in CHANGE_EVENT_KIND_LITERALS
    target_generation, target_d1 = (
        ((1, 1) if is_change else (None, None)) if target_pair is None else target_pair
    )
    cursor.execute(
        """
        INSERT INTO operation_events (
            tenant_id,
            id,
            game_id,
            generation,
            d1,
            d2,
            d5,
            event_kind,
            payload,
            state_diff,
            is_tombstone,
            target_generation,
            target_d1,
            expected_version,
            change_order
        ) VALUES (
            %(tenant_id)s,
            %(id)s,
            %(game_id)s,
            %(generation)s,
            %(d1)s,
            %(d2)s,
            %(d5)s,
            %(event_kind)s,
            %(payload)s,
            %(state_diff)s,
            %(is_tombstone)s,
            %(target_generation)s,
            %(target_d1)s,
            %(expected_version)s,
            %(change_order)s
        )
        RETURNING id
        """,
        {
            "tenant_id": tenant_id,
            "id": event_id,
            "game_id": game_id,
            "generation": None if is_change else 1,
            "d1": None if is_change else d1,
            "d2": None if is_change else d2,
            "d5": d5,
            "event_kind": event_kind,
            "payload": Jsonb({} if payload is None else payload),
            "state_diff": state_diff,
            "is_tombstone": is_tombstone,
            "target_generation": target_generation,
            "target_d1": target_d1,
            "expected_version": 1 if is_change else None,
            "change_order": 1 if is_change else None,
        },
    )
    assert cursor.fetchone() == (event_id,)
    return event_id


def _operation_event_check_status(
    cursor: psycopg.Cursor[Any],
) -> dict[str, bool]:
    """是正 C が追加した CHECK の存在と検証状態を返す。"""
    cursor.execute(
        """
        SELECT conname, convalidated
        FROM pg_constraint
        WHERE conrelid = 'operation_events'::regclass
          AND conname = ANY(%s)
        ORDER BY conname
        """,
        (
            [
                _D2_CONSTRAINT,
                _EVENT_KIND_CONSTRAINT,
                _EXPECTED_VERSION_CONSTRAINT,
                _STATE_DIFF_CONSTRAINT,
                _TARGET_CONSTRAINT,
                _TARGET_PAIR_CONSTRAINT,
                _TOMBSTONE_CONSTRAINT,
            ],
        ),
    )
    return {str(name): bool(validated) for name, validated in cursor.fetchall()}


def _operation_event_fk_matches(
    cursor: psycopg.Cursor[Any],
) -> dict[str, str]:
    """操作イベントの FK 4 本について PostgreSQL の MATCH 方式を返す。"""
    cursor.execute(
        """
        SELECT conname, confmatchtype
        FROM pg_constraint
        WHERE conrelid = 'operation_events'::regclass
          AND contype = 'f'
        ORDER BY conname
        """
    )
    match_name = {"f": "FULL", "s": "SIMPLE", "p": "PARTIAL"}
    return {str(name): match_name[str(match)] for name, match in cursor.fetchall()}


def test_operation_event_kind_and_state_diff_checks_round_trip(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """種別値域・V8 の正負例と migration 往復を検査する。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL",
            _sqlalchemy_url(cluster.admin_dsn),
        )
        config = _alembic_config()
        command.upgrade(config, "head")

        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                assert _operation_event_check_status(cursor) == {
                    _D2_CONSTRAINT: True,
                    _EVENT_KIND_CONSTRAINT: True,
                    _EXPECTED_VERSION_CONSTRAINT: True,
                    _STATE_DIFF_CONSTRAINT: True,
                    _TARGET_CONSTRAINT: True,
                    _TARGET_PAIR_CONSTRAINT: True,
                    _TOMBSTONE_CONSTRAINT: True,
                }
                assert _operation_event_fk_matches(cursor) == {
                    "fk_operation_events_game": "FULL",
                    "fk_operation_events_ledger": "FULL",
                    "fk_operation_events_slot": "SIMPLE",
                    "fk_operation_events_target": "SIMPLE",
                }
                tenant_id, game_id = _insert_game_context(cursor)

                with pytest.raises(
                    psycopg.errors.CheckViolation,
                    match=_STATE_DIFF_CONSTRAINT,
                ):
                    _insert_operation_event(
                        cursor,
                        tenant_id,
                        game_id,
                        event_kind=PLAY_INPUT_EVENT_KIND,
                        state_diff=None,
                        d1=1,
                        d2=1,
                    )

                for change_kind in CHANGE_EVENT_KIND_LITERALS:
                    with pytest.raises(
                        psycopg.errors.CheckViolation,
                        match=_STATE_DIFF_CONSTRAINT,
                    ):
                        _insert_operation_event(
                            cursor,
                            tenant_id,
                            game_id,
                            event_kind=change_kind,
                            state_diff=Jsonb({"outs": 1}),
                            d1=None,
                            d2=None,
                        )

                with pytest.raises(
                    psycopg.errors.CheckViolation,
                    match=_EVENT_KIND_CONSTRAINT,
                ):
                    _insert_operation_event(
                        cursor,
                        tenant_id,
                        game_id,
                        event_kind="unknown_event",
                        state_diff=None,
                        d1=4,
                        d2=4,
                    )

                with pytest.raises(
                    psycopg.errors.CheckViolation,
                    match=_TARGET_PAIR_CONSTRAINT,
                ):
                    _insert_operation_event(
                        cursor,
                        tenant_id,
                        game_id,
                        event_kind=EVENT_KIND_BY_CANONICAL_NAME["選手交代"],
                        state_diff=None,
                        d1=4,
                        d2=4,
                        target_pair=(1, None),
                    )

                with pytest.raises(
                    psycopg.errors.CheckViolation,
                    match=_D2_CONSTRAINT,
                ):
                    _insert_operation_event(
                        cursor,
                        tenant_id,
                        game_id,
                        event_kind=EVENT_KIND_BY_CANONICAL_NAME["選手交代"],
                        state_diff=None,
                        d1=2,
                        d2=2,
                        is_tombstone=True,
                    )

                with pytest.raises(
                    psycopg.errors.CheckViolation,
                    match=_TOMBSTONE_CONSTRAINT,
                ):
                    _insert_operation_event(
                        cursor,
                        tenant_id,
                        game_id,
                        event_kind=EVENT_KIND_BY_CANONICAL_NAME["選手交代"],
                        state_diff=None,
                        d1=3,
                        d2=None,
                        payload={"unexpected": True},
                        is_tombstone=True,
                    )

                # 変更イベントの墓標行は V9 禁止と墓標側の V11 禁止を同時に
                # 破るため、実表では片方だけを破る行を構成できない。V9 単独の
                # 負例は test_operation_event_c12.py のセル自動展開で検査する。

                normal_event_id = _insert_operation_event(
                    cursor,
                    tenant_id,
                    game_id,
                    event_kind=PLAY_INPUT_EVENT_KIND,
                    state_diff=Jsonb({"outs": 1}),
                    d1=1,
                    d2=1,
                    payload={"result": "non_pitch"},
                )
                change_event_id = _insert_operation_event(
                    cursor,
                    tenant_id,
                    game_id,
                    event_kind=CHANGE_EVENT_KIND_LITERALS[0],
                    state_diff=None,
                    d1=None,
                    d2=None,
                )
                tombstone_event_id = _insert_operation_event(
                    cursor,
                    tenant_id,
                    game_id,
                    event_kind=EVENT_KIND_BY_CANONICAL_NAME["選手交代"],
                    state_diff=None,
                    d1=5,
                    d2=None,
                    is_tombstone=True,
                )
                play_tombstone_event_id = _insert_operation_event(
                    cursor,
                    tenant_id,
                    game_id,
                    event_kind=PLAY_INPUT_EVENT_KIND,
                    state_diff=None,
                    d1=4,
                    d2=None,
                    is_tombstone=True,
                )
                assert (
                    len(
                        {
                            normal_event_id,
                            change_event_id,
                            tombstone_event_id,
                            play_tombstone_event_id,
                        }
                    )
                    == 4
                )
                cursor.execute(
                    """
                    SELECT id, is_tombstone, target_generation, target_d1
                    FROM operation_events
                    WHERE tenant_id = %s AND id = ANY(%s)
                    ORDER BY is_tombstone, id
                    """,
                    (
                        tenant_id,
                        [
                            normal_event_id,
                            change_event_id,
                            tombstone_event_id,
                            play_tombstone_event_id,
                        ],
                    ),
                )
                assert set(cursor.fetchall()) == {
                    (normal_event_id, False, None, None),
                    (change_event_id, False, 1, 1),
                    (tombstone_event_id, True, None, None),
                    (play_tombstone_event_id, True, None, None),
                }

                cursor.execute("DELETE FROM operation_events")
                cursor.execute("SELECT count(*) FROM operation_events")
                assert cursor.fetchone() == (0,)

        command.downgrade(config, "0021_medical_note_lifecycle")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                assert _operation_event_check_status(cursor) == {}
                assert _operation_event_fk_matches(cursor) == {
                    "fk_operation_events_game": "FULL",
                    "fk_operation_events_ledger": "FULL",
                    "fk_operation_events_slot": "FULL",
                    "fk_operation_events_target": "FULL",
                }

        command.upgrade(config, "head")
        command.current(config, check_heads=True)
        command.check(config)
