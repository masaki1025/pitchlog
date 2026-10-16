"""D5 の内部分類と入力原本の指紋を DB 不要で検査する。"""

from __future__ import annotations

from types import MappingProxyType
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from pitchlog.db.sync_protocol.models import IdempotencyLedger
from pitchlog.repositories.tokens import ImmutableValue, TenantOperationResult
from pitchlog.repositories.transaction import _TenantTransaction
from pitchlog.sync.idempotency import (
    classify_request_d5,
    classify_result,
    event_source_fingerprint,
    insert_result_or_recheck,
    source_fingerprint,
)
from pitchlog.sync.model import SyncEvent, SyncRequest
from pitchlog.sync.tokens import (
    IdempotencyLedgerInsertToken,
    IdempotencyLedgerReadToken,
)


def _saved_result(fingerprint: str) -> TenantOperationResult:
    """正本の列順を使った不変な台帳 read 結果を作る。"""
    values: dict[str, object] = {
        "tenant_id": uuid4(),
        "d5": uuid4(),
        "kind": "accepted",
        "source_fingerprint": fingerprint,
        "result": MappingProxyType({"state": "受理"}),
        "reason": None,
        "retired_at": None,
        "import_batch_id": None,
    }
    return TenantOperationResult(
        (
            tuple(
                cast(ImmutableValue, values[name])
                for name in IdempotencyLedger.__table__.c.keys()
            ),
        )
    )


def test_d5_three_internal_candidates_and_path_specific_conflict() -> None:
    """同じ D5 の内部候補 3 種と B3b / B13 の分岐を固定する。"""
    fingerprint = source_fingerprint({"d5": "a", "payload": {"a": 1}})
    assert (
        classify_result(TenantOperationResult(()), fingerprint, "P1").kind == "unused"
    )
    replay = classify_result(_saved_result(fingerprint), fingerprint, "P1")
    assert replay.kind == "stored_result"
    assert replay.stored is not None
    assert replay.stored.result["state"] == "受理"
    assert classify_result(_saved_result(fingerprint), "different", "P1").boundary == (
        "B3b"
    )
    assert classify_result(_saved_result(fingerprint), "different", "P3").boundary == (
        "B13"
    )


def test_source_fingerprint_covers_all_input_fields_and_normalizes_key_order() -> None:
    """JSON のキー順だけは同一視し、値・欠落・null は区別する。"""
    first = source_fingerprint({"payload": {"b": 2, "a": [1, None]}, "d5": "d"})
    assert first == source_fingerprint({"d5": "d", "payload": {"a": [1, None], "b": 2}})
    assert first != source_fingerprint({"d5": "d", "payload": {"a": [1, None]}})
    assert first != source_fingerprint({"d5": "d", "payload": {"a": [1, None], "b": 3}})
    assert source_fingerprint({"v5": None}) != source_fingerprint({})
    with pytest.raises(ValueError):
        source_fingerprint({"bad": float("nan")})


def test_event_source_fingerprint_preserves_stage_values_without_derived_reason() -> (
    None
):
    """イベントの全入力フィールドを原本として扱い、欠落と null を分ける。"""
    d5, game = str(uuid4()), str(uuid4())
    event = SyncEvent(d5, game, 1, "device", v5={"kind": "pitch"})
    same = SyncEvent(d5, game, 1, "device", v5={"kind": "pitch"})
    null_value = SyncEvent(d5, game, 1, "device", v5={"kind": "pitch"}, v8=None)
    assert event_source_fingerprint(event) == event_source_fingerprint(same)
    assert event_source_fingerprint(event) != event_source_fingerprint(null_value)


def test_request_classification_reads_all_candidates_before_application() -> None:
    """混在バッチの内部候補を要求順で読み、書き込みや A5 確定をしない。"""
    game = str(uuid4())
    events = (
        SyncEvent(str(uuid4()), game, 2, "device", v5="first"),
        SyncEvent(str(uuid4()), game, 1, "device", v5="second"),
        SyncEvent(str(uuid4()), game, 3, "device", v5="third"),
    )
    request = SyncRequest("P1", game, events, d4="device")
    rows = {
        events[0].d5: _saved_result(event_source_fingerprint(events[0])),
        events[1].d5: _saved_result("another-original"),
    }

    class _ReadHandle:
        """D5 台帳の read token だけを受ける。"""

        def __init__(self) -> None:
            """読み取った D5 を実行ごとに保持する。"""
            self.observed: list[str] = []

        def run(self, operation: object) -> TenantOperationResult:
            """要求のイベント順と read 専用を記録する。"""
            assert type(operation) is IdempotencyLedgerReadToken
            self.observed.append(str(operation.d5))
            return rows.get(str(operation.d5), TenantOperationResult(()))

    handle = _ReadHandle()
    candidates = classify_request_d5(cast(_TenantTransaction, handle), request)
    assert handle.observed == [event.d5 for event in events]
    assert [candidate.kind for candidate in candidates] == [
        "stored_result",
        "conflict",
        "unused",
    ]


class _ConstraintError(Exception):
    """一意制約の診断情報だけを持つテスト用 DB 例外。"""

    sqlstate = "23505"

    def __init__(self, constraint_name: str) -> None:
        """制約名を psycopg の診断属性と同じ形にする。"""
        self.diag = type("Diagnostic", (), {"constraint_name": constraint_name})()


class _ConflictHandle:
    """SAVEPOINT 失敗後に読み取りが続けられる契約を模擬する。"""

    def __init__(self, fingerprint: str, constraint_name: str) -> None:
        """先着の原本と、失敗した制約を固定する。"""
        self.fingerprint = fingerprint
        self.constraint_name = constraint_name
        self.read_count = 0

    def run(self, _operation: object) -> TenantOperationResult:
        """SAVEPOINT を戻した後の再照合だけを記録する。"""
        self.read_count += 1
        return _saved_result(self.fingerprint)

    def run_in_savepoint(self, _operation: object) -> TenantOperationResult:
        """台帳の一意制約違反を送出する。"""
        raise IntegrityError("INSERT", {}, _ConstraintError(self.constraint_name))


def test_only_d5_primary_key_conflict_is_rechecked() -> None:
    """D5 以外の制約違反は吸収せず、D5 競合は保存原本を照合し直す。"""
    d5 = uuid4()
    token = IdempotencyLedgerInsertToken(d5, "accepted", "same", "{}")
    handle = _ConflictHandle("same", "pk_idempotency_ledger")
    replay = insert_result_or_recheck(cast(_TenantTransaction, handle), token, "P1")
    assert replay is not None and replay.kind == "stored_result"
    assert handle.read_count == 1

    handle = _ConflictHandle("first", "pk_idempotency_ledger")
    collision = insert_result_or_recheck(cast(_TenantTransaction, handle), token, "P3")
    assert collision is not None and collision.boundary == "B13"

    handle = _ConflictHandle("same", "uq_idempotency_ledger_kind")
    replay = insert_result_or_recheck(cast(_TenantTransaction, handle), token, "P1")
    assert replay is not None and replay.kind == "stored_result"

    handle = _ConflictHandle("same", "some_other_unique_constraint")
    with pytest.raises(IntegrityError):
        insert_result_or_recheck(cast(_TenantTransaction, handle), token, "P1")
    assert handle.read_count == 0
