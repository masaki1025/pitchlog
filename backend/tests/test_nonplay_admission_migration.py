"""0042は後段のAPI schemaを前提にせずdefault-denyで配置する。"""

import re
import runpy
from pathlib import Path

import pytest
from alembic import op


def _statements(monkeypatch):
    """実upgradeを記録する。DB適用・認可の成功証明ではない。"""
    statements = []
    monkeypatch.setattr(op, "execute", lambda sql: statements.append(sql))
    migration = runpy.run_path(
        str(
            Path(__file__).parents[1]
            / "migrations/versions/0042_nonplay_write_admission.py"
        )
    )
    assert migration["down_revision"] == "0041_stats_fact_versions"
    migration["upgrade"]()
    return statements


def _check_function_schemas(statements):
    """0041までとbefore-rule配置だけで存在するschemaを前提に検査する。"""
    schemas = {"public", "sync_fence"}
    found = []
    for sql in statements:
        match = re.search(r"CREATE FUNCTION ([a-z_]+)\.([a-z_]+)\(", sql)
        if match:
            if match[1] not in schemas:
                raise ValueError("後段作成schemaへの先行依存")
            found.append((match[1], match[2]))
    return found


def test_guard_can_be_placed_before_product_api_schemas(monkeypatch):
    """実失敗のsync_fence_api前倒し依存を再導入しない。"""
    statements = _statements(monkeypatch)
    assert _check_function_schemas(statements) == [
        ("public", "protect_nonplay_admission")
    ]
    broken = [
        sql.replace(
            "public.protect_nonplay_admission",
            "sync_fence_api.protect_nonplay_admission",
        )
        for sql in statements
    ]
    with pytest.raises(ValueError, match="後段"):
        _check_function_schemas(broken)


def test_invoker_guard_owner_and_revocation_are_explicit(monkeypatch):
    """新権限を開けず、既callerを検査するguardを同じ2triggerへ束縛する。"""
    statements = _statements(monkeypatch)
    function = next(sql for sql in statements if "CREATE FUNCTION" in sql)
    assert (
        "RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp"
        in function
    )
    assert "SECURITY DEFINER" not in function
    assert "current_user<>'pitchlog_sync_right_fn_owner'" in function
    assert "TG_OP IN ('DELETE','TRUNCATE')" in function
    assert "OLD.state IN ('consumed','invalid')" in function
    assert (
        "ALTER FUNCTION public.protect_nonplay_admission() OWNER TO pitchlog_owner"
        in statements
    )
    assert any(
        "REVOKE ALL ON FUNCTION public.protect_nonplay_admission() FROM\n"
        "        PUBLIC,pitchlog_app" in sql
        for sql in statements
    )
    triggers = [sql for sql in statements if "CREATE TRIGGER" in sql]
    assert len(triggers) == 2
    assert all(
        "EXECUTE FUNCTION\n        public.protect_nonplay_admission()" in sql
        for sql in triggers
    )
    assert any("BEFORE INSERT OR UPDATE OR DELETE" in sql for sql in triggers)
    assert any("BEFORE TRUNCATE" in sql for sql in triggers)
    assert not any("GRANT " in sql for sql in statements)
