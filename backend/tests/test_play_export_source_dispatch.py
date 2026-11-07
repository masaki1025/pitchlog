"""CSV source dispatcherのscope拒否と実登録の固定性をSQLなしで確認する。"""

from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import operation_registry, transaction
from pitchlog.repositories.binding import TenantBindingError
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    prepare_function_operation,
)
from pitchlog.repositories.play_export_source_codec import ReadExportSourcePageToken
from pitchlog.repositories.play_export_source_operations import (
    ReadPlayExportSources,
    run_qualified_source_read,
    source_read_operation,
)


@pytest.fixture
def world(monkeypatch):
    """実handle発行/marker検査を保ち、SQL到達を拒否する単位fixture。"""
    key = object()
    context = make_tenant_context(UUID(int=1))
    calls = []

    def execute(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("未資格のsource readがSQLへ到達")

    session = SimpleNamespace(execute=execute)
    monkeypatch.setitem(transaction._TRANSACTION_RUNTIMES, key, (session, ExitStack()))
    handle = transaction._TenantTransaction(
        context,
        key,
        context.tenant_id,
        context._integrity_proof,
        transaction._HANDLE_CREATION_TOKEN,
    )
    return SimpleNamespace(handle=handle, key=key, calls=calls, monkeypatch=monkeypatch)


@pytest.mark.parametrize("bad", ["plain", "stats", "expired", "context", "marker"])
def test_other_or_expired_scope_executes_zero_sql(world, bad):
    """plain/stats scopeや失効/文脈交換/別markerを実gateで拒否する。"""
    handle, key = world.handle, world.key
    if bad == "stats":
        world.monkeypatch.setitem(transaction._STATS_READ_HANDLES, key, handle)
    if bad == "expired":
        handle._expire()
    if bad == "context":
        world.monkeypatch.setattr(handle, "_context", make_tenant_context(UUID(int=2)))
    if bad == "marker":
        world.monkeypatch.setitem(transaction._PLAY_EXPORT_HANDLES, key, object())
    with pytest.raises((TenantBindingError, RuntimeError)):
        handle.run(ReadExportSourcePageToken(UUID(int=3)))
    assert world.calls == []


def test_free_object_does_not_become_a_source_handle(world):
    """同じkey値を持つだけのobjectからread能力を作らない。"""
    fake = SimpleNamespace(_state_key=world.key)
    with pytest.raises(TenantBindingError):
        run_qualified_source_read(fake, ReadExportSourcePageToken(UUID(int=3)))
    assert world.calls == []


def test_registry_replacement_and_changed_token_execute_zero_sql(world):
    """同値登録copyや受付後書換えを真正scopeだけで成功させない。"""
    world.monkeypatch.setitem(transaction._PLAY_EXPORT_HANDLES, world.key, world.handle)
    spec = source_read_operation()
    changed = dict(operation_registry.FUNCTION_OPERATION_REGISTRY)
    changed[ReadExportSourcePageToken] = replace(spec)
    with world.monkeypatch.context() as patch:
        patch.setattr(operation_registry, "FUNCTION_OPERATION_REGISTRY", changed)
        with pytest.raises(FunctionOperationError):
            world.handle.run(ReadExportSourcePageToken(UUID(int=3)))
    request = ReadExportSourcePageToken(UUID(int=3))
    object.__setattr__(request, "page_size", 501)
    with pytest.raises(ValueError):
        world.handle.run(request)
    assert world.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("capability_id", "CAP:stats_primitives:read"),
        ("function_id", "stats_api.other"),
        ("max_rows", 501),
    ],
)
def test_registration_cannot_change_reserved_identity(field: str, value: Any):
    """新しい有限familyを任意SQL/別能力の登録へ使わない。"""
    with pytest.raises(FunctionOperationError):
        replace(source_read_operation(), **{field: value})


def test_generic_function_path_cannot_execute_source_token(world):
    """値tokenを汎用経路へ渡してscope制限を迂回できない。"""
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(
            ReadExportSourcePageToken(UUID(int=3)),
            UUID(int=1),
            operation_registry.FUNCTION_OPERATION_REGISTRY,
        )
    with pytest.raises(TenantBindingError):
        ReadPlayExportSources(world.handle, UUID(int=3))
    assert world.calls == []
