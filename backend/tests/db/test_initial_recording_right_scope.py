"""単一issuer/実台帳/実actor scopeの接合。開始HTTP/UIの成功ではない。"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from db_fixtures import _dsn_names

from .initial_recording_right_scope_support import (
    InitialGrantDatabase,
    isolated_initial_grant_database,
)

pytestmark = pytest.mark.requires_db


@pytest.fixture
def initial_scope_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InitialGrantDatabase]:
    """owned3PGだけを供給し、既autouseの実identity検査を無効化しない。"""
    with isolated_initial_grant_database(monkeypatch) as database:
        admin_name, role_name = _dsn_names()
        monkeypatch.setenv(admin_name, database.authority.database.primary_admin)
        monkeypatch.setenv(role_name, database.authority.database.endpoints.primary_dsn)
        yield database


@pytest.fixture
def admin_connection(
    initial_scope_database: InitialGrantDatabase,
) -> Iterator[psycopg.Connection]:
    """既identity autouseへ所有primaryの実adminを渡す。"""
    with psycopg.connect(
        initial_scope_database.authority.database.primary_admin
    ) as connection:
        yield connection


@pytest.fixture
def tested_role_connection(
    initial_scope_database: InitialGrantDatabase,
) -> Iterator[psycopg.Connection]:
    """既identity autouseへ所有primaryの実限定roleを渡す。"""
    with psycopg.connect(
        initial_scope_database.authority.database.endpoints.primary_dsn
    ) as connection:
        yield connection


def test_real_initial_scope_app_actor_acl_and_memberships(
    initial_scope_database: InitialGrantDatabase,
) -> None:
    """app/actorを実LOGINで分離し、秘密表DML/任意D4とapp9EXECUTEを拒否する。"""
    app = initial_scope_database.acl_probe("app")
    actor = initial_scope_database.acl_probe("actor")
    assert app == {
        "identity": ["pitchlog_app", "pitchlog_app"],
        "states": ["42501"] * 26,
    }
    assert actor == {
        "identity": ["pitchlog_initial_actor", "pitchlog_initial_actor"],
        "states": ["42501"] * 17,
    }
    assert initial_scope_database.ledger_snapshot() == ()


def test_real_initial_scope_commits_and_replays_same_v12_without_reserving(
    initial_scope_database: InitialGrantDatabase,
) -> None:
    """実reserve/claimと暗号保存後、同request再交付は同V12で予約を増やさない。"""
    database = initial_scope_database
    result = database.actor("""
first=issue()
second=issue(replace(owner,attempt_id=uuid4()))
assert first.recording_right_proof==second.recording_right_proof
assert first==second
print(json.dumps(receipt(first)))
""")
    assert result["game_id"] == str(database.game_id)
    assert result["device_id"] == str(database.device_id)
    assert type(result["generation"]) is int and result["generation"] == 1
    assert result["epoch"] == "1"
    rows = database.ledger_snapshot()
    assert len(rows) == 1
    assert rows[0] == (
        database.attempt_id,
        database.tenant_id,
        database.game_id,
        database.start_request_id,
        1,
        1,
        True,
        False,
    )
    saved = database.storage()
    assert all(len(rows) == 1 for rows in saved.values())
    generation = saved["recording_generations"][0]
    assert generation["generation"] == 1
    assert generation["kind"] == "normal" and generation["issuance_order"] == 1
    assert generation["confirmed_watermark"] == generation["applied_prefix"] == 0
    assert generation["holder_device"] == str(database.device_id)
    assert generation["proof_digest"] == "\\x" + result["proof_digest"]
    assert generation["recovery_generation"] == 1
    delivery = saved["recording_right_deliveries"][0]
    assert delivery["key_id"] == "k1"
    assert len(delivery["nonce"]) == 2 + 12 * 2
    assert len(delivery["ciphertext"]) == 2 + 48 * 2
    assert saved["game_start_attempts"][0]["outcome"] == "committed"
    # grant-only部品はゲーム開始/初期名簿保存をまだ実装していない。
    with psycopg.connect(database.authority.database.business_admin) as admin:
        assert admin.execute(
            "SELECT status,started_at FROM public.games WHERE id=%s",
            (database.game_id,),
        ).fetchone() == ("preparing", None)
        assert admin.execute("SELECT count(*) FROM public.game_lineups").fetchone() == (
            0,
        )


@pytest.mark.parametrize("reason", ("wrong", "missing", "revoked", "tenant", "foreign"))
def test_real_initial_scope_rejects_credentials_or_owner_before_reservation(
    initial_scope_database: InitialGrantDatabase,
    reason: str,
) -> None:
    """無効資格/失効/別tenant ownerは実台帳の予約前に停止する。"""
    database = initial_scope_database
    if reason == "revoked":
        with psycopg.connect(database.authority.database.business_admin) as admin:
            admin.execute(
                "UPDATE public.trusted_devices SET revoked_at=CURRENT_TIMESTAMP "
                "WHERE tenant_id=%s AND device_id=%s",
                (database.tenant_id, database.device_id),
            )
    mutations = {
        "wrong": "issue(credential='incorrect-public-vector')",
        "missing": "issue(replace(owner,device_id=uuid4()))",
        "revoked": "issue()",
        "tenant": f"issue(replace(owner,tenant_id=UUID('{database.other_tenant_id}')))",
        "foreign": (
            f"issue(replace(owner,tenant_id=UUID('{database.other_tenant_id}')),"
            f"selected_context=make_tenant_context(UUID('{database.other_tenant_id}')))"
        ),
    }
    result = database.actor(f"""
try:
    {mutations[reason]}
except InitialGrantUnavailable:
    print(json.dumps({{'refused':True}}))
else:
    raise AssertionError('invalid owner/credential acknowledged')
""")
    assert result == {"refused": True}
    assert database.ledger_snapshot() == ()
    assert all(rows == [] for rows in database.storage().values())


@pytest.mark.parametrize("mutation", ("payload", "device"))
def test_real_initial_scope_replay_rejects_owner_changes(
    initial_scope_database: InitialGrantDatabase,
    mutation: str,
) -> None:
    """同一requestを別payload/端末へ結び直さず、保存/実予約を維持する。"""
    database = initial_scope_database
    first = database.actor("print(json.dumps(receipt(issue())))")
    before = database.storage()
    reservations = database.ledger_snapshot()
    changed = (
        "replace(owner,request_digest=b'x'*32,attempt_id=uuid4())"
        if mutation == "payload"
        else f"replace(owner,device_id=UUID('{database.other_device_id}'),"
        "attempt_id=uuid4())"
    )
    result = database.actor(f"""
from sqlalchemy.exc import DBAPIError
try:
    issue({changed})
except (InitialGrantConflict,InitialGrantUnavailable,DBAPIError) as error:
    print(json.dumps({{'refused':True,'error_type':type(error).__name__}}))
else:
    raise AssertionError('changed replay acknowledged')
""")
    assert result["refused"] is True
    assert database.storage() == before
    assert database.ledger_snapshot() == reservations
    assert database.actor("print(json.dumps(receipt(issue())))") == first


@pytest.mark.parametrize("stage", ("generation", "delivery", "commit"))
def test_real_initial_scope_fault_rolls_back_all_business_inserts(
    initial_scope_database: InitialGrantDatabase,
    stage: str,
) -> None:
    """片側INSERT/遅延commit故障は実到達し、D4消費を巻き戻したと断定しない。"""
    from typing import Literal, cast

    database = initial_scope_database
    with database.fault(cast(Literal["generation", "delivery", "commit"], stage)):
        result = database.actor("""
from sqlalchemy.exc import DBAPIError
try:
    issue()
except DBAPIError as error:
    print(json.dumps({'refused':True,'error_type':type(error).__name__}))
else:
    raise AssertionError('failed transaction acknowledged')
""")
        assert result["refused"] is True
    saved = database.storage()
    assert saved["recording_generations"] == saved["recording_right_deliveries"] == []
    assert len(saved["game_start_requests"]) == len(saved["game_start_attempts"]) == 1
    assert saved["game_start_attempts"][0]["outcome"] == "pending"
    reservations = database.ledger_snapshot()
    assert len(reservations) == 1 and reservations[0][4:] == (1, 1, True, False)
    # 業務側rollback確定でもclaim済みD4を再利用/別attemptへ自動再送しない。
    retry = database.actor("""
from pitchlog.durable_rights_ledger import LedgerUnavailable,LedgerOutcomeUnconfirmed
from pitchlog.repositories.rg1 import RG1Unavailable
try:
    issue(replace(owner,attempt_id=uuid4()))
except (LedgerUnavailable,LedgerOutcomeUnconfirmed,
        InitialGrantUnavailable,RG1Unavailable) as error:
    print(json.dumps({'refused':True,'error_type':type(error).__name__}))
else:
    raise AssertionError('unresolved/claimed attempt automatically reissued')
""")
    assert retry["refused"] is True
    assert database.ledger_snapshot() == reservations
    assert database.storage() == saved
