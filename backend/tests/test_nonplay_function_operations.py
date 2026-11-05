"""取消6の閉metadata/単一ABI/decoder対向。DB資格の代用ではない。"""

from dataclasses import replace
from types import MappingProxyType
from uuid import UUID

import pytest
from sqlalchemy import literal, select
from sqlalchemy.dialects import postgresql
from test_stats_native_undo import decoder_receipt

from pitchlog.repositories import nonplay_function_operations as api
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    prepare_function_operation,
)
from pitchlog.repositories.operation_registry import FUNCTION_OPERATION_REGISTRY
from pitchlog.repositories.tokens import TenantOperationResult


def test_exact_six_canonical_registry_and_real_renderer_abi():
    """旧registryの実objectを保持し、新6は同renderer ABIだけを指す。"""
    api._verify_renderer()
    assert len(api.NONPLAY_FUNCTION_OPERATIONS) == 6
    for registration in api.NONPLAY_FUNCTION_OPERATIONS:
        assert FUNCTION_OPERATION_REGISTRY[registration.token_type] is registration
        api.validate_registration(registration)
        sql = str(registration.statement.compile(dialect=postgresql.dialect()))
        assert registration.function_id + "(" in sql
        assert registration.min_rows in (0, 1)
        assert registration.max_rows in (1, 100)
    contracts = api.contract_candidates()
    assert sum(x["metadata_only_token"] for x in contracts) == 4
    assert all(x["actual_operation_token"] for x in contracts)


@pytest.mark.parametrize("registration", api.NONPLAY_FUNCTION_OPERATIONS)
def test_no_constructor_or_generic_prepare_gives_sql_qualification(registration):
    """metadata型/rights型は自由構築不可、object.newもgeneric経路では拒否する。"""
    with pytest.raises(FunctionOperationError):
        registration.token_type()
    forged = object.__new__(registration.token_type)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(forged, UUID(int=1), FUNCTION_OPERATION_REGISTRY)


@pytest.mark.parametrize(
    "mutation",
    [
        "function",
        "capability",
        "operation",
        "sql",
        "inputs",
        "outputs",
        "decoder",
        "min-bool",
        "max",
        "nullable",
        "nonempty",
    ],
)
def test_registration_mutants_are_rejected_before_any_sql(mutation):
    """余剰SQL/未知ID/型/行数/decoder差を登録時に拒否する。"""
    original = api.NONPLAY_FUNCTION_OPERATIONS[2]
    changes = {
        "function": {"function_id": "sync_right_api.free_sql"},
        "capability": {"capability_id": "CAP:sync_nonplay:other"},
        "operation": {"operation_id": "SYNC_NONPLAY:other"},
        "sql": {"statement": select(literal(True))},
        "inputs": {"input_fields": tuple(reversed(original.input_fields))},
        "outputs": {"result_fields": (("record_json", int),)},
        "decoder": {"decoder": lambda result: result},
        "min-bool": {"min_rows": True},
        "max": {"max_rows": 101},
        "nullable": {"nullable_results": ("record_json",)},
        "nonempty": {"nonempty_inputs": ()},
    }
    with pytest.raises(FunctionOperationError):
        replace(original, **changes[mutation])


def test_changed_renderer_abi_does_not_validate_cached_metadata(monkeypatch):
    """本文producerのABI差替えをmetadataの自己整合で隠さない。"""
    original = api.candidate_function_bodies
    bodies = original()
    bodies["lock_nonplay_checkpoint"] = bodies["lock_nonplay_checkpoint"].replace(
        "p_request_json text", "p_request_json bigint", 1
    )
    monkeypatch.setattr(api, "candidate_function_bodies", lambda: bodies)
    with pytest.raises(FunctionOperationError):
        api.validate_registration(api.NONPLAY_FUNCTION_OPERATIONS[2])


@pytest.mark.parametrize(
    "index,rows",
    [
        (0, ((True,),)),
        (0, ((False,),)),
        (1, ((True, False),)),
        (2, (("{}",),)),
        (3, ()),
        (3, tuple(("{}",) for _ in range(100))),
        (4, ((True,),)),
        (5, ((decoder_receipt(),),)),
    ],
)
def test_closed_positive_decoders(index, rows):
    """read空pageとrights偽は正確に保持し、writeだけはTrue1行を要求する。"""
    assert api._decode(
        api.NONPLAY_FUNCTION_OPERATIONS[index], rows
    ) == TenantOperationResult(rows)


@pytest.mark.parametrize(
    "index,rows",
    [
        (0, ((1,),)),
        (1, ((True, 1),)),
        (2, ()),
        (2, ((None,),)),
        (2, (("{}", "extra"),)),
        (3, tuple(("{}",) for _ in range(101))),
        (4, ((1,),)),
        (4, ((False,),)),
        (5, ((True,),)),
        (5, ((False,),)),
        (5, (("{}",),)),
        (5, ((True,), (True,))),
        (2, [["{}"]]),
    ],
)
def test_decoder_does_not_repair_types_counts_or_false_write(index, rows):
    """型混同/超過/欠測/Falseを成功へ補完しない。"""
    with pytest.raises(FunctionOperationError):
        api._decode(api.NONPLAY_FUNCTION_OPERATIONS[index], rows)


def test_equal_but_noncanonical_registration_does_not_qualify_private_call():
    """同値別objectのregistry差替えを拒否する。"""
    from pitchlog.repositories.nonplay_prefix import _LockNonplayCheckpoint

    original = api.NONPLAY_FUNCTION_OPERATIONS[2]
    clone = replace(original)
    registry = dict(FUNCTION_OPERATION_REGISTRY)
    registry[original.token_type] = clone
    with pytest.raises(FunctionOperationError):
        api._registered(_LockNonplayCheckpoint("{}"), MappingProxyType(registry))
