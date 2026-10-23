"""単一Protocol、固定DDL/ACL、有限取消と拒否境界を検査する。"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
from time import sleep
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from pitchlog.durable_rights_ledger import (
    DurableLedger,
    LedgerEndpoints,
    LedgerOutcomeUnconfirmed,
    LedgerUnavailable,
    adapter,
)
from pitchlog.recording_rights.initial_grant import (
    DurableGenerationSource,
    RecoveryEpochFence,
    ReservedGeneration,
)

_PACKAGE = Path(adapter.__file__).parent


def test_fixed_manifest_and_single_supplier_protocol() -> None:
    """固定DDLと全API/roleを照合し、Protocol/DTOコピーを拒否する。"""
    manifest = json.loads((_PACKAGE / "manifest.json").read_text())
    ddl = (_PACKAGE / "schema.sql").read_bytes()
    assert hashlib.sha256(ddl).hexdigest() == manifest["ddl_sha256"]
    assert set(manifest) == {
        "schema_version",
        "postgres_version",
        "schema",
        "ddl_sha256",
        "tables",
        "roles",
        "functions",
        "synchronous_peer",
        "client",
        "boundaries",
        "protocol_source",
        "required_settings",
        "identity",
        "timeout_seconds",
    }
    assert manifest["tables"] == ["state", "highwater", "reservations"]
    assert manifest["required_settings"] == {
        "fsync": "on",
        "full_page_writes": "on",
        "synchronous_commit": "on",
        "synchronous_standby_names": "FIRST 1 (ledger_standby)",
    }
    assert manifest["client"] == {
        "psycopg": "3.3.4",
        "minimum_libpq": 170000,
        "cancel_safe_required": True,
    }
    assert manifest["identity"]["timeline"] == 1
    assert manifest["timeout_seconds"]["reconnect_cancelled_connection"] is False
    assert set(manifest["functions"]) == {
        "identity()",
        "epoch_fence()",
        "reservation(uuid,uuid,uuid,uuid)",
        "reserve(uuid,uuid,uuid,uuid)",
        "claim(uuid,uuid,uuid,uuid)",
        "advance_epoch(bigint)",
    }
    assert manifest["boundaries"]["cold_attach_proof_port"] == "NOT_PROVIDED"
    assert manifest["boundaries"]["promotion_issuance"] is False
    assert adapter.ReservedGeneration is ReservedGeneration
    assert adapter.RecoveryEpochFence is RecoveryEpochFence
    assert DurableGenerationSource in DurableLedger.__bases__
    source = Path(inspect.getfile(ReservedGeneration)).read_bytes()
    assert hashlib.sha256(source).hexdigest() == manifest["protocol_source"]["sha256"]
    assert b"FOR SHARE" in ddl and b"FOR UPDATE" in ddl
    assert (
        ddl.count(b"SECURITY DEFINER SET search_path = pg_catalog, pitchlog_ledger")
        == 6
    )
    assert b"REVOKE ALL ON ALL TABLES" in ddl
    tree = ast.parse(Path(adapter.__file__).read_text())
    assert not any(
        isinstance(n, ast.ClassDef)
        and n.name
        in {"ReservedGeneration", "RecoveryEpochFence", "DurableGenerationSource"}
        for n in ast.walk(tree)
    )


@pytest.mark.parametrize("value", [True, False, 0, -1, 2**63, 1.0, "1", None])
def test_bigint_boundary_rejects_untyped_values(value: object) -> None:
    """bool・float・上限越えをbigintとして再解釈しない。"""
    with pytest.raises(LedgerUnavailable):
        adapter._positive(value)


@pytest.mark.parametrize("value", [True, 0, -1, float("inf"), float("nan"), "1", 31])
def test_endpoint_timeout_is_finite_and_redacted(value: Any) -> None:
    """資格をreprへ出さず、未対応期限を接続前に拒否する。"""
    with pytest.raises(LedgerUnavailable):
        LedgerEndpoints(
            "test-primary", "test-standby", "test-business", "test-control", value
        )
    endpoints = LedgerEndpoints(
        "test-primary", "test-standby", "test-business", "test-control"
    )
    assert "test-primary" not in repr(endpoints)


@pytest.mark.parametrize("version,capable", [(160000, True), (180000, False)])
def test_legacy_cancel_is_refused_before_connection(
    monkeypatch: pytest.MonkeyPatch, version: int, capable: bool
) -> None:
    """旧libpqのlegacy fallbackは接続前に失敗閉鎖する。"""
    monkeypatch.setattr(adapter.pq, "version", lambda: version)
    monkeypatch.setattr(adapter.capabilities, "has_cancel_safe", lambda: capable)
    calls = []
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(LedgerUnavailable, match="^ledger unavailable$"):
        adapter._connect("not-an-operational-dsn", 1)
    assert calls == []


def test_cancelled_commit_success_return_remains_unconfirmed() -> None:
    """取消発行後の見かけの成功を成功応答に戻さない。"""
    calls = []

    class Connection:
        def commit(self) -> None:
            sleep(0.06)

        def cancel_safe(self, *, timeout: float) -> None:
            calls.append(timeout)

    with pytest.raises(LedgerOutcomeUnconfirmed, match="^ledger outcome unconfirmed$"):
        adapter._commit(cast(psycopg.Connection[Any], Connection()), 0.01)
    assert calls == [0.01]


def test_unknown_query_and_owner_are_rejected_before_execution() -> None:
    """任意SQL/未知操作/UUID風の文字列を実行口へ流さない。"""
    with pytest.raises(LedgerUnavailable):
        adapter._query(
            cast(psycopg.Connection[Any], object()),
            cast(adapter.Operation, "DROP TABLE x"),
        )
    with pytest.raises(LedgerUnavailable):
        adapter._owner((UUID(int=1), UUID(int=2), UUID(int=3), str(UUID(int=4))))


def test_post_commit_primary_read_failure_is_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COMMIT後最初のprimary再読故障も未確定へ写し、内部原因を秘匿する。"""

    def broken_identity(connection: psycopg.Connection[Any]) -> dict[str, Any]:
        raise RuntimeError("private internal transport detail")

    monkeypatch.setattr(adapter, "_identity", broken_identity)
    with pytest.raises(
        LedgerOutcomeUnconfirmed, match="^ledger outcome unconfirmed$"
    ) as captured:
        DurableLedger._confirmed(
            cast(DurableLedger, None), cast(psycopg.Connection[Any], None), None, ()
        )
    assert captured.value.__suppress_context__ is True


def test_elapsed_deadline_is_unconfirmed_even_when_timer_callback_is_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消threadのschedule遅延が期限越えの成功を作らない。"""

    class DelayedTimer:
        def __init__(self, *args: object) -> None:
            pass

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            pass

        def join(self, timeout: float) -> None:
            pass

        def is_alive(self) -> bool:
            return False

    class Connection:
        def commit(self) -> None:
            sleep(0.02)

    monkeypatch.setattr(adapter, "Timer", DelayedTimer)
    with pytest.raises(LedgerOutcomeUnconfirmed):
        adapter._commit(cast(psycopg.Connection[Any], Connection()), 0.001)
