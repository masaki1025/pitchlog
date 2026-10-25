"""実台帳・RG1・私有actorを接ぐ隔離fixture。enrollment/開始APIではない。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Literal
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from psycopg.conninfo import make_conninfo
from sqlalchemy import URL, create_engine

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import (
    apply_product_authz_before_rule_placement,
    apply_product_authz_ddl,
)
from pitchlog.repositories.initial_recording_right import _credential_digest

from . import durable_rights_ledger_support as ledger_support
from .durable_rights_ledger_support import (
    _PUBLIC_FIXTURE_PASSWORD,
    AuthorityDatabase,
    docker,
)
from .rg1_lifecycle_support import observed_identity

_BACKEND = Path(__file__).resolve().parents[2]
_INITIAL_REVISION = "0036_initial_recording_right_storage"
_ACTOR_UID = 20002
_CONTROLLER_UID = 20004
# 既initial候補の公開vector。運用資格/鍵を新発行しない。
_PUBLIC_CREDENTIAL = "credential-a"


def _install_initial_business(dsn: str) -> None:
    """owned初期化だけを正規migration/段階配置へ接ぐ。手書きACLを足さない。"""
    from psycopg.conninfo import conninfo_to_dict

    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL(
                "CREATE ROLE pitchlog_owner LOGIN NOSUPERUSER NOBYPASSRLS "
                "NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}"
            ).format(sql.Literal(_PUBLIC_FIXTURE_PASSWORD))
        )
        admin.execute("ALTER DATABASE ledger_fixture OWNER TO pitchlog_owner")
    owner_dsn = make_conninfo(
        dsn, user="pitchlog_owner", password=_PUBLIC_FIXTURE_PASSWORD
    )
    parameters = conninfo_to_dict(owner_dsn)

    def required(key: str) -> str:
        """所有DSNの有限fieldだけを型確認し、未設定を外部既定値へ逃がさない。"""
        value = parameters.get(key)
        assert type(value) is str and value, "所有fixture DSNのfieldが不正"
        return value

    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username=required("user"),
            password=required("password"),
            host=required("host"),
            port=int(required("port")),
            database=required("dbname"),
        ),
        hide_parameters=True,
    )
    try:
        with engine.begin() as connection:
            configuration = Config(str(_BACKEND / "alembic.ini"))
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "0033_game_rules_immutable")
        # 正規before-ruleが新表/列依存を保留できなければ、その拒否を維持する。
        with psycopg.connect(dsn) as admin:
            apply_product_authz_before_rule_placement(admin)
        with engine.begin() as connection:
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, _INITIAL_REVISION)
    finally:
        engine.dispose()
    with psycopg.connect(dsn) as admin:
        apply_product_authz_ddl(admin)
    # 初期scope用installer。RG1の0035までのS3完了証明を偽造しない。
    # rootの9SQL/fullprofile供給が不十分なら実適用/検査を失敗させる。
    with psycopg.connect(dsn) as admin:
        assert admin.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall() == [(_INITIAL_REVISION,)], "正規0036段階配置が未供給"
        role = admin.execute("SELECT oid FROM pg_roles WHERE rolname=session_user")
        row = role.fetchone()
        assert row is not None
        report = inspect_product_authz_catalog(
            admin, privileged_role_oids=frozenset({row[0]})
        )
        assert report.ok, "初期権を含む製品fullprofileが未供給/不一致"


@contextmanager
def isolated_initial_grant_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InitialGrantDatabase]:
    """実3PG/authority/controllerを所有し、失敗時も各所有者が掃除する。"""
    for name in (
        "PITCHLOG_TEST_ADMIN_DSN",
        "PITCHLOG_TEST_ROLE_DSN",
        "PITCHLOG_DATABASE_URL",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGHOSTADDR",
    ):
        monkeypatch.delenv(name, raising=False)
    # 製品auth/RG1/Sessionは差し替えず、旧fixtureの初期化順だけを変更する。
    with monkeypatch.context() as patch:
        patch.setattr(
            ledger_support, "_install_product_business", _install_initial_business
        )
        with ledger_support.isolated_authority_database() as authority:
            database = InitialGrantDatabase(authority)
            try:
                database.prepare()
                yield database
            finally:
                database.close()


class InitialGrantDatabase:
    """製品issuerの実actor subprocessと、所有DBの独立観測を管理する。"""

    def __init__(self, authority: AuthorityDatabase) -> None:
        """固定ownerをfixture seedとして用意する。認証済みHTTPとは主張しない。"""
        self.authority = authority
        self.controller: str | None = None
        self.tenant_id, self.other_tenant_id = uuid4(), uuid4()
        self.game_id, self.device_id, self.other_device_id = uuid4(), uuid4(), uuid4()
        self.start_request_id, self.attempt_id = uuid4(), uuid4()
        self.request_digest = hashlib.sha256(b"public-initial-scope-payload").digest()

    def prepare(self) -> None:
        """正式fullprofileの後でfixture行/peer設定/root非秘密配置を追加する。"""
        database = self.authority.database
        with psycopg.connect(database.business_admin) as admin:
            assert admin.execute(
                "SELECT state,recovery_generation FROM public.rg1_restore_gate"
            ).fetchall() == [("closed", None)]
            for tenant in (self.tenant_id, self.other_tenant_id):
                admin.execute(
                    "INSERT INTO public.tenants(id,name) VALUES (%s,%s)",
                    (tenant, "initial-scope-" + tenant.hex),
                )
            teams = (uuid4(), uuid4())
            for index, team in enumerate(teams):
                admin.execute(
                    "INSERT INTO public.team_records(tenant_id,id,kind,name) "
                    "VALUES (%s,%s,%s,%s)",
                    (
                        self.tenant_id,
                        team,
                        "self" if index == 0 else "opponent",
                        "初期権scope試験チーム",
                    ),
                )
            admin.execute(
                "INSERT INTO public.tenant_vocabularies"
                "(tenant_id,key,category,display_name) "
                "VALUES (%s,'initial_scope_tournament','tournament',"
                "'初期権scope試験大会')",
                (self.tenant_id,),
            )
            # 低水準scope試験の準備行。製品の作成/開始成功証拠には数えない。
            admin.execute(
                "INSERT INTO public.games(tenant_id,id,scheduled_at,game_type_key,"
                "tournament_key,away_team_record_id,home_team_record_id,applied_rules) "
                "SELECT %s,%s,CURRENT_TIMESTAMP,'game_official',"
                "'initial_scope_tournament',%s,%s,pg_catalog.jsonb_build_object("
                "'ruleSetId',r.id,'regulationInnings',r.regulation_innings,"
                "'cold',r.called_game_conditions,'overtime',r.extra_innings_limit,"
                "'tiebreak',r.tiebreak_rule,'dh',r.uses_dh) "
                "FROM public.rule_sets r JOIN public.game_type_rule_defaults d "
                "ON d.rule_set_id=r.id WHERE d.game_type_key='game_official'",
                (self.tenant_id, self.game_id, *teams),
            )
            assert admin.execute(
                "SELECT count(*) FROM public.games WHERE id=%s", (self.game_id,)
            ).fetchone() == (1,)
            # enrollment fixture投入。原資格をSQLに渡さず単一digestを再利用する。
            for device in (self.device_id, self.other_device_id):
                admin.execute(
                    "INSERT INTO public.trusted_devices"
                    "(tenant_id,device_id,credential_digest) VALUES (%s,%s,%s)",
                    (self.tenant_id, device, _credential_digest(_PUBLIC_CREDENTIAL)),
                )
            identity = observed_identity(admin, admin.info.backend_pid)
        self._prepare_peer()
        server_uid = int(
            docker("exec", database.business, "stat", "-c", "%u", "/proc/1")
        )
        client = dict(
            schema_version=1,
            socket_path="/control/initial/rg1.sock",
            controller_uid=_CONTROLLER_UID,
            application_uid=_ACTOR_UID,
        )
        controller = {
            **client,
            "application_uid": 20003,
            "business_socket_directory": "/business-socket",
            "business_port": 5432,
            "business_database": "ledger_fixture",
            "business_server_uid": server_uid,
            "ledger_endpoint": "/control/public/endpoint.json",
        }
        actor = {
            "database_url": "postgresql+psycopg://pitchlog_initial_actor@/"
            "ledger_fixture?host=%2Fbusiness-socket&sslmode=disable",
            **{
                key: identity[key]
                for key in (
                    "system_identifier",
                    "database_oid",
                    "database_name",
                    "postmaster_started_at",
                )
            },
        }
        code = (
            "import json,os; from pathlib import Path; "
            "p=Path('/control/initial'); p.mkdir(mode=0o755); "
            f"values={{'client.json':{client!r},'controller.json':{controller!r},"
            f"'actor.json':{actor!r}}}; "
            "[(p/name).write_text(json.dumps(value)) "
            "for name,value in values.items()]; "
            "[os.chmod(p/name,0o600 if name=='actor.json' else 0o644) "
            "for name in values]"
        )
        docker(*self.authority.command(root=True), "-c", code)
        self._start_controller()

    def _prepare_peer(self) -> None:
        """所有PG内だけへ3個のexact OS/LOGIN role対応を追加する。"""
        docker(
            "exec",
            self.authority.database.business,
            "bash",
            "-eu",
            "-c",
            "groupadd -g 20004 initial_controller && "
            "useradd -u 20004 -g 20004 -M initial_controller && "
            "groupadd -g 20002 initial_actor && "
            "useradd -u 20002 -g 20002 -M initial_actor && "
            "groupadd -g 20003 initial_app && "
            "useradd -u 20003 -g 20003 -M initial_app && "
            "sed -i '1ilocal all pitchlog_rg1_control_actor,pitchlog_initial_actor,"
            "pitchlog_app peer map=initial_scope_test' "
            "/var/lib/postgresql/data/pg_hba.conf && "
            "printf '%s\\n' "
            "'initial_scope_test initial_controller pitchlog_rg1_control_actor' "
            "'initial_scope_test initial_actor pitchlog_initial_actor' "
            "'initial_scope_test initial_app pitchlog_app' "
            ">> /var/lib/postgresql/data/pg_ident.conf",
        )
        with psycopg.connect(
            self.authority.database.business_admin, autocommit=True
        ) as admin:
            assert admin.execute("SELECT pg_reload_conf()").fetchone() == (True,)
            assert admin.execute(
                "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL"
            ).fetchone() == (0,)

    def _start_controller(self) -> None:
        """boolではなく実fresh peerとSQLのopen状態が成立するまで待つ。"""
        arguments = self.authority.command(root=True)
        arguments[1] = "--detach"
        self.controller = arguments[arguments.index("--name") + 1]
        code = """
from pathlib import Path
from pitchlog.recording_rights.rg1_lifecycle import serve_fresh_controller
try:
    serve_fresh_controller(Path('/control/initial/controller.json'))
except BaseException as error:
    print(type(error).__name__, flush=True)
    raise SystemExit(1)
"""
        docker(*arguments, "-u", "-c", code)
        deadline = monotonic() + 15
        while monotonic() < deadline:
            assert (
                docker("inspect", "--format", "{{.State.Running}}", self.controller)
                == "true"
            ), "実controller/freshの供給が不一致"
            with psycopg.connect(self.authority.database.business_admin) as admin:
                if admin.execute(
                    "SELECT state,recovery_generation FROM public.rg1_restore_gate"
                ).fetchall() == [("open", 1)]:
                    return
            sleep(0.1)
        raise AssertionError("実controller/fresh ready期限超過")

    def actor(self, body: str) -> dict[str, Any]:
        """root実runtimeを作り降格後の実issuerを実行する。資格を出力しない。"""
        arguments = self.authority.command(root=True)
        arguments[1:1] = [
            "--mount",
            f"type=bind,src={_BACKEND / 'tests'},dst=/fixture/backend/tests,readonly",
        ]
        owner = {
            "tenant_id": str(self.tenant_id),
            "game_id": str(self.game_id),
            "device_id": str(self.device_id),
            "start_request_id": str(self.start_request_id),
            "attempt_id": str(self.attempt_id),
            "request_digest": self.request_digest.hex(),
        }
        bootstrap = f"""
import base64,ctypes,hashlib,json,os,sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID,uuid4
sys.path.insert(0,'/fixture/backend/tests')
from test_authz_tenant_context import make_tenant_context
from pitchlog.durable_rights_ledger import DurableLedger
from pitchlog.recording_rights.initial_grant import (
    V12Box,InitialGrantUnavailable,InitialGrantConflict)
from pitchlog.recording_rights.initial_grant_broker import (
    _load_initial_actor_runtime,_close_initial_actor_runtime,_issue_initial_grant)
from pitchlog.recording_rights.rg1_lifecycle import configure_runtime
from pitchlog.repositories.initial_recording_right import _StartOwner
box=V12Box('k1',bytes(range(32)))
runtime=_load_initial_actor_runtime(Path('/control/initial/actor.json'),box)
os.setgroups([]);os.setgid(20002);os.setuid(20002)
assert ctypes.CDLL(None).prctl(38,1,0,0,0)==0
configure_runtime(Path('/control/initial/client.json'))
source=DurableLedger(Path('/control/public/endpoint.json'))
raw={owner!r}
fields=('tenant_id','game_id','start_request_id','device_id','attempt_id')
owner=_StartOwner(*(UUID(raw[k]) for k in fields),bytes.fromhex(raw['request_digest']))
# 既allowlistのtest専用文脈であり、実Cookie/HTTP認証の成功とは主張しない。
context=make_tenant_context(owner.tenant_id)
def issue(selected=owner,credential='credential-a',selected_context=context):
    with source.recovery_fence() as fence:
        return _issue_initial_grant(
            selected_context,runtime,selected,credential,source,fence)
def receipt(grant):
    return {{'game_id':str(grant.game_id),'device_id':str(grant.holder_device_id),
             'generation':grant.generation,'epoch':grant.recovery_generation,
             'proof_digest':hashlib.sha256(base64.urlsafe_b64decode(
                 grant.recording_right_proof+'=')).hexdigest()}}
"""
        # 失敗例も型だけを返す。raw例外/SQL/設定/資格をdockerログへ渡さない。
        script = (
            bootstrap
            + "\ntry:\n"
            + "\n".join("    " + line for line in body.splitlines())
            + "\nfinally:\n    _close_initial_actor_runtime(runtime)\n"
        )
        output = docker(*arguments, "-u", "-c", script)
        value = json.loads(output)
        assert type(value) is dict
        return value

    def ledger_snapshot(self) -> tuple[tuple[object, ...], ...]:
        """実primaryの有限な所有予約だけを観測する。caller proofに使わない。"""
        snapshots = []
        for dsn in (
            self.authority.database.primary_admin,
            self.authority.database.standby_admin,
        ):
            with psycopg.connect(dsn) as observer:
                snapshots.append(
                    tuple(
                        observer.execute(
                            "SELECT attempt_id,tenant_id,game_id,start_request_id,"
                            "generation,"
                            "recovery_generation,claimed,quarantined "
                            "FROM pitchlog_ledger.reservations "
                            "ORDER BY generation"
                        ).fetchall()
                    )
                )
        assert snapshots[0] == snapshots[1], "実同期peerの予約観測が不一致"
        return snapshots[0]

    def acl_probe(self, role: Literal["app", "actor"]) -> dict[str, Any]:
        """実peer LOGINから表DML/関数EXECUTE拒否を観測する。ACL変更はしない。"""
        user, uid = (
            ("pitchlog_app", 20003)
            if role == "app"
            else ("pitchlog_initial_actor", _ACTOR_UID)
        )
        arguments = self.authority.command(uid=uid)
        arguments[1:1] = [
            "--volume",
            f"{self.authority.database.business_socket}:/business-socket:ro",
        ]
        code = f"""
import json,psycopg
from uuid import UUID
from pitchlog.repositories.function_operations import _INITIAL_FUNCTION_TYPES
user={user!r}
states=[]
with psycopg.connect(host='/business-socket',dbname='ledger_fixture',user=user,
                     passfile='/dev/null',autocommit=True) as c:
    identity=c.execute('SELECT session_user,current_user').fetchone()
    assert identity==(user,user)
    for table in ('trusted_devices','game_start_requests','game_start_attempts',
                  'recording_right_deliveries'):
        statements=(f'SELECT * FROM public.{{table}}',
                    f'UPDATE public.{{table}} SET tenant_id=tenant_id WHERE false',
                    f'DELETE FROM public.{{table}} WHERE false',
                    f'INSERT INTO public.{{table}}(tenant_id) '
                    'SELECT NULL::uuid WHERE false')
        for statement in statements:
            try: c.execute(statement)
            except psycopg.errors.InsufficientPrivilege as e: states.append(e.sqlstate)
            else: raise AssertionError('direct secret storage access acknowledged')
    try:
        c.execute('INSERT INTO public.recording_generations '
                  '(tenant_id,game_id,generation,kind,issuance_order) '
                  "VALUES (%s,%s,999,'normal',999)",
                  (UUID('{self.tenant_id}'),UUID('{self.game_id}')))
    except psycopg.errors.InsufficientPrivilege as e: states.append(e.sqlstate)
    else: raise AssertionError('arbitrary generation insert acknowledged')
    if user=='pitchlog_app':
        for name,(inputs,*_) in _INITIAL_FUNCTION_TYPES.items():
            params=(UUID('{self.tenant_id}'),*tuple(None for _ in inputs))
            statement='SELECT '+name+'('+','.join('%s' for _ in params)+')'
            try: c.execute(statement,params)
            except psycopg.errors.InsufficientPrivilege as e: states.append(e.sqlstate)
            else: raise AssertionError('app initial-only EXECUTE acknowledged')
    assert c.execute('SELECT count(*) FROM pg_catalog.pg_auth_members WHERE '
                     'member=(SELECT oid FROM pg_roles WHERE rolname=%s) OR '
                     'roleid=(SELECT oid FROM pg_roles WHERE rolname=%s)',
                     (user,user)).fetchone()==(0,)
    print(json.dumps({{'identity':list(identity),'states':states}}))
"""
        value = json.loads(docker(*arguments, "-c", code))
        assert type(value) is dict
        return value

    def storage(self) -> dict[str, list[dict[str, Any]]]:
        """業務側の全保存対象を別管理接続で観測する。秘密値は返さない。"""
        with psycopg.connect(self.authority.database.business_admin) as admin:
            result: dict[str, list[dict[str, Any]]] = {}
            for table in (
                "game_start_requests",
                "game_start_attempts",
                "recording_generations",
                "recording_right_deliveries",
            ):
                rows = admin.execute(
                    sql.SQL(
                        "SELECT to_jsonb(t) FROM public.{} t WHERE tenant_id=%s"
                    ).format(sql.Identifier(table)),
                    (self.tenant_id,),
                ).fetchall()
                result[table] = [row[0] for row in rows]
            return result

    @contextmanager
    def fault(
        self, stage: Literal["generation", "delivery", "commit"]
    ) -> Iterator[None]:
        """専用sequenceで実到達を証明する。製品profileの成功証明には使わない。"""
        target = (
            "recording_generations"
            if stage == "generation"
            else "recording_right_deliveries"
        )
        trigger = (
            "CREATE CONSTRAINT TRIGGER initial_fault AFTER INSERT ON public.{} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION initial_scope_fault.fail()"
            if stage == "commit"
            else "CREATE TRIGGER initial_fault AFTER INSERT ON public.{} "
            "FOR EACH ROW EXECUTE FUNCTION initial_scope_fault.fail()"
        )
        with psycopg.connect(self.authority.database.business_admin) as admin:
            admin.execute("CREATE SCHEMA initial_scope_fault")
            admin.execute("REVOKE ALL ON SCHEMA initial_scope_fault FROM PUBLIC")
            admin.execute("CREATE SEQUENCE initial_scope_fault.reached")
            admin.execute(
                "CREATE FUNCTION initial_scope_fault.fail() RETURNS trigger "
                "LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp "
                "AS $$ BEGIN PERFORM "
                "pg_catalog.nextval('initial_scope_fault.reached'); "
                "RAISE EXCEPTION 'PRIVATE_INITIAL_SCOPE_FAULT'; END $$"
            )
            admin.execute(
                "REVOKE ALL ON FUNCTION initial_scope_fault.fail() FROM PUBLIC"
            )
            admin.execute(sql.SQL(trigger).format(sql.Identifier(target)))
        try:
            yield
        finally:
            with psycopg.connect(self.authority.database.business_admin) as admin:
                reached = admin.execute(
                    "SELECT last_value,is_called FROM initial_scope_fault.reached"
                ).fetchone()
                admin.execute(
                    sql.SQL("DROP TRIGGER initial_fault ON public.{}").format(
                        sql.Identifier(target)
                    )
                )
                admin.execute("DROP SCHEMA initial_scope_fault CASCADE")
            assert reached == (1, True), "実INSERT/commit故障点へ未到達"

    def close(self) -> None:
        """authorityの掃除より先に、このfixtureのcontrollerだけを回収する。"""
        if self.controller is not None:
            docker("rm", "--force", self.controller, check=False)
