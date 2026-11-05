"""歴史初球のopaque貸与と実唯一hostを照合する。実DB/認可成功ではない。"""

import json
from dataclasses import FrozenInstanceError
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, Uuid
from test_recorded_snapshot import recorded_bundle as recorded_bundle

from pitchlog.domainrt.first_ball_projection import _canonical_json
from pitchlog.domainrt.host import NodeDomainHost
from pitchlog.repositories import nonplay_prefix as prefix
from pitchlog.repositories import recorded_snapshot as api
from pitchlog.repositories import transaction as tx
from pitchlog.repositories.tokens import TenantOperationResult
from pitchlog.sync.control_provider.writer_binding_models import FirstBallWriteAdmission
from pitchlog.sync.model import SyncEvent
from pitchlog.sync.source_binding import _E1CoreSource


def wire(value):
    """DB型のfixtureを既JSONB表現へ機械変換する。"""
    if type(value) is UUID:
        return str(value)
    if type(value) is datetime:
        return value.isoformat()
    if type(value) is bytes:
        return "\\x" + value.hex()
    if type(value) is dict:
        return {k: wire(v) for k, v in value.items()}
    if type(value) in {list, tuple}:
        return [wire(v) for v in value]
    return value


@pytest.fixture
def historical(recorded_bundle, monkeypatch):
    """開始readとloan issuerだけがpure double、数学は真正host。"""
    b = recorded_bundle
    h = b.handle
    event = SyncEvent(str(uuid4()), str(b.game_id), 3, "own-current-generation", "undo")
    source = object.__new__(_E1CoreSource)
    source.scope = h
    source.event = event
    monkeypatch.setattr(
        _E1CoreSource,
        "read",
        lambda s, a, e: (
            object()
            if s is source and a is h and e is event
            else (_ for _ in ()).throw(RuntimeError("wrong source"))
        ),
    )
    admission = {}
    for c in FirstBallWriteAdmission.__table__.c:
        admission[c.name] = (
            None
            if c.nullable
            else 1
            if isinstance(c.type, (BigInteger, Integer))
            else False
            if isinstance(c.type, Boolean)
            else str(uuid4())
            if isinstance(c.type, Uuid)
            else datetime.fromisoformat("2026-11-06T00:00:00+00:00").isoformat()
            if isinstance(c.type, DateTime)
            else "\\x" + "78" * 32
            if isinstance(c.type, LargeBinary)
            else "fixture"
        )
    admission.update(
        tenant_id=str(b.tenant),
        game_id=str(b.game_id),
        state="consumed",
        d5=str(b.d5),
        source_event_id=str(b.event_id),
        play_row_id=str(b.row_id),
        internal_generation=b.generation["generation"],
        event_fingerprint=b.ledger["source_fingerprint"],
        wire_d4="original-firstball-generation",
        consumed_at="2026-11-06T00:00:00+00:00",
    )
    original_run_function = tx._TenantTransaction.run_function
    origin = str(uuid4())
    from pitchlog.sync.terminal_pitch_tokens import LineupStartedOriginReadToken

    def run_function(handle, token):
        if type(token) is LineupStartedOriginReadToken:
            assert (
                handle is h
                and token.game_id == b.game_id
                and token.generation == b.generation["generation"]
            )
            return TenantOperationResult(
                (
                    (
                        _canonical_json(
                            {"start_request_id": origin, "device_id": str(uuid4())}
                        ),
                    ),
                )
            )
        return original_run_function(handle, token)

    monkeypatch.setattr(tx._TenantTransaction, "run_function", run_function)
    value = SimpleNamespace(
        bundle=b,
        handle=h,
        event=event,
        source=source,
        admission=admission,
        origin=origin,
        runners=[],
    )

    def issue():
        evidence = prefix.HistoricalFirstBallEvidence(
            b.event_id,
            b.generation["generation"],
            1,
            *(
                _canonical_json(wire(v))
                for v in (
                    b.events[0],
                    b.ledger,
                    b.slots[0],
                    admission,
                    b.plays[0],
                    value.runners,
                )
            ),
        )
        runtime = tx._TRANSACTION_RUNTIMES[h._state_key]
        lifetime = h._writer_lifetime()
        loan = [h, event, source, lifetime, runtime, evidence, False]
        prefix._HISTORICAL_LOANS[h._state_key] = loan
        return loan

    value.issue = issue
    value.reference = dict(
        source_event_id=b.event_id, generation=b.generation["generation"], d1=1
    )
    with tx._sync_apply_active():
        try:
            yield value
        finally:
            prefix._HISTORICAL_LOANS.pop(h._state_key, None)


def read(value):
    """実getterのone-useを消費する新private入口だけを呼ぶ。"""
    return api._read_nonplay_first_ball_frame(
        value.handle, value.event, value.source, **value.reference
    )


def test_actual_host_and_real_one_use_getter_complete_frame(historical, monkeypatch):
    """現在D3=3でも歴史P1を再評価し、原diff/指紋/全41列を保持する。"""
    h = historical
    h.bundle.generation.update(confirmed_watermark=3, applied_prefix=3)
    loan = h.issue()
    calls = []
    original = NodeDomainHost.call

    def call(host, operation, raw):
        calls.append(operation)
        return original(host, operation, raw)

    monkeypatch.setattr(NodeDomainHost, "call", call)
    result = read(h)
    assert type(result) is api.HistoricalFirstBallFrame and loan[6] is True
    assert calls == [
        "validateInitialGameRoster",
        "deriveFirstPitchWithContinuation",
        "deriveLineupPlayPrefixWithContinuation",
    ]
    frame = json.loads(result.frame_json)
    assert frame["historyEntry"]["difference"] == h.bundle.events[0]["state_diff"]
    assert frame["beforeContext"]["current"]["stateFields"]["state.count.balls"] == "0"
    assert frame["afterContext"]["current"]["stateFields"]["state.count.balls"] == "1"
    assert frame["afterContext"]["lastPlayEvaluation"]["scope"] == "play-prefix-v3"
    assert frame["beforeContext"]["lineup"]["away"]["teamId"] == str(
        h.bundle.game["away_team_record_id"]
    )
    assert frame["play"]["source"]["generation"] == h.admission["wire_d4"] != h.event.d4
    assert result.stored_fingerprint == h.bundle.ledger["source_fingerprint"]
    assert json.loads(result.physical_json) == json.loads(result.expected_physical_json)
    assert len(json.loads(result.physical_json)["play_row"]) == 41
    assert json.loads(result.semantic_event_json)["event_kind"] == "play_input"
    with pytest.raises(FrozenInstanceError):
        result.d1 = 2
    with pytest.raises(RuntimeError):
        read(h)


@pytest.mark.parametrize(
    "fault",
    [
        "unissued",
        "clone-handle",
        "foreign-event",
        "foreign-source",
        "generation",
        "d1",
        "closed-tx",
    ],
)
def test_free_json_reference_and_expired_loan_are_not_qualification(historical, fault):
    """自由参照/同値clone/対象移植/失効を真正貸与へ昇格しない。"""
    h = historical
    if fault != "unissued":
        h.issue()
    if fault == "clone-handle":
        h.handle = SimpleNamespace(_state_key=h.handle._state_key)
    elif fault == "foreign-event":
        h.event = SyncEvent(
            h.event.d5, h.event.game_id, h.event.d1, h.event.d4, h.event.v5
        )
    elif fault == "foreign-source":
        h.source = object.__new__(_E1CoreSource)
    elif fault == "generation":
        h.reference["generation"] += 1
    elif fault == "d1":
        h.reference["d1"] = 2
    elif fault == "closed-tx":
        h.bundle.tx.is_active = False
    with pytest.raises((RuntimeError, AttributeError)):
        read(h)


@pytest.mark.parametrize(
    "fault",
    [
        "extra-column",
        "missing-column",
        "uuid-upper",
        "int-bool",
        "int-float",
        "float-bool",
        "float-infinite",
        "aware-date",
        "retired",
        "foreign-tenant",
        "different-ledger",
        "admission",
        "nonempty-runners",
        "payload",
        "v8",
        "physical",
        "legacy-pin",
    ],
)
def test_saved_original_or_column_corruption_never_becomes_frame(historical, fault):
    """全保存値/型/未知legacy pinの破損を成功へ補完しない。"""
    h = historical
    b = h.bundle
    if fault == "extra-column":
        b.events[0]["extra"] = 1
    elif fault == "missing-column":
        b.plays[0].pop("comment")
    elif fault == "uuid-upper":
        h.admission["source_event_id"] = "00000000-0000-4000-8000-00000000000A"
    elif fault == "int-bool":
        b.events[0]["d1"] = True
    elif fault == "int-float":
        b.events[0]["d2"] = 1024.0
    elif fault == "float-bool":
        b.plays[0]["course_x"] = True
    elif fault == "float-infinite":
        b.plays[0]["course_x"] = float("inf")
    elif fault == "aware-date":
        h.admission["consumed_at"] = "2026-11-06T00:00:00"
    elif fault == "retired":
        b.events[0]["retired_at"] = datetime.fromisoformat("2026-11-06T00:00:00+00:00")
    elif fault == "foreign-tenant":
        b.ledger["tenant_id"] = uuid4()
    elif fault == "different-ledger":
        b.ledger["d5"] = uuid4()
    elif fault == "admission":
        h.admission["state"] = "right_verified"
    elif fault == "nonempty-runners":
        h.runners = [{"unknown": True}]
    elif fault == "payload":
        b.saved_payload["calculation"]["response"]["value"]["t1"]["after"][
            "stateFields"
        ]["state.count.balls"] = "2"
    elif fault == "v8":
        b.events[0]["state_diff"] = {}
    elif fault == "physical":
        b.plays[0]["comment"] = "not-in-original"
    else:
        b.saved_payload["calculation"]["artifactSha256"] = "0" * 64
    with pytest.raises((RuntimeError, api.RecordedSnapshotCorrupt, ValueError)):
        h.issue()
        read(h)


def test_original_public_reader_still_refuses_current_depth_three(historical):
    """歴史hookのためにpublic D3=1/全rows1を緩めない。"""
    b = historical.bundle
    b.generation.update(confirmed_watermark=3, applied_prefix=3)
    with pytest.raises(api.RecordedSnapshotUnavailable):
        api._read_recorded_calculation(b.handle, b.game_id)


@pytest.mark.parametrize("column", api.RECORDED_PLAY_ROW_COLUMNS)
def test_each_of_41_physical_columns_is_checked(historical, column):
    """物理全41列の一葉変更を再評価済みframeへ混入させない。"""
    from sqlalchemy import Boolean, DateTime, Float, Integer, String, Uuid

    from pitchlog.db.game_state.models import PlayRow

    h = historical
    field = PlayRow.__table__.c[column]
    old = h.bundle.plays[0][column]
    if isinstance(field.type, Uuid):
        bad = uuid4()
    elif isinstance(field.type, Boolean):
        bad = not old if old is not None else True
    elif isinstance(field.type, Integer):
        bad = (old + 1) if old is not None else 1
    elif isinstance(field.type, Float):
        bad = (old + 0.125) if old is not None else 1.0
    elif isinstance(field.type, DateTime):
        bad = datetime.fromisoformat("2026-11-06T00:00:00+00:00")
    elif isinstance(field.type, String):
        bad = "unexpected-physical-value"
    else:
        raise AssertionError(column)
    h.bundle.plays[0][column] = bad
    h.issue()
    with pytest.raises((api.RecordedSnapshotUnavailable, api.RecordedSnapshotCorrupt)):
        read(h)


@pytest.mark.parametrize(
    "operation",
    [
        "validateInitialGameRoster",
        "deriveFirstPitchWithContinuation",
        "deriveLineupPlayPrefixWithContinuation",
    ],
)
def test_host_failure_does_not_become_frame_or_content_rejection(
    historical, monkeypatch, operation
):
    """既唯一hostの故障は外側へ伝播し、内容False/成功へ変換しない。"""
    h = historical
    h.issue()
    original = NodeDomainHost.call

    def call(host, selected, raw):
        if selected == operation:
            raise RuntimeError("fixed host failure")
        return original(host, selected, raw)

    monkeypatch.setattr(NodeDomainHost, "call", call)
    with pytest.raises(RuntimeError, match="fixed host failure"):
        read(h)


def test_immutable_loaded_source_is_rechecked_after_each_call(historical, monkeypatch):
    """一回hostでも途中source差替えを成功にしない。"""
    h = historical
    h.issue()
    original = NodeDomainHost.call

    def call(host, selected, raw):
        result = original(host, selected, raw)
        host._source += " "
        return result

    monkeypatch.setattr(NodeDomainHost, "call", call)
    with pytest.raises(api.RecordedSnapshotUnavailable):
        read(h)


@pytest.mark.parametrize("coordinate", [0, 1])
def test_jsonb_integral_double_representation_is_lossless(historical, coordinate):
    """PG JSONBが0/1と描画したDoubleを列型へ復元し、原JSON表現を保持する。"""
    h = historical
    h.bundle.saved_payload["observations"]["course"]["x"] = (
        "0" if coordinate == 0 else "263"
    )
    h.bundle.plays[0]["course_x"] = coordinate
    h.issue()
    value = read(h)
    actual = json.loads(value.physical_json)
    expected = json.loads(value.expected_physical_json)
    assert actual == expected and type(expected["play_row"]["course_x"]) is int
    assert expected["play_row"]["course_x"] == coordinate


def test_jsonb_exponent_overflow_is_not_accepted_as_finite(historical):
    """JSONの1e999をinfとして黙認せず、意味列全体の型を保持する。"""
    h = historical
    loan = h.issue()
    evidence = loan[5]
    from dataclasses import replace

    # 閉全列を保ち、result一葉だけを指数表現へ置き換える。
    ledger = json.loads(evidence.ledger_json)
    ledger["result"] = None
    raw = json.dumps(ledger).replace('"result": null', '"result": {"overflow": 1e999}')
    loan[5] = replace(evidence, ledger_json=raw)
    with pytest.raises(api.RecordedSnapshotUnavailable):
        read(h)
