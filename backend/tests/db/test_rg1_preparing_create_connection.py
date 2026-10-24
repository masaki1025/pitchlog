"""実fresh/RG1/認証を通す準備中試合作成HTTPの最小接合検証。"""

from __future__ import annotations

from collections.abc import Iterator
from time import monotonic, sleep
from uuid import UUID

import psycopg
import pytest
from db_fixtures import _dsn_names
from test_game_preparing_components import _create_payload

from pitchlog.db.game_state.rule_snapshot import (
    decode_applied_rules,
    encode_applied_rules,
)

from .durable_rights_ledger_support import (
    AuthorityDatabase,
)
from .rg1_preparing_create_support import (
    CreateFaultPhase,
    PreparingCreateDatabase,
    inject_preparing_create_failure,
    isolated_preparing_authority_database,
)
from .test_api_auth_exit_entry import _assert_read_metadata, _read_headers

pytestmark = pytest.mark.requires_db


@pytest.fixture
def authority_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[AuthorityDatabase]:
    """外部DSNを使わず共通identity検査へ所有接続先だけを供給する。"""
    admin_name, role_name = _dsn_names()
    monkeypatch.delenv(admin_name, raising=False)
    monkeypatch.delenv(role_name, raising=False)
    with isolated_preparing_authority_database(monkeypatch) as authority:
        monkeypatch.setenv(admin_name, authority.database.primary_admin)
        monkeypatch.setenv(role_name, authority.database.endpoints.primary_dsn)
        yield authority


@pytest.fixture
def admin_connection(
    authority_database: AuthorityDatabase,
) -> Iterator[psycopg.Connection]:
    """所有primaryの実admin接続で共通autouseを実行する。"""
    with psycopg.connect(authority_database.database.primary_admin) as connection:
        yield connection


@pytest.fixture
def tested_role_connection(
    authority_database: AuthorityDatabase,
) -> Iterator[psycopg.Connection]:
    """所有primaryの実制限app接続で共通autouseを実行する。"""
    with psycopg.connect(
        authority_database.database.endpoints.primary_dsn
    ) as connection:
        yield connection


def test_actual_http_login_fresh_create_commit_and_get(
    authority_database: AuthorityDatabase,
) -> None:
    """実HTTP login Cookie/C2からgameを初作成し、別GETの全保存値を照合する。"""
    database = PreparingCreateDatabase(authority_database)
    try:
        database.prepare()
        database.start_api()
        identity = database.identity
        assert identity is not None and database.origin is not None
        with database.http_client() as client:
            login = client.post(
                "/auth/login",
                json={"team_name": identity.name, "password": identity.password},
                headers={"Origin": database.origin, "X-Pitchlog-Request": "1"},
            )
            assert login.status_code == 200, "実HTTP loginが非成功"
            assert login.json()["tenant_id"] == str(identity.tenant_id)
            assert "Secure" in login.headers["set-cookie"]
            assert "HttpOnly" in login.headers["set-cookie"]
            assert "Path=/" in login.headers["set-cookie"]
            assert "Domain=" not in login.headers["set-cookie"]
            assert "__Host-pitchlog_token" in client.cookies
            headers = _read_headers(identity.tenant_id)
            headers.update({"Origin": database.origin, "X-Pitchlog-Request": "1"})
            body = {
                **_create_payload(),
                "away_team_record_id": str(database.teams[0]),
                "home_team_record_id": str(database.teams[1]),
                "tournament": {"kind": "new", "display_name": "実HTTP新大会"},
            }
            create_request = client.build_request(
                "POST", "/games", json=body, headers=headers
            )
            assert create_request.headers.get("cookie"), (
                "実login Cookieが自動再送されない"
            )
            created = client.send(create_request)
            assert created.status_code == 201, (
                "実HTTP POST /gamesが非201: " + database.diagnostic()
            )
            _assert_read_metadata(created, headers, success=True)
            saved = created.json()
            assert len(saved) == 13
            game_id = UUID(saved["id"])
            assert str(game_id) == saved["id"] and saved["status"] == "preparing"
            fetched_headers = _read_headers(identity.tenant_id)
            fetched = client.get(f"/games/{game_id}", headers=fetched_headers)
            assert fetched.status_code == 200
            _assert_read_metadata(fetched, fetched_headers, success=True)
            assert fetched.json() == saved
            assert created.history == fetched.history == []
        write_counts = tuple(
            int(line.split()[1])
            for line in database.diagnostic().splitlines()
            if line.startswith("API_INTEGER_RESULT ")
        )
        assert write_counts == (1, 1), "実大会/game INSERTの件数を補完しない"
        with psycopg.connect(authority_database.database.business_admin) as observer:
            rows = observer.execute(
                "SELECT id,tenant_id,status,applied_rules FROM public.games"
            ).fetchall()
            assert rows == [
                (game_id, identity.tenant_id, "preparing", saved["applied_rules"])
            ]
            assert (
                encode_applied_rules(decode_applied_rules(rows[0][3]))
                == saved["applied_rules"]
            )
            assert observer.execute(
                "SELECT display_name FROM public.tenant_vocabularies "
                "WHERE tenant_id=%s AND category='tournament' AND key=%s",
                (identity.tenant_id, saved["tournament_key"]),
            ).fetchone() == ("実HTTP新大会",)
            assert observer.execute(
                "SELECT count(*) FROM public.tenant_vocabularies "
                "WHERE tenant_id=%s AND category='tournament'",
                (identity.tenant_id,),
            ).fetchone() == (1,)
        assert authority_database.event_counts().get("activation_open") == 1
    finally:
        database.close()


@pytest.mark.parametrize("phase", ("before_insert", "after_insert", "deferred_commit"))
def test_actual_http_create_fault_cancels_game_and_new_tournament(
    authority_database: AuthorityDatabase, phase: CreateFaultPhase
) -> None:
    """語彙後/game後/commit故障で実到達・全取消・既存語彙の不変を確認する。"""
    database = PreparingCreateDatabase(authority_database)
    try:
        database.prepare()
        identity = database.identity
        assert identity is not None
        with psycopg.connect(authority_database.database.business_admin) as observer:
            observer.execute(
                "INSERT INTO public.tenant_vocabularies "
                "(tenant_id,key,category,display_name,disabled) "
                "VALUES (%s,'atomicity_existing','tournament','既存大会を保持',false)",
                (identity.tenant_id,),
            )
            # 一部の表示値だけでなく、旧語彙全行・全fieldを実DBで固定する。
            before = observer.execute(
                "SELECT pg_catalog.to_jsonb(v) FROM public.tenant_vocabularies v "
                "ORDER BY tenant_id,key"
            ).fetchall()
            assert len(before) == 1
        with inject_preparing_create_failure(database, phase) as fault:
            database.start_api()
            assert database.origin is not None
            with database.http_client() as client:
                login = client.post(
                    "/auth/login",
                    json={"team_name": identity.name, "password": identity.password},
                    headers={"Origin": database.origin, "X-Pitchlog-Request": "1"},
                )
                assert login.status_code == 200
                assert login.json()["tenant_id"] == str(identity.tenant_id)
                assert "__Host-pitchlog_token" in client.cookies
                headers = _read_headers(identity.tenant_id)
                headers.update({"Origin": database.origin, "X-Pitchlog-Request": "1"})
                request = client.build_request(
                    "POST",
                    "/games",
                    json={
                        **_create_payload(),
                        "away_team_record_id": str(database.teams[0]),
                        "home_team_record_id": str(database.teams[1]),
                        "tournament": {
                            "kind": "new",
                            "display_name": "故障時に残してはいけない新大会",
                        },
                    },
                    headers=headers,
                )
                assert request.headers.get("cookie"), "実login Cookieが未再送"
                failed = client.send(request)
                # 実create handlerの汎用例外/commit失敗→HTTPException(503)と
                # 共通HTTP handlerの固定封筒に従う。原本文を失敗logへ露出させない。
                assert failed.status_code == 503
                if failed.json() != {
                    "error": {"message": "リクエストを処理できません"}
                }:
                    raise AssertionError("故障の内部情報が固定HTTP外形へ漏れた")
                _assert_read_metadata(failed, headers, success=False)
                assert failed.history == []
                listed_headers = _read_headers(identity.tenant_id)
                listed = client.get("/games", headers=listed_headers)
                assert listed.status_code == 200
                _assert_read_metadata(listed, listed_headers, success=True)
                assert listed.json() == {"items": [], "next_cursor": None}
            assert fault.counters() == (
                1,
                1,
                0 if phase == "before_insert" else 1,
            ), "rollback非追随sequenceが実fault/語彙/game到達を示さない"
            with psycopg.connect(
                authority_database.database.business_admin
            ) as observer:
                assert observer.execute(
                    "SELECT count(*) FROM public.games"
                ).fetchone() == (0,)
                assert (
                    observer.execute(
                        "SELECT pg_catalog.to_jsonb(v) "
                        "FROM public.tenant_vocabularies v "
                        "ORDER BY tenant_id,key"
                    ).fetchall()
                    == before
                )
            writes = tuple(
                int(line.split()[1])
                for line in database.diagnostic().splitlines()
                if line.startswith("API_INTEGER_RESULT ")
            )
            assert writes == ((1, 1) if phase == "deferred_commit" else (1,))
            if phase == "deferred_commit":
                # COMMITの例外はscopeが完了へ補完せず実loanをabandonし、
                # fresh/controllerの未終端を保持する。SQLによる再openやPOST再送なし。
                deadline = monotonic() + 6
                while True:
                    with psycopg.connect(
                        authority_database.database.business_admin
                    ) as observer:
                        gate = observer.execute(
                            "SELECT state FROM public.rg1_restore_gate "
                            "WHERE singleton_id=1"
                        ).fetchone()
                    if gate == ("closed",) and not database.controller.running():
                        break
                    assert monotonic() < deadline, "commit不明後の実gateが閉じない"
                    sleep(0.05)
                assert (
                    authority_database.client("""
try:
    s.current_recovery_generation()
except LedgerUnavailable:
    print('COMMIT_UNCONFIRMED_CLOSED')
else:
    raise AssertionError('unconfirmed business commit remains open')
""")
                    == "COMMIT_UNCONFIRMED_CLOSED"
                )
                events = authority_database.event_counts()
                assert events.get("activation_open") == 1
                assert events.get("lease_close", 0) == events.get("INTENT", 0) == 0
            else:
                with psycopg.connect(
                    authority_database.database.business_admin
                ) as observer:
                    assert observer.execute(
                        "SELECT state FROM public.rg1_restore_gate WHERE singleton_id=1"
                    ).fetchone() == ("open",)
                assert database.controller.running()
    finally:
        database.close()
