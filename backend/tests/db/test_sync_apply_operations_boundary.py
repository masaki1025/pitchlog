"""同期 operation の越境拒否を使い捨ての製品 DB で検査する。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from test_authz_tenant_context import make_tenant_context

from pitchlog.authz.runtime_contract import APPLICATION_ROLE_NAME
from pitchlog.db.sync_protocol.models import InvalidationIntent
from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationTrigger,
    CacheScope,
)
from pitchlog.repositories.invalidation_intents import InvalidationIntentInsertToken
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.sync import tokens
from pitchlog.sync.intent_ids import derive_sync_intent_id, is_sync_intent_id

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db


@dataclass(frozen=True, slots=True)
class _SyncDatabase:
    """2 テナントの使い捨て製品 DB と試合 ID を保持する。"""

    catalog: ProvisionedProductCatalog
    tenant_a: UUID
    tenant_b: UUID
    game_a: UUID
    game_b: UUID


def _application_url(dsn: str) -> str:
    """使い捨てアプリロールの DSN を製品 engine 用 URL にする。"""
    values = conninfo_to_dict(dsn)
    username = values.get("user")
    password = values.get("password")
    host = values.get("host")
    port = values.get("port")
    database = values.get("dbname")
    return URL.create(
        "postgresql+psycopg",
        username=None if username is None else str(username),
        password=None if password is None else str(password),
        host=None if host is None else str(host),
        port=None if port is None else int(port),
        database=None if database is None else str(database),
        query={"sslmode": "disable"},
    ).render_as_string(hide_password=False)


@pytest.fixture
def sync_database(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> _SyncDatabase:
    """製品 DDL と認可を適用した DB に 2 テナントの参照先を作る。"""
    catalog = provisioned_product_catalog
    tenant_a, tenant_b = uuid4(), uuid4()
    game_a, game_b = uuid4(), uuid4()
    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "INSERT INTO system_vocabularies (key, category, display_name) "
            "VALUES ('official', 'game_type', '公式戦') ON CONFLICT (key) DO NOTHING"
        )
        for tenant_id, game_id in ((tenant_a, game_a), (tenant_b, game_b)):
            self_team, opponent_team = uuid4(), uuid4()
            cursor.execute(
                "INSERT INTO tenants (id, name, enabled) VALUES (%s, %s, true)",
                (tenant_id, f"sync-{tenant_id.hex}"),
            )
            cursor.execute(
                "INSERT INTO tenant_vocabularies "
                "(tenant_id, key, category, display_name) "
                "VALUES (%s, 'autumn', 'tournament', '秋季大会')",
                (tenant_id,),
            )
            cursor.executemany(
                "INSERT INTO team_records (tenant_id, id, kind, name) "
                "VALUES (%s, %s, %s, %s)",
                [
                    (tenant_id, self_team, "self", "自チーム"),
                    (tenant_id, opponent_team, "opponent", "対戦相手"),
                ],
            )
            cursor.execute(
                "INSERT INTO games (tenant_id, id, scheduled_at, game_type_key, "
                "tournament_key, away_team_record_id, home_team_record_id, "
                "applied_rules) VALUES (%s, %s, CURRENT_TIMESTAMP, 'official', "
                "'autumn', %s, %s, %s)",
                (tenant_id, game_id, opponent_team, self_team, Jsonb({})),
            )
            cursor.execute(
                "INSERT INTO recording_generations (tenant_id, game_id, "
                "generation, kind, issuance_order, holder_device) "
                "VALUES (%s, %s, 1, 'normal', 1, 'test-device')",
                (tenant_id, game_id),
            )
            cursor.execute(
                "INSERT INTO event_slots (tenant_id, game_id, generation, d1) "
                "VALUES (%s, %s, 1, 1)",
                (tenant_id, game_id),
            )
        password = secrets.token_urlsafe(24)
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(APPLICATION_ROLE_NAME), sql.Literal(password)
            )
        )
    catalog.applicator.commit()
    app_dsn = make_conninfo(
        catalog.owner_dsn, user=APPLICATION_ROLE_NAME, password=password
    )
    monkeypatch.setenv("PITCHLOG_DATABASE_URL", _application_url(app_dsn))
    monkeypatch.setenv("PITCHLOG_DATABASE_POOLED", "false")
    return _SyncDatabase(catalog, tenant_a, tenant_b, game_a, game_b)


def test_sync_two_tenant_read_insert_update_lock_boundary(
    sync_database: _SyncDatabase,
) -> None:
    """A の文脈で B の行を読まず、挿入・更新・行ロックもしない。"""
    db = sync_database
    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        assert len(scope.run(tokens.GameReadToken(db.game_a)).rows) == 1
        assert len(scope.run(tokens.GameLockToken(db.game_a)).rows) == 1
        assert (
            len(scope.run(tokens.RecordingGenerationLockToken(db.game_a, 1)).rows) == 1
        )
        assert scope.run(tokens.GameReadToken(db.game_b)).rows == ()
        assert scope.run(tokens.GameLockToken(db.game_b)).rows == ()
        assert scope.run(tokens.RecordingGenerationReadToken(db.game_b)).rows == ()
        assert scope.run(tokens.RecordingGenerationLockToken(db.game_b, 1)).rows == ()
        assert scope.run(tokens.EventSlotReadToken(db.game_b, 1, 1)).rows == ()
        assert scope.run(
            tokens.RecordingPrefixUpdateToken(db.game_b, 1, 1, 1)
        ).rows == ((0,),)
        assert scope.run(
            tokens.EventSlotVersionUpdateToken(db.game_b, 1, 1, 1, 2)
        ).rows == ((0,),)
        assert scope.run(
            tokens.RecordingPrefixUpdateToken(db.game_a, 1, 1, 1)
        ).rows == ((1,),)
        assert scope.run(
            tokens.EventSlotVersionUpdateToken(db.game_a, 1, 1, 1, 2)
        ).rows == ((1,),)
        assert scope.run(tokens.EventSlotInsertToken(db.game_a, 1, 2)).rows == ((1,),)

    with pytest.raises(DBAPIError) as blocked_insert:
        with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
            scope.run(tokens.EventSlotInsertToken(db.game_b, 1, 2))
    assert getattr(blocked_insert.value.orig, "sqlstate", None) in {"23503", "42501"}

    with tenant_transaction_scope(make_tenant_context(db.tenant_b)) as scope:
        assert len(scope.run(tokens.GameReadToken(db.game_b)).rows) == 1
        assert len(scope.run(tokens.GameLockToken(db.game_b)).rows) == 1
        assert (
            len(scope.run(tokens.RecordingGenerationLockToken(db.game_b, 1)).rows) == 1
        )
        assert len(scope.run(tokens.EventSlotReadToken(db.game_b, 1, 1)).rows) == 1
        assert scope.run(tokens.EventSlotReadToken(db.game_b, 1, 2)).rows == ()

    with db.catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT tenant_id, game_id, generation, d1, confirmed_version "
            "FROM event_slots WHERE tenant_id IN (%s, %s) ORDER BY tenant_id, d1",
            (db.tenant_a, db.tenant_b),
        )
        assert set(cursor.fetchall()) == {
            (db.tenant_a, db.game_a, 1, 1, 2),
            (db.tenant_a, db.game_a, 1, 2, 1),
            (db.tenant_b, db.game_b, 1, 1, 1),
        }
        cursor.execute(
            "SELECT confirmed_watermark, applied_prefix FROM recording_generations "
            "WHERE tenant_id = %s AND game_id = %s AND generation = 1",
            (db.tenant_b, db.game_b),
        )
        assert cursor.fetchone() == (0, 0)
    db.catalog.applicator.rollback()


def test_sync_shared_intent_targets_only_context_tenant(
    sync_database: _SyncDatabase,
) -> None:
    """④共有集計の対象と意図の read・update を文脈テナントに限定する。"""
    db = sync_database
    event_identity = str(uuid4())
    intent_id = derive_sync_intent_id(event_identity, "shared_total")
    tenant_index = list(InvalidationIntent.__table__.c.keys()).index("tenant_id")
    target_index = list(InvalidationIntent.__table__.c.keys()).index("target_tenant_id")
    intent_index = list(InvalidationIntent.__table__.c.keys()).index("intent_id")

    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        with pytest.raises(TypeError):
            tokens.SyncSharedInvalidationIntentInsertToken(
                event_identity, **{"target_tenant_id": db.tenant_b}
            )
        assert scope.run(
            tokens.SyncSharedInvalidationIntentInsertToken(event_identity)
        ).rows == ((1,),)
        old = InvalidationIntentInsertToken(
            CacheInvalidationTrigger.ROSTER_STATUS_CHANGE,
            uuid4(),
            CacheScope.SHARED_AGGREGATE,
        )
        scope.run(old)
        own = scope.run(tokens.InvalidationIntentReadToken(intent_id))
        assert len(own.rows) == 1
        assert own.rows[0][tenant_index] == db.tenant_a
        assert own.rows[0][target_index] == db.tenant_a
        cursor = ""
        observed: list[str] = []
        selected: list[str] = []
        for _ in range(3):
            page = scope.run(tokens.InvalidationIntentPendingToken(1, cursor))
            if not page.rows:
                break
            cursor = page.rows[0][intent_index]
            assert type(cursor) is str
            observed.append(cursor)
            if is_sync_intent_id(cursor):
                selected.append(cursor)
        assert observed == sorted((old.intent_id, intent_id))
        assert selected == [intent_id]

    with tenant_transaction_scope(make_tenant_context(db.tenant_b)) as scope:
        assert scope.run(tokens.InvalidationIntentReadToken(intent_id)).rows == ()
        assert scope.run(
            tokens.InvalidationIntentDeliveredToken(intent_id, datetime.now(UTC))
        ).rows == ((0,),)
        assert scope.run(
            tokens.SyncSharedInvalidationIntentInsertToken(event_identity)
        ).rows == ((1,),)
        other = scope.run(tokens.InvalidationIntentReadToken(intent_id))
        assert len(other.rows) == 1
        assert other.rows[0][tenant_index] == db.tenant_b
        assert other.rows[0][target_index] == db.tenant_b

    with tenant_transaction_scope(make_tenant_context(db.tenant_a)) as scope:
        original = scope.run(tokens.InvalidationIntentReadToken(intent_id))
        assert len(original.rows) == 1
        assert original.rows[0][target_index] == db.tenant_a
