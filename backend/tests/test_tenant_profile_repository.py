"""テナント情報の固定read operationをDBなしで検査する。"""

from dataclasses import fields
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.selectable import Select

from pitchlog.repositories.tenant_profile import (
    TENANT_PROFILE_OPERATIONS,
    TenantProfileReadToken,
)


def test_tenant_profile_token_has_no_caller_controlled_fields() -> None:
    """Tokenが文脈以外のテナント識別子を受け取れないことを確認する。"""
    token = TenantProfileReadToken()

    assert fields(token) == ()
    assert type(token).__dataclass_params__.frozen
    assert token.capability_id == "CAP:tenants:read"


def test_tenant_profile_registration_is_one_fixed_two_column_read() -> None:
    """登録文がtenantsのIDと名前を文脈IDだけで選ぶことを確認する。"""
    assert len(TENANT_PROFILE_OPERATIONS) == 1
    registration = TENANT_PROFILE_OPERATIONS[0]
    assert registration.token_type is TenantProfileReadToken
    assert registration.capability_id == "CAP:tenants:read"
    assert cast(Table, registration.tenant_column.table).name == "tenants"
    assert registration.tenant_column.key == "id"

    statement, parameters = registration.prepare(TenantProfileReadToken())
    assert isinstance(statement, Select)
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    assert tuple(column.name for column in statement.selected_columns) == ("id", "name")
    assert str(compiled) == (
        "SELECT tenants.id, tenants.name \n"
        "FROM tenants \n"
        "WHERE tenants.id = %(tenant_id)s::UUID"
    )
    assert parameters == {}


def test_tenant_profile_token_rejects_arguments() -> None:
    """任意tenant IDやSQLをTokenへ追加できないことを確認する。"""
    constructor = cast(Any, TenantProfileReadToken)
    with pytest.raises(TypeError):
        constructor(tenant_id="another-tenant")
    with pytest.raises(TypeError):
        constructor(statement="SELECT * FROM tenants")
