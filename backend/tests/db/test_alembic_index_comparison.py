"""owned0040実catalogでC反射修復と誤形状の閉拒否を検証する。"""

from __future__ import annotations

from typing import LiteralString

import pytest
from alembic import command
from alembic.util import CommandError
from db_fixtures import ProvisionedProductCatalog
from psycopg import sql
from sqlalchemy import create_engine, text

from pitchlog.db import alembic_index_comparison as target
from pitchlog.db.url import normalize_postgresql_url

from .test_alembic_migrations import _alembic_config, _sqlalchemy_url
from .test_schema_audit import _prepare_current_audit_index

pytestmark = pytest.mark.requires_db


def test_current0040_owner_upgrade_current_and_check_are_real(
    provisioned_product_catalog: ProvisionedProductCatalog,
):
    """旧S3から0040を明示適用し、実index証跡→current/checkを同ownerで通す。"""
    catalog = provisioned_product_catalog
    _prepare_current_audit_index(catalog)
    engine = create_engine(normalize_postgresql_url(_sqlalchemy_url(catalog.owner_dsn)))
    try:
        with engine.begin() as connection:
            assert connection.exec_driver_sql(
                "SELECT current_user,session_user"
            ).one() == ("pitchlog_owner", "pitchlog_owner")
            result = connection.execute(text(target._CATALOG_SQL))
            try:
                target._catalog_is_exact(result.fetchall())
            finally:
                result.close()
            cfg = _alembic_config()
            cfg.attributes["connection"] = connection
            command.current(cfg, check_heads=True)
            command.check(cfg)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "mutation",
    ["collation", "predicate", "expression", "unique", "order", "owner", "validity"],
)
def test_wrong_real0040_index_is_not_hidden(
    provisioned_product_catalog: ProvisionedProductCatalog,
    mutation: str,
):
    """同じowned catalogで誤C/述語/式/一意/方向/owner/validityを実変更し拒否する。"""
    catalog = provisioned_product_catalog
    _prepare_current_audit_index(catalog)
    # applicatorはこのfixture自身の隔離DB管理接続。全故障注入は同TX rollbackする。
    admin = catalog.applicator
    admin.rollback()
    with admin.transaction(force_rollback=True):
        if mutation in {"owner", "validity"}:
            if mutation == "owner":
                admin.execute(
                    "ALTER TABLE public.admin_vocabularies OWNER TO pitchlog_app"
                )
            else:
                admin.execute(
                    "UPDATE pg_catalog.pg_index SET indisvalid=false "
                    "WHERE indexrelid="
                    "'public.ix_admin_vocabularies_batted_ball_key_c'::regclass"
                )
        else:
            admin.execute("DROP INDEX public.ix_admin_vocabularies_batted_ball_key_c")
            expressions: dict[str, LiteralString] = {
                "collation": 'key COLLATE "POSIX"',
                "expression": 'lower(key) COLLATE "C"',
                "order": 'key COLLATE "C" DESC',
            }
            expression = expressions.get(mutation, 'key COLLATE "C"')
            predicate = (
                "category = 'other' AND disabled = false"
                if mutation == "predicate"
                else target._PREDICATE
            )
            unique = "UNIQUE " if mutation == "unique" else ""
            # 候補は上記閉じた定数だけ。利用者SQL/DSN/role作成・grantは無い。
            admin.execute(
                sql.SQL(
                    "CREATE {}INDEX ix_admin_vocabularies_batted_ball_key_c "
                    "ON public.admin_vocabularies ({}) WHERE {}"
                ).format(sql.SQL(unique), sql.SQL(expression), sql.SQL(predicate))
            )
            # 管理接続でCREATEしたindex ownerも正規ownerへ戻して他差分を単独にする。
            admin.execute(
                "ALTER TABLE public.admin_vocabularies OWNER TO pitchlog_owner"
            )
        # 実catalog故障は標準比較の前に用いる同じ閉validatorで拒否する。
        # 正常側は上の実command.check、hookへの接合は純試験で別に検証する。
        with admin.execute(target._CATALOG_SQL) as cursor:
            rows = cursor.fetchall()
        with pytest.raises(CommandError):
            target._catalog_is_exact(rows)
