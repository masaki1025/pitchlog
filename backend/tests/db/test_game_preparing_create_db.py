"""実RG1常閉から作成serviceが非成功で取引を終えることを確認する。"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import event
from test_authz_tenant_context import make_tenant_context
from test_game_preparing_components import _create_payload

from pitchlog.api.schemas.games import PreparingGameCreate
from pitchlog.repositories import transaction
from pitchlog.repositories.rg1 import RG1Unavailable
from pitchlog.services.game_creation import create_preparing_game

from .conftest import ProvisionedProductCatalog
from .test_api_auth_exit_entry import _app_engine
from .test_product_authz_authn_app import _app_dsn

pytestmark = pytest.mark.requires_db


def test_create_service_real_closed_rg1_rolls_back_before_business_sql(
    provisioned_product_catalog: ProvisionedProductCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """migration/製品DDL/実app接続で拒否する。HTTP認証/保存成功の証明ではない。"""
    from uuid import uuid4

    catalog = provisioned_product_catalog
    engine = _app_engine(_app_dsn(catalog))
    tenant_id = uuid4()
    statements: list[str] = []
    rollbacks: list[bool] = []

    @event.listens_for(engine, "before_cursor_execute")
    def observe(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    @event.listens_for(engine, "rollback")
    def observe_rollback(connection: Any) -> None:
        rollbacks.append(True)

    monkeypatch.setattr(transaction, "create_database_engine", lambda: engine)
    try:
        with pytest.raises(RG1Unavailable, match="閉じている"):
            with transaction.tenant_transaction_scope(
                make_tenant_context(tenant_id)
            ) as scope:
                create_preparing_game(
                    scope, PreparingGameCreate.model_validate(_create_payload())
                )
        assert any("rg1_api.rg1_read_open" in statement for statement in statements)
        assert not any("INSERT INTO" in statement.upper() for statement in statements)
        assert rollbacks
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM public.games WHERE tenant_id = %s", (tenant_id,)
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT count(*) FROM public.tenant_vocabularies WHERE tenant_id = %s",
                (tenant_id,),
            )
            assert cursor.fetchone() == (0,)
    finally:
        catalog.observer.rollback()
        engine.dispose()
