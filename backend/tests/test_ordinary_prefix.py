"""真正資格を生成しないcheckpoint閉値と有限SQLを検査する。"""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from pitchlog.authz.ordinary_prefix_sql import candidate_read_function_bodies
from pitchlog.repositories.function_operations import (
    FunctionOperationError,
    build_function_registry,
    prepare_function_operation,
)
from pitchlog.repositories.ordinary_prefix import (
    OrdinaryPrefixError,
    read_checkpoint_document,
)
from pitchlog.repositories.ordinary_prefix_operations import (
    ORDINARY_PREFIX_OPERATIONS,
    OrdinaryCheckpointLockToken,
    OrdinaryCheckpointReadToken,
    OrdinaryHistoryPageToken,
)
from pitchlog.sync.idempotency import source_fingerprint

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = json.loads(
    (
        ROOT
        / "contracts/state-transition/ordinary37_persistence_boundary_candidate_v1.json"
    ).read_text()
)


def _checkpoint():
    """採用済比較例の静的原本を複製する。実DB原本とは主張しない。"""
    return copy.deepcopy(CANDIDATE["examples"]["admission0"]["checkpoint"])


def test_checkpoint_all_values_roundtrip():
    """全欄とdigestを保持し、型成功をDB資格にはしない。"""
    raw = _checkpoint()
    value = read_checkpoint_document(json.dumps(raw))
    assert value.model_dump(mode="json", by_alias=True, exclude_unset=True) == raw


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "revision",
        "history_version",
        "wire_d4",
        "after",
        "rules",
        "content_digest",
    ],
)
def test_missing_or_changed_checkpoint_field_is_closed(field):
    """欠落・変更の隠蔽を拒否する。"""
    raw = _checkpoint()
    del raw[field]
    with pytest.raises(OrdinaryPrefixError):
        read_checkpoint_document(json.dumps(raw))


@pytest.mark.parametrize(
    "value", ["1\n", "1\r\n", "01", "-1", "9223372036854775808", 1, True]
)
def test_checkpoint_position_type_and_bounds(value):
    """型/末尾改行/bigint上限を補修しない。"""
    raw = _checkpoint()
    raw["revision"] = value
    raw["content_digest"] = source_fingerprint(
        {k: v for k, v in raw.items() if k != "content_digest"}
    )
    with pytest.raises(OrdinaryPrefixError):
        read_checkpoint_document(json.dumps(raw))


def test_checkpoint_unknown_field_duplicate_and_digest_corruption():
    """未知key/重複key/原内容の改竄を閉じる。"""
    raw = _checkpoint()
    for mutated in [{**raw, "unknown": True}, {**raw, "revision": "2"}]:
        with pytest.raises(OrdinaryPrefixError):
            read_checkpoint_document(json.dumps(mutated))
    with pytest.raises(OrdinaryPrefixError):
        read_checkpoint_document('{"version":"1",' + json.dumps(raw)[1:])


@pytest.mark.parametrize("limit", [1, 100])
def test_keyset_has_exact_scope_order_and_sql_limit_plus_one(limit):
    """SQL段でtenant/版/水位を絞り、app表直接権限を作らない。"""
    registry = build_function_registry(
        ORDINARY_PREFIX_OPERATIONS, frozenset(), frozenset()
    )
    token = OrdinaryHistoryPageToken(
        UUID(int=1), 2, 3, UUID(int=2), 4, 100, 50, 51, UUID(int=4), limit
    )
    operation, params = prepare_function_operation(token, UUID(int=9), registry)
    assert params == {
        "tenant_id": UUID(int=9),
        "game_id": UUID(int=1),
        "generation": 2,
        "history_version": 3,
        "checkpoint_id": UUID(int=2),
        "checkpoint_revision": 4,
        "upper_watermark": 100,
        "after_d1": 50,
        "after_d2": 51,
        "after_id": UUID(int=4),
        "page_size": limit,
    }
    sql = candidate_read_function_bodies()["read_ordinary_history_page"]
    for clause in [
        "x.tenant_id=p_tenant_id",
        "x.game_id=p_game_id",
        "x.internal_generation=p_generation",
        "x.history_version=p_history_version",
        "x.d1<=p_upper_watermark",
        "ORDER BY x.d1,x.d2,x.source_event_id",
        "LIMIT p_page_size+1",
        "FOR SHARE",
    ]:
        assert clause in sql
    assert "OFFSET" not in sql and operation.max_rows == 101


@pytest.mark.parametrize("limit", [0, 101, True, "1"])
def test_page_limit_rejects_bad_values(limit):
    """boolや範囲外を有効上限に補完しない。"""
    with pytest.raises(ValueError):
        OrdinaryHistoryPageToken(
            UUID(int=1), 1, 1, UUID(int=2), 1, 0, 0, 0, UUID(int=0), limit
        )


def test_checkpoint_read_and_writer_lock_are_separate_exact_operations():
    """readonlyにはnonceを持たせず、lockは実writer関数へ閉じる。"""
    registry = build_function_registry(
        ORDINARY_PREFIX_OPERATIONS, frozenset(), frozenset()
    )
    read = OrdinaryCheckpointReadToken(UUID(int=1), 1)
    lock = OrdinaryCheckpointLockToken(
        UUID(int=2), UUID(int=3), b"x" * 32, UUID(int=4), UUID(int=1), 1
    )
    read_spec, read_params = prepare_function_operation(read, UUID(int=9), registry)
    lock_spec, lock_params = prepare_function_operation(lock, UUID(int=9), registry)
    assert read_spec.function_id == "sync_right_api.read_ordinary_checkpoint"
    assert lock_spec.function_id == "sync_right_api.lock_ordinary_checkpoint"
    assert read_params == {
        "tenant_id": UUID(int=9),
        "game_id": UUID(int=1),
        "generation": 1,
    }
    assert lock_params == {
        "tenant_id": UUID(int=9),
        "attempt_id": UUID(int=2),
        "phase_id": UUID(int=3),
        "binding_nonce": b"x" * 32,
        "device_id": UUID(int=4),
        "game_id": UUID(int=1),
        "generation": 1,
    }
    sql = candidate_read_function_bodies()
    assert "assert_writer_binding" not in sql["read_ordinary_checkpoint"]
    assert "assert_writer_binding" in sql["lock_ordinary_checkpoint"]
    assert "FOR UPDATE OF c" in sql["lock_ordinary_checkpoint"]
    assert "FOR UPDATE" not in sql["read_ordinary_checkpoint"]
    assert read_spec.min_rows == lock_spec.min_rows == 0
    assert read_spec.max_rows == lock_spec.max_rows == 1


def test_forced_page_size_mutation_is_rejected_at_execution_boundary():
    """constructor後の強制変更も有限関数の実行直前で拒否する。"""
    registry = build_function_registry(
        ORDINARY_PREFIX_OPERATIONS, frozenset(), frozenset()
    )
    token = OrdinaryHistoryPageToken(
        UUID(int=1), 1, 1, UUID(int=2), 1, 0, 0, 0, UUID(int=0), 1
    )
    object.__setattr__(token, "page_size", 101)
    with pytest.raises(FunctionOperationError):
        prepare_function_operation(token, UUID(int=9), registry)
