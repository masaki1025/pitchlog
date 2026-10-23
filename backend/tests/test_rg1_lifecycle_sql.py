"""RG1固定SQLのACL・lock・実観測境界を静的に検査する。

実PGへの適用/競合・fresh成功・実画面保存の証拠ではない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

_SQL_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/pitchlog/recording_rights/rg1_lifecycle.sql"
)
_CONTROL_NAMES = frozenset(
    {
        "try_controller_lease",
        "release_controller_lease",
        "close_gate",
        "open_fresh_gate",
        "controller_lease_alive",
        "read_closed_gate",
    }
)
_NAMESPACE = 0x52473143
_ACTOR = "pitchlog_rg1_control_actor"
_OWNER = "pitchlog_rg1_control_owner"
_FUNCTION = re.compile(
    r"CREATE OR REPLACE FUNCTION rg1_control\.([a-z0-9_]+)\(([^)]*)\)\s+"
    r"RETURNS (boolean|jsonb|text)\s+LANGUAGE plpgsql\s+VOLATILE\s+"
    r"SECURITY DEFINER\s+SET search_path = pg_catalog, pg_temp\s+"
    r"AS \$function\$(.*?)\$function\$;",
    re.DOTALL,
)


@dataclass(frozen=True)
class _Function:
    arguments: str
    returns: str
    body: str


def _source() -> str:
    """製品候補のSQLそのものを読む。"""
    return _SQL_PATH.read_text(encoding="utf-8")


def _functions() -> dict[str, _Function]:
    """閉じたSECDEF・固定path文法に一致する全関数を抽出する。"""
    matches = _FUNCTION.findall(_source())
    assert len(matches) == 7
    assert len({name for name, *_ in matches}) == 7
    return {
        name: _Function(args, returns, body) for name, args, returns, body in matches
    }


def _without_comments(source: str) -> str:
    """コメントを除き、実ステートメントだけを検査する。"""
    return re.sub(r"--[^\n]*", "", source)


def test_exact_function_surface_and_security_configuration() -> None:
    """制御6無引数とtenant一致の固定read1件だけを公開面にする。"""
    functions = _functions()
    assert set(functions) == _CONTROL_NAMES | {"scope_binding"}
    for name, function in functions.items():
        assert function.arguments == (
            "p_tenant_id uuid" if name == "scope_binding" else ""
        )
        assert function.returns == (
            "text"
            if name == "scope_binding"
            else "jsonb"
            if name == "read_closed_gate"
            else "boolean"
        )
        signature = f"rg1_control.{name}({'uuid' if name == 'scope_binding' else ''})"
        assert f"ALTER FUNCTION {signature}\n    OWNER TO {_OWNER};" in _source()
        assert f"REVOKE ALL PRIVILEGES ON FUNCTION {signature}" in _source()
    assert _source().count("CREATE OR REPLACE FUNCTION ") == 7
    assert "SECURITY INVOKER" not in _source()


def test_role_attributes_and_database_profile_are_minimal() -> None:
    """actor以外のLOGIN、membership、DBのCREATE/TEMPを足さない。"""
    source = _without_comments(_source())
    for role, login in ((_OWNER, "NOLOGIN"), (_ACTOR, "LOGIN")):
        match = re.search(rf"CREATE ROLE {role} (.*?);", source, re.DOTALL)
        assert match is not None
        assert set(match[1].split()) == {
            login,
            "NOSUPERUSER",
            "NOBYPASSRLS",
            "NOINHERIT",
            "NOCREATEROLE",
            "NOCREATEDB",
            "NOREPLICATION",
        }
    assert "GRANT CONNECT ON DATABASE %I TO " + _ACTOR in source
    assert "REVOKE CREATE, TEMPORARY ON DATABASE %I FROM " + _ACTOR in source
    assert source.count("pg_catalog.has_database_privilege(") == 2
    assert "'TEMPORARY'" in source and "'CREATE'" in source
    assert not re.search(r"GRANT\s+pitchlog_[a-z0-9_]+\s+TO", source)
    assert "pg_read_all_stats" not in source
    assert "PASSWORD" not in source


def test_execute_acl_is_exact_and_keeps_public_builtins_unchanged() -> None:
    """appはscope_bindingだけ、旧read ownerはalive helperだけへ制限する。"""
    source = _without_comments(_source())
    grants = re.findall(
        r"GRANT EXECUTE ON FUNCTION ([a-z0-9_.]+\([^)]*\))\s+TO ([a-z0-9_]+);",
        source,
    )
    expected = {(f"rg1_control.{name}()", _ACTOR) for name in _CONTROL_NAMES}
    expected |= {
        ("rg1_control.controller_lease_alive()", "pitchlog_rg1_fn_owner"),
        ("rg1_control.scope_binding(uuid)", "pitchlog_app"),
        ("pg_catalog.pg_control_system()", _OWNER),
    }
    assert len(grants) == len(set(grants))
    assert set(grants) == expected
    assert not re.search(r"REVOKE[^;]*ON FUNCTION pg_catalog\.", source, re.DOTALL)
    assert not re.search(r"GRANT[^;]+TO PUBLIC", source, re.DOTALL)
    assert "ALTER DEFAULT PRIVILEGES" not in source
    assert "GRANT USAGE ON SCHEMA rg1_control" in source


def test_only_singleton_state_column_and_singleton_rls_are_added() -> None:
    """表/列追加なし、ownerのSELECT2列とUPDATE(state)だけに閉じる。"""
    source = _without_comments(_source())
    grants = re.findall(
        r"GRANT ([^;]+) ON TABLE ([a-z0-9_.]+) TO ([a-z0-9_]+);",
        re.sub(r"\s+", " ", source),
    )
    assert grants == [
        (
            "SELECT (singleton_id, state), UPDATE (state)",
            "public.rg1_restore_gate",
            _OWNER,
        )
    ]
    assert "FOR SELECT TO " + _OWNER + " USING (singleton_id = 1)" in source
    assert "FOR UPDATE TO " + _OWNER in source
    assert "USING (singleton_id = 1) WITH CHECK (singleton_id = 1)" in source
    assert not re.search(
        r"CREATE TABLE|ADD COLUMN|INSERT INTO|DELETE FROM|TRUNCATE", source
    )
    assert re.findall(r"UPDATE public\.([a-z0-9_]+) SET state", source) == [
        "rg1_restore_gate",
        "rg1_restore_gate",
    ]
    assert "public.games" not in source


@pytest.mark.parametrize("name", sorted(_CONTROL_NAMES - {"controller_lease_alive"}))
def test_actor_operations_verify_session_and_own_database_controller_lock(
    name: str,
) -> None:
    """任意role/別DB/別PIDの鍵だけをactorの保持と誤認しない。"""
    body = _functions()[name].body
    assert f"session_user IS DISTINCT FROM '{_ACTOR}'" in body
    assert "current_setting('transaction_isolation') <> 'read committed'" in body
    assert "controller_lock.pid = pg_catalog.pg_backend_pid()" in body
    assert "backend.usename = 'pitchlog_rg1_control_actor'" in body
    assert "backend.datid = controller_lock.database" in body
    assert "controller_lock.database = (" in body
    assert "WHERE datname = pg_catalog.current_database()" in body
    assert "controller_lock.classid = 1380397379::oid" in body
    assert "controller_lock.objid = 1::oid" in body
    assert "controller_lock.objsubid = 2" in body
    assert "controller_lock.mode = 'ExclusiveLock'" in body
    assert "controller_lock.granted" in body


def test_advisory_keys_are_two_int_distinct_and_reentrant_try_does_not_stack() -> None:
    """専用namespaceの2キーだけを使い、保持済みtryで再取得しない。"""
    assert _NAMESPACE == 1380397379
    calls = re.findall(
        r"pg_catalog\.pg_(?:try_advisory_lock|advisory_unlock)\((\d+), (\d+)\)",
        _source(),
    )
    assert set(calls) == {(str(_NAMESPACE), "1"), (str(_NAMESPACE), "2")}
    assert "pg_advisory_unlock_all" not in _source()
    assert "pg_advisory_lock(" not in _source()
    body = _functions()["try_controller_lease"].body
    assert body.count("pg_catalog.pg_try_advisory_lock(") == 1
    assert body.index("RETURN true;") < body.index("pg_catalog.pg_try_advisory_lock(")
    assert "pg_stat_clear_snapshot()" in body


@pytest.mark.parametrize(
    "name", ["release_controller_lease", "read_closed_gate", "open_fresh_gate"]
)
def test_committed_closed_check_precedes_any_new_row_lock_or_unlock(name: str) -> None:
    """XID未割当を入口で検査し、同取引/子取引closeを確定と認めない。"""
    functions = _functions()
    body = functions[name].body
    assert body.count("pg_current_xact_id_if_assigned()") == 1
    assert body.index("pg_current_xact_id_if_assigned()") < body.index("SELECT state")
    assert "gate_state <> 'closed'" in body
    assert "pg_current_xact_id()" not in body
    for other in (
        "close_gate",
        "try_controller_lease",
        "controller_lease_alive",
        "scope_binding",
    ):
        assert "pg_current_xact_id_if_assigned()" not in functions[other].body


def test_close_does_not_release_lease_and_release_orders_open_before_controller() -> (
    None
):
    """closed更新とlease解放を別取引にし、開放中の先行解放を拒否する。"""
    functions = _functions()
    close = functions["close_gate"].body
    assert (
        "UPDATE public.rg1_restore_gate SET state = 'closed' WHERE singleton_id = 1;"
        in close
    )
    assert "pg_advisory_unlock" not in close
    assert "GET DIAGNOSTICS changed = ROW_COUNT;" in close
    release = functions["release_controller_lease"].body
    assert release.index("gate_state <> 'closed'") < release.index(
        "pg_advisory_unlock("
    )
    assert release.index("pg_advisory_unlock(1380397379, 2)") < release.index(
        "pg_advisory_unlock(1380397379, 1)"
    )
    assert release.count("open_lock.pid = pg_catalog.pg_backend_pid()") == 2


def test_live_helper_requires_same_actor_pid_database_and_both_live_keys() -> None:
    """appが同キーを偽装してもactorのsession userと両leaseに一致しない。"""
    body = _functions()["controller_lease_alive"].body
    assert "pg_stat_clear_snapshot()" in body
    assert "controller_lock.pid = open_lock.pid" in body
    assert "controller_lock.database = open_lock.database" in body
    assert "backend.pid = open_lock.pid AND backend.datid = open_lock.database" in body
    assert f"backend.usename = '{_ACTOR}'" in body
    assert "open_lock.objid = 2::oid AND open_lock.objsubid = 2" in body
    assert "controller_lock.objid = 1::oid AND controller_lock.objsubid = 2" in body
    assert body.count("mode = 'ExclusiveLock'") == 2
    assert "open_lock.granted" in body and "controller_lock.granted" in body
    assert "pg_current_xact_id_if_assigned" not in body
    assert "pg_backend_pid()" not in body


@pytest.mark.parametrize("name", ["read_closed_gate", "scope_binding"])
def test_identity_fields_are_actual_server_observations_and_not_fence_claims(
    name: str,
) -> None:
    """caller値をmetadataに使わず、実scopeの5項目だけを共通観測する。"""
    body = _functions()[name].body
    projection = body.split("SELECT pg_catalog.jsonb_build_object(", 1)[1]
    assert "control.system_identifier::text" in projection
    assert "database.oid::bigint" in projection
    assert "database.datname::text" in projection
    assert "pg_postmaster_start_time() AT TIME ZONE 'UTC'" in projection
    assert "'backend_pid', pg_catalog.pg_backend_pid()" in projection
    assert "FROM pg_catalog.pg_control_system() AS control" in projection
    assert "WHERE database.datname = pg_catalog.current_database()" in projection
    assert "p_tenant_id" not in projection
    assert not re.search(r"'(?:epoch|fence|all_writers|all_paths)[a-z_]*'", projection)
    if name == "scope_binding":
        assert "p_tenant_id IS DISTINCT FROM tenant_context" in body
        assert "current_setting('app.tenant_id', true)" in body
        assert "tenant_context IS NULL" in body
        assert ")::text INTO STRICT observed" in body
        assert "'gate_state'" not in projection
    else:
        assert "'gate_state', gate_state" in projection


def test_fixed_sql_has_no_trailing_whitespace() -> None:
    """未追跡でもSQL全行を検査し、旧diffcheckの見落としを繰り返さない。"""
    assert all(line == line.rstrip() for line in _source().splitlines())


def test_no_unrecognized_grant_statement_bypasses_the_acl_matrix() -> None:
    """別の有効GRANT文法を追加して有限ACL検査を素通りさせない。"""
    source = _without_comments(_source())
    # 関数9、schema USAGE2、singleton列1、固定動的CONNECT1。
    assert len(re.findall(r"\bGRANT\b", source, flags=re.IGNORECASE)) == 13
