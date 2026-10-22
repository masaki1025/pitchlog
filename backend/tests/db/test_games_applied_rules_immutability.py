"""試合の規則snapshotが初回保存後にDBで不変となることを検査する恒久試験。"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg.types.json import Jsonb

from pitchlog.db.game_state.models import Game

from .conftest import DisposablePostgres
from .test_alembic_migrations import _alembic_config, _sqlalchemy_url
from .test_immutability_matrix import _seed_behavior_rows

pytestmark = pytest.mark.requires_db

_ROOT = Path(__file__).resolve().parents[3]
_BEFORE_TRIGGER = "trg_games_applied_rules_immutable"
_AFTER_TRIGGER = "trg_games_applied_rules_final_immutable"
_BEFORE_FUNCTION = "prevent_games_applied_rules_update"
_AFTER_FUNCTION = "verify_games_applied_rules_final"
_REJECTION = "games.applied_rules is immutable after insert"


def test_games_applied_rules_rejects_change_after_insert(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """初回INSERT・同値/別列更新を許し、異値更新と同一transactionを全取消する。"""
    with disposable_postgres_cluster() as cluster:
        monkeypatch.setenv(
            "PITCHLOG_MIGRATION_DATABASE_URL", _sqlalchemy_url(cluster.admin_dsn)
        )
        command.upgrade(_alembic_config(), "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            _seed_behavior_rows(connection)
            row = connection.execute(
                "SELECT tenant_id, id, applied_rules FROM public.games"
            ).fetchone()
            assert row is not None and row[2] == {}
            initial = {
                "ruleSetId": str(uuid4()),
                "regulationInnings": 9,
                "coldConditions": [],
                "extensionLimit": None,
                "tiebreak": None,
                "dh": False,
            }
            new_id = uuid4()
            inserted = connection.execute(
                """
                INSERT INTO public.games (
                    tenant_id, id, scheduled_at, game_type_key,
                    tournament_key, away_team_record_id,
                    home_team_record_id, applied_rules
                )
                SELECT tenant_id, %s, scheduled_at, game_type_key,
                       tournament_key, away_team_record_id,
                       home_team_record_id, %s
                FROM public.games WHERE tenant_id = %s AND id = %s
                RETURNING tenant_id, id, applied_rules
                """,
                (new_id, Jsonb(initial), *row[:2]),
            ).fetchone()
            assert inserted is not None and inserted[2] == initial
            tenant_id, game_id = inserted[:2]

            # 実テーブルに対する最小権限ロールでもトリガの拒否を確認する。
            connection.execute("CREATE ROLE pitchlog_app")
            connection.execute("GRANT USAGE ON SCHEMA public TO pitchlog_app")
            connection.execute("GRANT SELECT, UPDATE ON public.games TO pitchlog_app")
            connection.execute("SET ROLE pitchlog_app")
            assert connection.execute("SELECT current_role").fetchone() == (
                "pitchlog_app",
            )
            connection.execute(
                "UPDATE public.games SET status = 'in_progress' "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, game_id),
            )
            connection.execute(
                "UPDATE public.games SET applied_rules = %s "
                "WHERE tenant_id = %s AND id = %s",
                (Jsonb(initial), tenant_id, game_id),
            )
            with pytest.raises(
                psycopg.errors.CheckViolation, match=_REJECTION
            ) as changed:
                connection.execute(
                    "UPDATE public.games SET applied_rules = %s "
                    "WHERE tenant_id = %s AND id = %s",
                    (Jsonb({"changed": True}), tenant_id, game_id),
                )
            assert changed.value.sqlstate == "23514"
            assert connection.execute(
                "SELECT applied_rules FROM public.games "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, game_id),
            ).fetchone() == (initial,)

            with pytest.raises(psycopg.errors.CheckViolation, match=_REJECTION):
                with connection.transaction():
                    connection.execute(
                        "UPDATE public.games SET status = 'finished' "
                        "WHERE tenant_id = %s AND id = %s",
                        (tenant_id, game_id),
                    )
                    connection.execute(
                        "UPDATE public.games SET applied_rules = %s "
                        "WHERE tenant_id = %s AND id = %s",
                        (Jsonb({"changed": True}), tenant_id, game_id),
                    )
            assert connection.execute(
                "SELECT status, applied_rules FROM public.games "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, game_id),
            ).fetchone() == ("in_progress", initial)
            connection.execute("RESET ROLE")

            # 別列のBEFOREトリガが最終行を変更してもAFTER側で拒否する。
            connection.execute(
                """
                CREATE FUNCTION public.probe_change_rules_during_status_update()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    NEW.applied_rules := '{"mutated":true}'::jsonb;
                    RETURN NEW;
                END;
                $$
                """
            )
            connection.execute(
                """
                CREATE TRIGGER probe_change_rules_during_status_update
                BEFORE UPDATE OF status ON public.games FOR EACH ROW
                EXECUTE FUNCTION public.probe_change_rules_during_status_update()
                """
            )
            with pytest.raises(psycopg.errors.CheckViolation, match=_REJECTION):
                connection.execute(
                    "UPDATE public.games SET status = 'finished' "
                    "WHERE tenant_id = %s AND id = %s",
                    (tenant_id, game_id),
                )
            assert connection.execute(
                "SELECT status, applied_rules FROM public.games "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, game_id),
            ).fetchone() == ("in_progress", initial)
            connection.execute(
                "DROP TRIGGER probe_change_rules_during_status_update ON public.games"
            )
            connection.execute(
                "DROP FUNCTION public.probe_change_rules_during_status_update()"
            )

            triggers = connection.execute(
                """
                SELECT t.tgname, pg_get_triggerdef(t.oid), t.tgenabled
                FROM pg_trigger AS t
                WHERE t.tgrelid = 'public.games'::regclass
                  AND t.tgname IN (%s, %s)
                  AND NOT t.tgisinternal
                """,
                (_BEFORE_TRIGGER, _AFTER_TRIGGER),
            ).fetchall()
            by_name = {
                name: (definition, enabled) for name, definition, enabled in triggers
            }
            assert set(by_name) == {_BEFORE_TRIGGER, _AFTER_TRIGGER}
            assert all(enabled == "O" for _, enabled in by_name.values())
            assert "BEFORE UPDATE OF applied_rules" in by_name[_BEFORE_TRIGGER][0]
            assert "AFTER UPDATE ON public.games" in by_name[_AFTER_TRIGGER][0]
            assert (
                "old.applied_rules is distinct from new.applied_rules"
                in by_name[_AFTER_TRIGGER][0].lower()
            )
            for function_name in (_BEFORE_FUNCTION, _AFTER_FUNCTION):
                function = connection.execute(
                    "SELECT pg_get_functiondef(%s::regprocedure)",
                    (f"public.{function_name}()",),
                ).fetchone()
                assert function is not None and "23514" in function[0]

            # 既存行の異値訂正は、特権接続でも拒否される（正当な訂正・復旧は別ゲート）。
            with pytest.raises(psycopg.errors.CheckViolation, match=_REJECTION):
                connection.execute(
                    "UPDATE public.games SET applied_rules = %s "
                    "WHERE tenant_id = %s AND id = %s",
                    (Jsonb({"restored": True}), *row[:2]),
                )
            assert connection.execute(
                "SELECT applied_rules FROM public.games "
                "WHERE tenant_id = %s AND id = %s",
                row[:2],
            ).fetchone() == ({},)

        command.downgrade(_alembic_config(), "0032_rg1_restore_gate")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            assert connection.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid = "
                "'public.games'::regclass AND tgname IN (%s, %s)",
                (_BEFORE_TRIGGER, _AFTER_TRIGGER),
            ).fetchone() == (0,)
            for function_name in (_BEFORE_FUNCTION, _AFTER_FUNCTION):
                assert connection.execute(
                    "SELECT to_regprocedure(%s)",
                    (f"public.{function_name}()",),
                ).fetchone() == (None,)
            assert connection.execute(
                "SELECT applied_rules FROM public.games "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, game_id),
            ).fetchone() == (initial,)
        command.upgrade(_alembic_config(), "head")
        with psycopg.connect(cluster.admin_dsn, autocommit=True) as connection:
            with pytest.raises(psycopg.errors.CheckViolation, match=_REJECTION):
                connection.execute(
                    "UPDATE public.games SET applied_rules = %s "
                    "WHERE tenant_id = %s AND id = %s",
                    (Jsonb({"changed_after_reupgrade": True}), tenant_id, game_id),
                )
            assert connection.execute(
                "SELECT applied_rules FROM public.games "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, game_id),
            ).fetchone() == (initial,)


def test_games_applied_rules_manifest_and_orm_declare_same_protection() -> None:
    """保護列をmanifestとORMの双方で同じ値に固定する。"""
    manifest: dict[str, Any] = json.loads(
        (_ROOT / "contracts/db/schema-manifest.json").read_text(encoding="utf-8")
    )
    games = next(table for table in manifest["tables"] if table["name"] == "games")
    assert games["immutability"]["protected_columns"] == ["applied_rules"]
    assert Game.immutability.protected_columns == frozenset({"applied_rules"})
