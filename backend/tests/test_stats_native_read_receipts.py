"""実DBを使わず、RRRO私有状態とreaderのreceipt/一回資格だけを検査する。"""

from __future__ import annotations

import copy
from contextlib import ExitStack
from dataclasses import fields, replace
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.orm import Session
from test_authz_tenant_context import make_tenant_context

from pitchlog.repositories import play_export_primitives as read
from pitchlog.repositories import stats, transaction
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.stats.generated.receiver import METRIC_IDS, SOURCE_MODEL_HASH


@pytest.fixture
def world(monkeypatch):
    """実RRRO gateは保持し、DB開始/SQL実行の代用としない状態fixture。"""
    handles, calls, sessions = [], [], []
    state = SimpleNamespace(hook=None, consume=True, row_count=2, fail=False)

    def runtime():
        session = Session()
        sessions.append(session)
        return session, ExitStack()

    def handle():
        key = object()
        context = make_tenant_context(UUID(int=1))
        transaction._TRANSACTION_RUNTIMES[key] = runtime()
        value = transaction._TenantTransaction(
            context,
            key,
            context.tenant_id,
            context._integrity_proof,
            transaction._HANDLE_CREATION_TOKEN,
        )
        transaction._STATS_READ_HANDLES[key] = value
        handles.append((value, key))
        return value

    def dispatch(value, operation):
        # 後段dispatcherとの一回資格interfaceを試す。実SQL/RRRO開始ではない。
        if state.hook:
            state.hook(value, operation)
        if state.fail:
            raise RuntimeError("synthetic dispatch failure")
        if state.consume:
            qualified = read._qualified_stats_read_call(value, operation)
            assert qualified.operation is operation
            calls.append((value, qualified))
        if type(operation) is read.OpenPrimitiveSnapshotToken:
            return TenantOperationResult(
                (
                    (
                        UUID(int=2),
                        1,
                        "a" * 64,
                        SOURCE_MODEL_HASH,
                        1,
                        state.row_count,
                        "synthetic-same-transaction",
                        "current_open",
                    ),
                )
            )
        if type(operation) is read.ReadPrimitivePageToken:
            number = 1 if operation.after_d2 is None else operation.after_d2 + 1
            rows = (
                ()
                if number > state.row_count
                else (
                    (
                        METRIC_IDS[0],
                        "available",
                        Decimal(number),
                        number,
                        UUID(int=number),
                    ),
                )
            )
            return TenantOperationResult(rows)
        assert type(operation) is stats.ReadPrimitiveTotalsToken
        return TenantOperationResult(
            tuple((m, "available", Decimal(1)) for m in METRIC_IDS)
        )

    monkeypatch.setattr(transaction._TenantTransaction, "run_function", dispatch)
    world = SimpleNamespace(handle=handle, calls=calls, state=state, runtime=runtime)
    yield world
    for value, key in handles:
        value._expire()
        transaction._TRANSACTION_RUNTIMES.pop(key, None)
        read._READ_CALLS.pop(key, None)
    for session in sessions:
        session.close()


def _reader(world):
    """同じprivate gateを通る本物のhandle型とreaderを作る。"""
    handle = world.handle()
    return handle, read.ReadPlayExportPrimitives(handle, maximum_integer_chars=100)


def _scope():
    """値scope自体は資格ではない。"""
    return read.PrimitiveScope(UUID(int=10), UUID(int=11), SOURCE_MODEL_HASH)


def _clone(value):
    """constructorを迂回して全fieldを複製する敵対例。"""
    clone = object.__new__(type(value))
    for field in fields(value):
        object.__setattr__(clone, field.name, getattr(value, field.name))
    return clone


def test_real_reader_call_interface_pages_totals_and_finite_iteration(world):
    """同reader/receiptでだけ本物TX値を渡し、COUNTまで有限に読む。"""
    handle, reader = _reader(world)
    receipt = reader.open(_scope())
    assert world.calls[-1][1].transaction_id is None
    pages = list(reader.pages(receipt, page_size=1))
    assert len(pages) == 2
    assert [p.rows[0]["value"] for p in pages] == ["1", "2"]
    totals = stats.read_primitive_totals(reader, receipt)
    assert set(totals) == set(METRIC_IDS)
    assert all(v[1].transaction_id == receipt.transaction_id for v in world.calls[1:])
    assert all(v[0] is handle for v in world.calls)
    assert not read._READ_CALLS
    with pytest.raises(read.PrimitiveReadError):
        read._qualified_stats_read_call(handle, world.calls[-1][1].operation)


@pytest.mark.parametrize("consumer", ["page", "pages", "totals"])
@pytest.mark.parametrize("factory", [copy.copy, _clone])
def test_receipt_clone_or_new_cannot_borrow_genuine_values(world, consumer, factory):
    """同じowner/値/TX文字列でも実Openのidentityを複製できない。"""
    _, reader = _reader(world)
    receipt = reader.open(_scope())
    fake = factory(receipt)
    assert fake == receipt and fake is not receipt
    before = len(world.calls)
    with pytest.raises(read.PrimitiveReadError):
        if consumer == "page":
            reader.read_page(fake)
        elif consumer == "pages":
            list(reader.pages(fake))
        else:
            stats.read_primitive_totals(reader, fake)
    assert len(world.calls) == before


def test_receipt_constructor_cannot_issue_with_owner_private_key(world):
    """ownerのkeyを知っても公開constructorから成功receiptを作れない。"""
    _, reader = _reader(world)
    with pytest.raises(read.PrimitiveReadError):
        read.PrimitiveSnapshot(
            _owner=reader,
            _key=reader._key,
            scope=_scope(),
            row=(
                UUID(int=2),
                1,
                "a" * 64,
                SOURCE_MODEL_HASH,
                1,
                2,
                "synthetic-same-transaction",
                "current_open",
            ),
        )


@pytest.mark.parametrize("same_handle", [True, False])
def test_receipt_is_not_transferable_to_same_scope_other_reader(world, same_handle):
    """同scope/TX文字列でも同readerと実handleを置き換えられない。"""
    handle, reader = _reader(world)
    receipt = reader.open(_scope())
    other = read.ReadPlayExportPrimitives(
        handle if same_handle else world.handle(), maximum_integer_chars=100
    )
    second = other.open(_scope())
    assert second.transaction_id == receipt.transaction_id
    for action in [
        lambda: other.read_page(receipt),
        lambda: stats.read_primitive_totals(other, receipt),
    ]:
        with pytest.raises(read.PrimitiveReadError):
            action()


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 2),
        ("revision", True),
        ("transaction_id", "forged"),
        ("row_count", 100),
        ("source_set_sha256", "b" * 64),
        ("fact_version_id", UUID(int=99)),
        ("completion_state", "confirmed_ended"),
    ],
)
def test_mutated_genuine_receipt_values_are_rejected(world, field, value):
    """frozen迂回書換えも発行時の完全値と照合する。"""
    _, reader = _reader(world)
    receipt = reader.open(_scope())
    object.__setattr__(receipt, field, value)
    with pytest.raises(read.PrimitiveReadError):
        reader.read_page(receipt)
    with pytest.raises(read.PrimitiveReadError):
        stats.read_primitive_totals(reader, receipt)


@pytest.mark.parametrize("variant", ["free", "clone", "other-receipt", "mutated"])
def test_cursor_requires_page_identity_and_original_receipt(world, variant):
    """binding値を真似たcursorや別receipt/位置の流用をSQL前に拒否する。"""
    _, reader = _reader(world)
    receipt = reader.open(_scope())
    cursor = reader.read_page(receipt, page_size=1).next_cursor
    assert cursor is not None
    if variant == "free":
        cursor = read.PrimitiveCursor(
            cursor.d2, cursor.source_event_id, cursor.metric_id, _binding=receipt
        )
    elif variant == "clone":
        cursor = _clone(cursor)
    elif variant == "other-receipt":
        receipt = reader.open(_scope())
    else:
        object.__setattr__(cursor, "d2", 0)
    before = len(world.calls)
    with pytest.raises(read.PrimitiveReadError):
        reader.read_page(receipt, cursor=cursor)
    assert len(world.calls) == before


@pytest.mark.parametrize(
    "operation",
    [
        read.OpenPrimitiveSnapshotToken(UUID(int=10), UUID(int=11), SOURCE_MODEL_HASH),
        read.ReadPrimitivePageToken(
            UUID(int=10),
            UUID(int=11),
            UUID(int=2),
            1,
            "a" * 64,
            SOURCE_MODEL_HASH,
            None,
            None,
            None,
            1,
        ),
        stats.ReadPrimitiveTotalsToken(
            UUID(int=10), UUID(int=11), UUID(int=2), 1, "a" * 64, SOURCE_MODEL_HASH
        ),
    ],
)
def test_direct_run_and_run_function_cannot_issue_private_call(world, operation):
    """値tokenの直接実行は同じRRRO handleでもSQL前に拒否される。"""
    handle, _ = _reader(world)
    for execute in (handle.run, handle.run_function):
        with pytest.raises(read.PrimitiveReadError):
            execute(operation)
    assert world.calls == []


def test_getter_consumes_once_and_rejects_other_token_or_handle(world):
    """実呼出し内でもclone/別handle/二重取得で一回資格を盗めない。"""
    handle, reader = _reader(world)
    other = world.handle()
    seen = []

    def inspect(value, operation):
        for wrong_handle, wrong_op in [(value, replace(operation)), (other, operation)]:
            with pytest.raises(read.PrimitiveReadError):
                read._qualified_stats_read_call(wrong_handle, wrong_op)
        qualified = read._qualified_stats_read_call(value, operation)
        assert qualified.operation is operation
        with pytest.raises(read.PrimitiveReadError):
            read._qualified_stats_read_call(value, operation)
        seen.append(qualified)

    world.state.hook = inspect
    world.state.consume = False
    receipt = reader.open(_scope())
    reader.read_page(receipt)
    stats.read_primitive_totals(reader, receipt)
    assert len(seen) == 3 and seen[0].transaction_id is None
    assert all(c.transaction_id == receipt.transaction_id for c in seen[1:])
    assert handle._state_key not in read._READ_CALLS


@pytest.mark.parametrize("variant", ["expired", "no-marker", "runtime-replaced"])
def test_scope_expiry_and_runtime_identity_are_preserved(world, variant):
    """真正root gateの失効・marker・同state-key別runtimeを成功へ補わない。"""
    handle, reader = _reader(world)
    receipt = reader.open(_scope())
    key = handle._state_key
    if variant == "expired":
        handle._expire()
    elif variant == "no-marker":
        transaction._STATS_READ_HANDLES.pop(key)
    else:
        transaction._TRANSACTION_RUNTIMES[key] = world.runtime()
    with pytest.raises(read.PrimitiveReadError):
        reader.read_page(receipt)


def test_missing_consume_and_dispatch_failure_leave_no_qualification(world):
    """dispatcher未接続の値成功や例外後の資格残留を許可しない。"""
    _, reader = _reader(world)
    world.state.consume = False
    with pytest.raises(read.PrimitiveReadError):
        reader.open(_scope())
    assert not read._READ_CALLS
    world.state.fail = True
    with pytest.raises(RuntimeError, match="synthetic dispatch failure"):
        reader.open(_scope())
    assert not read._READ_CALLS


def test_reader_new_or_clone_is_not_a_registered_reader(world):
    """実型の__new__/slot複製だけではreaderを発行しない。"""
    _, reader = _reader(world)
    fake = object.__new__(read.ReadPlayExportPrimitives)
    for name in ("_handle", "_state_key", "_key", "_maximum_integer_chars"):
        setattr(fake, name, getattr(reader, name))
    with pytest.raises(read.PrimitiveReadError):
        fake.open(_scope())


def test_empty_receipt_is_finite_and_decoding_has_no_authority(world):
    """空COUNTは呼出しを増やさず、低層decodeだけではcursor資格を作れない。"""
    _, reader = _reader(world)
    world.state.row_count = 0
    receipt = reader.open(_scope())
    assert list(reader.pages(receipt)) == []
    decoded = read._decode_page(
        ((METRIC_IDS[0], "available", 1, 1, UUID(int=1)),),
        None,
        1,
        100,
        binding=receipt,
    )
    with pytest.raises(read.PrimitiveReadError):
        reader.read_page(receipt, cursor=decoded.next_cursor)


def test_uninitialized_or_copied_handle_cannot_borrow_rrro_marker(world):
    """実型のhandleを複製してもrootのmarker identityとは一致しない。"""
    genuine = world.handle()
    for populate in (False, True):
        fake = object.__new__(transaction._TenantTransaction)
        if populate:
            for name in transaction._TenantTransaction.__slots__:
                setattr(fake, name, getattr(genuine, name))
        with pytest.raises(read.PrimitiveReadError):
            read.ReadPlayExportPrimitives(fake, maximum_integer_chars=100)
        with pytest.raises(read.PrimitiveReadError):
            read._qualified_stats_read_call(fake, object())


@pytest.mark.parametrize("kind", ["open", "page", "totals"])
def test_command_values_cannot_change_during_qualified_call(world, kind):
    """元tokenのidentityが同じでも受付後の値書換えを拒否する。"""
    _, reader = _reader(world)
    receipt = None if kind == "open" else reader.open(_scope())

    def mutate(handle, operation):
        object.__setattr__(operation, "game_id", UUID(int=99))

    world.state.hook = mutate
    before = len(world.calls)
    with pytest.raises(read.PrimitiveReadError):
        if kind == "open":
            reader.open(_scope())
        elif kind == "page":
            reader.read_page(receipt)
        else:
            stats.read_primitive_totals(reader, receipt)
    assert len(world.calls) == before
    assert not read._READ_CALLS


def test_scope_mutation_during_open_cannot_relabel_issued_receipt(world):
    """実Openが読んだscopeと発行するreceiptの三値を分離できない。"""
    _, reader = _reader(world)
    scope = _scope()

    def mutate(handle, operation):
        object.__setattr__(scope, "player_id", UUID(int=99))

    world.state.hook = mutate
    with pytest.raises(read.PrimitiveReadError):
        reader.open(scope)
    assert not read._reader_state(reader).receipts


def test_reentrant_read_cannot_borrow_existing_call(world):
    """同handleの別readerからも実呼出し中へ再入して資格を増やせない。"""
    handle, reader = _reader(world)
    other = read.ReadPlayExportPrimitives(handle, maximum_integer_chars=100)

    def nested(value, operation):
        with pytest.raises(read.PrimitiveReadError):
            other.open(_scope())

    world.state.hook = nested
    reader.open(_scope())
    assert len(world.calls) == 1


@pytest.mark.parametrize("target", ["scope", "version", "cursor"])
def test_uuid_object_mutation_cannot_change_captured_identity_values(world, target):
    """UUID参照自体を共有しても内部整数の迂回書換えを検出する。"""
    _, reader = _reader(world)
    receipt = reader.open(_scope())
    cursor = None
    if target == "scope":
        value = receipt.scope.game_id
    elif target == "version":
        value = receipt.fact_version_id
    else:
        cursor = reader.read_page(receipt, page_size=1).next_cursor
        value = cursor.source_event_id
    object.__setattr__(value, "int", 99)
    before = len(world.calls)
    with pytest.raises(read.PrimitiveReadError):
        reader.read_page(receipt, cursor=cursor)
    assert len(world.calls) == before


@pytest.mark.parametrize("kind", ["page", "totals"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("game_id", UUID(int=99)),
        ("player_id", UUID(int=99)),
        ("fact_version_id", UUID(int=99)),
        ("revision", 99),
        ("source_set_sha256", "b" * 64),
        ("model_sha256", "sha256:" + "b" * 64),
    ],
)
def test_private_call_cannot_pair_arbitrary_values_with_genuine_receipt(
    world, kind, field, value
):
    """私有contextへも真正receiptと異なる値の命令を組み合わせられない。"""
    handle, reader = _reader(world)
    receipt = reader.open(_scope())
    args = (
        receipt.scope.game_id,
        receipt.scope.player_id,
        receipt.fact_version_id,
        receipt.revision,
        receipt.source_set_sha256,
        receipt.scope.model_sha256,
    )
    operation = (
        read.ReadPrimitivePageToken(*args, None, None, None, 1)
        if kind == "page"
        else stats.ReadPrimitiveTotalsToken(*args)
    )
    operation = replace(operation, **{field: value})
    with pytest.raises(read.PrimitiveReadError):
        with read._read_call(reader, operation, receipt=receipt):
            handle.run_function(operation)
    assert len(world.calls) == 1
    assert not read._READ_CALLS
