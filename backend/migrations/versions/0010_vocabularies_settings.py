"""語彙 3 層とシステム設定値を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_vocabularies_settings"
down_revision: str | Sequence[str] | None = "0009_medical_notes_pdf_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM_VOCABULARY_FUNCTION = "prevent_system_vocabularies_update"
_SYSTEM_VOCABULARY_TRIGGER = "trg_system_vocabularies_immutable"
_ADMIN_VOCABULARY_FUNCTION = "prevent_admin_vocabularies_identity_update"
_ADMIN_VOCABULARY_TRIGGER = "trg_admin_vocabularies_identity_immutable"
_TENANT_VOCABULARY_FUNCTION = "prevent_tenant_vocabularies_identity_update"
_TENANT_VOCABULARY_TRIGGER = "trg_tenant_vocabularies_identity_immutable"
_SYSTEM_SETTING_FUNCTION = "prevent_system_settings_key_update"
_SYSTEM_SETTING_TRIGGER = "trg_system_settings_key_immutable"


def upgrade() -> None:
    """語彙・設定表、既存参照元の FK、不変性トリガを追加する。"""
    op.create_table(
        "system_vocabularies",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "disabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint("category IN ('game_type', 'roster_status')"),
        sa.PrimaryKeyConstraint("key", name="pk_system_vocabularies"),
    )
    op.create_table(
        "admin_vocabularies",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "disabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint("category IN ('batting_result', 'batted_ball', 'season')"),
        sa.PrimaryKeyConstraint("key", name="pk_admin_vocabularies"),
    )
    op.create_table(
        "tenant_vocabularies",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("pitch_family", sa.Text(), nullable=True),
        sa.Column("abbreviation", sa.Text(), nullable=True),
        sa.Column(
            "disabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('pitch_type', 'strategy', 'tournament', 'roster_label')"
        ),
        sa.CheckConstraint("category <> 'pitch_type' OR pitch_family IS NOT NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_vocabularies_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "key",
            name="pk_tenant_vocabularies",
        ),
    )
    op.create_table(
        "system_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_system_settings"),
    )

    op.create_foreign_key(
        "fk_players_roster_status",
        "players",
        "system_vocabularies",
        ["roster_status_key"],
        ["key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_players_roster_label",
        "players",
        "tenant_vocabularies",
        ["tenant_id", "roster_label_key"],
        ["tenant_id", "key"],
        ondelete="NO ACTION",
        match="FULL",
    )
    op.create_foreign_key(
        "fk_games_game_type",
        "games",
        "system_vocabularies",
        ["game_type_key"],
        ["key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_games_tournament",
        "games",
        "tenant_vocabularies",
        ["tenant_id", "tournament_key"],
        ["tenant_id", "key"],
        ondelete="NO ACTION",
        match="FULL",
    )
    op.create_foreign_key(
        "fk_game_type_rule_defaults_type",
        "game_type_rule_defaults",
        "system_vocabularies",
        ["game_type_key"],
        ["key"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )
    op.create_foreign_key(
        "fk_tournament_rule_assignments_tournament",
        "tournament_rule_assignments",
        "tenant_vocabularies",
        ["tenant_id", "tournament_key"],
        ["tenant_id", "key"],
        ondelete="NO ACTION",
        match="FULL",
    )

    op.execute(
        f"""
        CREATE FUNCTION {_SYSTEM_VOCABULARY_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.key, NEW.category, NEW.display_name, NEW.disabled)
               IS DISTINCT FROM
               ROW(OLD.key, OLD.category, OLD.display_name, OLD.disabled) THEN
                RAISE EXCEPTION 'system vocabulary is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_SYSTEM_VOCABULARY_TRIGGER}
        BEFORE UPDATE OF key, category, display_name, disabled
        ON system_vocabularies
        FOR EACH ROW
        EXECUTE FUNCTION {_SYSTEM_VOCABULARY_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_ADMIN_VOCABULARY_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.key, NEW.category)
               IS DISTINCT FROM ROW(OLD.key, OLD.category) THEN
                RAISE EXCEPTION 'admin vocabulary identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_ADMIN_VOCABULARY_TRIGGER}
        BEFORE UPDATE OF key, category ON admin_vocabularies
        FOR EACH ROW
        EXECUTE FUNCTION {_ADMIN_VOCABULARY_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_TENANT_VOCABULARY_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.key, NEW.category)
               IS DISTINCT FROM ROW(OLD.key, OLD.category) THEN
                RAISE EXCEPTION 'tenant vocabulary identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TENANT_VOCABULARY_TRIGGER}
        BEFORE UPDATE OF key, category ON tenant_vocabularies
        FOR EACH ROW
        EXECUTE FUNCTION {_TENANT_VOCABULARY_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_SYSTEM_SETTING_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.key IS DISTINCT FROM OLD.key THEN
                RAISE EXCEPTION 'system setting key is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_SYSTEM_SETTING_TRIGGER}
        BEFORE UPDATE OF key ON system_settings
        FOR EACH ROW
        EXECUTE FUNCTION {_SYSTEM_SETTING_FUNCTION}()
        """
    )


def downgrade() -> None:
    """語彙・設定表、既存参照元の FK、不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_SYSTEM_SETTING_TRIGGER} ON system_settings")
    op.execute(f"DROP FUNCTION {_SYSTEM_SETTING_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_TENANT_VOCABULARY_TRIGGER} ON tenant_vocabularies")
    op.execute(f"DROP FUNCTION {_TENANT_VOCABULARY_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_ADMIN_VOCABULARY_TRIGGER} ON admin_vocabularies")
    op.execute(f"DROP FUNCTION {_ADMIN_VOCABULARY_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_SYSTEM_VOCABULARY_TRIGGER} ON system_vocabularies")
    op.execute(f"DROP FUNCTION {_SYSTEM_VOCABULARY_FUNCTION}()")

    op.drop_constraint(
        "fk_tournament_rule_assignments_tournament",
        "tournament_rule_assignments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_game_type_rule_defaults_type",
        "game_type_rule_defaults",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_games_tournament",
        "games",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_games_game_type",
        "games",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_players_roster_label",
        "players",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_players_roster_status",
        "players",
        type_="foreignkey",
    )

    op.drop_table("system_settings")
    op.drop_table("tenant_vocabularies")
    op.drop_table("admin_vocabularies")
    op.drop_table("system_vocabularies")
