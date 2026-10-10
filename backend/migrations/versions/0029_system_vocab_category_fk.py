"""システム固定語彙への参照に区分の一致を強制する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_system_vocab_category_fk"
down_revision: str | Sequence[str] | None = "0028_tenant_login_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROSTER_STATUS = "roster_status"
_GAME_TYPE = "game_type"


def _reject_existing_rows() -> None:
    """所有者に全行を見せて区分違いを検出し、元の FORCE 状態へ戻す。"""
    op.execute(
        """
        DO $preflight$
        DECLARE
            players_forced boolean;
            games_forced boolean;
            defaults_forced boolean;
            vocabularies_forced boolean;
        BEGIN
            SELECT relforcerowsecurity INTO players_forced
            FROM pg_catalog.pg_class
            WHERE oid = 'public.players'::pg_catalog.regclass;
            SELECT relforcerowsecurity INTO games_forced
            FROM pg_catalog.pg_class
            WHERE oid = 'public.games'::pg_catalog.regclass;
            SELECT relforcerowsecurity INTO defaults_forced
            FROM pg_catalog.pg_class
            WHERE oid = 'public.game_type_rule_defaults'::pg_catalog.regclass;
            SELECT relforcerowsecurity INTO vocabularies_forced
            FROM pg_catalog.pg_class
            WHERE oid = 'public.system_vocabularies'::pg_catalog.regclass;

            -- 失敗時はトランザクションのロールバックで FORCE 状態が戻る。
            IF players_forced THEN
                EXECUTE 'ALTER TABLE public.players NO FORCE ROW LEVEL SECURITY';
            END IF;
            IF games_forced THEN
                EXECUTE 'ALTER TABLE public.games NO FORCE ROW LEVEL SECURITY';
            END IF;
            IF defaults_forced THEN
                EXECUTE 'ALTER TABLE public.game_type_rule_defaults
                         NO FORCE ROW LEVEL SECURITY';
            END IF;
            IF vocabularies_forced THEN
                EXECUTE 'ALTER TABLE public.system_vocabularies
                         NO FORCE ROW LEVEL SECURITY';
            END IF;

            IF EXISTS (
                SELECT 1 FROM public.players AS player
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.system_vocabularies AS vocabulary
                    WHERE vocabulary.key = player.roster_status_key
                      AND vocabulary.category = 'roster_status'
                )
            ) THEN
                RAISE EXCEPTION '0029 の事前検査に失敗: players に区分の合わない参照';
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.games AS game
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.system_vocabularies AS vocabulary
                    WHERE vocabulary.key = game.game_type_key
                      AND vocabulary.category = 'game_type'
                )
            ) THEN
                RAISE EXCEPTION '0029 の事前検査に失敗: games に区分の合わない参照';
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.game_type_rule_defaults AS defaults
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.system_vocabularies AS vocabulary
                    WHERE vocabulary.key = defaults.game_type_key
                      AND vocabulary.category = 'game_type'
                )
            ) THEN
                RAISE EXCEPTION
                '0029 の事前検査に失敗: game_type_rule_defaults に区分の合わない参照';
            END IF;

            IF vocabularies_forced THEN
                EXECUTE 'ALTER TABLE public.system_vocabularies
                         FORCE ROW LEVEL SECURITY';
            END IF;
            IF defaults_forced THEN
                EXECUTE 'ALTER TABLE public.game_type_rule_defaults
                         FORCE ROW LEVEL SECURITY';
            END IF;
            IF games_forced THEN
                EXECUTE 'ALTER TABLE public.games FORCE ROW LEVEL SECURITY';
            END IF;
            IF players_forced THEN
                EXECUTE 'ALTER TABLE public.players FORCE ROW LEVEL SECURITY';
            END IF;
        END
        $preflight$;
        """
    )


def upgrade() -> None:
    """参照先の一意性と定数列を足し、事前検査後に複合参照へ替える。"""
    op.create_unique_constraint(
        "uq_system_vocabularies_key_category",
        "system_vocabularies",
        ["key", "category"],
    )

    op.add_column(
        "players",
        sa.Column(
            "roster_status_category",
            sa.Text(),
            server_default=sa.text("'roster_status'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        None, "players", f"roster_status_category = '{_ROSTER_STATUS}'"
    )
    op.add_column(
        "games",
        sa.Column(
            "game_type_category",
            sa.Text(),
            server_default=sa.text("'game_type'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(None, "games", f"game_type_category = '{_GAME_TYPE}'")
    op.add_column(
        "game_type_rule_defaults",
        sa.Column(
            "game_type_category",
            sa.Text(),
            server_default=sa.text("'game_type'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        None, "game_type_rule_defaults", f"game_type_category = '{_GAME_TYPE}'"
    )

    _reject_existing_rows()

    op.drop_constraint("fk_players_roster_status", "players", type_="foreignkey")
    op.create_foreign_key(
        "fk_players_roster_status",
        "players",
        "system_vocabularies",
        ["roster_status_key", "roster_status_category"],
        ["key", "category"],
        match="FULL",
        ondelete="NO ACTION",
    )
    op.drop_constraint("fk_games_game_type", "games", type_="foreignkey")
    op.create_foreign_key(
        "fk_games_game_type",
        "games",
        "system_vocabularies",
        ["game_type_key", "game_type_category"],
        ["key", "category"],
        match="FULL",
        ondelete="NO ACTION",
    )
    op.drop_constraint(
        "fk_game_type_rule_defaults_type", "game_type_rule_defaults", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_game_type_rule_defaults_type",
        "game_type_rule_defaults",
        "system_vocabularies",
        ["game_type_key", "game_type_category"],
        ["key", "category"],
        match="FULL",
        ondelete="NO ACTION",
    )


def downgrade() -> None:
    """単列参照へ戻してから定数列と参照先の一意性を外す。"""
    op.drop_constraint("fk_players_roster_status", "players", type_="foreignkey")
    op.create_foreign_key(
        "fk_players_roster_status",
        "players",
        "system_vocabularies",
        ["roster_status_key"],
        ["key"],
        match="SIMPLE",
        ondelete="NO ACTION",
    )
    op.drop_constraint("fk_games_game_type", "games", type_="foreignkey")
    op.create_foreign_key(
        "fk_games_game_type",
        "games",
        "system_vocabularies",
        ["game_type_key"],
        ["key"],
        match="SIMPLE",
        ondelete="NO ACTION",
    )
    op.drop_constraint(
        "fk_game_type_rule_defaults_type", "game_type_rule_defaults", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_game_type_rule_defaults_type",
        "game_type_rule_defaults",
        "system_vocabularies",
        ["game_type_key"],
        ["key"],
        match="SIMPLE",
        ondelete="NO ACTION",
    )

    op.drop_column("players", "roster_status_category")
    op.drop_column("games", "game_type_category")
    op.drop_column("game_type_rule_defaults", "game_type_category")
    op.drop_constraint(
        "uq_system_vocabularies_key_category", "system_vocabularies", type_="unique"
    )
