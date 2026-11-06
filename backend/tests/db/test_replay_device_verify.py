"""DI1再掲端末readの実owner・RLS・資格をowned PGで検査する。"""

from uuid import uuid4

import psycopg
import pytest

from pitchlog.repositories.initial_recording_right import _credential_digest

from . import test_initial_recording_right_scope as initial
from .first_ball_stamp_support import peer
from .sync_writer_binding_support import ACTOR, APP, _literal
from .test_device_state_read_activation import _business
from .test_device_state_read_activation import activated as activated_fixture

_DI1_FIXTURE = activated_fixture
admin_connection = initial.admin_connection
tested_role_connection = initial.tested_role_connection


@pytest.fixture
def initial_scope_database(request):
    """既identity autouseをowned正式catalogのDSNへ結ぶ。"""
    return request.getfixturevalue("activated_fixture").owner


pytestmark = pytest.mark.requires_db


def _read(tenant, device, digest):
    return (
        "SELECT device_matches FROM sync_right_api.verify_replay_device("
        + _literal(str(tenant) if tenant else None)
        + "::uuid,"
        + _literal(str(device) if device else None)
        + "::uuid,"
        + _literal(digest)
        + "::bytea)"
    )


def test_real_role_tenant_credential_and_no_write(request):
    """真正資格だけtrue、偽ID/資格/失効/別tenant/別roleは閉拒否。"""
    env = request.getfixturevalue("activated_fixture")
    good = _credential_digest("credential-a")
    bad = _credential_digest("credential-b")
    foreign, other, revoked = uuid4(), uuid4(), uuid4()
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        conn.execute(
            "INSERT INTO public.tenants(id,name) VALUES (%s,%s)",
            (foreign, "di1-fixture-" + str(foreign)),
        )
        conn.execute(
            "INSERT INTO public.trusted_devices(tenant_id,device_id,credential_digest)"
            " VALUES (%s,%s,%s)",
            (foreign, other, good),
        )
        conn.execute(
            "INSERT INTO public.trusted_devices"
            "(tenant_id,device_id,credential_digest,revoked_at)"
            " VALUES (%s,%s,%s,CURRENT_TIMESTAMP)",
            (env.ctx.tenant, revoked, good),
        )
        conn.commit()
    before = _business(env)
    with peer(env.db, APP) as app:
        env.ctx.begin(app)
        for device, digest, expected in (
            (env.ctx.device, good, "t"),
            (env.ctx.device, bad, "f"),
            (uuid4(), good, "f"),
            (revoked, good, "f"),
            (other, good, "f"),
        ):
            rows, state, _ = app.run(_read(env.ctx.tenant, device, digest))
            assert state == "00000" and rows == (expected,)
        assert app.run("COMMIT")[1] == "00000"
    assert _business(env) == before
    for role, tenant, device, digest in (
        (ACTOR, env.ctx.tenant, env.ctx.device, good),
        (APP, foreign, other, good),
        (APP, None, env.ctx.device, good),
        (APP, env.ctx.tenant, None, good),
        (APP, env.ctx.tenant, env.ctx.device, b"x"),
    ):
        with peer(env.db, role) as app:
            env.ctx.begin(app)
            _, state, _ = app.run(_read(tenant, device, digest))
            assert state == "42501"
            app.run("ROLLBACK")
    assert _business(env) == before


def test_revocation_before_b5_fails_and_after_b5_waits_for_d5_scope(request):
    """先行失効はfalse、取得済み行lockはD5を読む同TXの終結まで残る。"""
    env = request.getfixturevalue("activated_fixture")
    digest = _credential_digest("credential-a")
    with peer(env.db, APP) as app:
        env.ctx.begin(app)
        rows, state, _ = app.run(_read(env.ctx.tenant, env.ctx.device, digest))
        assert state == "00000" and rows == ("t",)
        with psycopg.connect(env.ctx.admin_dsn) as admin:
            admin.execute("SET lock_timeout='250ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable) as blocked:
                admin.execute(
                    "UPDATE public.trusted_devices SET revoked_at=clock_timestamp() "
                    "WHERE tenant_id=%s AND device_id=%s",
                    (env.ctx.tenant, env.ctx.device),
                )
            assert blocked.value.sqlstate == "55P03"
            admin.rollback()
            # 端末照合と同じapp TXで既D5 read相当の正式台帳SELECTを終える。
            rows, state, _ = app.run(
                "SELECT count(*) FROM public.idempotency_ledger "
                "WHERE tenant_id=" + _literal(str(env.ctx.tenant)) + "::uuid "
                "AND d5=" + _literal(str(uuid4())) + "::uuid"
            )
            assert state == "00000" and rows == ("0",)
            assert app.run("COMMIT")[1] == "00000"
            admin.execute(
                "UPDATE public.trusted_devices SET revoked_at=clock_timestamp() "
                "WHERE tenant_id=%s AND device_id=%s",
                (env.ctx.tenant, env.ctx.device),
            )
            admin.commit()
        env.ctx.begin(app)
        rows, state, _ = app.run(_read(env.ctx.tenant, env.ctx.device, digest))
        assert state == "00000" and rows == ("f",)
        assert app.run("COMMIT")[1] == "00000"
