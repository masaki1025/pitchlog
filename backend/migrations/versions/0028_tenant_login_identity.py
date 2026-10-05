"""チーム名の正規化と認証主体・トークンの同一テナント制約を追加する。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_tenant_login_identity"
down_revision: str | Sequence[str] | None = "0027_seed_roster_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = "public.authn_normalize_team_name(text)"
# Unicode White_Space の 25 文字。U& のエスケープを使い、制御文字を SQL に直書きしない。
_WHITE_SPACE = (
    "U&'\\0009\\000A\\000B\\000C\\000D\\0020\\0085\\00A0"
    "\\1680\\2000\\2001\\2002\\2003\\2004\\2005\\2006"
    "\\2007\\2008\\2009\\200A\\2028\\2029\\202F\\205F\\3000'"
)


def _reject_existing_rows() -> None:
    """既存行の不整合を検出し、名前や参照先を変更せずに止める。"""
    op.execute(
        """
        DO $preflight$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM public.tenants
                WHERE retired_at IS NULL
                GROUP BY public.authn_normalize_team_name(name)
                HAVING pg_catalog.count(*) > 1
            ) THEN
                RAISE EXCEPTION '0028 の事前検査に失敗: 正規化名の重複';
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.tenants
                WHERE retired_at IS NULL
                  AND pg_catalog.char_length(
                      public.authn_normalize_team_name(name)
                  ) > 64
            ) THEN
                RAISE EXCEPTION '0028 の事前検査に失敗: 正規化名が 64 文字超';
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.tenant_auth_subjects
                GROUP BY tenant_id HAVING pg_catalog.count(*) > 1
            ) THEN
                RAISE EXCEPTION '0028 の事前検査に失敗: 同じテナントに複数の認証主体';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.tenant_tokens AS token
                JOIN public.tenant_auth_subjects AS subject
                  ON subject.id = token.auth_subject_id
                WHERE token.tenant_id <> subject.tenant_id
            ) THEN
                RAISE EXCEPTION '0028 の事前検査に失敗: トークンのテナント不一致';
            END IF;
        END
        $preflight$;
        """
    )


def upgrade() -> None:
    """純粋な正規化関数、生成列、一意性と複合参照を追加する。"""
    op.execute(
        f"""
        CREATE FUNCTION public.authn_normalize_team_name(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
        SECURITY INVOKER
        SET search_path = pg_catalog, pg_temp
        AS $function$
            SELECT pg_catalog.lower(
                pg_catalog.btrim(
                    pg_catalog."normalize"($1, 'NFKC'), {_WHITE_SPACE}
                ) COLLATE pg_catalog.pg_c_utf8
            )
        $function$;
        """
    )
    op.add_column(
        "tenants", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True)
    )
    _reject_existing_rows()
    op.add_column(
        "tenants",
        sa.Column(
            "name_normalized",
            sa.Text(),
            sa.Computed("public.authn_normalize_team_name(name)", persisted=True),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_tenants_name_normalized_length",
        "tenants",
        "pg_catalog.char_length(name_normalized) <= 64",
    )
    op.create_index(
        "uq_tenants_active_name_normalized",
        "tenants",
        ["name_normalized"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_unique_constraint(
        "uq_tenant_auth_subjects_tenant",
        "tenant_auth_subjects",
        ["tenant_id"],
    )
    op.create_unique_constraint(
        "uq_tenant_auth_subjects_tenant_id",
        "tenant_auth_subjects",
        ["tenant_id", "id"],
    )
    op.drop_constraint("fk_tenant_tokens_subject", "tenant_tokens", type_="foreignkey")
    op.create_foreign_key(
        "fk_tenant_tokens_subject",
        "tenant_tokens",
        "tenant_auth_subjects",
        ["tenant_id", "auth_subject_id"],
        ["tenant_id", "id"],
        match="FULL",
        ondelete="NO ACTION",
    )


def downgrade() -> None:
    """複合参照から逆順に外し、0027 seed 時点の表構造へ戻す。"""
    op.drop_constraint("fk_tenant_tokens_subject", "tenant_tokens", type_="foreignkey")
    op.create_foreign_key(
        "fk_tenant_tokens_subject",
        "tenant_tokens",
        "tenant_auth_subjects",
        ["auth_subject_id"],
        ["id"],
        match="SIMPLE",
        ondelete="NO ACTION",
    )
    op.drop_constraint(
        "uq_tenant_auth_subjects_tenant_id", "tenant_auth_subjects", type_="unique"
    )
    op.drop_constraint(
        "uq_tenant_auth_subjects_tenant", "tenant_auth_subjects", type_="unique"
    )
    op.drop_index("uq_tenants_active_name_normalized", table_name="tenants")
    op.drop_constraint("ck_tenants_name_normalized_length", "tenants", type_="check")
    op.drop_column("tenants", "name_normalized")
    op.drop_column("tenants", "retired_at")
    op.execute(f"DROP FUNCTION {_FUNCTION}")
