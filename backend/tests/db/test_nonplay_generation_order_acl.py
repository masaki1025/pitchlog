"""正式owned製品構成でlegacy世代順序の最小列ACLを検査する。"""

import psycopg
import pytest
from product_authz_tenant_owned_cases import TENANT_A, TENANT_B

from .test_product_authz_other_profiles import (
    _open_app_connection,
    _set_tenant_context,
)
from .test_product_authz_other_profiles import (
    provisioned_product_catalog as provisioned_product_catalog,
)

pytestmark = pytest.mark.requires_db

_FUNCTION_IDENTITY = (
    "sync_right_api.read_nonplay_active_history("
    "uuid,uuid,bigint,uuid,bigint,bigint,bigint,bigint,bigint,bigint,uuid,integer)"
)


def test_nonplay_generation_order_owner_column_only(provisioned_product_catalog):
    """正式DDL適用後の実role・tenantで順序列のSELECTだけを追加確認する。"""
    catalog = provisioned_product_catalog
    key = (
        "COLUMN-ACL:public:recording_generations:issuance_order:"
        "pitchlog_sync_right_fn_owner"
    )
    rows = [
        row
        for row in catalog.asset["column_acl_expectations"]
        if row["expectation_id"] == key
    ]
    assert len(rows) == 1
    assert rows[0]["grantee_role_id"] == "pitchlog_sync_right_fn_owner"
    assert rows[0]["privilege_ids"] == ["SELECT"]
    assert rows[0]["grant_option"] is False

    with catalog.applicator.cursor() as cursor:
        cursor.execute(
            "SELECT "
            "pg_catalog.has_column_privilege("
            "'pitchlog_sync_right_fn_owner',"
            "'public.recording_generations','issuance_order','SELECT'),"
            "pg_catalog.has_any_column_privilege("
            "'pitchlog_sync_right_fn_owner',"
            "'public.recording_generations','UPDATE'),"
            "pg_catalog.has_table_privilege("
            "'pitchlog_sync_right_fn_owner',"
            "'public.recording_generations','SELECT'),"
            "pg_catalog.has_column_privilege("
            "'pitchlog_app',"
            "'public.recording_generations','issuance_order','SELECT'),"
            "pg_catalog.has_column_privilege("
            "'pitchlog_app',"
            "'public.recording_generations','issuance_order','UPDATE'),"
            "pg_catalog.has_column_privilege("
            "'pitchlog_app',"
            "'public.recording_generations','recovery_generation','UPDATE'),"
            "(SELECT pg_catalog.pg_get_userbyid(p.proowner) "
            "FROM pg_catalog.pg_proc p WHERE p.oid=%s::regprocedure)",
            (_FUNCTION_IDENTITY,),
        )
        assert cursor.fetchone() == (
            True,
            False,
            False,
            True,
            True,
            False,
            "pitchlog_sync_right_fn_owner",
        )
    catalog.applicator.rollback()

    with _open_app_connection(catalog) as app:
        for own, other in ((TENANT_A, TENANT_B), (TENANT_B, TENANT_A)):
            with app.cursor() as cursor:
                _set_tenant_context(cursor, own)
                cursor.execute(
                    "SELECT tenant_id,issuance_order "
                    "FROM public.recording_generations WHERE tenant_id=%s",
                    (own,),
                )
                visible = cursor.fetchall()
                assert visible and all(row[0] == own for row in visible)
                cursor.execute(
                    "SELECT tenant_id FROM public.recording_generations "
                    "WHERE tenant_id=%s",
                    (other,),
                )
                assert cursor.fetchall() == []
            app.rollback()
        with pytest.raises(psycopg.Error) as denied:
            with app.cursor() as cursor:
                _set_tenant_context(cursor, TENANT_A)
                cursor.execute(
                    "UPDATE public.recording_generations "
                    "SET recovery_generation=1 WHERE tenant_id=%s",
                    (TENANT_A,),
                )
        assert denied.value.sqlstate == "42501"
        app.rollback()
