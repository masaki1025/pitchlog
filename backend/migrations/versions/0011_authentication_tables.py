"""認証主体、資格情報、セッション、通常トークンを追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_authentication_tables"
down_revision: str | Sequence[str] | None = "0010_vocabularies_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_AUTH_SUBJECT_FUNCTION = "prevent_tenant_auth_subjects_update"
_TENANT_AUTH_SUBJECT_TRIGGER = "trg_tenant_auth_subjects_immutable"
_TENANT_CREDENTIAL_FUNCTION = "prevent_tenant_credentials_subject_update"
_TENANT_CREDENTIAL_TRIGGER = "trg_tenant_credentials_subject_immutable"
_ADMIN_CREDENTIAL_FUNCTION = "prevent_admin_credentials_id_update"
_ADMIN_CREDENTIAL_TRIGGER = "trg_admin_credentials_id_immutable"
_ADMIN_SESSION_FUNCTION = "prevent_admin_sessions_identity_update"
_ADMIN_SESSION_TRIGGER = "trg_admin_sessions_identity_immutable"
_TENANT_TOKEN_FUNCTION = "prevent_tenant_tokens_identity_update"
_TENANT_TOKEN_TRIGGER = "trg_tenant_tokens_identity_immutable"


def upgrade() -> None:
    """認証5表と不変列トリガを追加する。"""
    op.create_table(
        "tenant_auth_subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_auth_subjects_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_auth_subjects"),
    )
    op.create_index(
        "ix_tenant_auth_subjects_tenant",
        "tenant_auth_subjects",
        ["tenant_id", "id"],
        unique=False,
    )
    op.create_table(
        "tenant_credentials",
        sa.Column("auth_subject_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "generation",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("generation > 0"),
        sa.ForeignKeyConstraint(
            ["auth_subject_id"],
            ["tenant_auth_subjects.id"],
            name="fk_tenant_credentials_subject",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint(
            "auth_subject_id",
            name="pk_tenant_credentials",
        ),
    )
    op.create_table(
        "admin_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "generation",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("generation > 0"),
        sa.PrimaryKeyConstraint("id", name="pk_admin_credentials"),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_credential_id", sa.Uuid(), nullable=False),
        sa.Column("credential_generation", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("credential_generation > 0"),
        sa.CheckConstraint("expires_at >= last_used_at"),
        sa.ForeignKeyConstraint(
            ["admin_credential_id"],
            ["admin_credentials.id"],
            name="fk_admin_sessions_credential",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_sessions"),
    )
    op.create_index(
        "ix_admin_sessions_expiry",
        "admin_sessions",
        ["expires_at", "id"],
        unique=False,
    )
    op.create_table(
        "tenant_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("auth_subject_id", sa.Uuid(), nullable=False),
        sa.Column("credential_generation", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("credential_generation > 0"),
        sa.CheckConstraint("expires_at >= last_used_at"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_tokens_tenant",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["auth_subject_id"],
            ["tenant_auth_subjects.id"],
            name="fk_tenant_tokens_subject",
            match="SIMPLE",
            ondelete="NO ACTION",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_tokens"),
    )
    op.create_index(
        "ix_tenant_tokens_expiry",
        "tenant_tokens",
        ["tenant_id", "expires_at", "id"],
        unique=False,
    )

    op.execute(
        f"""
        CREATE FUNCTION {_TENANT_AUTH_SUBJECT_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id, NEW.tenant_id)
               IS DISTINCT FROM ROW(OLD.id, OLD.tenant_id) THEN
                RAISE EXCEPTION 'tenant auth subject is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TENANT_AUTH_SUBJECT_TRIGGER}
        BEFORE UPDATE OF id, tenant_id ON tenant_auth_subjects
        FOR EACH ROW
        EXECUTE FUNCTION {_TENANT_AUTH_SUBJECT_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_TENANT_CREDENTIAL_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.auth_subject_id IS DISTINCT FROM OLD.auth_subject_id THEN
                RAISE EXCEPTION 'tenant credential subject is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TENANT_CREDENTIAL_TRIGGER}
        BEFORE UPDATE OF auth_subject_id ON tenant_credentials
        FOR EACH ROW
        EXECUTE FUNCTION {_TENANT_CREDENTIAL_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_ADMIN_CREDENTIAL_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id THEN
                RAISE EXCEPTION 'admin credential ID is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_ADMIN_CREDENTIAL_TRIGGER}
        BEFORE UPDATE OF id ON admin_credentials
        FOR EACH ROW
        EXECUTE FUNCTION {_ADMIN_CREDENTIAL_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_ADMIN_SESSION_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(NEW.id, NEW.admin_credential_id, NEW.credential_generation)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.admin_credential_id, OLD.credential_generation) THEN
                RAISE EXCEPTION 'admin session identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_ADMIN_SESSION_TRIGGER}
        BEFORE UPDATE OF id, admin_credential_id, credential_generation
        ON admin_sessions
        FOR EACH ROW
        EXECUTE FUNCTION {_ADMIN_SESSION_FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_TENANT_TOKEN_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF ROW(
                NEW.id,
                NEW.tenant_id,
                NEW.auth_subject_id,
                NEW.credential_generation
            ) IS DISTINCT FROM ROW(
                OLD.id,
                OLD.tenant_id,
                OLD.auth_subject_id,
                OLD.credential_generation
            ) THEN
                RAISE EXCEPTION 'tenant token identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TENANT_TOKEN_TRIGGER}
        BEFORE UPDATE OF id, tenant_id, auth_subject_id, credential_generation
        ON tenant_tokens
        FOR EACH ROW
        EXECUTE FUNCTION {_TENANT_TOKEN_FUNCTION}()
        """
    )


def downgrade() -> None:
    """認証5表と不変列トリガを除去する。"""
    op.execute(f"DROP TRIGGER {_TENANT_TOKEN_TRIGGER} ON tenant_tokens")
    op.execute(f"DROP FUNCTION {_TENANT_TOKEN_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_ADMIN_SESSION_TRIGGER} ON admin_sessions")
    op.execute(f"DROP FUNCTION {_ADMIN_SESSION_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_ADMIN_CREDENTIAL_TRIGGER} ON admin_credentials")
    op.execute(f"DROP FUNCTION {_ADMIN_CREDENTIAL_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_TENANT_CREDENTIAL_TRIGGER} ON tenant_credentials")
    op.execute(f"DROP FUNCTION {_TENANT_CREDENTIAL_FUNCTION}()")
    op.execute(f"DROP TRIGGER {_TENANT_AUTH_SUBJECT_TRIGGER} ON tenant_auth_subjects")
    op.execute(f"DROP FUNCTION {_TENANT_AUTH_SUBJECT_FUNCTION}()")

    op.drop_index("ix_tenant_tokens_expiry", table_name="tenant_tokens")
    op.drop_table("tenant_tokens")
    op.drop_index("ix_admin_sessions_expiry", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_table("admin_credentials")
    op.drop_table("tenant_credentials")
    op.drop_index(
        "ix_tenant_auth_subjects_tenant",
        table_name="tenant_auth_subjects",
    )
    op.drop_table("tenant_auth_subjects")
