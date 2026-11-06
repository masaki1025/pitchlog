"""成績固定5登録と私有実行経路の閉集合を検証する。実PGの受理ではない。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import frozen_history
from sqlalchemy import Integer, bindparam, column, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.functions import Function

from pitchlog.repositories import operation_registry as registry
from pitchlog.repositories import stats_function_codec as codec
from pitchlog.repositories import stats_native_operations as api
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    build_function_registry,
    decode_function_result,
    prepare_function_operation,
)
from pitchlog.repositories.play_export_primitives import (
    OpenPrimitiveSnapshotToken,
    ReadPrimitivePageToken,
)
from pitchlog.repositories.stats import ReadPrimitiveTotalsToken
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.stats.facts import SavePrimitiveSourceToken
from pitchlog.stats.generated.receiver import SOURCE_MODEL_HASH

U = UUID(int=1)


def _descriptor(r):
    """接合前に固定した同じ表記で旧登録の全値を比較する。"""
    return {
        "operation_id": r.operation_id,
        "capability_id": r.capability_id,
        "token_type": r.token_type.__module__ + "." + r.token_type.__qualname__,
        "function_id": r.function_id,
        "sql": str(r.statement.compile(dialect=postgresql.dialect())),
        "inputs": [(n, t.__module__ + "." + t.__qualname__) for n, t in r.input_fields],
        "results": [
            (n, t.__module__ + "." + t.__qualname__) for n, t in r.result_fields
        ],
        "min": r.min_rows,
        "max": r.max_rows,
        "nonempty": r.nonempty_inputs,
        "nullable": r.nullable_results,
        "aware": r.aware_datetime_results,
        "decoder": r.decoder.__module__ + "." + r.decoder.__qualname__,
    }


def test_existing_registrations_keep_order_sql_types_decoder_and_values():
    """接合基線25367の登録・generic tenant契約を新familyのために緩めない。"""
    start = registry.PRODUCT_FUNCTION_OPERATIONS.index(
        api.STATS_NATIVE_FUNCTION_OPERATIONS[0]
    )
    prefix = registry.PRODUCT_FUNCTION_OPERATIONS[:start]
    replay = tuple(
        row
        for row in prefix
        if row.operation_id == "SYNC_FIRST_BALL:verify_replay_device"
    )
    assert len(prefix) == 23 and len(replay) == 1
    from pitchlog.repositories.first_ball import REPLAY_DEVICE_VERIFY_OPERATION

    assert replay[0] is REPLAY_DEVICE_VERIFY_OPERATION
    assert replay[0].operation_id == "SYNC_FIRST_BALL:verify_replay_device"
    old = tuple(row for row in prefix if row is not replay[0])
    assert len(old) == 22
    raw = (
        json.dumps(
            [_descriptor(r) for r in old],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    assert hashlib.sha256(
        raw.encode()
    ).hexdigest() == frozen_history.read_original_pr197_pin(
        "stats_native_old_registry_sha256"
    )
    assert (
        registry.PRODUCT_FUNCTION_OPERATIONS[start : start + 5]
        == api.STATS_NATIVE_FUNCTION_OPERATIONS
    )
    for r in old:
        assert registry.FUNCTION_OPERATION_REGISTRY[r.token_type] is r


def test_five_exact_metadata_typed_statements_and_no_tenant_injection():
    """同codecの5identityだけが正確なSQL/引数順/行型を持つ。"""
    rows = api.STATS_NATIVE_FUNCTION_OPERATIONS
    assert len(rows) == 5
    assert {r.operation_id for r in rows} == {
        "STATS_PRIMITIVES:save_source",
        "STATS_PRIMITIVES:read_writer_state",
        "STATS_PRIMITIVES:open_snapshot",
        "STATS_PRIMITIVES:read_page",
        "STATS_PRIMITIVES:read_totals",
    }
    assert [len(r.input_fields) for r in rows] == [8, 5, 3, 11, 7]
    assert [len(r.result_fields) for r in rows] == [4, 2, 8, 5, 3]
    assert [(r.min_rows, r.max_rows) for r in rows] == [
        (1, 1),
        (1, 1),
        (1, 1),
        (0, 500),
        (27, 27),
    ]
    for r in rows:
        name = r.function_id.split(".")[1]
        expected = codec._call(name, (None,) * len(codec._SPECS[name][0]))
        assert api._same_statement(r.statement, expected.statement)
        assert "tenant_id" not in str(r.statement)
        assert r.decoder is api._private_decoder
        api.validate_registration(r)
    assert (
        api.require_read_registration(
            OpenPrimitiveSnapshotToken(U, U, SOURCE_MODEL_HASH),
            registry.FUNCTION_OPERATION_REGISTRY,
        ).operation_id
        == "STATS_PRIMITIVES:open_snapshot"
    )
    assert len(api.contract_candidates()) == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("function_id", "stats_api.unknown"),
        ("function_id", "public.save_primitive_source"),
        ("operation_id", "STATS_PRIMITIVES:unknown"),
        ("capability_id", "CAP:players:read"),
        ("input_fields", ()),
        ("result_fields", (("source_event_id", str),)),
        ("min_rows", True),
        ("max_rows", 2),
        ("nullable_results", ("wrong",)),
        ("decoder", lambda x: x),
        ("token_type", OpenPrimitiveSnapshotToken),
    ],
)
def test_registered_shape_mutations_are_rejected(field, value):
    """fn/token/cap/型/上限/decoderの同時自己一致を許さない。"""
    with pytest.raises(FunctionOperationError):
        replace(api.STATS_NATIVE_FUNCTION_OPERATIONS[0], **{field: value})


@pytest.mark.parametrize(
    "change", ["where", "arity", "type", "tenant", "namespace", "literal"]
)
def test_sql_mutations_are_rejected(change):
    """Caller SQL/追加bind/型/名前空間を有限5へ紛れ込ませない。"""
    r = api.STATS_NATIVE_FUNCTION_OPERATIONS[1]
    if change == "where":
        statement = r.statement.where(bindparam("extra", type_=Integer()) == 1)
    else:
        inputs, outputs = codec._SPECS["read_primitive_writer_state"]
        args = [bindparam(n, type_=t) for n, t in inputs]
        if change == "arity":
            args = args[:-1]
        elif change == "type":
            args[0] = bindparam(inputs[0][0], type_=Integer())
        elif change == "tenant":
            args.insert(0, bindparam("tenant_id", type_=Integer()))
        elif change == "literal":
            args[0] = bindparam(
                inputs[0][0], U, type_=inputs[0][1], literal_execute=True
            )
        table = Function(
            "read_primitive_writer_state",
            *args,
            packagenames=("public" if change == "namespace" else "stats_api",),
        ).table_valued(*(column(n, t) for n, t in outputs))
        statement = select(*table.c)
    with pytest.raises(FunctionOperationError):
        replace(r, statement=statement)


def _public_tokens():
    return [
        OpenPrimitiveSnapshotToken(U, U, SOURCE_MODEL_HASH),
        ReadPrimitivePageToken(
            U, U, U, 1, "a" * 64, SOURCE_MODEL_HASH, None, None, None, 1
        ),
        ReadPrimitiveTotalsToken(U, U, U, 1, "a" * 64, SOURCE_MODEL_HASH),
    ]


def test_public_values_and_private_metadata_never_prepare_generically():
    """Private getter無しのprepare/direct decoderは登録済型でも拒否する。"""
    for token in _public_tokens():
        with pytest.raises(FunctionOperationError):
            prepare_function_operation(token, U, registry.FUNCTION_OPERATION_REGISTRY)
    for r in api.STATS_NATIVE_FUNCTION_OPERATIONS[:2]:
        with pytest.raises(FunctionOperationError):
            r.token_type()
        forged = object.__new__(r.token_type)
        with pytest.raises(FunctionOperationError):
            prepare_function_operation(forged, U, registry.FUNCTION_OPERATION_REGISTRY)
        with pytest.raises(FunctionOperationError):
            decode_function_result(r, TenantOperationResult(()))
    value = SavePrimitiveSourceToken(U, U, U, SOURCE_MODEL_HASH, 0, None, "{}")
    assert type(value) not in registry.FUNCTION_OPERATION_REGISTRY
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(value, U, registry.FUNCTION_OPERATION_REGISTRY)


def test_registry_forgery_and_incompatible_call_do_not_become_authority():
    """同値clone/未登録/他statementをmetadata資格へ置換できない。"""
    op = OpenPrimitiveSnapshotToken(U, U, SOURCE_MODEL_HASH)
    spec = api.require_read_registration(op, registry.FUNCTION_OPERATION_REGISTRY)
    changed = dict(registry.FUNCTION_OPERATION_REGISTRY)
    changed[type(op)] = replace(spec)
    with pytest.raises(FunctionOperationError):
        api.require_read_registration(op, changed)
    call = codec.build_open_snapshot_call(U, U, SOURCE_MODEL_HASH)
    api.require_registered_call(spec, call, registry.FUNCTION_OPERATION_REGISTRY)
    with pytest.raises(FunctionOperationError):
        api.require_registered_call(
            spec,
            replace(call, function_id="public.unknown"),
            registry.FUNCTION_OPERATION_REGISTRY,
        )
    before = codec.build_writer_state_call(
        U, U, U, SOURCE_MODEL_HASH, binding_nonce=b"n" * 32
    )
    actual = api.require_private_writer_call(
        "STATS_PRIMITIVES:read_writer_state",
        before,
        registry.FUNCTION_OPERATION_REGISTRY,
    )
    assert actual is api.STATS_NATIVE_FUNCTION_OPERATIONS[1]
    for wrong in ["unknown", "STATS_PRIMITIVES:read_page"]:
        with pytest.raises(FunctionOperationError):
            api.require_private_writer_call(
                wrong, before, registry.FUNCTION_OPERATION_REGISTRY
            )


@pytest.mark.parametrize(
    "first",
    [
        "operation_registry",
        "transaction",
        "play_export_primitives",
        "stats_native_operations",
    ],
)
def test_real_cold_import_orders_and_same_runtime_type(first):
    """真正transaction型を置換せずimport循環だけを解消する。"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from pitchlog.repositories import {first}; "
            "from pitchlog.repositories import transaction, operation_registry, "
            "play_export_primitives; "
            "assert len(operation_registry.PRODUCT_FUNCTION_OPERATIONS)==43",
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_build_registry_does_not_adopt_post_construction_modified_stats():
    """frozen迂回変更もregistry構築時に再検査する。"""
    copied = replace(api.STATS_NATIVE_FUNCTION_OPERATIONS[0])
    object.__setattr__(copied, "capability_id", "CAP:players:read")
    with pytest.raises(FunctionOperationError):
        build_function_registry((copied,), frozenset())


@pytest.mark.parametrize(
    "mode",
    [
        "first-ball-play-v1",
        "ordinary-pitch-play-v1",
        "play-prefix-play-v2",
        "play-prefix-play-v3",
    ],
)
def test_private_metadata_tokens_direct_run_function_have_zero_sql(mode, monkeypatch):
    """正式metadata型の手作りobjectでも直接実行能力を持たない。"""
    from types import SimpleNamespace
    from typing import Any, cast

    from test_stats_native_flush import flush_rig

    from pitchlog.repositories import transaction

    # native fixtureはrunだけをrow doubleへ替えるため、実methodは先に保持する。
    actual_run = transaction._TenantTransaction.run
    generator = cast(Any, flush_rig).__wrapped__(
        SimpleNamespace(param=mode), monkeypatch
    )
    r = next(generator)
    try:
        for registration in api.STATS_NATIVE_FUNCTION_OPERATIONS[:2]:
            token = object.__new__(registration.token_type)
            with pytest.raises(RuntimeError):
                actual_run(r.handle, token)
            with pytest.raises(RuntimeError):
                r.handle.run_function(token)
        value = SavePrimitiveSourceToken(U, U, U, SOURCE_MODEL_HASH, 0, None, "{}")
        with pytest.raises(RuntimeError):
            actual_run(r.handle, value)
        with pytest.raises(RuntimeError):
            r.handle.run_function(value)
        assert r.calls == []
    finally:
        generator.close()
