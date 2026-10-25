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
