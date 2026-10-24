"""所有3PG/実fresh/controllerと実HTTPアプリを接続する隔離補助。"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Literal, cast
from urllib.parse import urlsplit
from urllib.request import Request
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.db.stage_a_startup import advance_stage_a_from_s0

from . import durable_rights_ledger_support as ledger_support
from .conftest import ProvisionedProductCatalog
from .durable_rights_ledger_support import (
    _PUBLIC_FIXTURE_PASSWORD,
    AuthorityDatabase,
    docker,
)
from .rg1_fresh_controller_support import FreshControllerDatabase
from .test_product_authz_authn_app import _Identity, _seed_identity, _seed_settings

_ROOT = Path(__file__).resolve().parents[3]


def _validated_frontend_origin(origin: str) -> str:
    """所有browserの明示HTTP loopback originだけを設定値として受け取る。"""
    try:
        if type(origin) is not str:
            raise ValueError
        parsed = urlsplit(origin)
        port = parsed.port
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port is None
            or not 0 < port < 65536
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or origin != f"http://127.0.0.1:{port}"
        ):
            raise ValueError
        return origin
    except ValueError:
        raise ValueError("所有frontendの明示loopback originが必要") from None


@contextmanager
def isolated_preparing_authority_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[AuthorityDatabase]:
    """試験用初期化だけをラップし、追加subject前の真のS3を完了する。"""
    original = ledger_support._install_product_business
    initialized: list[str] = []

    def install_then_stage(dsn: str) -> None:
        original(dsn)
        with psycopg.connect(dsn, autocommit=True) as admin:
            assert admin.execute(
                "SELECT count(*) FROM pg_catalog.pg_roles "
                "WHERE rolname='pitchlog_ledger_identity_probe'"
            ).fetchone() == (0,)
            # 今回使わない旧fixture writerの権限は恒久撤去し、後で復元しない。
            admin.execute(
                "REVOKE CONNECT,TEMPORARY ON DATABASE ledger_fixture "
                "FROM pitchlog_fixture_business_writer"
            )
            assert admin.execute(
                "SELECT pg_catalog.has_database_privilege("
                "'pitchlog_fixture_business_writer',current_database(),'CONNECT'), "
                "pg_catalog.has_database_privilege("
                "'pitchlog_fixture_business_writer',current_database(),'TEMPORARY')"
            ).fetchone() == (False, False)
            admin.execute(
                sql.SQL("ALTER ROLE pitchlog_owner PASSWORD {}").format(
                    sql.Literal(_PUBLIC_FIXTURE_PASSWORD)
                )
            )
        stage = advance_stage_a_from_s0(
            owner_dsn=make_conninfo(
                dsn, user="pitchlog_owner", password=_PUBLIC_FIXTURE_PASSWORD
            ),
            applicator_dsn=dsn,
        )
        assert stage.completed_stage == "S3" and stage.publishable is False
        initialized.append("strict_S3_before_identity_enrollment_controller")

    # 製品callback/認可/検査は変更しない。同processの試験初期化順だけを差し替える。
    with monkeypatch.context() as patch:
        patch.setattr(ledger_support, "_install_product_business", install_then_stage)
        with ledger_support.isolated_authority_database() as authority:
            assert initialized == ["strict_S3_before_identity_enrollment_controller"]
            yield authority


class _OwnedLoopbackCookiePolicy(DefaultCookiePolicy):
    """実loginのSecure Cookieを、所有HTTP origin一つだけへ自動再送する。"""

    def __init__(self, origin: str) -> None:
        """運用HTTPSの代用ではなく、隔離HTTP transportの範囲を固定する。"""
        parsed = urlsplit(origin)
        assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
        assert parsed.port is not None and 0 < parsed.port < 65536
        self._origin = origin
        super().__init__(secure_protocols=("http", "https"))

    def _owned(self, request: Request) -> bool:
        parsed = urlsplit(request.get_full_url())
        return (
            f"{parsed.scheme}://{parsed.netloc}" == self._origin
            and parsed.hostname == "127.0.0.1"
            and parsed.username is None
            and parsed.password is None
        )

    def set_ok(self, cookie: Cookie, request: Request) -> bool:
        """他host/port/originのCookieを受け入れない。"""
        return (
            self._owned(request)
            and cookie.name == "__Host-pitchlog_token"
            and cookie.secure
            and cookie.path == "/"
            and not cookie.domain_specified
            and super().set_ok(cookie, request)
        )

    def return_ok(self, cookie: Cookie, request: Request) -> bool:
        """SecureのHTTP例外を所有origin以外へ広げない。"""
        return self._owned(request) and super().return_ok(cookie, request)


class _OwnedLoopbackClient(httpx.Client):
    """HTTPXのコピーで所有origin限定CookiePolicyを既定policyへ戻さない。"""

    def _merge_cookies(self, cookies: Any = None) -> CookieJar:
        """要求単位のCookie注入を禁止し、実login応答の同じjarだけを使う。"""
        assert cookies is None, "試験要求へのCookie注入は禁止"
        # RequestはCookies wrapperを再コピーするが、CookieJarは同じpolicyを保持する。
        return self.cookies.jar


@dataclass(frozen=True)
class _SeedCatalog:
    """既存認証seed helperへ実所有admin接続だけを渡すadapter。"""

    applicator: psycopg.Connection[Any]


class PreparingCreateDatabase:
    """手製game保存を持たず、実APIの起動と所有資源だけを管理する。"""

    def __init__(self, authority: AuthorityDatabase) -> None:
        """既存authorityと別名のcontroller/APIを管理する。"""
        self.authority = authority
        self.controller = FreshControllerDatabase(authority)
        self.api_container: str | None = None
        self.origin: str | None = None
        self.identity: _Identity | None = None
        self.teams = (uuid4(), uuid4())

    def prepare(self) -> None:
        """正規S3と認証/チームだけを用意し、games事前投入0を照合する。"""
        database = self.authority.database
        with psycopg.connect(database.business_admin, autocommit=True) as admin:
            assert admin.execute("SELECT session_user,current_user").fetchone() == (
                "ledger_fixture_admin",
                "ledger_fixture_admin",
            )
            assert admin.execute(
                "SELECT version_num FROM public.alembic_version"
            ).fetchall() == [("0034_stage_a_rule_defaults",)]
        with psycopg.connect(database.business_admin) as admin:
            catalog = cast(ProvisionedProductCatalog, _SeedCatalog(admin))
            _seed_settings(catalog)
            self.identity = _seed_identity(
                catalog,
                make_conninfo(
                    host="/business-socket",
                    dbname="ledger_fixture",
                    user="pitchlog_app",
                ),
            )
            for index, team in enumerate(self.teams):
                admin.execute(
                    "INSERT INTO public.team_records(tenant_id,id,kind,name) "
                    "VALUES (%s,%s,%s,%s)",
                    (
                        self.identity.tenant_id,
                        team,
                        "self" if index == 0 else "opponent",
                        f"実作成チーム{index}",
                    ),
                )
            assert admin.execute("SELECT count(*) FROM public.games").fetchone() == (0,)
            assert admin.execute(
                "SELECT count(*) FROM public.rule_sets"
            ).fetchone() == (5,)
        self.controller.prepare()
        self._check_candidate_profile()
        self.controller.start()

    def _check_candidate_profile(self) -> None:
        """追加後の厳密検査は赤のまま保持し、固定候補以外の差を拒否する。"""
        with psycopg.connect(self.authority.database.business_admin) as admin:
            row = admin.execute(
                "SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user"
            ).fetchone()
            assert row is not None
            report = inspect_product_authz_catalog(
                admin, privileged_role_oids=frozenset({row[0]})
            )
            assert not report.ok, "候補の追加権限を正式S3成功へ読み替えない"
            changes = {}
            for violation in report.violations:
                assert isinstance(violation.expected, tuple)
                assert isinstance(violation.actual, tuple)
                expected = set(violation.expected)
                actual = set(violation.actual)
                assert not expected - actual, "旧製品profileの欠落/変更を拒否"
                changes[violation.check_id] = actual - expected
            predicate = ("singleton_id", "=", "1")
            assert changes == {
                "PRODUCT-CATALOG:DATABASE-ACL": {
                    ("pitchlog_ledger_identity_probe", "CONNECT", False),
                    ("pitchlog_rg1_control_actor", "CONNECT", False),
                },
                "PRODUCT-CATALOG:SCHEMA-ACL": {
                    ("public", "pitchlog_rg1_control_owner", "USAGE", False)
                },
                "PRODUCT-CATALOG:COLUMN-ACL": {
                    (
                        "public",
                        "rg1_restore_gate",
                        column,
                        "pitchlog_rg1_control_owner",
                        privilege,
                        False,
                    )
                    for column, privilege in (
                        ("singleton_id", "SELECT"),
                        ("state", "SELECT"),
                        ("state", "UPDATE"),
                    )
                },
                "PRODUCT-CATALOG:POLICIES": {
                    (
                        "public",
                        "rg1_restore_gate",
                        "rg1_control_select_singleton",
                        "select",
                        ("pitchlog_rg1_control_owner",),
                        "permissive",
                        predicate,
                        None,
                    ),
                    (
                        "public",
                        "rg1_restore_gate",
                        "rg1_control_update_singleton",
                        "update",
                        ("pitchlog_rg1_control_owner",),
                        "permissive",
                        predicate,
                        predicate,
                    ),
                },
            }, "固定候補外の厳密catalog差分を拒否"
            self.candidate_catalog_deltas = changes
            print("CANDIDATE_PROFILE_UNACCEPTED", sorted(changes), flush=True)
            roles = admin.execute(
                "SELECT rolname,rolsuper,rolbypassrls,rolcanlogin,rolcreaterole,"
                "rolcreatedb,rolreplication,rolinherit FROM pg_catalog.pg_roles "
                "WHERE rolname IN ('pitchlog_app','pitchlog_ledger_identity_owner',"
                "'pitchlog_ledger_identity_probe','pitchlog_rg1_control_owner',"
                "'pitchlog_rg1_control_actor') ORDER BY rolname"
            ).fetchall()
            assert roles == [
                ("pitchlog_app", False, False, True, False, False, False, False),
                # 既存identity sourceのNOLOGIN ownerは既定INHERIT。membershipは0。
                (
                    "pitchlog_ledger_identity_owner",
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                ),
                (
                    "pitchlog_ledger_identity_probe",
                    False,
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                ),
                (
                    "pitchlog_rg1_control_actor",
                    False,
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                ),
                (
                    "pitchlog_rg1_control_owner",
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                ),
            ]
            assert admin.execute(
                "SELECT count(*) FROM pg_catalog.pg_auth_members m "
                "JOIN pg_catalog.pg_roles r ON r.oid=m.roleid OR r.oid=m.member "
                "WHERE r.rolname IN ('pitchlog_app','pitchlog_ledger_identity_owner',"
                "'pitchlog_ledger_identity_probe','pitchlog_rg1_control_owner',"
                "'pitchlog_rg1_control_actor')"
            ).fetchone() == (0,)
            assert admin.execute(
                "SELECT n.nspname,pg_catalog.pg_get_userbyid(n.nspowner) "
                "FROM pg_catalog.pg_namespace n WHERE n.nspname IN "
                "('rg1_control','pitchlog_ledger_observer') ORDER BY n.nspname"
            ).fetchall() == [
                ("pitchlog_ledger_observer", "pitchlog_ledger_identity_owner"),
                ("rg1_control", "pitchlog_rg1_control_owner"),
            ]
            function_grants = admin.execute(
                "SELECT p.proname,r.rolname,x.privilege_type,x.is_grantable "
                "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n "
                "ON n.oid=p.pronamespace CROSS JOIN LATERAL "
                "pg_catalog.aclexplode(p.proacl) x LEFT JOIN pg_catalog.pg_roles r "
                "ON r.oid=x.grantee WHERE n.nspname='rg1_control' "
                "AND x.grantee<>p.proowner ORDER BY 1,2"
            ).fetchall()
            actor_functions = (
                "close_gate",
                "controller_lease_alive",
                "open_fresh_gate",
                "read_closed_gate",
                "release_controller_lease",
                "try_controller_lease",
            )
            assert function_grants == sorted(
                [
                    *(
                        (name, "pitchlog_rg1_control_actor", "EXECUTE", False)
                        for name in actor_functions
                    ),
                    (
                        "controller_lease_alive",
                        "pitchlog_rg1_fn_owner",
                        "EXECUTE",
                        False,
                    ),
                    ("scope_binding", "pitchlog_app", "EXECUTE", False),
                ]
            )
            assert admin.execute(
                "SELECT count(*) FROM pg_catalog.pg_proc p "
                "JOIN pg_catalog.pg_namespace n "
                "ON n.oid=p.pronamespace WHERE n.nspname='rg1_control' AND "
                "(pg_catalog.pg_get_userbyid(p.proowner)<>'pitchlog_rg1_control_owner' "
                "OR NOT p.prosecdef OR p.proconfig IS DISTINCT FROM "
                "ARRAY['search_path=pg_catalog, pg_temp'])"
            ).fetchone() == (0,)
            assert admin.execute(
                "SELECT count(*) FROM pg_catalog.pg_proc p "
                "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='rg1_control'"
            ).fetchone() == (7,)
            assert admin.execute(
                "SELECT p.proname,pg_catalog.pg_get_userbyid(p.proowner),p.prosecdef,"
                "p.proconfig FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n "
                "ON n.oid=p.pronamespace WHERE n.nspname='pitchlog_ledger_observer'"
            ).fetchall() == [
                (
                    "identity",
                    "pitchlog_ledger_identity_owner",
                    True,
                    ["search_path=pg_catalog, pg_temp"],
                )
            ]
            assert admin.execute(
                "SELECT r.rolname,x.privilege_type,x.is_grantable "
                "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n "
                "ON n.oid=p.pronamespace CROSS JOIN LATERAL "
                "pg_catalog.aclexplode(p.proacl) x LEFT JOIN pg_catalog.pg_roles r "
                "ON r.oid=x.grantee WHERE n.nspname='pitchlog_ledger_observer' "
                "AND x.grantee<>p.proowner"
            ).fetchall() == [("pitchlog_ledger_identity_probe", "EXECUTE", False)]
            assert admin.execute(
                "SELECT r.rolname,c.relname,a.attname,permission.name "
                "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_attribute a "
                "JOIN pg_catalog.pg_class c ON c.oid=a.attrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                "CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) "
                "permission(name) WHERE n.nspname='public' AND c.relkind='r' "
                "AND a.attnum>0 AND NOT a.attisdropped AND r.rolname IN "
                "('pitchlog_rg1_control_owner','pitchlog_rg1_control_actor',"
                "'pitchlog_ledger_identity_owner','pitchlog_ledger_identity_probe') "
                "AND pg_catalog.has_column_privilege("
                "r.oid,c.oid,a.attnum,permission.name) "
                "ORDER BY 1,2,3,4"
            ).fetchall() == [
                (
                    "pitchlog_rg1_control_owner",
                    "rg1_restore_gate",
                    "singleton_id",
                    "SELECT",
                ),
                ("pitchlog_rg1_control_owner", "rg1_restore_gate", "state", "SELECT"),
                ("pitchlog_rg1_control_owner", "rg1_restore_gate", "state", "UPDATE"),
            ]
            assert admin.execute(
                "SELECT r.rolname,pg_catalog.has_database_privilege("
                "r.oid,current_database(),"
                "'CONNECT'),pg_catalog.has_database_privilege(r.oid,current_database(),"
                "'CREATE'),pg_catalog.has_database_privilege(r.oid,current_database(),"
                "'TEMPORARY') FROM pg_catalog.pg_roles r WHERE r.rolname IN "
                "('pitchlog_ledger_identity_probe','pitchlog_rg1_control_actor',"
                "'pitchlog_fixture_business_writer') ORDER BY r.rolname"
            ).fetchall() == [
                ("pitchlog_fixture_business_writer", False, False, False),
                ("pitchlog_ledger_identity_probe", True, False, False),
                ("pitchlog_rg1_control_actor", True, False, False),
            ]

    def start_api(self, *, frontend_origin: str | None = None) -> None:
        """root配置した実client設定と実appをUID20003のuvicornで公開する。"""
        allowed_origin = (
            None
            if frontend_origin is None
            else _validated_frontend_origin(frontend_origin)
        )
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.origin = f"http://127.0.0.1:{port}"
        allowed_origin = self.origin if allowed_origin is None else allowed_origin
        arguments = self.authority.command(root=True)
        assert arguments[1] == "--rm"
        arguments[1] = "--detach"
        self.api_container = arguments[arguments.index("--name") + 1]
        assert self.api_container not in {
            self.authority.service,
            self.controller.container,
        }
        arguments[arguments.index("PYTHONPATH=/code:/deps")] = (
            "PYTHONPATH=/product/backend/src:/deps"
        )
        arguments[1:1] = [
            "--publish",
            f"127.0.0.1:{port}:8000",
            "--mount",
            f"type=bind,src={_ROOT},dst=/product,readonly",
        ]
        code = f"""
import base64,os,sys,threading,traceback
from pathlib import Path
try:
    target=Path('/run/pitchlog')
    target.mkdir(mode=0o755)
    source=Path('/control/rg1/client.json').read_bytes()
    config=target/'rg1-client.json'
    config.write_bytes(source)
    config.chmod(0o644)
    assert config.stat().st_uid==0 and config.read_bytes()==source
    os.environ['PITCHLOG_DATABASE_URL']=(
        'postgresql+psycopg://pitchlog_app@/ledger_fixture'
        '?host=/business-socket&sslmode=disable&gssencmode=disable')
    os.environ['PITCHLOG_DATABASE_POOLED']='false'
    os.environ['PITCHLOG_TOKEN_SIGNING_KEY_B64']=base64.b64encode(b'r'*32).decode('ascii')
    os.environ['PITCHLOG_ALLOWED_ORIGINS']={allowed_origin!r}
    os.setgroups([])
    os.setgid(20003)
    os.setuid(20003)
    assert os.geteuid()==20003 and os.getegid()==20003 and not os.getgroups()
    observed_sources={{
        'repositories/transaction.py','repositories/base.py',
        'repositories/function_operations.py','repositories/rg1.py',
        'recording_rights/rg1_lifecycle.py','services/game_creation.py',
        'repositories/rule_resolution.py','db/game_state/rule_snapshot.py',
        'api/routers/games.py',
    }}
    def observe_exception(frame,event,arg):
        # 値/戻り/例外を変更せず、例外型と固定source位置だけを観測する。
        relative=frame.f_code.co_filename.removeprefix('/product/backend/src/pitchlog/')
        if (event=='exception' and relative in observed_sources
            and issubclass(arg[0],Exception)):
            original=getattr(arg[1],'orig',None)
            state=getattr(original,'sqlstate',None)
            if not isinstance(state,str) or len(state)!=5: state='-'
            print('API_EXCEPTION',relative,frame.f_code.co_name,
                  frame.f_lineno,arg[0].__name__,state,flush=True)
        if (event=='return' and relative=='repositories/base.py'
            and frame.f_code.co_name=='_materialize_execution_result'):
            rows=getattr(arg,'rows',None)
            if (isinstance(rows,tuple) and len(rows)==1 and len(rows[0])==1
                and type(rows[0][0]) is int):
                print('API_INTEGER_RESULT',rows[0][0],flush=True)
        return observe_exception
    sys.settrace(observe_exception)
    threading.settrace(observe_exception)
    from pitchlog.api.app import create_app
    import uvicorn
    uvicorn.run(create_app(),host='0.0.0.0',port=8000,access_log=False,log_config=None)
except BaseException as error:
    print(type(error).__name__,flush=True)
    for frame in traceback.extract_tb(error.__traceback__):
        print(frame.name,frame.lineno,flush=True)
    raise SystemExit(1)
"""
        docker(*arguments, "-u", "-c", code)
        assert docker("port", self.api_container, "8000/tcp") == f"127.0.0.1:{port}"
        deadline = monotonic() + 15
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=1) as client:
            while monotonic() < deadline:
                assert self.api_running(), "実API起動拒否: " + self.diagnostic()
                try:
                    response = client.get(self.origin + "/health")
                    if response.status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                sleep(0.1)
        raise AssertionError("実API起動期限超過: " + self.diagnostic())

    def api_running(self) -> bool:
        """所有API containerの生存だけを観測する。"""
        assert self.api_container is not None
        return (
            docker("inspect", "--format", "{{.State.Running}}", self.api_container)
            == "true"
        )

    def diagnostic(self) -> str:
        """起動wrapperの資格なし型/関数/行だけを読む。"""
        assert self.api_container is not None
        return docker("logs", "--tail", "30", self.api_container, check=False)

    def http_client(self) -> httpx.Client:
        """Cookieを注入せず、実login応答だけを保持するHTTP clientを作る。"""
        assert self.origin is not None
        policy = _OwnedLoopbackCookiePolicy(self.origin)
        # 設定したHTTP例外が他host・port・schemeへ拡張されないことを先に確認。
        assert policy._owned(Request(self.origin + "/games"))
        assert not policy._owned(Request(self.origin.replace("127.0.0.1", "localhost")))
        assert not policy._owned(Request("http://127.0.0.1:1/games"))
        assert not policy._owned(Request("https://127.0.0.1/games"))

        def require_owned_origin(request: httpx.Request) -> None:
            """redirectや絶対URL指定で所有origin外へ送信しない。"""
            assert policy._owned(Request(str(request.url)))

        return _OwnedLoopbackClient(
            base_url=self.origin,
            cookies=CookieJar(policy=policy),
            trust_env=False,
            follow_redirects=False,
            timeout=15,
            event_hooks={"request": [require_owned_origin]},
        )

    def close(self) -> None:
        """API→controller→外側authority fixtureの順に所有資源を閉じる。"""
        if self.api_container is not None:
            docker("rm", "--force", self.api_container, check=False)
        self.controller.close()


CreateFaultPhase = Literal["before_insert", "after_insert", "deferred_commit"]


@dataclass(frozen=True)
class PreparingCreateFault:
    """取消されない所有sequenceで、実SQL故障への到達を観測する。"""

    authority: AuthorityDatabase
    phase: CreateFaultPhase

    def counters(self) -> tuple[int, int, int]:
        """trigger到達/新語彙可視/game可視の実回数を返す。"""
        with psycopg.connect(self.authority.database.business_admin) as observer:
            values = []
            for name in ("reached", "vocabulary_visible", "game_visible"):
                row = observer.execute(
                    sql.SQL(
                        "SELECT CASE WHEN is_called THEN last_value ELSE 0 END "
                        "FROM pitchlog_create_atomicity.{}"
                    ).format(sql.Identifier(name))
                ).fetchone()
                assert row is not None
                values.append(row[0])
        return values[0], values[1], values[2]


@contextmanager
def inject_preparing_create_failure(
    database: PreparingCreateDatabase, phase: CreateFaultPhase
) -> Iterator[PreparingCreateFault]:
    """所有businessだけへ実triggerを置き、製品sourceや判定を差し替えない。"""
    if phase not in {"before_insert", "after_insert", "deferred_commit"}:
        raise ValueError("未知の試合作成故障位置")
    dsn = database.authority.database.business_admin
    # 故障専用schemaはcanonical profileとは別の検証環境であり、正式認可に数えない。
    with psycopg.connect(dsn) as admin:
        admin.execute("CREATE SCHEMA pitchlog_create_atomicity")
        admin.execute("REVOKE ALL ON SCHEMA pitchlog_create_atomicity FROM PUBLIC")
        for name in ("reached", "vocabulary_visible", "game_visible"):
            admin.execute(
                sql.SQL("CREATE SEQUENCE pitchlog_create_atomicity.{}").format(
                    sql.Identifier(name)
                )
            )
        admin.execute("""
CREATE FUNCTION pitchlog_create_atomicity.fail_game() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pitchlog_create_atomicity, pg_temp AS $fault$
BEGIN
    PERFORM pg_catalog.nextval('pitchlog_create_atomicity.reached');
    IF EXISTS (
        SELECT 1 FROM public.tenant_vocabularies
        WHERE tenant_id = NEW.tenant_id AND key = NEW.tournament_key
          AND category = 'tournament' AND disabled = false
    ) THEN
        PERFORM pg_catalog.nextval('pitchlog_create_atomicity.vocabulary_visible');
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.games
        WHERE tenant_id = NEW.tenant_id AND id = NEW.id
    ) THEN
        PERFORM pg_catalog.nextval('pitchlog_create_atomicity.game_visible');
    END IF;
    RAISE EXCEPTION 'PITCHLOG_PRIVATE_ATOMICITY_FAULT'
        USING ERRCODE = 'P0001';
END
$fault$;
REVOKE ALL ON FUNCTION pitchlog_create_atomicity.fail_game() FROM PUBLIC;
""")
        if phase == "deferred_commit":
            admin.execute("""
CREATE CONSTRAINT TRIGGER preparing_create_atomicity_fault
AFTER INSERT ON public.games DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION pitchlog_create_atomicity.fail_game()
""")
        else:
            admin.execute(
                sql.SQL(
                    "CREATE TRIGGER preparing_create_atomicity_fault {} "
                    "INSERT ON public.games FOR EACH ROW EXECUTE FUNCTION "
                    "pitchlog_create_atomicity.fail_game()"
                ).format(sql.SQL("BEFORE" if phase == "before_insert" else "AFTER"))
            )
    try:
        yield PreparingCreateFault(database.authority, phase)
    finally:
        with psycopg.connect(dsn) as admin:
            admin.execute(
                "DROP TRIGGER preparing_create_atomicity_fault ON public.games"
            )
            admin.execute("DROP SCHEMA pitchlog_create_atomicity CASCADE")
