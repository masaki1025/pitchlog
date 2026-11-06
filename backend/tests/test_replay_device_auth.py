"""DI1再掲B5をexact operationと正式本文で検査する。"""

from types import SimpleNamespace
from uuid import UUID

import pytest

from pitchlog.authz.first_ball_product import body, declaration
from pitchlog.authz.sync_right_sql import render_replay_device_verify_create_sql
from pitchlog.repositories.first_ball import _VerifyReplayDeviceToken
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.sync import apply

KEY = "FUNCTION:sync_right_api:verify_replay_device(uuid, uuid, bytea)"


def test_formal_body_and_acl_are_exact():
    """登録表・owner・実本文を単一rendererに束縛する。"""
    row = declaration("functions", KEY)
    assert row is not None
    assert row["owner_role_id"] == "pitchlog_sync_right_fn_owner"
    assert row["acl_expectations"] == [
        {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
    ]
    assert row["revoked_acl_expectations"] == [
        {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
    ]
    sql = render_replay_device_verify_create_sql()
    stored = body("function", KEY)
    assert stored is not None
    assert sql.replace("CREATE OR REPLACE FUNCTION", "CREATE FUNCTION", 1) in stored
    for clause in (
        "session_user <> 'pitchlog_app'",
        "current_user <> 'pitchlog_sync_right_fn_owner'",
        "p_tenant_id IS DISTINCT FROM",
        "pg_catalog.octet_length(p_credential_digest) <> 32",
        "d.tenant_id=p_tenant_id",
        "d.device_id=p_device_id",
        "d.credential_digest,d.revoked_at INTO stored_digest,revoked",
        "FOR SHARE",
        "revoked IS NULL",
        "stored_digest=p_credential_digest",
    ):
        assert clause in sql
    assert "INSERT" not in sql and "UPDATE" not in sql
    assert "writer_bindings" not in sql and "first_ball_write_admissions" not in sql


def test_exact_token_has_secret_free_repr_and_read_only_statement():
    """新資格は再掲専用exact型で、秘密はreprから漏らさない。"""
    token = _VerifyReplayDeviceToken(UUID(int=3), b"c" * 32)
    spec = FUNCTION_OPERATION_REGISTRY[type(token)]
    assert spec.operation_id == "SYNC_FIRST_BALL:verify_replay_device"
    assert spec.input_fields == (("device_id", UUID), ("credential_digest", bytes))
    assert spec.result_fields == (("device_matches", bool),)
    assert "cccc" not in repr(token)
    assert "verify_replay_device" in str(spec.statement)
    assert "bind_device" not in str(spec.statement)


@pytest.mark.parametrize("rows", [((True,),), ((False,),)])
def test_helper_preserves_exact_boolean(monkeypatch, rows):
    """DB戻り値の真偽だけを使い、falseを成功へ補わない。"""

    class Scope:
        def run_function(self, token):
            assert type(token) is _VerifyReplayDeviceToken
            return SimpleNamespace(rows=rows)

    result = apply._verify_replay_device(Scope(), UUID(int=2), b"d" * 32)
    assert result is rows[0][0]


@pytest.mark.parametrize("rows", [(), ((1,),), ((True, True),), ((None,),)])
def test_helper_rejects_noncanonical_rows(monkeypatch, rows):
    """欠落・余剰・異型を閉拒否する。"""

    class Scope:
        def run_function(self, token):
            return SimpleNamespace(rows=rows)

    with pytest.raises(RuntimeError, match="読取結果"):
        apply._verify_replay_device(Scope(), UUID(int=2), b"d" * 32)
