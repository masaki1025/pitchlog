"""正式installerの端末状態readをowned PGで検査する。資格はfixtureと区別する。"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from db_fixtures import _product_role_ids, _snapshot_product_catalog

from pitchlog.authz import product_provisioning as provision

from . import test_initial_recording_right_scope as initial
from .first_ball_stamp_support import exec_text, peer
from .sync_writer_binding_support import ACTOR, APP, _literal
from .test_first_ball_stamp_issuance import _make_env

pytestmark = pytest.mark.requires_db
admin_connection = initial.admin_connection
tested_role_connection = initial.tested_role_connection
_IDENTITY = "sync_right_api.read_device_state(uuid,uuid)"


@dataclass(repr=False)
class _ActivatedState:
    """pytestの失敗reprへ元fixtureのproof等を展開しない閉じたview。"""

    owner: Any
    db: Any
    ctx: Any


@pytest.fixture
def activated() -> Iterator[Any]:
    """正式installerだけで新readを持つ自己所有PGを得る。"""
    owned_volumes: set[str] = set()
    try:
        with pytest.MonkeyPatch.context() as patch:
            with contextmanager(_make_env)(patch, apply=True) as env:
                database = env.owner.authority.database
                containers = (
                    database.primary,
                    database.standby,
                    database.business,
                    *env.owner.authority._names,
                )
                for container in containers:
                    observed = subprocess.run(
                        [
                            "docker",
                            "inspect",
                            "--format",
                            "{{json .Mounts}}",
                            container,
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if observed.returncode:
                        continue  # --rmの自己所有短命workerは既に終了している。
                    mounts = json.loads(observed.stdout)
                    owned_volumes.update(
                        row["Name"] for row in mounts if row["Type"] == "volume"
                    )
                yield _ActivatedState(env.owner, env.db, env.ctx)
    finally:
        # 記録した自己所有containerのmountだけ。既存/出所不明volumeは削除しない。
        for volume in sorted(owned_volumes):
            present = subprocess.run(
                ["docker", "volume", "inspect", volume],
                capture_output=True,
                check=False,
            )
            if present.returncode:
                continue  # 既fixtureが正しく削除したnamed volume。
            users = subprocess.check_output(
                ["docker", "ps", "-aq", "--filter", "volume=" + volume], text=True
            ).strip()
            assert not users, "自己所有volumeを利用中のcontainerが残った"
            subprocess.run(
                ["docker", "volume", "rm", volume],
                capture_output=True,
                check=True,
            )


@pytest.fixture
def initial_scope_database(activated: Any) -> Any:
    """既identity autouseへ自己所有DBを渡す。"""
    return activated.owner


def _catalog(conn):
    """role/schema/table/columnACL/policy/functionを含む全catalogを固定する。"""
    root = Path(__file__).resolve().parents[3]
    asset = json.loads((root / "contracts/authz/product/ddl-elements.json").read_text())
    try:
        return _snapshot_product_catalog(conn, _product_role_ids(asset))
    finally:
        conn.rollback()


def _business(env):
    """全印/原本と端末の全値を順序付きJSONで比較する。"""
    tables = (
        "public.trusted_devices",
        "public.operation_events",
        "public.play_rows",
        "public.idempotency_ledger",
        "public.event_slots",
        "sync_fence.writer_bindings",
        "sync_fence.writer_admissions",
        "sync_fence.first_ball_write_admissions",
    )
    result = []
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        for table in tables:
            row = conn.execute(
                "SELECT coalesce(jsonb_agg(to_jsonb(t) "
                "ORDER BY to_jsonb(t)::text),'[]'::jsonb) FROM " + table + " t"
            ).fetchone()
            assert row is not None
            result.append((table, row[0]))
    return tuple(result)


def test_real_app_read_is_tenant_limited_and_read_only(activated):
    """同tenantのactiveだけtrue、不在/失効/実在別tenantはfalseにする。"""
    env = activated
    foreign, other, revoked = uuid4(), uuid4(), uuid4()
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        conn.execute(
            "INSERT INTO public.tenants(id,name) VALUES (%s,%s)",
            (foreign, "read-fixture-" + str(foreign)),
        )
        conn.execute(
            "INSERT INTO public.trusted_devices(tenant_id,device_id,"
            "credential_digest) VALUES (%s,%s,%s)",
            (foreign, other, bytes(32)),
        )
        conn.execute(
            "INSERT INTO public.trusted_devices(tenant_id,device_id,"
            "credential_digest,revoked_at) VALUES (%s,%s,%s,CURRENT_TIMESTAMP)",
            (env.ctx.tenant, revoked, bytes(32)),
        )
        conn.commit()
        before_catalog = _catalog(conn)
    before = _business(env)
    with peer(env.db, APP) as app:
        env.ctx.begin(app)
        for device, expected in (
            (env.ctx.device, "t"),
            (uuid4(), "f"),
            (revoked, "f"),
            (other, "f"),
        ):
            rows, state, _ = app.run(
                "SELECT device_active FROM sync_right_api.read_device_state("
                + _literal(str(env.ctx.tenant))
                + "::uuid,"
                + _literal(str(device))
                + "::uuid)"
            )
            assert state == "00000" and rows == (expected,)
        assert app.run("COMMIT")[1] == "00000"
    assert _business(env) == before
    with psycopg.connect(env.ctx.admin_dsn) as conn:
        assert _catalog(conn) == before_catalog


def test_invalid_role_tenant_and_null_are_not_false(activated):
    """境界違反を結果falseへ補完しない。実app/別roleを使う。"""
    env = activated
    for role, tenant, device in (
        (ACTOR, env.ctx.tenant, env.ctx.device),
        (APP, uuid4(), env.ctx.device),
        (APP, None, env.ctx.device),
        (APP, env.ctx.tenant, None),
    ):
        before = _business(env)
        with peer(env.db, role) as app:
            env.ctx.begin(app)
            _, state, _ = app.run(
                "SELECT * FROM sync_right_api.read_device_state("
                + _literal(str(tenant) if tenant else None)
                + "::uuid,"
                + _literal(str(device) if device else None)
                + "::uuid)"
            )
            assert state == "42501"
            app.run("ROLLBACK")
        assert _business(env) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "body",
        "public",
        "app-extra",
        "security",
        "search-path",
        "returns",
        "arguments",
    ],
)
def test_reapply_rejects_collision_without_repair(activated, mutation):
    """定義/全ACLの変異を自動修復せず、そのまま拒否する。"""
    statements = {
        "owner": f"ALTER FUNCTION {_IDENTITY} OWNER TO pitchlog_owner",
        "body": (
            "CREATE OR REPLACE FUNCTION sync_right_api.read_device_state("
            "p_tenant_id uuid,p_device_id uuid) RETURNS TABLE(device_active boolean) "
            "LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp "
            "AS $$ BEGIN RETURN QUERY SELECT false; END $$"
        ),
        "public": f"GRANT EXECUTE ON FUNCTION {_IDENTITY} TO PUBLIC",
        "app-extra": (
            f"GRANT EXECUTE ON FUNCTION {_IDENTITY} TO pitchlog_app WITH GRANT OPTION"
        ),
        "security": f"ALTER FUNCTION {_IDENTITY} SECURITY INVOKER",
        "search-path": f"ALTER FUNCTION {_IDENTITY} SET search_path=public",
        "returns": (
            f"DROP FUNCTION {_IDENTITY}; "
            "CREATE FUNCTION sync_right_api.read_device_state(p_tenant_id uuid,"
            "p_device_id uuid) RETURNS integer LANGUAGE SQL AS 'SELECT 1'"
        ),
        "arguments": (
            f"DROP FUNCTION {_IDENTITY}; "
            "CREATE FUNCTION sync_right_api.read_device_state("
            "p_tenant_id uuid,p_device_id text) RETURNS TABLE(device_active boolean) "
            "LANGUAGE SQL AS 'SELECT false'"
        ),
    }
    with psycopg.connect(activated.ctx.admin_dsn) as conn:
        exec_text(conn, statements[mutation])
        conn.commit()
        before = _catalog(conn)
        with pytest.raises((psycopg.Error, provision.ProductProvisioningError)):
            provision.apply_product_authz_ddl(conn)
        assert _catalog(conn) == before
    # 改変済みDBはfixtureが破棄する。手動修復して次試験へ流用しない。


def test_exact_reapply_preserves_entire_catalog(activated):
    """全属性・ACL・NULL/空を含むcatalog全値を再適用前後で維持する。"""
    with psycopg.connect(activated.ctx.admin_dsn) as conn:
        before = _catalog(conn)
        provision.apply_product_authz_ddl(conn)
        assert _catalog(conn) == before


@pytest.mark.parametrize(
    "checkpoint", ["product:3:after_helper_function_creation", "product:6:during"]
)
def test_creation_and_acl_failure_roll_back_all_catalog(
    activated, monkeypatch, checkpoint
):
    """新関数の再作成/ACL後の故障でも全catalogをbeforeへ戻す。"""

    class Injected(RuntimeError):
        """公開固定値の試験故障。"""

    with psycopg.connect(activated.ctx.admin_dsn) as conn:
        exec_text(conn, f"DROP FUNCTION {_IDENTITY}")
        conn.commit()
        before = _catalog(conn)
        hits = []

        def fail(point):
            if point == checkpoint:
                assert conn.execute(
                    "SELECT to_regprocedure(%s) IS NOT NULL", (_IDENTITY,)
                ).fetchone() == (True,)
                hits.append(point)
                raise Injected("owned read activation fault")

        with monkeypatch.context() as patch:
            patch.setattr(provision, "_record_product_checkpoint", fail)
            with pytest.raises(Injected):
                provision.apply_product_authz_ddl(conn)
        assert hits == [checkpoint]
        assert _catalog(conn) == before
        provision.apply_product_authz_ddl(conn)
        assert conn.execute(
            "SELECT to_regprocedure(%s) IS NOT NULL", (_IDENTITY,)
        ).fetchone() == (True,)


def test_cookie_context_registered_runtime_read(activated):
    """実Cookieから発行したcontextと実appUIDで正式run_functionを通す。"""
    db = activated.owner
    password = "public-device-read-owned-A1"
    with psycopg.connect(activated.ctx.admin_dsn) as conn:
        subject = uuid4()
        conn.execute(
            "INSERT INTO public.tenant_auth_subjects(id,tenant_id) VALUES (%s,%s)",
            (subject, db.tenant_id),
        )
        conn.execute(
            "INSERT INTO public.tenant_credentials(auth_subject_id,password_hash) "
            "VALUES (%s,authn_crypto.crypt(%s,authn_crypto.gen_salt('bf',12)))",
            (subject, password),
        )
        for key, value in {
            "auth.token_ttl_seconds": 3600,
            "auth.team_login.window_seconds": 3600,
            "auth.team_login.throttle_threshold": 3,
            "auth.team_login.throttle_step_ms": 25,
            "auth.team_login.throttle_max_ms": 200,
        }.items():
            conn.execute(
                "INSERT INTO public.system_settings(key,value) VALUES (%s,%s) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                (key, str(value)),
            )
        row = conn.execute(
            "SELECT name FROM public.tenants WHERE id=%s", (db.tenant_id,)
        ).fetchone()
        assert row is not None
        name = row[0]
        conn.commit()
    args = db._broker_arguments(uid=20003)
    args[1:1] = [
        "--volume",
        f"{db.authority.database.business_socket}:/business-socket:ro",
    ]
    code = f"""
import os,sys,json,base64,asyncio,traceback
from uuid import UUID
assert os.geteuid()==20003 and os.getegid()==20003
os.environ['PITCHLOG_TOKEN_SIGNING_KEY_B64']=base64.b64encode(bytes(range(32))).decode()
os.environ['PITCHLOG_ALLOWED_ORIGINS']='https://test'
os.environ['PITCHLOG_DATABASE_URL']='postgresql+psycopg://pitchlog_app@/ledger_fixture?host=%2Fbusiness-socket&sslmode=disable'
os.environ['PITCHLOG_DATABASE_POOLED']='false'
from httpx import AsyncClient,ASGITransport
from pitchlog.api.app import create_app
from pitchlog.repositories.tenant_context_issuance import (
    issue_tenant_context_from_presented_token)
from pitchlog.repositories.transaction import tenant_transaction_scope
from pitchlog.repositories.first_ball import _ReadFirstBallDeviceStateToken
app=create_app()
def safe_error(kind,value,tb):
    print(json.dumps({{'fixture_failure':kind.__name__,
        'frames':[(x.name,x.lineno) for x in traceback.extract_tb(tb)]}}))
sys.excepthook=safe_error
async def run():
    async with AsyncClient(
        transport=ASGITransport(app=app),base_url='https://test') as client:
        response=await client.post('/auth/login',json={{'team_name':{name!r},'password':{password!r}}},headers={{'Origin':'https://test','X-Pitchlog-Request':'1'}})
        assert response.status_code==200
        cookie=client.cookies.get('__Host-pitchlog_token')
        assert cookie
        issued=issue_tenant_context_from_presented_token(cookie,app.state.token_presentation)
        assert issued is not None
        context,_=issued
        assert str(context.tenant_id)=={str(db.tenant_id)!r}
        with tenant_transaction_scope(context) as handle:
            result=handle.run_function(_ReadFirstBallDeviceStateToken(UUID({str(db.device_id)!r})))
            assert result.rows==((True,),)
        try:
            handle.run_function(_ReadFirstBallDeviceStateToken(UUID({str(db.device_id)!r})))
        except RuntimeError:
            pass
        else:
            raise AssertionError('expired read was accepted')
        print(json.dumps({{'cookie_authenticated':True,'runtime_read':True,'expired_rejected':True}}))
asyncio.run(run())
"""
    process = subprocess.run(
        ["docker", *args, "-u", "-c", code], capture_output=True, text=True, timeout=90
    )
    try:
        value = json.loads(process.stdout)
    except ValueError:
        raise AssertionError("app peerの安全応答が非JSON") from None
    assert process.returncode == 0, value
    assert value == {
        "cookie_authenticated": True,
        "runtime_read": True,
        "expired_rejected": True,
    }
