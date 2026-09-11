"""分析グループ・参加・付与・招待を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_analysis_groups"
down_revision: str | Sequence[str] | None = "0013_player_merge_rate_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ANALYSIS_GROUP_FUNCTION = "prevent_analysis_groups_id_update"
_ANALYSIS_GROUP_TRIGGER = "trg_analysis_groups_id_immutable"
_GROUP_MEMBERSHIP_FUNCTION = "prevent_group_memberships_identity_update"
_GROUP_MEMBERSHIP_TRIGGER = "trg_group_memberships_identity_immutable"
_SHARING_GRANT_FUNCTION = "prevent_sharing_grants_membership_update"
_SHARING_GRANT_TRIGGER = "trg_sharing_grants_membership_immutable"
_GROUP_INVITATION_FUNCTION = "prevent_group_invitations_identity_update"
_GROUP_INVITATION_TRIGGER = "trg_group_invitations_identity_immutable"


def upgrade() -> None:
    """グループ4表、管理者ログの越境FK、不変性トリガを追加する。"""
    op.create_table(
        "analysis_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('active', 'terminated')"),
        sa.CheckConstraint("(status = 'terminated') = (terminated_at IS NOT NULL)"),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_groups"),
    )
    op.create_table(
        "group_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Text(),
            server_default=sa.text("'member'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'member')"),
        sa.CheckConstraint("status IN ('active', 'left')"),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["analysis_groups.id"],
            name="fk_group_memberships_group",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_group_memberships_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_group_memberships"),
    )
    op.create_index(
        "uq_group_memberships_active",
        "group_memberships",
        ["group_id", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_group_memberships_tenant",
        "group_memberships",
        ["tenant_id", "status", "group_id"],
        unique=False,
    )
    op.create_table(
        "sharing_grants",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column(
            "grant_flags",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["group_memberships.id"],
            name="fk_sharing_grants_membership",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("membership_id", name="pk_sharing_grants"),
    )
    op.create_table(
        "group_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'unconsumed'"),
            nullable=False,
        ),
        sa.Column(
            "initial_role",
            sa.Text(),
            server_default=sa.text("'member'"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('unconsumed', 'consumed', 'revoked')"),
        sa.CheckConstraint("initial_role IN ('admin', 'member')"),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["analysis_groups.id"],
            name="fk_group_invitations_group",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_group_invitations"),
        sa.UniqueConstraint("code_hash", name="uq_group_invitations_code_hash"),
    )
    op.create_index(
        "ix_group_invitations_expiry",
        "group_invitations",
        ["expires_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'unconsumed'"),
    )
    op.create_foreign_key(
        "fk_admin_operation_logs_group",
        "admin_operation_logs",
        "analysis_groups",
        ["group_id"],
        ["id"],
        ondelete="NO ACTION",
        match="SIMPLE",
    )

    op.execute(
        f"""
        CREATE FUNCTION {_ANALYSIS_GROUP_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id THEN
                RAISE EXCEPTION 'analysis group ID is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_ANALYSIS_GROUP_TRIGGER}
        BEFORE UPDATE OF id ON analysis_groups
        FOR EACH ROW
        EXECUTE FUNCTION {_ANALYSIS_GROUP_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_GROUP_MEMBERSHIP_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id, NEW.group_id, NEW.tenant_id, NEW.joined_at)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.group_id, OLD.tenant_id, OLD.joined_at) THEN
                RAISE EXCEPTION 'group membership identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_GROUP_MEMBERSHIP_TRIGGER}
        BEFORE UPDATE OF id, group_id, tenant_id, joined_at
        ON group_memberships
        FOR EACH ROW
        EXECUTE FUNCTION {_GROUP_MEMBERSHIP_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_SHARING_GRANT_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.membership_id IS DISTINCT FROM OLD.membership_id THEN
                RAISE EXCEPTION 'sharing grant membership is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_SHARING_GRANT_TRIGGER}
        BEFORE UPDATE OF membership_id ON sharing_grants
        FOR EACH ROW
        EXECUTE FUNCTION {_SHARING_GRANT_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_GROUP_INVITATION_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id, NEW.group_id, NEW.code_hash, NEW.initial_role)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.group_id, OLD.code_hash, OLD.initial_role) THEN
                RAISE EXCEPTION 'group invitation identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_GROUP_INVITATION_TRIGGER}
        BEFORE UPDATE OF id, group_id, code_hash, initial_role
        ON group_invitations
        FOR EACH ROW
        EXECUTE FUNCTION {_GROUP_INVITATION_FUNCTION}()
        """
    )


def downgrade() -> None:
    """グループ4表、管理者ログの越境FK、不変性トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_GROUP_INVITATION_TRIGGER} ON group_invitations")
    op.execute(f"DROP FUNCTION {_GROUP_INVITATION_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_SHARING_GRANT_TRIGGER} ON sharing_grants")
    op.execute(f"DROP FUNCTION {_SHARING_GRANT_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_GROUP_MEMBERSHIP_TRIGGER} ON group_memberships")
    op.execute(f"DROP FUNCTION {_GROUP_MEMBERSHIP_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_ANALYSIS_GROUP_TRIGGER} ON analysis_groups")
    op.execute(f"DROP FUNCTION {_ANALYSIS_GROUP_FUNCTION}()")

    op.drop_constraint(
        "fk_admin_operation_logs_group",
        "admin_operation_logs",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_group_invitations_expiry",
        table_name="group_invitations",
    )
    op.drop_table("group_invitations")
    op.drop_table("sharing_grants")
    op.drop_index(
        "ix_group_memberships_tenant",
        table_name="group_memberships",
    )
    op.drop_index(
        "uq_group_memberships_active",
        table_name="group_memberships",
    )
    op.drop_table("group_memberships")
    op.drop_table("analysis_groups")
