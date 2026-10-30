"""所有3PGで開始と初期権の同一business確定を検査する。HTTP証拠ではない。"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from pitchlog.db.game_state.rule_snapshot import (
    decode_applied_rules,
    encode_applied_rules,
)

from . import test_initial_recording_right_scope as _grant_scope_tests
from .initial_recording_right_scope_support import InitialGrantDatabase

pytestmark = pytest.mark.requires_db

admin_connection = _grant_scope_tests.admin_connection
tested_role_connection = _grant_scope_tests.tested_role_connection
initial_scope_database = _grant_scope_tests.initial_scope_database


@pytest.fixture(scope="session")
def product_node_binary(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """製品Dockerfileが固定する同じNode imageのbinaryだけをreadonly供給する。"""
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    image = re.search(
        r"^FROM (node:[^ ]+) AS node_runtime$", dockerfile.read_text(), re.M
    )
    assert image is not None, "製品Node imageの固定宣言がない"
    name = "pitchlog-start-node-" + uuid4().hex
    target = tmp_path_factory.mktemp("product-node") / "node"

    def docker(*args: str) -> None:
        result = subprocess.run(["docker", *args], capture_output=True, timeout=120)
        assert result.returncode == 0, "所有Node fixture操作が非成功"

    try:
        docker(
            "create",
            "--name",
            name,
            "--label",
            "pitchlog.owner=start-atomic-test",
            image[1],
        )
        docker("cp", name + ":/usr/local/bin/node", str(target))
        target.chmod(0o755)
        yield target
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name], capture_output=True, timeout=45
        )


def _canonical_saved_rule(
    admin: psycopg.Connection, rule_id: UUID
) -> dict[str, object]:
    """実規則行を単一codecでcanonical保存形へ変換するfixture。"""
    row = admin.execute(
        "SELECT jsonb_build_object('ruleSetId',id,'regulationInnings',"
        "regulation_innings,"
        "'coldConditions',called_game_conditions,'extensionLimit',extra_innings_limit,"
        "'tiebreak',tiebreak_rule,'dh',uses_dh) FROM public.rule_sets WHERE id=%s",
        (rule_id,),
    ).fetchone()
    assert row is not None
    return encode_applied_rules(decode_applied_rules(row[0]))


@pytest.fixture
def start_database(
    initial_scope_database: InitialGrantDatabase,
    product_node_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> InitialGrantDatabase:
    """既安全owned3PG helperへ20公式選手と実Nodeを有限供給する。"""
    db = initial_scope_database
    original = db.authority.command

    def command(**kwargs: Any) -> list[str]:
        args = original(**kwargs)
        args[1:1] = [
            "--mount",
            f"type=bind,src={product_node_binary},dst=/usr/local/bin/node,readonly",
        ]
        return args

    monkeypatch.setattr(db.authority, "command", command)
    with psycopg.connect(db.authority.database.business_admin) as admin:
        teams = admin.execute(
            "SELECT away_team_record_id,home_team_record_id FROM public.games "
            "WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        assert teams is not None
        # 通常UI createで到達可能なgame_other規則の実保存値に合わせる。
        prior = db.game_id
        db.game_id = uuid4()
        selected = admin.execute(
            "SELECT rule_set_id FROM public.game_type_rule_defaults "
            "WHERE game_type_key='game_other'"
        ).fetchone()
        assert selected is not None
        saved_rule = _canonical_saved_rule(admin, selected[0])
        admin.execute(
            "INSERT INTO public.games(tenant_id,id,scheduled_at,game_type_key,"
            "tournament_key,"
            "away_team_record_id,home_team_record_id,applied_rules) "
            "SELECT g.tenant_id,%s,g.scheduled_at,'game_other',g.tournament_key,"
            "g.away_team_record_id,g.home_team_record_id,%s FROM public.games g "
            "WHERE g.tenant_id=%s AND g.id=%s",
            (db.game_id, Jsonb(saved_rule), db.tenant_id, prior),
        )
        for team, offset in zip(teams, (100, 200), strict=True):
            for i in range(1, 11):
                admin.execute(
                    "INSERT INTO public.players(tenant_id,id,team_record_id,"
                    "name,uniform_number,roster_status_key) "
                    "VALUES (%s,%s,%s,'開始試験公式選手',%s,'active')",
                    (db.tenant_id, UUID(int=offset + i), team, str(i)),
                )
    return db


def _start_script(size: int = 10, extra: str = "") -> str:
    """既helperの降格済actorから実製品入口を呼ぶ。公開合成要求のみ。"""
    return f"""
from test_initial_game_start_components import _body
from pitchlog.api.schemas.game_start import GameStartRequest
from pitchlog.repositories.game_start import bind_initial_start_request
from pitchlog.recording_rights.initial_grant_broker import _start_initial_game
body=_body({size})
body['device_id']=str(owner.device_id);body['start_request_id']=str(owner.start_request_id)
body['device_credential']='credential-a'
bound=bind_initial_start_request(GameStartRequest.model_validate(body),tenant_id=owner.tenant_id,
                                game_id=owner.game_id,attempt_id=owner.attempt_id)
def start(selected=bound):
    with source.recovery_fence() as fence:
        value=_start_initial_game(context,runtime,selected,'credential-a',source,fence)
    return {{**receipt(value.grant),'started_at':value.receipt.started_at.isoformat(),
             'away_lineup_id':str(value.receipt.away_lineup_id),
             'home_lineup_id':str(value.receipt.home_lineup_id)}}
{extra}
"""


def _saved(db: InitialGrantDatabase) -> dict[str, Any]:
    """原本と権利/attempt/UM2を独立adminから有限観測する。"""
    with psycopg.connect(db.authority.database.business_admin) as admin:
        game = admin.execute(
            "SELECT status,started_at FROM public.games WHERE tenant_id=%s AND id=%s",
            (db.tenant_id, db.game_id),
        ).fetchone()
        lineups = admin.execute(
            "SELECT id,team_record_id,entries_with_uniform_number_snapshot "
            "FROM public.game_lineups "
            "WHERE tenant_id=%s AND game_id=%s ORDER BY team_record_id",
            (db.tenant_id, db.game_id),
        ).fetchall()
        memories = admin.execute(
            "SELECT team_record_id,lineup FROM public.lineup_memories WHERE "
            "tenant_id=%s",
            (db.tenant_id,),
        ).fetchall()
    return dict(game=game, lineups=lineups, memories=memories, rights=db.storage())


@pytest.mark.parametrize("size", [9, 10])
def test_real_start_and_grant_commit_and_replay_immutable_originals(
    start_database: InitialGrantDatabase, size: int, tmp_path: Path
) -> None:
    """実配置/両原本/UM2/時刻/権利を確定し、再送は現役名簿を再計算しない。"""
    db = start_database
    if size == 9:
        # 既規則不変triggerを迂回しない。fixtureの別preparing gameを明示作成する。
        with psycopg.connect(db.authority.database.business_admin) as admin:
            prior = db.game_id
            db.game_id = uuid4()
            rule_id = uuid4()
            admin.execute(
                "INSERT INTO public.rule_sets(id,regulation_innings,"
                "called_game_conditions,"
                "extra_innings_limit,tiebreak_rule,uses_dh) VALUES (%s,9,"
                "'[]',9,NULL,false)",
                (rule_id,),
            )
            saved_rule = _canonical_saved_rule(admin, rule_id)
            admin.execute(
                "INSERT INTO public.games(tenant_id,id,scheduled_at,game_type_key,"
                "tournament_key,"
                "away_team_record_id,home_team_record_id,applied_rules) "
                "SELECT tenant_id,%s,scheduled_at,game_type_key,tournament_key,"
                "away_team_record_id,home_team_record_id,%s FROM public.games "
                "WHERE tenant_id=%s AND id=%s",
                (db.game_id, Jsonb(saved_rule), db.tenant_id, prior),
            )
    before = _saved(db)
    first = db.actor(_start_script(size, "print(json.dumps(start()))"))
    saved = _saved(db)
    assert saved["game"][0] == "in_progress" and saved["game"][1] is not None
    assert len(saved["lineups"]) == 2 and all(
        len(row[2]) == size for row in saved["lineups"]
    )
    assert len(saved["memories"]) == 1 and len(saved["memories"][0][1]) == size
    assert (
        len(saved["rights"]["recording_generations"])
        == len(saved["rights"]["recording_right_deliveries"])
        == 1
    )
    assert saved["rights"]["game_start_attempts"][0]["outcome"] == "committed"
    ledger = db.ledger_snapshot()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "UPDATE public.players SET uniform_number='changed',"
            "roster_status_key='ob' WHERE tenant_id=%s",
            (db.tenant_id,),
        )
    replay = db.actor(
        _start_script(
            size,
            """bound=replace(bound,owner=replace(bound.owner,attempt_id=uuid4()))
print(json.dumps(start(bound)))""",
        )
    )
    assert replay == first and db.ledger_snapshot() == ledger and _saved(db) == saved

    def public_state(value: dict[str, Any]) -> dict[str, Any]:
        return dict(
            game=value["game"],
            lineups=value["lineups"],
            memories=value["memories"],
            rights_counts={k: len(v) for k, v in value["rights"].items()},
            outcomes=[r["outcome"] for r in value["rights"]["game_start_attempts"]],
        )

    (tmp_path / "start-observations.json").write_text(
        json.dumps(
            dict(
                status="UNACCEPTED_OWNED_FIXTURE_EVIDENCE_NOT_HTTP_UI",
                size=size,
                first=first,
                replay=replay,
                before=public_state(before),
                after=public_state(saved),
                external_d4_consumed=ledger[0][6],
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n"
    )


@contextmanager
def _start_fault(db: InitialGrantDatabase, stage: str) -> Iterator[None]:
    """Owned fixtureだけへ故障triggerを追加し、必ず除去する。"""
    if stage == "proof":
        yield
        return
    if stage in {"generation", "delivery", "commit"}:
        with db.fault(stage):
            yield
        return
    table = {"lineup": "game_lineups", "memory": "lineup_memories", "status": "games"}[
        stage
    ]
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            "CREATE FUNCTION public.initial_start_fixture_fault() RETURNS "
            "trigger LANGUAGE plpgsql AS "
            "$$ BEGIN RAISE EXCEPTION 'owned fixture failure'; END; $$"
        )
        condition = sql.SQL("")
        if stage == "lineup":
            home = admin.execute(
                "SELECT home_team_record_id FROM public.games WHERE "
                "tenant_id=%s AND id=%s",
                (db.tenant_id, db.game_id),
            ).fetchone()
            assert home is not None
            condition = sql.SQL("WHEN (NEW.team_record_id={})").format(
                sql.Literal(home[0])
            )
        admin.execute(
            sql.SQL(
                "CREATE TRIGGER initial_start_fixture_fault BEFORE INSERT OR "
                "UPDATE ON public.{} "
                "FOR EACH ROW {} EXECUTE FUNCTION public.initial_start_fixture_fault()"
            ).format(sql.Identifier(table), condition)
        )
    try:
        yield
    finally:
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(
                sql.SQL("DROP TRIGGER initial_start_fixture_fault ON public.{}").format(
                    sql.Identifier(table)
                )
            )
            admin.execute("DROP FUNCTION public.initial_start_fixture_fault()")


@pytest.mark.parametrize(
    "stage", ["lineup", "memory", "status", "proof", "generation", "delivery", "commit"]
)
def test_real_start_fault_cancels_all_business_but_consumes_external_d4(
    start_database: InitialGrantDatabase, stage: str
) -> None:
    """全取消と外部claim消費を別々に観測し、不明を成功/新採番にしない。"""
    db = start_database
    with _start_fault(db, stage):
        proof_fault = f"expect_proof_fault={stage == 'proof'!r}\n"
        if stage == "proof":
            proof_fault += (
                "\ndef proof_failure(*args): "
                "raise RuntimeError('owned proof failure')\n"
                "V12Box.issue=proof_failure\n"
            )
        result = db.actor(
            _start_script(
                extra=proof_fault
                + """
from sqlalchemy.exc import DBAPIError
try: start()
except DBAPIError as error:
    print(json.dumps({'rejected':True,'type':type(error).__name__}))
except RuntimeError as error:
    if not expect_proof_fault or type(error) is not RuntimeError: raise
    print(json.dumps({'rejected':True,'type':type(error).__name__}))
else: raise AssertionError('fault acknowledged as success')"""
            )
        )
        assert result["rejected"] is True
    saved = _saved(db)
    assert saved["game"] == ("preparing", None)
    assert saved["lineups"] == saved["memories"] == []
    assert (
        saved["rights"]["recording_generations"]
        == saved["rights"]["recording_right_deliveries"]
        == []
    )
    assert saved["rights"]["game_start_attempts"][0]["outcome"] == "pending"
    ledger = db.ledger_snapshot()
    assert len(ledger) == 1 and ledger[0][4:] == (1, 1, True, False)
    retry = db.actor(
        _start_script(
            extra="""
from pitchlog.durable_rights_ledger import LedgerUnavailable,LedgerOutcomeUnconfirmed
from pitchlog.repositories.rg1 import RG1Unavailable
bound=replace(bound,owner=replace(bound.owner,attempt_id=uuid4()))
try: start(bound)
except (LedgerUnavailable,LedgerOutcomeUnconfirmed,
        InitialGrantUnavailable,RG1Unavailable):
    print(json.dumps({'rejected':True}))
else: raise AssertionError('claimed unresolved start automatically reissued')
"""
        )
    )
    assert (
        retry == {"rejected": True}
        and db.ledger_snapshot() == ledger
        and _saved(db) == saved
    )


@pytest.mark.parametrize(
    "reason", ["missing", "wrong_team", "inactive", "duplicate_order"]
)
def test_real_start_rejects_unavailable_or_invalid_selected_roster(
    start_database: InitialGrantDatabase, reason: str
) -> None:
    """選択外rosterで補完せず、実read/単一TSの拒否後もbusinessを残さない。"""
    db = start_database
    if reason == "inactive":
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(
                "UPDATE public.players SET roster_status_key='ob' WHERE "
                "tenant_id=%s AND id=%s",
                (db.tenant_id, UUID(int=101)),
            )
    mutate = {
        "missing": "body['away'][0]['player_id']=str(UUID(int=999))",
        "wrong_team": "body['away'][0]['player_id']=body['home'][0]['player_id']",
        "inactive": "pass",
        "duplicate_order": "body['away'][1]['batting_order']=1",
    }[reason]
    script = _start_script(
        extra=f"""
{mutate}
bound=bind_initial_start_request(GameStartRequest.model_validate(body),tenant_id=owner.tenant_id,
                                game_id=owner.game_id,attempt_id=owner.attempt_id)
from sqlalchemy.exc import DBAPIError
try: start(bound)
except (DBAPIError,InitialGrantConflict): print(json.dumps({{'rejected':True}}))
else: raise AssertionError('invalid roster acknowledged')"""
    )
    assert db.actor(script) == {"rejected": True}
    saved = _saved(db)
    assert (
        saved["game"] == ("preparing", None)
        and saved["lineups"] == saved["memories"] == []
    )
    assert (
        saved["rights"]["recording_generations"]
        == saved["rights"]["recording_right_deliveries"]
        == []
    )
    assert len(db.ledger_snapshot()) == 1 and db.ledger_snapshot()[0][4:] == (
        1,
        1,
        True,
        False,
    )


def test_real_start_does_not_promote_grant_only_committed(
    start_database: InitialGrantDatabase,
) -> None:
    """同じ全payload digestでも開始原本なしの旧成功はstart再交付にしない。"""
    db = start_database
    result = db.actor(
        _start_script(
            extra="""
from sqlalchemy.exc import DBAPIError
old=issue(bound.owner)
try: start()
except (DBAPIError,InitialGrantConflict): print(json.dumps({'rejected':True}))
else: raise AssertionError('grant-only committed promoted to started')"""
        )
    )
    assert result == {"rejected": True}
    saved = _saved(db)
    assert (
        saved["game"] == ("preparing", None)
        and saved["lineups"] == saved["memories"] == []
    )
    assert (
        len(saved["rights"]["recording_generations"]) == 1
        and len(db.ledger_snapshot()) == 1
    )


def test_real_start_replay_changed_payload_does_not_reserve_again(
    start_database: InitialGrantDatabase,
) -> None:
    """同requestの1field変更を新attempt/別開始へ自動変換しない。"""
    db = start_database
    db.actor(_start_script(extra="print(json.dumps(start()))"))
    before = _saved(db)
    ledger = db.ledger_snapshot()
    result = db.actor(
        _start_script(
            extra="""
from sqlalchemy.exc import DBAPIError
body['away'][0]['player_id']=str(UUID(int=999))
bound=bind_initial_start_request(GameStartRequest.model_validate(body),tenant_id=owner.tenant_id,
                                game_id=owner.game_id,attempt_id=uuid4())
try: start(bound)
except (DBAPIError,InitialGrantConflict): print(json.dumps({'rejected':True}))
else: raise AssertionError('changed payload replay accepted')"""
        )
    )
    assert (
        result == {"rejected": True}
        and _saved(db) == before
        and db.ledger_snapshot() == ledger
    )


def test_real_start_owner_rls_and_actor_app_direct_access_denied(
    start_database: InitialGrantDatabase,
) -> None:
    """実owner越境SELECT/INSERT/UPDATEとactor/appの直接DMLを拒否する。"""
    db = start_database
    with psycopg.connect(
        db.authority.database.business_admin, autocommit=True
    ) as admin:
        for role in ("pitchlog_initial_actor",):
            for statement in (
                sql.SQL(
                    "UPDATE public.games SET status='in_progress' WHERE id={}"
                ).format(sql.Literal(db.game_id)),
                sql.SQL(
                    "INSERT INTO public.game_lineups(tenant_id,id,game_id,"
                    "team_record_id,entries_with_uniform_number_snapshot) "
                    "VALUES ({},{},{},{},'[]')"
                ).format(
                    sql.Literal(db.tenant_id),
                    sql.Literal(uuid4()),
                    sql.Literal(db.game_id),
                    sql.Literal(uuid4()),
                ),
            ):
                with admin.transaction():
                    admin.execute(
                        sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role))
                    )
                    admin.execute(
                        "SELECT set_config('app.tenant_id',%s,true)",
                        (str(db.tenant_id),),
                    )
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        admin.execute(statement)
        for name in ("read_initial_start_context", "persist_initial_start"):
            assert admin.execute(
                "SELECT has_function_privilege('pitchlog_app',%s,'EXECUTE')",
                (f"initial_right_api.{name}(uuid,uuid,uuid,uuid,bytea,text)",),
            ).fetchone() == (False,)
        with admin.transaction():
            admin.execute("SET LOCAL ROLE pitchlog_initial_fn_owner")
            admin.execute(
                "SELECT set_config('app.tenant_id',%s,true)", (str(db.tenant_id),)
            )
            assert admin.execute(
                "SELECT count(id) FROM public.games WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, db.game_id),
            ).fetchone() == (1,)
            admin.execute(
                "SELECT set_config('app.tenant_id',%s,true)", (str(db.other_tenant_id),)
            )
            assert admin.execute(
                "SELECT count(id) FROM public.games WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, db.game_id),
            ).fetchone() == (0,)
            assert (
                admin.execute(
                    "UPDATE public.games SET status='in_progress' WHERE "
                    "tenant_id=%s AND id=%s",
                    (db.tenant_id, db.game_id),
                ).rowcount
                == 0
            )
        with admin.transaction():
            admin.execute("SET LOCAL ROLE pitchlog_initial_fn_owner")
            admin.execute(
                "SELECT set_config('app.tenant_id',%s,true)", (str(db.other_tenant_id),)
            )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                admin.execute(
                    "INSERT INTO public.game_lineups(tenant_id,id,game_id,"
                    "team_record_id,entries_with_uniform_number_snapshot) "
                    "VALUES (%s,%s,%s,%s,'[]')",
                    (db.tenant_id, uuid4(), db.game_id, uuid4()),
                )


def test_real_worker_cookie_enroll_start_and_noncreating_resolve(
    start_database: InitialGrantDatabase,
    tmp_path,
) -> None:
    """実Unix/UID/Node/PGで3commandを接ぐ。HTTP/UI成功は主張しない。"""
    from concurrent.futures import ThreadPoolExecutor
    from time import monotonic, sleep

    from .durable_rights_ledger_support import docker

    db = start_database
    token, subject = uuid4(), uuid4()
    with psycopg.connect(db.authority.database.business_admin) as admin:
        admin.execute(
            (
                "INSERT INTO public.system_settings(key,value) VALUES ('"
                "auth.token_ttl_seconds','3600') ON CONFLICT(key) DO UPD"
                "ATE SET value=EXCLUDED.value"
            )
        )
        admin.execute(
            "INSERT INTO public.tenant_auth_subjects(tenant_id,id) VALUES (%s,%s)",
            (db.tenant_id, subject),
        )
        admin.execute(
            (
                "INSERT INTO public.tenant_credentials(auth_subject_id,p"
                "assword_hash,generation) VALUES (%s,'public-unused-logi"
                "n-vector',1)"
            ),
            (subject,),
        )
        admin.execute(
            (
                "INSERT INTO public.tenant_tokens(tenant_id,id,auth_subj"
                "ect_id,credential_generation,expires_at,last_used_at) V"
                "ALUES (%s,%s,%s,1,clock_timestamp()+interval '1 hour',c"
                "lock_timestamp())"
            ),
            (db.tenant_id, token, subject),
        )
    before = db.ledger_snapshot()
    assert before == ()
    with db.broker_worker(token) as worker:
        # cold poolの3並列は全て実enroll。資格はclient内だけで保持し出力しない。
        def enroll_one(_):
            return db.broker_client("""
from time import monotonic
started=monotonic()
reply=client.call(_EnrollDeviceCommand(identity))
assert reply.status=='enrolled' and reply.value is not None
assert len(reply.value.device_credential.get_secret_value())==43
assert reply.value.device_credential.get_secret_value()!='**********'
print(json.dumps({'enrolled':True,'seconds':monotonic()-started}))
""")

        with ThreadPoolExecutor(max_workers=3) as executor:
            parallel = list(executor.map(enroll_one, range(3)))
        assert all(r["enrolled"] for r in parallel)
        normal = db.broker_client(f"""
from test_initial_game_start_components import _body
from pitchlog.api.schemas.game_start import GameStartRequest
from pitchlog.repositories.game_start import InitialStartPayload,_entries
from dataclasses import replace
from time import monotonic
reply=client.call(_EnrollDeviceCommand(identity))
assert reply.status=='enrolled' and reply.value is not None
pair=reply.value
assert pair.device_credential.get_secret_value()!='**********'
body=_body(10)
body['device_id']=str(pair.device_id);body['start_request_id']=str(UUID('{db.start_request_id}'))
body['device_credential']=pair.device_credential.get_secret_value()
request=GameStartRequest.model_validate(body)
command=_StartInitialGameCommand(identity,UUID('{db.game_id}'),request.start_request_id,
    request.device_id,request.device_credential,InitialStartPayload(_entries(request.away),_entries(request.home)))
# 0行lookupはintent/attempt/予約を作らずunresolved。
missing=client.call(_ResolveStartCommand(command))
assert missing.status=='unresolved' and missing.value is None
started=monotonic()
first=client.call(command)
elapsed=monotonic()-started
assert first.status=='started' and first.value is not None
assert first.value.recording_right_proof.get_secret_value()!='**********'
again=client.call(_ResolveStartCommand(command))
assert again.status=='started' and again.value is not None
assert again.value==first.value
altered=replace(command,payload=InitialStartPayload(
    tuple(reversed(command.payload.away)),command.payload.home))
assert client.call(_ResolveStartCommand(altered)).status=='unresolved'
changed=replace(command,start_request_id=uuid4())
assert client.call(_ResolveStartCommand(changed)).status=='unresolved'
print(json.dumps({{'started':True,'committed_resolve':True,'same_V12_receipt':True,
    'raw_enrollment_credential_used_for_DB_start':True,'missing_unresolved':True,
    'device_id':str(pair.device_id),'seconds':elapsed}}))
""")
        assert normal["started"] and normal["committed_resolve"]
        saved = _saved(db)
        assert saved["game"][0] == "in_progress" and len(saved["lineups"]) == 2
        assert all(len(r[2]) == 10 for r in saved["lineups"])
        assert len(db.ledger_snapshot()) == 1
        fixed_ledger = db.ledger_snapshot()
        fixed_storage = db.storage()
        # app UID以外は同じwireを送っても拒否。0件許容やpeer申告を使わない。
        wrong_peer = db.broker_client(
            """
try:client.call(_EnrollDeviceCommand(identity))
except InitialBrokerUnavailable:pass
else:raise AssertionError('actor peer accepted as app')
print(json.dumps({'rejected':True}))
""",
            uid=20002,
        )
        assert wrong_peer == dict(rejected=True)
        invalid = db.broker_client(
            """
wrong=_BrokerIdentity(identity.expected_tenant_id,uuid4(),SecretStr('invalid-cookie'))
assert client.call(_EnrollDeviceCommand(wrong)).status=='denied'
other=_BrokerIdentity(UUID('"""
            + str(db.other_tenant_id)
            + """'),uuid4(),identity.cookie)
assert client.call(_EnrollDeviceCommand(other)).status=='denied'
print(json.dumps({'denied':True}))
"""
        )
        assert invalid == dict(denied=True)
        # 既fixture資格でpendingを設置する負例。normalは実enrollを使った。
        from test_initial_game_start_components import _body

        from pitchlog.api.schemas.game_start import GameStartRequest
        from pitchlog.repositories.game_start import bind_initial_start_request

        pending_request, pending_attempt = uuid4(), uuid4()
        pending_body = _body(10)
        pending_body.update(
            device_id=str(db.device_id),
            start_request_id=str(pending_request),
            device_credential="credential-a",
        )
        bound = bind_initial_start_request(
            GameStartRequest.model_validate(pending_body),
            tenant_id=db.tenant_id,
            game_id=db.game_id,
            attempt_id=pending_attempt,
        )
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(
                (
                    "INSERT INTO public.game_start_requests(tenant_id,game_i"
                    "d,start_request_id,device_id,request_digest) VALUES (%s"
                    ",%s,%s,%s,%s)"
                ),
                (
                    db.tenant_id,
                    db.game_id,
                    pending_request,
                    db.device_id,
                    bound.owner.request_digest,
                ),
            )
            admin.execute(
                (
                    "INSERT INTO public.game_start_attempts(tenant_id,attemp"
                    "t_id,game_id,start_request_id,device_id) VALUES (%s,%s,"
                    "%s,%s,%s)"
                ),
                (
                    db.tenant_id,
                    pending_attempt,
                    db.game_id,
                    pending_request,
                    db.device_id,
                ),
            )
        pending_script = f"""
from test_initial_game_start_components import _body
from pitchlog.api.schemas.game_start import GameStartRequest
from pitchlog.repositories.game_start import InitialStartPayload,_entries
body=_body(10);body.update(device_id='{db.device_id}',start_request_id='{pending_request}',device_credential='credential-a')
request=GameStartRequest.model_validate(body)
command=_StartInitialGameCommand(identity,UUID('{db.game_id}'),request.start_request_id,
    request.device_id,request.device_credential,InitialStartPayload(_entries(request.away),_entries(request.home)))
reply=client.call(_ResolveStartCommand(command))
assert reply.status=='unresolved' and reply.value is None
print(json.dumps({{'unresolved':True}}))
"""
        pending = db.broker_client(pending_script)
        assert pending == dict(unresolved=True)
        # 旧transactionのrequest lockを実際に保持。worker timeoutは終結証明ではない。
        with psycopg.connect(db.authority.database.business_admin) as blocker:
            blocker.execute(
                (
                    "SELECT start_request_id FROM public.game_start_requests"
                    " WHERE tenant_id=%s AND game_id=%s AND start_request_id"
                    "=%s FOR UPDATE"
                ),
                (db.tenant_id, db.game_id, pending_request),
            )
            locked = db.broker_client(pending_script)
            assert locked == dict(unresolved=True)
            blocker.rollback()
        with psycopg.connect(db.authority.database.business_admin) as admin:
            assert admin.execute(
                (
                    "SELECT attempt_id,outcome FROM public.game_start_attemp"
                    "ts WHERE tenant_id=%s AND start_request_id=%s"
                ),
                (db.tenant_id, pending_request),
            ).fetchall() == [(pending_attempt, "pending")]
            fn = (
                "initial_right_api.lookup_existing_start_attempt"
                "(uuid,uuid,uuid,uuid,bytea)"
            )
            assert admin.execute(
                "SELECT has_function_privilege(%s,%s,'EXECUTE')", ("pitchlog_app", fn)
            ).fetchone() == (False,)
            assert admin.execute(
                "SELECT has_function_privilege(%s,%s,'EXECUTE')",
                ("pitchlog_initial_auth_verifier", fn),
            ).fetchone() == (False,)
        assert db.ledger_snapshot() == fixed_ledger
        # 確定済み保存原本はpending seedと別に不変。
        assert (
            db.storage()["recording_generations"]
            == fixed_storage["recording_generations"]
        )
        assert (
            db.storage()["recording_right_deliveries"]
            == fixed_storage["recording_right_deliveries"]
        )
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(
                "UPDATE public.trusted_devices SET revoked_at=clock_timestamp() "
                "WHERE tenant_id=%s AND device_id=%s",
                (db.tenant_id, db.device_id),
            )
        revoked = db.broker_client(pending_script)
        assert revoked == dict(unresolved=True)
        # 受信直後にclientを閉じる別要求。実commitを親が観測するまで照会を待つ。
        lost_game, lost_request = uuid4(), uuid4()
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(
                "INSERT INTO public.games(tenant_id,id,scheduled_at,game_type_key,"
                "tournament_key,"
                "away_team_record_id,home_team_record_id,applied_rules) "
                "SELECT tenant_id,%s,scheduled_at,game_type_key,tournament_key,"
                "away_team_record_id,home_team_record_id,applied_rules "
                "FROM public.games "
                "WHERE tenant_id=%s AND id=%s",
                (lost_game, db.tenant_id, db.game_id),
            )
        lost_script = f"""
import socket,time
from test_initial_game_start_components import _body
from pitchlog.api.schemas.game_start import GameStartRequest
from pitchlog.repositories.game_start import InitialStartPayload,_entries
from pitchlog.recording_rights.initial_grant_broker import (
    _encode_initial_command,_check_broker_socket,_check_broker_peer)
pair=client.call(_EnrollDeviceCommand(identity)).value;assert pair is not None
body=_body(10);body.update(device_id=str(pair.device_id),start_request_id='{lost_request}',
    device_credential=pair.device_credential.get_secret_value())
request=GameStartRequest.model_validate(body)
command=_StartInitialGameCommand(identity,UUID('{lost_game}'),request.start_request_id,
    request.device_id,request.device_credential,InitialStartPayload(_entries(request.away),_entries(request.home)))
endpoint=client._endpoint
_check_broker_socket(endpoint)
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as channel:
    channel.settimeout(1.5);channel.connect(str(endpoint.path))
    _check_broker_peer(channel);_check_broker_socket(endpoint)
    channel.sendall(_encode_initial_command(command));channel.shutdown(socket.SHUT_WR)
# commit有無をこの切断だけから推定しない。以下のmarkerは試験同期専用。
deadline=time.monotonic()+10
while not Path('/run/pitchlog/reply-commit-observed').exists():
    assert time.monotonic()<deadline
    time.sleep(0.05)
reply=client.call(_ResolveStartCommand(command))
assert reply.status=='started' and reply.value is not None
again=client.call(_ResolveStartCommand(command))
assert again.value==reply.value
assert reply.value.recording_right_proof.get_secret_value()!='**********'
print(json.dumps({{'lost_reply_then_committed_resolve':True,'same_V12_receipt':True}}))
"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            lost_future = executor.submit(db.broker_client, lost_script)
            deadline = monotonic() + 10
            with psycopg.connect(
                db.authority.database.business_admin, autocommit=True
            ) as admin:
                while monotonic() < deadline:
                    row = admin.execute(
                        "SELECT count(*) FROM public.recording_right_deliveries "
                        "WHERE tenant_id=%s AND game_id=%s AND start_request_id=%s",
                        (db.tenant_id, lost_game, lost_request),
                    ).fetchone()
                    if row == (1,):
                        break
                    sleep(0.05)
                else:
                    raise AssertionError("返信喪失要求の実commitへ未到達")
                assert admin.execute(
                    "SELECT status FROM public.games WHERE tenant_id=%s AND id=%s",
                    (db.tenant_id, lost_game),
                ).fetchone() == ("in_progress",)
            docker(
                "exec",
                "--user",
                "0",
                worker,
                "/runtime/bin/python3.12",
                "-c",
                "from pathlib import Path; "
                "Path('/run/pitchlog/reply-commit-observed').open('x')"
                ".write('public test synchronization')",
            )
            lost_reply = lost_future.result(timeout=15)
        assert lost_reply == dict(
            lost_reply_then_committed_resolve=True, same_V12_receipt=True
        )
        assert len(db.ledger_snapshot()) == 2

        # 実queue飽和はDB開始前に閉じ、資格/新deviceを成功補完しない。
        with psycopg.connect(db.authority.database.business_admin) as admin:
            device_count = admin.execute(
                "SELECT count(*) FROM public.trusted_devices"
            ).fetchone()
            pool_counts = admin.execute(
                "SELECT usename,count(*) FROM pg_stat_activity WHERE usename IN "
                "('pitchlog_initial_actor','pitchlog_initial_auth_verifier') "
                "GROUP BY usename"
            ).fetchall()
            assert all(0 < count <= 3 for _role, count in pool_counts)
        saturated = db.broker_client("""
import socket,time
from pitchlog.recording_rights.initial_grant_broker import _load_broker_endpoint
endpoint=_load_broker_endpoint()
channels=[]
try:
    deadline=time.monotonic()+0.5
    for _ in range(6):
        channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        channel.settimeout(1.5)
        try:
            while True:
                try:
                    channel.connect(str(endpoint.path))
                    break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise
                    time.sleep(0.005)
        except BaseException:
            channel.close()
            raise
        channels.append(channel)
    assert len(channels)==6
    time.sleep(0.1)
    try:client.call(_EnrollDeviceCommand(identity))
    except InitialBrokerUnavailable:pass
    else:raise AssertionError('saturated queue produced enrollment')
finally:
    for channel in channels:channel.close()
print(json.dumps({'non_success':True}))
""")
        assert saturated == dict(non_success=True)
        with psycopg.connect(db.authority.database.business_admin) as admin:
            assert (
                admin.execute("SELECT count(*) FROM public.trusted_devices").fetchone()
                == device_count
            )

        # 既製品Nodeの実子processだけをSIGSTOP。host/caller/業務式を差し替えない。
        fault_game, fault_request = uuid4(), uuid4()
        with psycopg.connect(db.authority.database.business_admin) as admin:
            admin.execute(
                "INSERT INTO public.games(tenant_id,id,scheduled_at,game_type_key,"
                "tournament_key,away_team_record_id,home_team_record_id,applied_rules) "
                "SELECT tenant_id,%s,scheduled_at,game_type_key,tournament_key,"
                "away_team_record_id,home_team_record_id,applied_rules "
                "FROM public.games "
                "WHERE tenant_id=%s AND id=%s",
                (fault_game, db.tenant_id, db.game_id),
            )
        stop_node_code = """
import os,signal,time,json,sys,traceback
from pathlib import Path
def error_hook(kind,value,tb):
    print(json.dumps({'monitor_failure_type':kind.__name__,
        'frames':[(f.name,f.lineno) for f in traceback.extract_tb(tb)]}),flush=True)
sys.excepthook=error_hook
deadline=time.monotonic()+15
while time.monotonic()<deadline:
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():continue
        try:
            raw=(path/'cmdline').read_bytes().split(b'\\0')
            status=(path/'status').read_text()
            if raw[0] not in (b'node',b'/usr/local/bin/node'):continue
            actual=(path/'exe').stat();expected=Path('/usr/local/bin/node').stat()
            if (actual.st_dev,actual.st_ino)!=(expected.st_dev,expected.st_ino):continue
            values={line.split(':',1)[0]:line.split(':',1)[1].strip()
                for line in status.splitlines() if ':' in line}
            if values['PPid']!='1' or values['Uid'].split()[0]!='20002':continue
            os.kill(int(path.name),signal.SIGSTOP)
            print(json.dumps({'owned_Node_stopped':True,'pid':int(path.name),
                'ppid':1,'uid':20002,'executable_inode_match':True,
                'stopped_monotonic':time.monotonic()}));raise SystemExit(0)
        except (FileNotFoundError,ProcessLookupError):continue
    time.sleep(0.001)
raise AssertionError('owned Node process not reached')
"""

        def run_node_monitor() -> dict[str, Any]:
            """同UIDの実観測を安全fieldだけへ閉じ、失敗も証拠へ返す。"""
            try:
                process = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "--user",
                        "20002:20002",
                        worker,
                        "/runtime/bin/python3.12",
                        "-c",
                        stop_node_code,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except (subprocess.TimeoutExpired, OSError) as error:
                return {"returncode": None, "failure_type": type(error).__name__}
            try:
                observed = json.loads(process.stdout)
                assert type(observed) is dict
                assert set(observed) in (
                    {
                        "owned_Node_stopped",
                        "pid",
                        "ppid",
                        "uid",
                        "executable_inode_match",
                        "stopped_monotonic",
                    },
                    {"monitor_failure_type", "frames"},
                )
            except (ValueError, AssertionError):
                observed = {"monitor_failure_type": "InvalidDiagnostic", "frames": []}
            return {
                "returncode": process.returncode,
                "observation": observed,
                "stderr_present": bool(process.stderr),
            }

        with ThreadPoolExecutor(max_workers=1) as executor:
            stop_future = executor.submit(run_node_monitor)
            node_failed = db.broker_client(f"""
from test_initial_game_start_components import _body
from pitchlog.api.schemas.game_start import GameStartRequest
from pitchlog.repositories.game_start import InitialStartPayload,_entries
reply=client.call(_EnrollDeviceCommand(identity));assert reply.status=='enrolled'
pair=reply.value;assert pair is not None
body=_body(10);body.update(device_id=str(pair.device_id),start_request_id='{fault_request}',
    device_credential=pair.device_credential.get_secret_value())
request=GameStartRequest.model_validate(body)
command=_StartInitialGameCommand(identity,UUID('{fault_game}'),request.start_request_id,
    request.device_id,request.device_credential,InitialStartPayload(_entries(request.away),_entries(request.home)))
try:
    reply=client.call(command)
    observed={{'status':reply.status,'value_is_none':reply.value is None}}
except InitialBrokerUnavailable:
    observed={{'status':'transport-unavailable','value_is_none':True}}
print(json.dumps(observed))
""")
            node_monitor = stop_future.result(timeout=25)
            node_stop = node_monitor.get("observation", {})
        # 診断は閉enum/boolean/所有PIDと有限DB状態だけ。資格/例外値は記録しない。
        with psycopg.connect(db.authority.database.business_admin) as observer:
            fault_status = observer.execute(
                "SELECT status FROM public.games WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, fault_game),
            ).fetchone()
            fault_attempts = observer.execute(
                "SELECT outcome FROM public.game_start_attempts "
                "WHERE tenant_id=%s AND start_request_id=%s",
                (db.tenant_id, fault_request),
            ).fetchall()
        (tmp_path / "worker-node-diagnostic.json").write_text(
            json.dumps(
                {
                    "reply": node_failed,
                    "actual_Node_monitor": node_monitor,
                    "game_status": fault_status,
                    "attempt_outcomes": fault_attempts,
                    "ledger_claimed": [row[6] for row in db.ledger_snapshot()],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        assert node_monitor["returncode"] == 0
        assert node_stop["owned_Node_stopped"] is True
        assert node_stop["ppid"] == 1 and node_stop["uid"] == 20002
        assert node_stop["executable_inode_match"] is True
        assert type(node_stop["pid"]) is int and node_stop["pid"] > 1
        assert node_failed in (
            {"status": "unresolved", "value_is_none": True},
            {"status": "transport-unavailable", "value_is_none": True},
        )
        from time import monotonic, sleep

        deadline = monotonic() + 10
        with psycopg.connect(
            db.authority.database.business_admin, autocommit=True
        ) as admin:
            while monotonic() < deadline:
                try:
                    with admin.transaction():
                        row = admin.execute(
                            "SELECT device_id FROM public.game_start_requests "
                            "WHERE tenant_id=%s "
                            "AND game_id=%s AND start_request_id=%s FOR UPDATE NOWAIT",
                            (db.tenant_id, fault_game, fault_request),
                        ).fetchone()
                    assert row is not None
                    break
                except psycopg.errors.LockNotAvailable:
                    sleep(0.05)
            else:
                raise AssertionError("Node failure business TX did not finish")
            assert admin.execute(
                "SELECT status FROM public.games WHERE tenant_id=%s AND id=%s",
                (db.tenant_id, fault_game),
            ).fetchone() == ("preparing",)
            assert admin.execute(
                "SELECT count(*) FROM public.game_lineups "
                "WHERE tenant_id=%s AND game_id=%s",
                (db.tenant_id, fault_game),
            ).fetchone() == (0,)
            assert admin.execute(
                (
                    "SELECT outcome FROM public.game_start_attempts WHERE te"
                    "nant_id=%s AND start_request_id=%s"
                ),
                (db.tenant_id, fault_request),
            ).fetchall() == [("pending",)]
        assert len(db.ledger_snapshot()) == 3
        assert db.ledger_snapshot()[-1][6] is True

        # 最後は所有business PG停止で実checkout/接続不能を起こす。共有PGへ触れない。
        docker("stop", "--time", "1", db.authority.database.business)
        disconnected = db.broker_client("""
try:client.call(_EnrollDeviceCommand(identity))
except InitialBrokerUnavailable:pass
else:raise AssertionError('unavailable database returned credential')
print(json.dumps({'non_success':True}))
""")
        assert disconnected == dict(non_success=True)
        # rootが所有するworkerだけを停止し、同clientは成功へ補完しない。
        docker("stop", "--time", "1", worker)
        stopped = db.broker_client("""
try:client.call(_EnrollDeviceCommand(identity))
except InitialBrokerUnavailable:pass
else:raise AssertionError('stopped worker returned success')
print(json.dumps({'unavailable':True}))
""")
        assert stopped == dict(unavailable=True)
    (tmp_path / "worker-observations.json").write_text(
        json.dumps(
            dict(
                parallel_enroll3=parallel,
                normal=normal,
                wrong_peer=wrong_peer,
                invalid_cookie=invalid,
                pending_nonterminal=pending,
                lost_reply=lost_reply,
                revoked_device=revoked,
                old_TX_lock_timeout=locked,
                stopped_worker=stopped,
                committed_resolve_additional_D4=0,
                pending_lookup_additional_attempts=0,
                queue_saturated=saturated,
                pool_counts=pool_counts,
                actual_Node_stopped=node_failed,
                actual_business_PG_stopped=disconnected,
                HTTP_UI=False,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
